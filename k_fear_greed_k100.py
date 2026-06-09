"""
K100-탐욕공포지수 (K-Fear & Greed Index — KOSPI100)
=====================================================
KOSPI100 지수 기반 K-탐욕공포지수 산출.

[현재 상황]
KOSPI100 지수 시계열 API 확보 중 (2026-06-03 기준 미해결):
- 네이버 모바일 API: GitHub Actions IP에서 409
- 네이버 PC API: 404
- Stooq/FDR: KOSPI100 심볼 미지원
→ API 확보 시 get_kospi100_index_close() 함수만 수정
주가_강도·주가_폭은 KOSPI 전체 공용 데이터 사용 (KOSPI100 전용 미구현)
"""

import sys
import warnings
import pandas as pd
import requests
import FinanceDataReader as fdr
from datetime import datetime, timedelta
warnings.filterwarnings("ignore")

from factors.config import make_config, ALL_FACTOR_COLS, COL_INDEX, COL_GRADE, COL_UPDATE_TIME
from factors import (
    momentum  as f_momentum,
    strength  as f_strength,
    breadth   as f_breadth,
    credit    as f_credit,
    volatility as f_volatility,
    safehaven as f_safehaven,
)

OUTPUT_PATH_K100 = "k_fear_greed_result_k100.csv"


def get_kospi100_index_close(cfg) -> pd.Series:
    """
    KOSPI100 지수 종가 시계열 반환.
    실패 시 KS11(KOSPI 전체) fallback 사용.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.naver.com",
        "Accept": "application/json, text/plain, */*",
    }

    start_dt = datetime.strptime(cfg.data_start_fdr, "%Y-%m-%d")
    end_dt   = datetime.strptime(cfg.today_fdr, "%Y-%m-%d")

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
            df = fdr.DataReader(sym, cfg.data_start_fdr, cfg.today_fdr)
            if len(df) > 100 and "Close" in df.columns:
                print(f"  [K100] Stooq 수집 성공 (심볼: {sym}): {len(df)}일")
                return df["Close"].astype(float)
        except Exception:
            continue

    # 4안: KS11 fallback
    df = fdr.DataReader("KS11", cfg.data_start_fdr, cfg.today_fdr)
    if len(df) > 100 and "Close" in df.columns:
        print(f"  [K100] KOSPI100 API 없음 → KS11 fallback 사용 ({len(df)}일)")
        return df["Close"].astype(float)

    raise ValueError("KOSPI100 지수 시계열 수집 실패 — 모든 API 시도 소진")


def _parse_naver_items(items: list, source: str) -> pd.Series:
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
    print(f"  [K100] 종가 수집 완료 ({source}): {len(df)}일치")
    return df["close"]


def _label(score) -> str:
    if pd.isna(score): return "데이터 없음"
    if score <= 25:    return "극단적 공포"
    if score <= 45:    return "공포"
    if score <= 55:    return "중립"
    if score <= 75:    return "탐욕"
    return "극단적 탐욕"


def calc_k100_fear_greed_index(cfg) -> pd.DataFrame:
    print("\n=== K100-탐욕공포지수 산출 시작 [KOSPI100] ===\n")

    close = get_kospi100_index_close(cfg)
    trading_days = close.index

    strength_s = f_strength.calc(cfg, trading_days=trading_days)
    breadth_s  = f_breadth.calc(cfg, trading_days=trading_days)

    factors = {"주가_모멘텀": f_momentum.calc(cfg, close=close)}
    if not strength_s.empty:
        factors["주가_강도"] = strength_s
    if not breadth_s.empty:
        factors["주가_폭"] = breadth_s
    factors["신용스프레드"]  = f_credit.calc(cfg)
    factors["시장_변동성"]   = f_volatility.calc(cfg, close=close)
    factors["안전자산_수요"] = f_safehaven.calc(cfg, close=close)

    print(f"  실제 사용 인자: {len(factors)}개 ({', '.join(factors.keys())})")

    result = pd.DataFrame(factors)
    result = result[result.index.isin(trading_days)]
    result[COL_INDEX] = result[list(factors.keys())].mean(axis=1, skipna=True)
    result[COL_GRADE] = result[COL_INDEX].apply(_label)
    result[COL_UPDATE_TIME] = ""
    result.loc[result.index[-1], COL_UPDATE_TIME] = cfg.base_dt.strftime("%H:%M")

    latest   = result.iloc[-1]
    date_str = result.index[-1].strftime("%Y-%m-%d")
    print("\n" + "=" * 52)
    print(f"  K100-탐욕공포지수  |  {date_str}  기준")
    print("=" * 52)
    print(f"  최종 지수  :  {latest[COL_INDEX]:.1f}  ({latest[COL_GRADE]})")
    print("=" * 52)

    return result


if __name__ == "__main__":
    cfg = make_config()

    if cfg.base_dt.weekday() >= 5:
        print(f"[종료] {cfg.today_fdr}은 주말 — 실행 건너뜀")
        sys.exit(0)

    result_df = calc_k100_fear_greed_index(cfg)

    display_cols = [c for c in ALL_FACTOR_COLS + [COL_INDEX, COL_GRADE] if c in result_df.columns]
    print("\n[최근 10일 인자별 점수 — KOSPI100]")
    print(result_df[display_cols].tail(10).to_string())

    result_df.index.name = "날짜"
    existing = [c for c in display_cols if c in result_df.columns]
    clean = result_df.dropna(subset=existing)
    clean.to_csv(OUTPUT_PATH_K100, encoding="utf-8-sig")
    print(f"결과 저장: {OUTPUT_PATH_K100} ({len(clean)}행)")
