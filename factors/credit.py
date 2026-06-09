"""인자 5: 신용스프레드 — 회사채 BBB- 3년물 vs 국고채 3년물 (ECOS API)."""
import pandas as pd
from .config import Config, COL_CREDIT
from .utils import normalize_series, get_ecos_data

# ECOS 통계표 코드
_STAT_CODE   = "817Y002"
_TREASURY_3Y = "010200000"  # 국고채 3년물
_CORP_BBB_3Y = "010320000"  # 회사채 BBB- 3년물


def calc(cfg: Config) -> pd.Series:
    treasury = get_ecos_data(cfg, _STAT_CODE, _TREASURY_3Y)
    corp     = get_ecos_data(cfg, _STAT_CODE, _CORP_BBB_3Y)
    spread   = (corp - treasury).dropna()
    return normalize_series(spread, invert=True)


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    result = calc(cfg)
    print(f"[{COL_CREDIT}] 최근 5일:\n{result.tail(5)}")
