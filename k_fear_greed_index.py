"""
K-탐욕공포지수 (K-Fear & Greed Index) — 메인 오케스트레이터
============================================================
각 인자는 factors/ 패키지의 개별 모듈에서 관리.
단독 테스트: python -m factors.momentum (또는 각 모듈 직접 실행)
"""
import sys
import warnings
import requests
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")

from factors.config import make_config, is_krx_trading_day, ALL_FACTOR_COLS
from factors.config import (
    COL_MOMENTUM, COL_STRENGTH, COL_BREADTH, COL_PCR,
    COL_CREDIT, COL_VOLATILITY, COL_SAFEHAVEN,
    COL_INDEX, COL_GRADE, COL_UPDATE_TIME,
)
from factors import (
    momentum  as f_momentum,
    strength  as f_strength,
    breadth   as f_breadth,
    pcr       as f_pcr,
    credit    as f_credit,
    volatility as f_volatility,
    safehaven as f_safehaven,
)
from factors.utils import get_kospi_close

OUTPUT_PATH     = "k_fear_greed_result.csv"
CNN_FNG_URL     = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


# ── 등급 라벨 ──────────────────────────────────────────────────
def _label(score) -> str:
    if pd.isna(score): return "데이터 없음"
    if score <= 25:    return "극단적 공포"
    if score <= 45:    return "공포"
    if score <= 55:    return "중립"
    if score <= 75:    return "탐욕"
    return "극단적 탐욕"


# ── CNN 지수 조회 ───────────────────────────────────────────────
def _fetch_cnn():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    }
    try:
        fng   = requests.get(CNN_FNG_URL, timeout=10, headers=headers).json()["fear_and_greed"]
        score = round(float(fng["score"]), 1)
        print(f"[CNN] Fear & Greed: {score} ({fng['rating']})")
        return score, fng["rating"]
    except Exception as e:
        print(f"[CNN] 조회 실패: {e}")
        return None, None


# ── 결과 저장 ──────────────────────────────────────────────────
def _save(result_df: pd.DataFrame, path: str):
    result_df.index.name = "날짜"
    existing = [c for c in ALL_FACTOR_COLS if c in result_df.columns]
    clean    = result_df.dropna(subset=existing)
    clean.to_csv(path, encoding="utf-8-sig")
    print(f"결과 저장: {path} ({len(clean)}행)")


# ── 메인 산출 ──────────────────────────────────────────────────
def calc_k_fear_greed_index(cfg) -> pd.DataFrame:
    print("\n=== K-탐욕공포지수 산출 시작 [KOSPI 전체] ===\n")

    close = get_kospi_close(cfg)

    # PCR 먼저 수집 (오래 걸리므로 앞에 배치)
    pcr_series = f_pcr.calc(cfg, trading_days=close.index) if cfg.krx_auth_key else None
    if not cfg.krx_auth_key:
        print(f"[4/7] {COL_PCR} — KRX_AUTH_KEY 미설정, 건너뜀")

    print("[2/7] 주가 강도 계산 중...")
    strength_s = f_strength.calc(cfg, trading_days=close.index)

    print("[3/7] 주가 폭 (McClellan Summation) 계산 중...")
    breadth_s  = f_breadth.calc(cfg, trading_days=close.index)

    print("[1/7] 주가 모멘텀 계산 중...")
    print("[5/7] 신용스프레드 계산 중 (ECOS API)...")
    print("[6/7] 시장 변동성 계산 중...")
    print("[7/7] 안전자산 수요 계산 중...")

    factors = {COL_MOMENTUM: f_momentum.calc(cfg, close=close)}
    if not strength_s.empty:
        factors[COL_STRENGTH] = strength_s
    else:
        print(f"  [경고] {COL_STRENGTH} 수집 실패 — 인자 제외")
    if not breadth_s.empty:
        factors[COL_BREADTH] = breadth_s
    else:
        print(f"  [경고] {COL_BREADTH} 수집 실패 — 인자 제외")
    if pcr_series is not None:
        factors[COL_PCR] = pcr_series
    factors[COL_CREDIT]     = f_credit.calc(cfg)
    factors[COL_VOLATILITY] = f_volatility.calc(cfg, close=close)
    factors[COL_SAFEHAVEN]  = f_safehaven.calc(cfg, close=close)

    print(f"  실제 사용 인자: {len(factors)}개 ({', '.join(factors.keys())})")

    result = pd.DataFrame(factors)
    result = result[result.index.isin(close.index)]  # 거래일만 유지
    result[COL_INDEX] = result[list(factors.keys())].mean(axis=1, skipna=True)
    result[COL_GRADE] = result[COL_INDEX].apply(_label)
    result[COL_UPDATE_TIME] = ""
    result.loc[result.index[-1], COL_UPDATE_TIME] = cfg.base_dt.strftime("%H:%M")

    # 요약 출력
    latest   = result.iloc[-1]
    date_str = result.index[-1].strftime("%Y-%m-%d")
    meta = {
        COL_MOMENTUM:   ("↑탐욕",        "KOSPI vs MA125"),
        COL_STRENGTH:   ("↑탐욕",        "상승/하락 거래량 비율"),
        COL_BREADTH:    ("↑탐욕",        "McClellan Summation"),
        COL_PCR:        ("↓탐욕(invert)", "KOSPI200 P/C 비율"),
        COL_CREDIT:     ("↓탐욕(invert)", "BBB- 스프레드"),
        COL_VOLATILITY: ("↓탐욕(invert)", "20일 실현변동성"),
        COL_SAFEHAVEN:  ("↑탐욕",        "주식-채권 상대수익"),
    }
    print("\n" + "=" * 52)
    print(f"  K-탐욕공포지수  |  {date_str}  기준")
    print("=" * 52)
    print(f"  최종 지수  :  {latest[COL_INDEX]:.1f}  ({latest[COL_GRADE]})")
    print("-" * 52)
    for col in factors:
        val  = latest[col]
        vstr = f"{val:.1f}" if not pd.isna(val) else "  N/A"
        direction, note = meta[col]
        print(f"  {col:<14}  {vstr:>10}  {direction}  ({note})")
    print("=" * 52)

    return result


# ── 실행 진입점 ────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = make_config()

    if not is_krx_trading_day(cfg.base_dt):
        print(f"[종료] {cfg.today_fdr}은 비거래일 (주말/공휴일) — 실행 건너뜀")
        sys.exit(0)

    result_df = calc_k_fear_greed_index(cfg)

    print("\n[최근 10일 인자별 점수]")
    display_cols = [c for c in ALL_FACTOR_COLS + [COL_INDEX, COL_GRADE] if c in result_df.columns]
    print(result_df[display_cols].tail(10).to_string())

    cnn_score, cnn_rating = _fetch_cnn()
    result_df["CNN_탐욕공포지수"] = np.nan
    result_df["CNN_등급"] = ""
    if cnn_score is not None:
        result_df.loc[result_df.index[-1], "CNN_탐욕공포지수"] = cnn_score
        result_df.loc[result_df.index[-1], "CNN_등급"]        = cnn_rating

    _save(result_df, OUTPUT_PATH)
