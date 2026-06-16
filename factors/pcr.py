"""인자 4: 풋/콜 비율 — KOSPI200 옵션 (KRX OpenAPI)."""
import os
import time
import subprocess
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from .config import Config, COL_PCR, PCR_CACHE_PATH
from .utils import normalize_series, get_kospi_close

ABORT_THRESHOLD = 10
BATCH_SIZE      = 50
BATCH_DELAY     = 15


def _fetch_one(cfg: Config, date_str: str):
    time.sleep(0.5)
    from pykrx_openapi import KRXOpenAPI
    api   = KRXOpenAPI(api_key=cfg.krx_auth_key)
    rows  = api.get_options_daily_trade(bas_dd=date_str).get("OutBlock_1", [])
    if not rows:
        return None, []
    k200 = [r for r in rows
            if "KOSPI200" in str(r.get("PROD_NM", "")) or "KOSPI200" in str(r.get("ISU_NM", ""))]
    if not k200:
        k200 = rows
    call_vol = sum(int(r.get("ACC_TRDVOL", 0) or 0) for r in k200
                   if str(r.get("RGHT_TP_NM", "")).upper() in ("CALL", "콜"))
    put_vol  = sum(int(r.get("ACC_TRDVOL", 0) or 0) for r in k200
                   if str(r.get("RGHT_TP_NM", "")).upper() in ("PUT", "풋"))
    ratio = put_vol / call_vol if call_vol > 0 else None
    return ratio, rows


def calc(cfg: Config, trading_days: pd.DatetimeIndex = None) -> pd.Series | None:
    if not cfg.krx_auth_key:
        print(f"  [경고] KRX_AUTH_KEY 미설정 — {COL_PCR} 건너뜀")
        return None

    pcr_start = (cfg.base_dt - timedelta(days=400 * 7 // 5 + 30)).strftime("%Y-%m-%d")
    if trading_days is None:
        trading_days = get_kospi_close(cfg).index
    all_dates = trading_days[trading_days >= pd.Timestamp(pcr_start)]

    cache: dict = {}
    if os.path.exists(PCR_CACHE_PATH):
        try:
            df    = pd.read_csv(PCR_CACHE_PATH, index_col=0, parse_dates=True, encoding="utf-8-sig")
            cache = df.iloc[:, 0].dropna().to_dict()
            print(f"[4/7] {COL_PCR} — 캐시 로드: {len(cache)}일")
        except Exception as e:
            print(f"[4/7] {COL_PCR} — 캐시 로드 실패 (재수집): {e}")

    missing = [d for d in all_dates if d not in set(cache.keys())]
    print(f"  신규 수집 필요: {len(missing)}일 / 전체 목표: {len(all_dates)}일")

    if missing:
        new_data: dict = {}
        first_printed  = False
        batches        = [missing[i:i+BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        print(f"  배치 수집: {len(batches)}배치 × 최대 {BATCH_SIZE}건")

        aborted = False
        for b_idx, batch in enumerate(batches, 1):
            if aborted:
                break
            print(f"\n  ── 배치 [{b_idx}/{len(batches)}] 시작: {len(batch)}건 ──")
            t0 = time.time()
            executor = ThreadPoolExecutor(max_workers=2)
            try:
                futures = {executor.submit(_fetch_one, cfg, d.strftime("%Y%m%d")): d for d in batch}
                consecutive_empty = 0
                for fut in as_completed(futures):
                    d = futures[fut]
                    try:
                        ratio, rows = fut.result(timeout=30)
                        if not first_printed and rows:
                            print(f"  [진단] 필드: {list(rows[0].keys())}")
                            first_printed = True
                        consecutive_empty = 0 if rows else consecutive_empty + 1
                        if ratio is not None:
                            new_data[d] = ratio
                    except Exception:
                        consecutive_empty += 1
                    if consecutive_empty >= ABORT_THRESHOLD:
                        print(f"  [조기 중단] 연속 {consecutive_empty}회 빈 응답")
                        aborted = True
                        break
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            print(f"  배치 [{b_idx}] 완료 — {time.time()-t0:.0f}초, 누적 {len(new_data)}일")
            cache.update(new_data)
            if new_data:
                _save_cache(cache, pcr_start)
            if b_idx < len(batches) and not aborted:
                print(f"  {BATCH_DELAY}초 대기...")
                time.sleep(BATCH_DELAY)

        cache.update(new_data)
        _save_cache(cache, pcr_start)

    available = {k: v for k, v in cache.items()
                 if pd.Timestamp(pcr_start) <= k <= pd.Timestamp(cfg.today_fdr)}
    if len(available) < 20:
        print(f"  [경고] {COL_PCR} 데이터 부족 ({len(available)}일) — 인자 제외")
        return None

    print(f"  사용 데이터: {len(available)}일치 P/C 비율")
    return normalize_series(pd.Series(available).sort_index(), invert=True)


def _git_push(filepath: str, message: str):
    subprocess.run(["git", "config", "user.name",  "github-actions[bot]"], check=False)
    subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", filepath], check=False)
    res = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [git] commit 실패 (이미 최신이거나 권한 없음): {res.stderr.strip()}")
        return
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip() or "main"
    subprocess.run(["git", "pull", "--rebase", "origin", branch], check=False)
    r = subprocess.run(["git", "push", "origin", branch], capture_output=True, text=True)
    if r.returncode == 0:
        print(f"  [git] push 완료 → {branch}")
    else:
        print(f"  [git] push 실패: {r.stderr.strip()}")


def _save_cache(cache: dict, pcr_start: str):
    series = pd.Series(cache).sort_index()
    series = series[series.index >= pd.Timestamp(pcr_start)]
    series.to_csv(PCR_CACHE_PATH, header=["pcr_raw"], encoding="utf-8-sig")
    print(f"  캐시 저장: {len(series)}일 → {PCR_CACHE_PATH}")
    _git_push(PCR_CACHE_PATH, f"PCR 캐시 저장: {len(series)}일")


if __name__ == "__main__":
    from factors.config import make_config
    cfg = make_config()
    result = calc(cfg)
    if result is not None:
        print(f"[{COL_PCR}] 최근 5일:\n{result.tail(5)}")
    else:
        print(f"[{COL_PCR}] 수집 실패")
