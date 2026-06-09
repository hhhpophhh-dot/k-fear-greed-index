"""
KOSPI 일별매매정보 캐시 — 주가강도·주가폭 공용.
KRX OpenAPI (data-dbg.krx.co.kr) 날짜당 1회 요청.
"""
import os
import time
import subprocess
import pandas as pd
from .config import Config, STOCK_MARKET_CACHE_PATH

_cache: pd.DataFrame | None = None
ABORT_THRESHOLD = 10


def _fetch_one(cfg: Config, date_str: str) -> dict | None:
    try:
        from pykrx_openapi import KRXOpenAPI
        api  = KRXOpenAPI(api_key=cfg.krx_auth_key)
        rows = api.get_stock_market_daily_trade(bas_dd=date_str).get("OutBlock_1", [])
    except Exception as e:
        print(f"  [오류] {date_str} 수집 실패: {e}")
        return None

    if not rows:
        return None

    kospi = [r for r in rows if "KOSPI" in str(r.get("MKT_NM", "")) or "유가증권" in str(r.get("MKT_NM", ""))]
    if not kospi:
        kospi = rows

    adv = dec = 0
    for r in kospi:
        try:
            vol = int(str(r.get("ACC_TRDVOL", "0")).replace(",", "") or 0)
            chg = float(str(r.get("FLUC_RT",   "0")).replace(",", "") or 0)
            if chg > 0:   adv += vol
            elif chg < 0: dec += vol
        except Exception:
            continue
    return {"adv_vol": adv, "dec_vol": dec}


def get(cfg: Config, trading_days: pd.DatetimeIndex = None) -> pd.DataFrame | None:
    """
    캐시 로드 후 누락 날짜만 수집. 반환: DataFrame(adv_vol, dec_vol) 또는 None.
    """
    global _cache
    if _cache is not None:
        return _cache

    if not cfg.krx_auth_key:
        print("  [경고] KRX_AUTH_KEY 미설정 — 주가_강도·주가_폭 수집 불가")
        return None

    from .utils import get_kospi_close
    if trading_days is None:
        trading_days = get_kospi_close(cfg).index

    data_start_ts = pd.Timestamp(cfg.data_start_fdr)
    all_dates     = trading_days[trading_days >= data_start_ts]

    cache_df = pd.DataFrame()
    if os.path.exists(STOCK_MARKET_CACHE_PATH):
        try:
            cache_df = pd.read_csv(STOCK_MARKET_CACHE_PATH, index_col=0,
                                   parse_dates=True, encoding="utf-8-sig")
            print(f"  시장데이터 캐시 로드: {len(cache_df)}일")
        except Exception as e:
            print(f"  시장데이터 캐시 로드 실패 (재수집): {e}")

    cached_set = set(cache_df.index) if not cache_df.empty else set()
    missing    = [d for d in all_dates if d not in cached_set]
    print(f"  시장데이터 신규 수집: {len(missing)}일 / 전체: {len(all_dates)}일")

    if missing:
        new_rows = {}
        consecutive_empty = 0
        for i, d in enumerate(missing):
            result = _fetch_one(cfg, d.strftime("%Y%m%d"))
            if result is None:
                consecutive_empty += 1
                if consecutive_empty >= ABORT_THRESHOLD:
                    print(f"  [조기 중단] 연속 {consecutive_empty}회 빈 응답 — API 한도 소진 추정")
                    break
            else:
                consecutive_empty = 0
                new_rows[d] = result
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(missing)}] 수집 중...")
            time.sleep(0.3)

        if new_rows:
            new_df   = pd.DataFrame.from_dict(new_rows, orient="index")
            cache_df = pd.concat([cache_df, new_df]).sort_index()
            cache_df = cache_df[~cache_df.index.duplicated(keep="last")]
            cache_df.to_csv(STOCK_MARKET_CACHE_PATH, encoding="utf-8-sig")
            print(f"  시장데이터 캐시 저장: {len(cache_df)}일 → {STOCK_MARKET_CACHE_PATH}")
            subprocess.run(["git", "add", STOCK_MARKET_CACHE_PATH], check=False)
            res = subprocess.run(
                ["git", "commit", "-m", f"시장데이터 캐시 저장: {len(cache_df)}일"],
                capture_output=True, text=True,
            )
            if res.returncode == 0:
                branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True,
                ).stdout.strip() or "main"
                subprocess.run(["git", "pull", "--rebase", "origin", branch], check=False)
                subprocess.run(["git", "push", "origin", branch], check=False)

    if cache_df.empty:
        print("  [경고] 시장데이터 수집 실패 — 주가_강도·주가_폭 NaN 처리")
        return None

    _cache = cache_df
    return cache_df


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    df  = get(cfg)
    if df is not None:
        print(f"시장데이터 {len(df)}일\n{df.tail(5)}")
    else:
        print("수집 실패")
