"""인자 7: 안전자산 수요 — KOSPI 20일 수익률 vs 국고채 금리 변화."""
import pandas as pd
from .config import Config, COL_SAFEHAVEN
from .utils import normalize_series, get_kospi_close, get_ecos_data

_STAT_CODE   = "817Y002"
_TREASURY_3Y = "010200000"


def calc(cfg: Config, close: pd.Series = None) -> pd.Series:
    c            = close if close is not None else get_kospi_close(cfg)
    kospi_ret_20 = c.pct_change(periods=20)

    treasury        = get_ecos_data(cfg, _STAT_CODE, _TREASURY_3Y)
    bond_ret_proxy  = -(treasury.diff(periods=20) / 100)

    df = pd.DataFrame({"kospi": kospi_ret_20, "bond": bond_ret_proxy}).dropna()
    safe_haven = df["kospi"] - df["bond"]
    return normalize_series(safe_haven, invert=False)


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    result = calc(cfg)
    print(f"[{COL_SAFEHAVEN}] 최근 5일:\n{result.tail(5)}")
