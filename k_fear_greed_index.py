"""
K-탐욕공포지수 (K-Fear & Greed Index)
====================================
CNN Fear & Greed Index의 한국판 구현 - KOSPI 기반

[산출 방식]
- 6개 인자 각각 0~100으로 정규화 (과거 252거래일 대비 백분위 기반)
- 동일가중 평균 → 최종 지수

[데이터 수집]
- KOSPI 지수        : FinanceDataReader (KS11) — KRX 로그인 불필요
- 개별 종목 OHLCV   : pykrx get_market_ohlcv_by_date — KRX 로그인 불필요
- 종목 목록          : FinanceDataReader StockListing('KOSPI')
- 금리 데이터        : 한국은행 ECOS API
- 시장 변동성        : KOSPI 20일 실현 변동성 (VKOSPI 공개 API 없음으로 대체)

[실행 조건]
- 매일 17:00 이후 실행 (pykrx는 KRX 마감 후 16:00~17:00 반영)
- ECOS API 키 필요 (https://ecos.bok.or.kr 에서 발급)

[사전 설치]
pip install pykrx finance-datareader pandas numpy requests
"""

import os
import requests
import pandas as pd
import numpy as np
from pykrx import stock
import FinanceDataReader as fdr
from datetime import datetime, timedelta, timezone
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# ⚙️ 설정
# ============================================================
ECOS_API_KEY    = os.environ.get("ECOS_API_KEY", "X2QOJYHO80BJKPBF1ODJ")
CNN_FNG_URL     = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
LOOKBACK_DAYS = 252                        # 정규화 기준 기간 (약 1년 거래일)
CUTOFF_HOUR   = 17                         # 데이터 기준일 전환 시각 (17:00 이후 = 당일)

# 17:00 이전이면 전날, 이후면 당일을 기준일로 사용 (KST 기준)
_KST = timezone(timedelta(hours=9))
_now = datetime.now(_KST)
if _now.hour < CUTOFF_HOUR:
    _base = _now - timedelta(days=1)
else:
    _base = _now

TODAY     = _base.strftime("%Y%m%d")        # pykrx 형식 (YYYYMMDD)
TODAY_FDR = _base.strftime("%Y-%m-%d")      # FDR 형식 (YYYY-MM-DD)

print(f"[기준일] {TODAY[:4]}-{TODAY[4:6]}-{TODAY[6:]} "
      f"({'당일' if _now.hour >= CUTOFF_HOUR else '전일'} 기준, 현재 {_now.strftime('%H:%M')})")

# 3년치 데이터 (52주 신고가/신저가 1년 + 정규화 1년 + 여유)
_data_start = datetime.today() - timedelta(days=365 * 3)
DATA_START     = _data_start.strftime("%Y%m%d")   # pykrx 형식
DATA_START_FDR = _data_start.strftime("%Y-%m-%d") # FDR 형식


# ============================================================
# 🔧 공통 유틸리티
# ============================================================

def normalize_series(series: pd.Series, invert: bool = False) -> pd.Series:
    """
    과거 LOOKBACK_DAYS(252거래일) 대비 오늘 값의 백분위를 0~100으로 변환.

    - invert=False: 값이 높을수록 탐욕 (주가 모멘텀, 신고가 비율 등)
    - invert=True : 값이 높을수록 공포 (변동성, 신용스프레드)
    """
    def rolling_rank(x):
        if len(x) < 2:
            return np.nan
        return (x.rank().iloc[-1] - 1) / (len(x) - 1) * 100

    normalized = series.rolling(LOOKBACK_DAYS).apply(rolling_rank, raw=False)

    if invert:
        normalized = 100 - normalized

    return normalized


def get_ecos_data(stat_code: str, item_code: str, start_date: str, end_date: str) -> pd.Series:
    """
    한국은행 ECOS API로 일별 데이터 수집.

    Args:
        stat_code : ECOS 통계표 코드 (예: "817Y002")
        item_code : 항목 코드 (예: "010200000" = 국고채 3년물)
        start_date: "YYYYMMDD" 형식
        end_date  : "YYYYMMDD" 형식

    Returns:
        날짜 인덱스의 float Series
    """
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_API_KEY}/json/kr"
        f"/1/10000/{stat_code}/D/{start_date}/{end_date}/{item_code}"
    )
    resp = requests.get(url, timeout=30)
    data = resp.json()

    if "StatisticSearch" not in data:
        raise ValueError(f"ECOS API 오류: {data}")

    rows = data["StatisticSearch"]["row"]
    df = pd.DataFrame(rows)[["TIME", "DATA_VALUE"]].copy()
    df["TIME"] = pd.to_datetime(df["TIME"], format="%Y%m%d")
    df["DATA_VALUE"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    df = df.set_index("TIME").sort_index()
    df = df.resample("B").last().ffill()

    return df["DATA_VALUE"]


def get_kospi_close() -> pd.Series:
    """FDR로 KOSPI 종가 시계열 반환 (KS11)."""
    df = fdr.DataReader("KS11", DATA_START_FDR, TODAY_FDR)
    return df["Close"].astype(float)


# ============================================================
# 📦 KOSPI 전 종목 데이터 캐시 (주가강도 + 주가폭 공용)
# ============================================================
_kospi_stock_cache: dict | None = None


def get_kospi_stock_data() -> dict:
    """
    KOSPI 전 종목의 종가 / 거래량 / 등락률을 DataFrame으로 반환.

    데이터는 한 번만 수집하고 캐시해 두어 주가강도·주가폭에서 공용으로 사용.
    pykrx get_market_ohlcv_by_date는 개별 종목 단위로 KRX 로그인 없이 동작함.

    Returns:
        dict with keys 'close', 'volume', 'change' (각각 날짜 × 종목 DataFrame)
    """
    global _kospi_stock_cache
    if _kospi_stock_cache is not None:
        return _kospi_stock_cache

    # 종목 목록: FDR StockListing ('KOSPI') — KRX 로그인 불필요
    kospi_list = fdr.StockListing("KOSPI")
    tickers = kospi_list["Code"].tolist()

    print(f"  KOSPI 전 종목 {len(tickers)}개 수집 중 (약 2~5분 소요)...")

    close_dict  = {}
    vol_dict    = {}
    chg_dict    = {}
    fail_count  = 0

    for i, ticker in enumerate(tickers):
        try:
            df = stock.get_market_ohlcv_by_date(DATA_START, TODAY, ticker)
            if len(df) > 60:
                close_dict[ticker] = df["종가"]
                vol_dict[ticker]   = df["거래량"]
                chg_dict[ticker]   = df["등락률"]
        except Exception:
            fail_count += 1
            continue

        if (i + 1) % 200 == 0:
            print(f"  [{i+1}/{len(tickers)}] 완료 (실패: {fail_count}건)")

    print(f"  수집 완료: {len(close_dict)}개 종목 (실패: {fail_count}건)")

    _kospi_stock_cache = {
        "close":  pd.DataFrame(close_dict),
        "volume": pd.DataFrame(vol_dict),
        "change": pd.DataFrame(chg_dict),
    }
    return _kospi_stock_cache


# ============================================================
# 📊 인자 1: 주가 모멘텀 (Price Momentum)
# ============================================================
def calc_price_momentum() -> pd.Series:
    """
    KOSPI 종가 vs 125일 이동평균의 이격률(%)

    이격률 = (KOSPI 종가 - MA125) / MA125 × 100
    이격률이 높을수록 탐욕 → invert=False

    데이터: FinanceDataReader KS11 (KRX 로그인 불필요)
    """
    print("[1/6] 주가 모멘텀 계산 중...")

    close = get_kospi_close()
    ma125 = close.rolling(window=125).mean()
    momentum = (close - ma125) / ma125 * 100

    return normalize_series(momentum.dropna(), invert=False)


# ============================================================
# 📊 인자 2: 주가 강도 (Price Strength)
# ============================================================
def calc_price_strength():
    """
    KOSPI 전 종목 중 52주 신고가/신저가 종목 수 비율

    비율 = 신고가 종목 수 / (신고가 + 신저가 종목 수)
    비율이 높을수록 탐욕 → invert=False

    데이터: pykrx get_market_ohlcv_by_date (개별 종목, KRX 로그인 불필요)

    Returns: (정규화된 시리즈, 신고가_종목수 시리즈, 신저가_종목수 시리즈)
    """
    print("[2/6] 주가 강도 계산 중 (전 종목 수집, 수분 소요)...")

    data = get_kospi_stock_data()
    close_df = data["close"]

    rolling_high = close_df.rolling(window=252).max()
    rolling_low  = close_df.rolling(window=252).min()

    new_highs = (close_df >= rolling_high).sum(axis=1)
    new_lows  = (close_df <= rolling_low).sum(axis=1)
    total = new_highs + new_lows

    ref_date = close_df.index[-1]
    nh = int(new_highs.loc[ref_date])
    nl = int(new_lows.loc[ref_date])
    print(f"  [진단] pykrx 마지막 날짜: {ref_date.strftime('%Y-%m-%d')}")
    print(f"  [진단] 52주 신고가: {nh}개 / 신저가: {nl}개 / 비율: {nh/(nh+nl)*100:.1f}%" if nh+nl > 0 else f"  [진단] 신고가: {nh}개 / 신저가: {nl}개")

    ratio = new_highs / total.replace(0, np.nan)
    ratio = ratio.fillna(0.5)

    return normalize_series(ratio.dropna(), invert=False), new_highs, new_lows


# ============================================================
# 📊 인자 3: 주가 폭 (McClellan Summation Index, 거래량 기반)
# ============================================================
def calc_market_breadth() -> pd.Series:
    """
    McClellan Summation Index (거래량 기반)

    Step 1. 매일 상승/하락 거래량 집계
        - 상승 거래량: 등락률 > 0 종목들의 거래량 합
        - 하락 거래량: 등락률 < 0 종목들의 거래량 합
    Step 2. 순거래량 비율 = (Adv_Vol - Dec_Vol) / (Adv_Vol + Dec_Vol)
    Step 3. McClellan Oscillator = EMA(19) - EMA(39)
    Step 4. McClellan Summation = Oscillator 누적합

    높을수록 탐욕 → invert=False

    데이터: pykrx get_market_ohlcv_by_date (종목별 루프, KRX 로그인 불필요)
    """
    print("[3/6] 주가 폭 (McClellan Summation) 계산 중...")

    data = get_kospi_stock_data()
    vol_df = data["volume"]
    chg_df = data["change"]

    # 날짜별 상승/하락 거래량 집계
    adv_vol = vol_df.where(chg_df > 0, 0).sum(axis=1)
    dec_vol = vol_df.where(chg_df < 0, 0).sum(axis=1)
    total   = adv_vol + dec_vol

    net_ratio = (adv_vol - dec_vol) / total.replace(0, np.nan)
    net_ratio = net_ratio.dropna().sort_index()

    ema19 = net_ratio.ewm(span=19, adjust=False).mean()
    ema39 = net_ratio.ewm(span=39, adjust=False).mean()
    oscillator = ema19 - ema39
    summation  = oscillator.cumsum()

    return normalize_series(summation.dropna(), invert=False)


# ============================================================
# ❌ 인자 4: 풋/콜 비율 — 제외 (B안 적용)
# ============================================================
# pykrx 옵션 함수 없음 + KRX 포털 세션 인증 필요 → 공개 수집 불가


# ============================================================
# 📊 인자 5: 신용스프레드 (Credit Spread)
# ============================================================
def calc_credit_spread() -> pd.Series:
    """
    회사채 BBB- 3년물 금리 - 국고채 3년물 금리 (단위: %)

    스프레드 높을수록 공포 → invert=True

    ECOS API 코드:
    - 통계표: 817Y002
    - 국고채 3년물  : 010200000
    - 회사채 BBB- 3년물: 010320000
    """
    print("[4/6] 신용스프레드 계산 중 (ECOS API)...")

    treasury_3y = get_ecos_data("817Y002", "010200000", DATA_START, TODAY)
    corp_bbb_3y = get_ecos_data("817Y002", "010320000", DATA_START, TODAY)

    spread = corp_bbb_3y - treasury_3y

    return normalize_series(spread.dropna(), invert=True)


# ============================================================
# 📊 인자 6: 시장 변동성 (Realized Volatility as VKOSPI proxy)
# ============================================================
def calc_market_volatility() -> pd.Series:
    """
    KOSPI 20일 실현 변동성 (연율화, %)

    VKOSPI(한국판 VIX)는 공개 API가 없으므로 KOSPI 일간 수익률의
    20일 롤링 표준편차를 연율화하여 대리 지표로 사용.
    실현 변동성은 내재 변동성(VIX계)과 강한 양의 상관관계를 가짐.

    실현 변동성 = std(20일 일간 수익률) × sqrt(252) × 100 (%)

    높을수록 공포 → invert=True

    데이터: FinanceDataReader KS11 (KRX 로그인 불필요)
    """
    print("[5/6] 시장 변동성 (실현변동성 - VKOSPI 대체) 계산 중...")

    close  = get_kospi_close()
    ret    = close.pct_change()
    rv20   = ret.rolling(20).std() * np.sqrt(252) * 100   # 연율화 퍼센트

    return normalize_series(rv20.dropna(), invert=True)


# ============================================================
# 📊 인자 7: 안전자산 수요 (Safe Haven Demand)
# ============================================================
def calc_safe_haven_demand() -> pd.Series:
    """
    KOSPI 20일 수익률 - 국고채 3년물 20일 금리 변화

    KOSPI 20일 수익률    = (KOSPI 종가 / 20영업일 전 종가) - 1
    국고채 20일 금리 Δ   = 현재 금리 - 20영업일 전 금리 (상승 = 채권 가격 하락 → 부호 반전)

    양수: 주식 강세 → 탐욕 / 음수: 채권 강세 → 공포
    높을수록 탐욕 → invert=False

    데이터: FDR KS11 + ECOS API
    """
    print("[6/6] 안전자산 수요 계산 중...")

    kospi_close = get_kospi_close()
    kospi_ret_20 = kospi_close.pct_change(periods=20)

    treasury = get_ecos_data("817Y002", "010200000", DATA_START, TODAY)
    treasury_chg_20 = treasury.diff(periods=20)
    treasury_ret_proxy = -treasury_chg_20 / 100   # 금리 상승 = 채권 수익률 악화

    df = pd.DataFrame({
        "kospi_ret": kospi_ret_20,
        "bond_ret":  treasury_ret_proxy,
    }).dropna()

    safe_haven = df["kospi_ret"] - df["bond_ret"]

    return normalize_series(safe_haven, invert=False)


# ============================================================
# 🏆 최종 지수 산출
# ============================================================
def calc_k_fear_greed_index() -> pd.DataFrame:
    """
    6개 인자 각각 0~100 정규화 후 동일가중 평균 → K-탐욕공포지수

    [지수 해석 기준]
    0  ~ 25: 극단적 공포 (Extreme Fear)
    25 ~ 45: 공포 (Fear)
    45 ~ 55: 중립 (Neutral)
    55 ~ 75: 탐욕 (Greed)
    75 ~100: 극단적 탐욕 (Extreme Greed)
    """
    print("\n=== K-탐욕공포지수 산출 시작 (6개 인자) ===\n")

    strength_series, raw_highs, raw_lows = calc_price_strength()
    factors = {
        "주가_모멘텀":   calc_price_momentum(),
        "주가_강도":     strength_series,
        "주가_폭":       calc_market_breadth(),
        "신용스프레드":  calc_credit_spread(),
        "시장_변동성":   calc_market_volatility(),
        "안전자산_수요": calc_safe_haven_demand(),
    }

    result = pd.DataFrame(factors)
    result["신고가_종목수"] = raw_highs.reindex(result.index)
    result["신저가_종목수"] = raw_lows.reindex(result.index)
    result["K_탐욕공포지수"] = result.mean(axis=1, skipna=True)

    def label(score):
        if pd.isna(score):  return "데이터 없음"
        if score <= 25:     return "극단적 공포"
        elif score <= 45:   return "공포"
        elif score <= 55:   return "중립"
        elif score <= 75:   return "탐욕"
        else:               return "극단적 탐욕"

    result["등급"] = result["K_탐욕공포지수"].apply(label)

    # 스크립트 실행 시각(KST)을 최신 행에만 기록
    result["업데이트_시각"] = ""
    result.loc[result.index[-1], "업데이트_시각"] = _now.strftime("%H:%M")

    # ── 최신 날짜 요약 출력 ──
    latest   = result.iloc[-1]
    date_str = result.index[-1].strftime("%Y-%m-%d")

    print("\n" + "=" * 52)
    print(f"  K-탐욕공포지수  |  {date_str}  기준")
    print("=" * 52)
    print(f"  최종 지수  :  {latest['K_탐욕공포지수']:.1f}  ({latest['등급']})")
    print("-" * 52)
    print(f"  {'인자':<14}  {'정규화 점수':>10}  비고")
    print("-" * 52)

    meta = {
        "주가_모멘텀":   ("↑탐욕",           "KOSPI vs MA125"),
        "주가_강도":     ("↑탐욕",           "52주 신고가 비율"),
        "주가_폭":       ("↑탐욕",           "McClellan Summation"),
        "신용스프레드":  ("↓탐욕(invert)",   "BBB- 스프레드"),
        "시장_변동성":   ("↓탐욕(invert)",   "20일 실현변동성"),
        "안전자산_수요": ("↑탐욕",           "주식-채권 상대수익"),
    }
    for col in factors:
        val  = latest[col]
        vstr = f"{val:.1f}" if not pd.isna(val) else "  N/A"
        direction, note = meta[col]
        print(f"  {col:<14}  {vstr:>10}  {direction}  ({note})")

    print("=" * 52)

    return result


# ============================================================
# ▶️ 실행 진입점
# ============================================================
def fetch_cnn_fear_greed():
    """CNN Fear & Greed Index 현재값 조회 (비공식 엔드포인트, 실패 시 None 반환)"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        "Origin": "https://edition.cnn.com",
    }
    try:
        resp = requests.get(CNN_FNG_URL, timeout=10, headers=headers)
        resp.raise_for_status()
        fng = resp.json()["fear_and_greed"]
        score  = round(float(fng["score"]), 1)
        rating = fng["rating"]
        print(f"[CNN] Fear & Greed: {score} ({rating})")
        return score, rating
    except Exception as e:
        print(f"[CNN] 데이터 조회 실패: {e}")
        return None, None


if __name__ == "__main__":
    result_df = calc_k_fear_greed_index()

    print("\n[최근 10일 인자별 점수]")
    factor_cols = [
        "주가_모멘텀", "주가_강도", "주가_폭",
        "신용스프레드", "시장_변동성", "안전자산_수요",
        "K_탐욕공포지수", "등급",
    ]
    print(result_df[factor_cols].tail(10).to_string())

    # CNN Fear & Greed Index 조회 → 최신 행에 저장
    cnn_score, cnn_rating = fetch_cnn_fear_greed()
    result_df["CNN_탐욕공포지수"] = np.nan
    result_df["CNN_등급"] = ""
    if cnn_score is not None:
        result_df.loc[result_df.index[-1], "CNN_탐욕공포지수"] = cnn_score
        result_df.loc[result_df.index[-1], "CNN_등급"] = cnn_rating

    # 날짜 컬럼명 명시 + 6개 인자 모두 유효한 행만 저장 (HTML 시각화 호환)
    output_path = "k_fear_greed_result.csv"
    result_df.index.name = "날짜"
    factor_col_list = ["주가_모멘텀", "주가_강도", "주가_폭",
                       "신용스프레드", "시장_변동성", "안전자산_수요"]
    result_df_clean = result_df.dropna(subset=factor_col_list)
    # 신고가/신저가 정수 변환 (NaN은 유지)
    for col in ["신고가_종목수", "신저가_종목수"]:
        result_df_clean[col] = result_df_clean[col].where(
            result_df_clean[col].isna(), result_df_clean[col].astype(int)
        )
    result_df_clean.to_csv(output_path, encoding="utf-8-sig")
    print(f"\n결과 저장: {output_path} ({len(result_df_clean)}행)")
