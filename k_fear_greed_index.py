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
import time
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
KRX_AUTH_KEY    = os.environ.get("KRX_AUTH_KEY", "")
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


def get_naver_kospi100_close() -> pd.Series:
    """
    네이버 금융 모바일 API로 KOSPI100 지수 종가 시계열 반환.

    FDR이 KOSPI100 심볼을 미지원하므로 네이버 금융 API를 직접 호출.
    3년치 단일 요청 시 409 오류 발생 → 1년 단위 청크로 분할 요청.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com",
        "Accept": "application/json, text/plain, */*",
    }
    url = "https://m.stock.naver.com/api/index/KOSPI100/price"

    # 1년 단위 청크로 분할 요청 (단일 3년 요청 시 409)
    start_dt = datetime.strptime(DATA_START_FDR, "%Y-%m-%d")
    end_dt   = datetime.strptime(TODAY_FDR, "%Y-%m-%d")
    all_items = []
    first_chunk = True

    chunk_start = start_dt
    while chunk_start <= end_dt:
        chunk_end = min(chunk_start + timedelta(days=89), end_dt)  # 90일 청크
        params = {
            "startTime": chunk_start.strftime("%Y%m%d"),
            "endTime":   chunk_end.strftime("%Y%m%d"),
            "timeframe": "day",
        }
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("priceInfos", data.get("prices", []))
        if first_chunk and items:
            print(f"  [진단] KOSPI100 API 응답 키: {list(items[0].keys())}")
            first_chunk = False
        all_items.extend(items)
        chunk_start = chunk_end + timedelta(days=1)
        time.sleep(0.3)  # 청크 간 짧은 딜레이 (Rate limit 방지)

    if not all_items:
        raise ValueError("KOSPI100 API 응답 비어있음")

    records = []
    for item in all_items:
        date_str  = item.get("localTradedAt") or item.get("date") or item.get("dt")
        close_val = item.get("closePrice")    or item.get("close") or item.get("cls")
        if date_str and close_val:
            try:
                records.append({
                    "date":  pd.to_datetime(str(date_str)[:10]),
                    "close": float(str(close_val).replace(",", "")),
                })
            except Exception:
                pass

    if len(records) < 20:
        raise ValueError(f"KOSPI100 데이터 부족 ({len(records)}개). API 응답 구조 확인 필요")

    df = pd.DataFrame(records).set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]  # 청크 경계 중복 제거
    print(f"  KOSPI100 종가 수집 완료: {len(df)}일치")
    return df["close"]


def get_kospi100_tickers() -> list:
    """
    FDR StockListing('KOSPI')에서 시가총액 상위 100개 종목 코드 반환.

    KRX 공식 KOSPI100 구성 종목(반기 갱신)과 완전히 일치하지 않으나,
    시총 상위 100종목이 공식 구성과 80~90% 이상 겹쳐 실용적 대체재로 사용.
    """
    kospi_list = fdr.StockListing("KOSPI")
    # 시가총액 컬럼 탐색 (FDR 버전별 컬럼명 상이)
    marcap_col = next(
        (c for c in kospi_list.columns if c.lower() in ("marcap", "mktcap", "marketcap", "cap")),
        None
    )
    if marcap_col is None:
        raise ValueError(f"시가총액 컬럼 없음. 컬럼 목록: {list(kospi_list.columns)}")

    top100 = (
        kospi_list.dropna(subset=[marcap_col])
        .nlargest(100, marcap_col)["Code"]
        .tolist()
    )
    return top100


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
def calc_price_momentum(_close: pd.Series = None) -> pd.Series:
    """
    KOSPI(또는 KOSPI100) 종가 vs 125일 이동평균의 이격률(%)

    이격률 = (종가 - MA125) / MA125 × 100
    이격률이 높을수록 탐욕 → invert=False
    """
    print("[1/7] 주가 모멘텀 계산 중...")

    close = _close if _close is not None else get_kospi_close()
    ma125 = close.rolling(window=125).mean()
    momentum = (close - ma125) / ma125 * 100

    return normalize_series(momentum.dropna(), invert=False)


# ============================================================
# 📊 인자 2: 주가 강도 (Price Strength)
# ============================================================
def calc_price_strength(_stock_data: dict = None):
    """
    52주 신고가/신저가 종목 수 비율

    비율 = 신고가 종목 수 / (신고가 + 신저가 종목 수)
    비율이 높을수록 탐욕 → invert=False

    Returns: (정규화된 시리즈, 신고가_종목수 시리즈, 신저가_종목수 시리즈)
    """
    print("[2/7] 주가 강도 계산 중...")

    data = _stock_data if _stock_data is not None else get_kospi_stock_data()
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
def calc_market_breadth(_stock_data: dict = None) -> pd.Series:
    """
    McClellan Summation Index (거래량 기반)

    Step 1. 상승/하락 거래량 집계
    Step 2. 순거래량 비율 = (Adv_Vol - Dec_Vol) / (Adv_Vol + Dec_Vol)
    Step 3. McClellan Oscillator = EMA(19) - EMA(39)
    Step 4. McClellan Summation = Oscillator 누적합

    높을수록 탐욕 → invert=False
    """
    print("[3/7] 주가 폭 (McClellan Summation) 계산 중...")

    data = _stock_data if _stock_data is not None else get_kospi_stock_data()
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
# 📊 인자 4: 풋/콜 비율 (Put/Call Ratio)
# ============================================================
PCR_CACHE_PATH = "pcr_raw_data.csv"   # 원시 P/C 비율 캐시 파일


# ============================================================
def calc_put_call_ratio() -> pd.Series:
    """
    KOSPI200 옵션 풋/콜 비율

    P/C 비율 = KOSPI200 풋옵션 일별 거래량 / 콜옵션 일별 거래량
    높을수록 공포(풋 매수 우위) → invert=True

    데이터: KRX Open API (openapi.krx.co.kr)
    인증: AUTH_KEY 헤더 — data.krx.co.kr 세션 쿠키와 무관한 별도 시스템
    환경변수: KRX_AUTH_KEY (GitHub Secret)

    캐시: pcr_raw_data.csv — 최초 1회만 전체 수집, 이후 신규 날짜만 호출
    """
    if not KRX_AUTH_KEY:
        raise ValueError("KRX_AUTH_KEY 환경변수가 설정되지 않았습니다.")

    try:
        from pykrx_openapi import KRXOpenAPI
    except ImportError:
        raise ImportError("pykrx-openapi 미설치: pip install pykrx-openapi")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 수집 목표 기간 (252일 정규화 + 여유)
    pcr_start = (datetime.today() - timedelta(days=400 * 7 // 5 + 30)).strftime("%Y-%m-%d")
    all_dates  = pd.bdate_range(start=pcr_start, end=TODAY_FDR)

    # ── 캐시 로드 ──
    pcr_cache: dict = {}
    if os.path.exists(PCR_CACHE_PATH):
        try:
            cache_df = pd.read_csv(PCR_CACHE_PATH, index_col=0, parse_dates=True,
                                   encoding="utf-8-sig")
            pcr_cache = cache_df.iloc[:, 0].dropna().to_dict()
            print(f"[4/7] 풋/콜 비율 — 캐시 로드: {len(pcr_cache)}일")
        except Exception as e:
            print(f"[4/7] 풋/콜 비율 — 캐시 로드 실패 (재수집): {e}")

    # ── 미수집 날짜만 API 호출 ──
    missing = [d for d in all_dates if d not in pcr_cache]
    print(f"  신규 수집 필요: {len(missing)}일 / 전체 목표: {len(all_dates)}일")

    if missing:
        def _fetch_one(date_str):
            local_api = KRXOpenAPI(api_key=KRX_AUTH_KEY)
            result = local_api.get_options_daily_trade(bas_dd=date_str)
            rows = result.get("OutBlock_1", [])
            if not rows:
                return None, rows
            k200 = [r for r in rows if "KOSPI200" in str(r.get("itmNm", ""))]
            if not k200:
                k200 = rows
            call_vol = sum(int(r.get("acmlTrdvol", 0) or 0) for r in k200 if r.get("rghtTpCd") == "C")
            put_vol  = sum(int(r.get("acmlTrdvol", 0) or 0) for r in k200 if r.get("rghtTpCd") == "P")
            ratio = put_vol / call_vol if call_vol > 0 else None
            return ratio, rows

        new_data: dict = {}
        first_row_printed = False

        PCR_ABORT_THRESHOLD = 10  # 연속 빈 응답 N회 → API 한도 소진으로 판단하고 중단

        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_date = {
                executor.submit(_fetch_one, d.strftime("%Y%m%d")): d
                for d in missing
            }
            completed = 0
            consecutive_empty = 0
            aborted = False
            for future in as_completed(future_to_date):
                date = future_to_date[future]
                completed += 1
                try:
                    ratio, rows = future.result(timeout=30)
                    if not first_row_printed and rows:
                        print(f"  [진단] API 응답 필드: {list(rows[0].keys())}")
                        first_row_printed = True
                    if rows:
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                    if ratio is not None:
                        new_data[date] = ratio
                except Exception:
                    consecutive_empty += 1
                if completed % 50 == 0:
                    print(f"  [{completed}/{len(missing)}] 처리 중... (신규 유효: {len(new_data)}일)")
                if consecutive_empty >= PCR_ABORT_THRESHOLD:
                    print(f"  [조기 중단] 연속 {consecutive_empty}회 빈 응답 — API 한도 소진 추정. 수집 중단.")
                    aborted = True
                    break

        print(f"  신규 수집 완료: {len(new_data)}일")
        pcr_cache.update(new_data)

        # ── 캐시 저장 (데이터가 있을 때만, 오래된 데이터 정리) ──
        if pcr_cache:
            cache_series = pd.Series(pcr_cache).sort_index()
            cutoff = pd.Timestamp(pcr_start)
            cache_series = cache_series[cache_series.index >= cutoff]
            cache_series.to_csv(PCR_CACHE_PATH, header=["pcr_raw"], encoding="utf-8-sig")
            print(f"  캐시 저장: {len(cache_series)}일 → {PCR_CACHE_PATH}")
        else:
            print(f"  캐시 저장 건너뜀: 데이터 없음")

    # ── 목표 기간 내 데이터로 정규화 ──
    available = {k: v for k, v in pcr_cache.items()
                 if pd.Timestamp(pcr_start) <= k <= pd.Timestamp(TODAY_FDR)}
    if len(available) < 20:
        print(f"  [경고] 풋/콜 비율 데이터 부족 ({len(available)}일) — 일일 호출 한도 초과 가능성. 해당 인자 제외.")
        return None

    print(f"  사용 데이터: {len(available)}일치 P/C 비율")
    return normalize_series(pd.Series(available).sort_index(), invert=True)


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
    print("[5/7] 신용스프레드 계산 중 (ECOS API)...")

    treasury_3y = get_ecos_data("817Y002", "010200000", DATA_START, TODAY)
    corp_bbb_3y = get_ecos_data("817Y002", "010320000", DATA_START, TODAY)

    spread = corp_bbb_3y - treasury_3y

    return normalize_series(spread.dropna(), invert=True)


# ============================================================
# 📊 인자 6: 시장 변동성 (Realized Volatility as VKOSPI proxy)
# ============================================================
def calc_market_volatility(_close: pd.Series = None) -> pd.Series:
    """
    20일 실현 변동성 (연율화, %, VKOSPI 대체)

    실현 변동성 = std(20일 일간 수익률) × sqrt(252) × 100 (%)
    높을수록 공포 → invert=True
    """
    print("[6/7] 시장 변동성 (실현변동성) 계산 중...")

    close = _close if _close is not None else get_kospi_close()
    ret   = close.pct_change()
    rv20  = ret.rolling(20).std() * np.sqrt(252) * 100

    return normalize_series(rv20.dropna(), invert=True)


# ============================================================
# 📊 인자 7: 안전자산 수요 (Safe Haven Demand)
# ============================================================
def calc_safe_haven_demand(_close: pd.Series = None) -> pd.Series:
    """
    지수 20일 수익률 - 국고채 3년물 20일 금리 변화

    양수: 주식 강세 → 탐욕 / 음수: 채권 강세 → 공포
    높을수록 탐욕 → invert=False
    """
    print("[7/7] 안전자산 수요 계산 중...")

    kospi_close  = _close if _close is not None else get_kospi_close()
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
def calc_k_fear_greed_index(universe: str = "all") -> pd.DataFrame:
    """
    6개 인자 각각 0~100 정규화 후 동일가중 평균 → K-탐욕공포지수

    universe: 'all'  = KOSPI 전체 (기본)
              'k100' = KOSPI100 (시가총액 상위 100)

    [지수 해석 기준]
    0  ~ 25: 극단적 공포 / 25 ~ 45: 공포 / 45 ~ 55: 중립
    55 ~ 75: 탐욕 / 75 ~100: 극단적 탐욕
    """
    label = "KOSPI100" if universe == "k100" else "KOSPI 전체"

    # PCR: KRX_AUTH_KEY 있고, 캐시 파일에 유효 데이터 ≥20일 있을 때만 시도
    # 캐시 미존재(첫 실행) 또는 데이터 부족 → 완전 건너뜀 (API 호출 없음)
    has_pcr = False
    if bool(KRX_AUTH_KEY) and universe == "all" and os.path.exists(PCR_CACHE_PATH):
        try:
            _pcr_df = pd.read_csv(PCR_CACHE_PATH, index_col=0, parse_dates=True,
                                   encoding="utf-8-sig")
            has_pcr = len(_pcr_df.dropna()) >= 20
        except Exception:
            pass
    if not has_pcr and universe == "all":
        print("[4/7] 풋/콜 비율 — 캐시 데이터 없음, 건너뜀 (6인자로 계속)")
    print(f"\n=== K-탐욕공포지수 산출 시작 [{label}] ===\n")

    # ── 데이터 소스 선택 ──
    if universe == "k100":
        index_close = get_naver_kospi100_close()
        tickers_100 = get_kospi100_tickers()
        all_data    = get_kospi_stock_data()   # 캐시에서 재사용
        avail       = [t for t in tickers_100 if t in all_data["close"].columns]
        print(f"  KOSPI100 종목 필터: {len(avail)}개 사용 (요청 100개 중)")
        stock_data = {
            "close":  all_data["close"][avail],
            "volume": all_data["volume"][avail],
            "change": all_data["change"][avail],
        }
    else:
        index_close = None   # 각 함수에서 기본값(KS11) 사용
        stock_data  = None   # 각 함수에서 전체 캐시 사용

    strength_series, raw_highs, raw_lows = calc_price_strength(_stock_data=stock_data)
    factors = {
        "주가_모멘텀":   calc_price_momentum(_close=index_close),
        "주가_강도":     strength_series,
        "주가_폭":       calc_market_breadth(_stock_data=stock_data),
    }
    if has_pcr:
        pcr = calc_put_call_ratio()
        if pcr is not None:
            factors["풋콜_비율"] = pcr
    factors["신용스프레드"]  = calc_credit_spread()
    factors["시장_변동성"]   = calc_market_volatility(_close=index_close)
    factors["안전자산_수요"] = calc_safe_haven_demand(_close=index_close)

    n_factors = len(factors)
    print(f"  실제 사용 인자: {n_factors}개 ({', '.join(factors.keys())})")

    result = pd.DataFrame(factors)
    result["신고가_종목수"] = raw_highs.reindex(result.index)
    result["신저가_종목수"] = raw_lows.reindex(result.index)
    result["K_탐욕공포지수"] = result[list(factors.keys())].mean(axis=1, skipna=True)

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
        "풋콜_비율":     ("↓탐욕(invert)",   "KOSPI200 P/C 비율"),
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


def _save_result(result_df: pd.DataFrame, output_path: str):
    """결과 DataFrame을 CSV로 저장 (공통 후처리)."""
    result_df.index.name = "날짜"
    base_factors = ["주가_모멘텀", "주가_강도", "주가_폭",
                    "신용스프레드", "시장_변동성", "안전자산_수요"]
    result_clean = result_df.dropna(subset=base_factors)
    for col in ["신고가_종목수", "신저가_종목수"]:
        if col in result_clean.columns:
            result_clean[col] = result_clean[col].where(
                result_clean[col].isna(), result_clean[col].astype(int)
            )
    result_clean.to_csv(output_path, encoding="utf-8-sig")
    print(f"결과 저장: {output_path} ({len(result_clean)}행)")


if __name__ == "__main__":
    # ── KOSPI 전체 ──
    result_df = calc_k_fear_greed_index(universe="all")

    print("\n[최근 10일 인자별 점수 — KOSPI 전체]")
    factor_cols = ["주가_모멘텀", "주가_강도", "주가_폭",
                   "신용스프레드", "시장_변동성", "안전자산_수요",
                   "K_탐욕공포지수", "등급"]
    print(result_df[factor_cols].tail(10).to_string())

    # CNN Fear & Greed Index 조회 → 전체 지수 최신 행에 저장
    cnn_score, cnn_rating = fetch_cnn_fear_greed()
    result_df["CNN_탐욕공포지수"] = np.nan
    result_df["CNN_등급"] = ""
    if cnn_score is not None:
        result_df.loc[result_df.index[-1], "CNN_탐욕공포지수"] = cnn_score
        result_df.loc[result_df.index[-1], "CNN_등급"] = cnn_rating

    _save_result(result_df, "k_fear_greed_result.csv")

    # ── KOSPI100 ──
    try:
        result_k100 = calc_k_fear_greed_index(universe="k100")
        print("\n[최근 10일 인자별 점수 — KOSPI100]")
        print(result_k100[factor_cols].tail(10).to_string())
        _save_result(result_k100, "k_fear_greed_result_k100.csv")
    except Exception as e:
        print(f"\n[경고] KOSPI100 지수 산출 실패 (건너뜀): {e}")
