"""공유 유틸리티: 정규화, ECOS API, KOSPI 종가."""
import requests
import pandas as pd
import numpy as np
from .config import Config, LOOKBACK_DAYS


def normalize_series(series: pd.Series, invert: bool = False) -> pd.Series:
    """
    과거 LOOKBACK_DAYS(252거래일) 대비 오늘 값의 백분위를 0~100으로 변환.
    invert=True: 값이 높을수록 공포 (변동성, 신용스프레드 등)
    """
    def rolling_rank(x):
        if len(x) < 2:
            return np.nan
        return (x.rank().iloc[-1] - 1) / (len(x) - 1) * 100

    normalized = series.rolling(LOOKBACK_DAYS).apply(rolling_rank, raw=False)
    return 100 - normalized if invert else normalized


def get_ecos_data(cfg: Config, stat_code: str, item_code: str) -> pd.Series:
    """한국은행 ECOS API로 일별 데이터 수집."""
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{cfg.ecos_api_key}/json/kr"
        f"/1/10000/{stat_code}/D/{cfg.data_start}/{cfg.today}/{item_code}"
    )
    resp = requests.get(url, timeout=30)
    data = resp.json()

    if "StatisticSearch" not in data:
        raise ValueError(f"ECOS API 오류: {data}")

    rows = data["StatisticSearch"]["row"]
    df = pd.DataFrame(rows)[["TIME", "DATA_VALUE"]].copy()
    df["TIME"]       = pd.to_datetime(df["TIME"], format="%Y%m%d")
    df["DATA_VALUE"] = pd.to_numeric(df["DATA_VALUE"], errors="coerce")
    df = df.set_index("TIME").sort_index()
    df = df.resample("B").last().ffill()
    return df["DATA_VALUE"]


def get_kospi_close(cfg: Config) -> pd.Series:
    """FDR로 KOSPI 종가 시계열 반환 (KS11)."""
    import FinanceDataReader as fdr
    df = fdr.DataReader("KS11", cfg.data_start_fdr, cfg.today_fdr)
    return df["Close"].astype(float)
