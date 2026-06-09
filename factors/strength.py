"""인자 2: 주가 강도 — 상승/하락 거래량 비율 (KRX OpenAPI)."""
import pandas as pd
import numpy as np
from .config import Config, COL_STRENGTH
from .utils import normalize_series
from . import market_data


def calc(cfg: Config, trading_days: pd.DatetimeIndex = None) -> pd.Series:
    mkt = market_data.get(cfg, trading_days)
    if mkt is None or "adv_vol" not in mkt.columns:
        print(f"  [경고] {COL_STRENGTH} 데이터 없음 — NaN 반환")
        return pd.Series(dtype=float)

    total = mkt["adv_vol"] + mkt["dec_vol"]
    ratio = (mkt["adv_vol"] / total.replace(0, np.nan)).fillna(0.5).sort_index()

    ref = ratio.index[-1]
    print(f"  [{COL_STRENGTH}] 마지막 날짜: {ref.strftime('%Y-%m-%d')}, 상승비율: {ratio.loc[ref]*100:.1f}%")
    return normalize_series(ratio.dropna(), invert=False)


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    result = calc(cfg)
    print(f"[{COL_STRENGTH}] 최근 5일:\n{result.tail(5)}")
