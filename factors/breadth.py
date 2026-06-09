"""인자 3: 주가 폭 — McClellan Summation Index (KRX OpenAPI)."""
import pandas as pd
import numpy as np
from .config import Config, COL_BREADTH
from .utils import normalize_series
from . import market_data


def calc(cfg: Config, trading_days: pd.DatetimeIndex = None) -> pd.Series:
    mkt = market_data.get(cfg, trading_days)
    if mkt is None or "adv_vol" not in mkt.columns:
        print(f"  [경고] {COL_BREADTH} 데이터 없음 — NaN 반환")
        return pd.Series(dtype=float)

    adv   = mkt["adv_vol"].sort_index()
    dec   = mkt["dec_vol"].sort_index()
    total = adv + dec

    net_ratio  = (adv - dec) / total.replace(0, np.nan)
    net_ratio  = net_ratio.dropna().sort_index()
    ema19      = net_ratio.ewm(span=19, adjust=False).mean()
    ema39      = net_ratio.ewm(span=39, adjust=False).mean()
    summation  = (ema19 - ema39).cumsum()

    return normalize_series(summation.dropna(), invert=False)


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    result = calc(cfg)
    print(f"[{COL_BREADTH}] 최근 5일:\n{result.tail(5)}")
