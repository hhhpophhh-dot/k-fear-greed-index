"""
공통 설정 및 날짜 계산 — 모든 인자 모듈이 이 Config를 주입받아 사용.
하드코딩 없이 환경변수 + 런타임 계산으로만 동작.
"""
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


# ── 상수 ──────────────────────────────────────────────────────
LOOKBACK_DAYS   = 252    # 정규화 기준 기간 (약 1년 거래일)
CUTOFF_HOUR     = 17     # 이 시각 이후면 당일 기준, 미만이면 전일 기준 (KST)
DATA_YEARS      = 3      # 수집 기간 (년)

# 캐시 파일 경로
PCR_CACHE_PATH          = "pcr_raw_data.csv"
STOCK_MARKET_CACHE_PATH = "stock_market_data.csv"

# KRX OpenAPI 엔드포인트
KRX_API_BASE = "https://data-dbg.krx.co.kr/svc/apis"

# 인자 컬럼명 — 하드코딩 방지용 상수
COL_MOMENTUM   = "주가_모멘텀"
COL_STRENGTH   = "주가_강도"
COL_BREADTH    = "주가_폭"
COL_PCR        = "풋콜_비율"
COL_CREDIT     = "신용스프레드"
COL_VOLATILITY = "시장_변동성"
COL_SAFEHAVEN  = "안전자산_수요"
COL_INDEX      = "K_탐욕공포지수"
COL_GRADE      = "등급"
COL_UPDATE_TIME = "업데이트_시각"

ALL_FACTOR_COLS = [
    COL_MOMENTUM, COL_STRENGTH, COL_BREADTH,
    COL_PCR, COL_CREDIT, COL_VOLATILITY, COL_SAFEHAVEN,
]


@dataclass
class Config:
    ecos_api_key: str
    krx_auth_key: str

    # 기준일 (런타임에 계산)
    base_dt:      datetime = field(default_factory=datetime.now)
    today:        str = ""        # YYYYMMDD
    today_fdr:    str = ""        # YYYY-MM-DD
    data_start:   str = ""        # YYYYMMDD
    data_start_fdr: str = ""      # YYYY-MM-DD

    def __post_init__(self):
        self.today        = self.base_dt.strftime("%Y%m%d")
        self.today_fdr    = self.base_dt.strftime("%Y-%m-%d")
        _ds = self.base_dt - timedelta(days=365 * DATA_YEARS)
        self.data_start     = _ds.strftime("%Y%m%d")
        self.data_start_fdr = _ds.strftime("%Y-%m-%d")


def is_krx_trading_day(dt: datetime) -> bool:
    """exchange_calendars XKRX 기준 거래일 여부 반환."""
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XKRX")
    return cal.is_session(dt.strftime("%Y-%m-%d"))


def make_config() -> Config:
    """환경변수 + 현재 시각으로 Config 생성."""
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    base_dt = (now - timedelta(days=1)) if now.hour < CUTOFF_HOUR else now

    cfg = Config(
        ecos_api_key=os.environ.get("ECOS_API_KEY", ""),
        krx_auth_key=os.environ.get("KRX_AUTH_KEY", ""),
        base_dt=base_dt,
    )
    print(f"[기준일] {cfg.today_fdr} "
          f"({'전일' if now.hour < CUTOFF_HOUR else '당일'} 기준, 현재 {now.strftime('%H:%M')} KST)")
    return cfg
