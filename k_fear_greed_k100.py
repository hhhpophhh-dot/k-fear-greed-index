"""
K100-탐욕공포지수 (K-Fear & Greed Index — KOSPI100)
=====================================================
KOSPI100 지수 기반 K-탐욕공포지수 산출.

[KOSPI100 지수 시계열]
- k100_index_cache.csv에서 읽기만 함 (수집은 collect_k100_cache.py 담당)
- 캐시 부족 시 KS11 fallback 사용
"""

import os
import sys
import warnings
import pandas as pd
import FinanceDataReader as fdr
warnings.filterwarnings("ignore")

from factors.config import make_config, is_krx_trading_day, ALL_FACTOR_COLS, COL_INDEX, COL_GRADE, COL_UPDATE_TIME
from factors import (
    momentum  as f_momentum,
    strength  as f_strength,
    breadth   as f_breadth,
    credit    as f_credit,
    volatility as f_volatility,
    safehaven as f_safehaven,
)

OUTPUT_PATH_K100 = "k_fear_greed_result_k100.csv"
K100_CACHE_PATH = "k100_index_cache.csv"
MIN_CACHE_DAYS = 100


def get_kospi100_index_close(cfg) -> pd.Series:
    """
    KOSPI100 지수 종가 시계열 반환.
    k100_index_cache.csv에서 읽고, 부족하면 KS11 fallback.
    """
    if os.path.exists(K100_CACHE_PATH):
        try:
            df = pd.read_csv(K100_CACHE_PATH, index_col=0, parse_dates=True,
                             encoding="utf-8-sig")
            series = df.iloc[:, 0].dropna().astype(float)
            series = series[series.index >= cfg.data_start_fdr]
            if len(series) >= MIN_CACHE_DAYS:
                print(f"  [K100] 캐시 로드 성공: {len(series)}일")
                return series
            print(f"  [K100] 캐시 부족 ({len(series)}일 < {MIN_CACHE_DAYS}일)")
        except Exception as e:
            print(f"  [K100] 캐시 읽기 실패: {e}")
    else:
        print(f"  [K100] 캐시 파일 없음: {K100_CACHE_PATH}")

    df = fdr.DataReader("KS11", cfg.data_start_fdr, cfg.today_fdr)
    if len(df) > MIN_CACHE_DAYS and "Close" in df.columns:
        print(f"  [K100] KS11 fallback 사용 ({len(df)}일)")
        return df["Close"].astype(float)

    raise ValueError("KOSPI100 지수 시계열 확보 실패 — 캐시 없음, KS11 fallback 실패")


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

    if not is_krx_trading_day(cfg.base_dt):
        print(f"[종료] {cfg.today_fdr}은 비거래일 (주말/공휴일) — 실행 건너뜀")
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
