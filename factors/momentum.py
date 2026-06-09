"""인자 1: 주가 모멘텀 — KOSPI vs 125일 이동평균 이격률."""
import pandas as pd
from .config import Config, COL_MOMENTUM
from .utils import normalize_series, get_kospi_close


def calc(cfg: Config, close: pd.Series = None) -> pd.Series:
    """
    KOSPI 종가 vs MA125 이격률 정규화.
    close: 외부에서 이미 수집한 종가 Series (없으면 자체 수집)
    """
    c = close if close is not None else get_kospi_close(cfg)
    ma125    = c.rolling(window=125).mean()
    momentum = (c - ma125) / ma125 * 100
    return normalize_series(momentum.dropna(), invert=False)


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    result = calc(cfg)
    print(f"[{COL_MOMENTUM}] 최근 5일:\n{result.tail(5)}")
