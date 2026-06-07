"""
K100-탐욕공포지수 (K-Fear & Greed Index — KOSPI100)
=====================================================
KOSPI100 기반 K-탐욕공포지수 산출 스크립트.
k_fear_greed_index.py의 공통 함수를 import해서 사용하며,
KOSPI100 지수 시계열 수집 방법만 별도 관리.

[현재 상황]
KOSPI100 지수 시계열 API 확보 중 (2026-06-03 기준 미해결):
- 네이버 모바일 API: GitHub Actions IP에서 409
- 네이버 PC API: 404
- Stooq/FDR: KOSPI100 심볼 미지원
→ API 확보 시 get_kospi100_index_close() 함수만 수정
"""

import os
import requests
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# 공통 함수/상수 import
from k_fear_greed_index import (
    TODAY, TODAY_FDR, DATA_START, DATA_START_FDR,
    ECOS_API_KEY, LOOKBACK_DAYS,
    normalize_series, get_ecos_data,
    get_kospi_stock_data,
    calc_price_momentum, calc_price_strength, calc_market_breadth,
    calc_credit_spread, calc_market_volatility, calc_safe_haven_demand,
    _save_result, _now,
)


# ============================================================
# 📊 KOSPI100 지수 시계열 수집 (현재 개선 작업 중)
# ============================================================
def get_kospi100_index_close() -> pd.Series:
    """
    KOSPI100 지수 종가 시계열 반환.

    [현재 상태] API 확보 중 — 해결 시 이 함수만 수정하면 됨.
    시도 순서:
    1. 네이버 금융 모바일 API (m.stock.naver.com) — GitHub Actions IP 409 이슈
    2. 네이버 금융 PC API (api.stock.naver.com) — 404 이슈
    3. Stooq / FDR — 심볼 미지원
    """
    k100_start = (datetime.today() - timedelta(days=365 * 2)).strftime("%Y-%m-%d")
    start_dt = datetime.strptime(k100_start, "%Y-%m-%d")
    end_dt   = datetime.strptime(TODAY_FDR, "%Y-%m-%d")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com",
        "Accept": "application/json, text/plain, */*",
    }

    # 1안: 네이버 모바일 API (90일 청크)
    try:
        all_items = []
        chunk_start = start_dt
        while chunk_start <= end_dt:
            chunk_end = min(chunk_start + timedelta(days=89), end_dt)
            params = {
                "startTime": chunk_start.strftime("%Y%m%d"),
                "endTime":   chunk_end.strftime("%Y%m%d"),
                "timeframe": "day",
            }
            resp = requests.get(
                "https://m.stock.naver.com/api/index/KOSPI100/price",
                params=params, headers=headers, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            items = data if isinstance(data, list) else data.get("priceInfos", data.get("prices", []))
            all_items.extend(items)
            chunk_start = chunk_end + timedelta(days=1)

        if all_items:
            return _parse_naver_items(all_items, "모바일 API")
        raise ValueError("응답 비어있음")
    except Exception as e:
        print(f"  [K100] 네이버 모바일 API 실패: {e}")

    # 2안: 네이버 PC API
    try:
        resp = requests.get(
            "https://api.stock.naver.com/index/KOSPI100/basicIndicesByTradedAt",
            params={"startTradedAt": start_dt.strftime("%Y-%m-%d"),
                    "endTradedAt":   end_dt.strftime("%Y-%m-%d")},
            headers={**headers, "Referer": "https://finance.naver.com/sise/sise_index.nhn?code=KOSPI100"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("indices", data.get("prices", []))
        if items:
            return _parse_naver_items(items, "PC API")
        raise ValueError("응답 비어있음")
    except Exception as e:
        print(f"  [K100] 네이버 PC API 실패: {e}")

    # 3안: Stooq (FDR)
    for sym in ["^ksp100", "KSP100.PL", "KS100.WA"]:
        try:
            df = fdr.DataReader(sym, k100_start, TODAY_FDR)
            if len(df) > 100 and "Close" in df.columns:
                print(f"  [K100] Stooq 수집 성공 (심볼: {sym}): {len(df)}일")
                return df["Close"].astype(float)
        except Exception:
            continue

    # 4안: KOSPI 전체(KS11) fallback — 지수 시계열 없을 때 대체 사용
    try:
        df = fdr.DataReader("KS11", k100_start, TODAY_FDR)
        if len(df) > 100 and "Close" in df.columns:
            print(f"  [K100] ⚠️  KOSPI100 지수 API 없음 → KS11(KOSPI 전체) fallback 사용 ({len(df)}일)")
            return df["Close"].astype(float)
    except Exception as e:
        print(f"  [K100] KS11 fallback 실패: {e}")

    raise ValueError("KOSPI100 지수 시계열 수집 실패 — 모든 API 시도 소진")


def _parse_naver_items(items: list, source: str) -> pd.Series:
    """네이버 API 응답 파싱 공통 함수."""
    records = []
    for item in items:
        date_str  = (item.get("localTradedAt") or item.get("tradedAt")
                     or item.get("date") or item.get("dt"))
        close_val = (item.get("closePrice") or item.get("endPrice")
                     or item.get("close") or item.get("cls"))
        if date_str and close_val:
            try:
                records.append({
                    "date":  pd.to_datetime(str(date_str)[:10]),
                    "close": float(str(close_val).replace(",", "")),
                })
            except Exception:
                pass

    if len(records) < 20:
        raise ValueError(f"데이터 부족 ({len(records)}개)")

    df = pd.DataFrame(records).set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    print(f"  [K100] 종가 수집 완료 ({source}): {len(df)}일치 | 응답 키: {list(items[0].keys())}")
    return df["close"]


# ============================================================
# 📦 KOSPI100 종목 필터
# ============================================================
def get_kospi100_tickers() -> list:
    """FDR 시가총액 상위 100개 종목 코드 반환."""
    kospi_list = fdr.StockListing("KOSPI")
    marcap_col = next(
        (c for c in kospi_list.columns if c.lower() in ("marcap", "mktcap", "marketcap", "cap")),
        None,
    )
    if marcap_col is None:
        raise ValueError(f"시가총액 컬럼 없음: {list(kospi_list.columns)}")
    return (
        kospi_list.dropna(subset=[marcap_col])
        .nlargest(100, marcap_col)["Code"]
        .tolist()
    )


# ============================================================
# 🏆 K100 지수 산출
# ============================================================
def calc_k100_fear_greed_index() -> pd.DataFrame:
    """
    KOSPI100 기반 K-탐욕공포지수 산출.
    공통 calc 함수를 KOSPI100 종목/지수 데이터로 호출.
    """
    print("\n=== K100-탐욕공포지수 산출 시작 [KOSPI100] ===\n")

    index_close = get_kospi100_index_close()

    all_data    = get_kospi_stock_data()
    tickers_100 = get_kospi100_tickers()
    avail       = [t for t in tickers_100 if t in all_data["close"].columns]
    print(f"  KOSPI100 종목 필터: {len(avail)}개 사용 (요청 100개 중)")
    stock_data = {
        "close":  all_data["close"][avail],
        "volume": all_data["volume"][avail],
        "change": all_data["change"][avail],
    }

    strength_series, raw_highs, raw_lows = calc_price_strength(_stock_data=stock_data)
    factors = {
        "주가_모멘텀":   calc_price_momentum(_close=index_close),
        "주가_강도":     strength_series,
        "주가_폭":       calc_market_breadth(_stock_data=stock_data),
        "신용스프레드":  calc_credit_spread(),
        "시장_변동성":   calc_market_volatility(_close=index_close),
        "안전자산_수요": calc_safe_haven_demand(_close=index_close),
    }

    print(f"  실제 사용 인자: {len(factors)}개 ({', '.join(factors.keys())})")

    result = pd.DataFrame(factors)
    result["신고가_종목수"]  = raw_highs.reindex(result.index)
    result["신저가_종목수"]  = raw_lows.reindex(result.index)
    result["K_탐욕공포지수"] = result[list(factors.keys())].mean(axis=1, skipna=True)

    def grade(score):
        if pd.isna(score):  return "데이터 없음"
        if score <= 25:     return "극단적 공포"
        elif score <= 45:   return "공포"
        elif score <= 55:   return "중립"
        elif score <= 75:   return "탐욕"
        else:               return "극단적 탐욕"

    result["등급"] = result["K_탐욕공포지수"].apply(grade)
    result["업데이트_시각"] = ""
    result.loc[result.index[-1], "업데이트_시각"] = _now.strftime("%H:%M")

    latest   = result.iloc[-1]
    date_str = result.index[-1].strftime("%Y-%m-%d")
    print("\n" + "=" * 52)
    print(f"  K100-탐욕공포지수  |  {date_str}  기준")
    print("=" * 52)
    print(f"  최종 지수  :  {latest['K_탐욕공포지수']:.1f}  ({latest['등급']})")
    print("=" * 52)

    return result


# ============================================================
# ▶️ 실행 진입점
# ============================================================
if __name__ == "__main__":
    result_k100 = calc_k100_fear_greed_index()

    factor_cols = ["주가_모멘텀", "주가_강도", "주가_폭",
                   "신용스프레드", "시장_변동성", "안전자산_수요",
                   "K_탐욕공포지수", "등급"]
    print("\n[최근 10일 인자별 점수 — KOSPI100]")
    print(result_k100[factor_cols].tail(10).to_string())

    _save_result(result_k100, "k_fear_greed_result_k100.csv")
