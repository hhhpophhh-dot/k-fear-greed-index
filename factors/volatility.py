"""인자 6: 시장 변동성 — KOSPI 20일 실현변동성 (VKOSPI 대체)."""
import numpy as np
import pandas as pd
from .config import Config, COL_VOLATILITY
from .utils import normalize_series, get_kospi_close


def calc(cfg: Config, close: pd.Series = None) -> pd.Series:
    c    = close if close is not None else get_kospi_close(cfg)
    rv20 = c.pct_change().rolling(20).std() * np.sqrt(252) * 100
    return normalize_series(rv20.dropna(), invert=True)


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    result = calc(cfg)
    print(f"[{COL_VOLATILITY}] 최근 5일:\n{result.tail(5)}")
