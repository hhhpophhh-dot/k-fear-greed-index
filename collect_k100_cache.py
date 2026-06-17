"""
KOSPI100 지수 종가 캐시 수집 스크립트 (수집 전용)
================================================
KRX OpenAPI get_kospi_daily_trade(bas_dd) → KOSPI100 레코드 필터 → CSV 캐시 저장.

[사용법]
- GitHub Actions에서 수동 실행 (collect_k100_cache.yml)
- 일일 API 한도(1,000~2,000회) 소진 시 자동 중단, 다음 날 재실행하면 이어서 수집
- 캐시 충분히 축적되면 k_fear_greed_k100.py가 이 파일을 읽어서 지수 산출

[캐시 파일]
- k100_index_cache.csv: 날짜, k100_close 컬럼
"""

import os
import time as _time
import subprocess as _sp
import pandas as pd
from datetime import datetime, timedelta, timezone
import warnings
warnings.filterwarnings("ignore")

KRX_AUTH_KEY = os.environ.get("KRX_AUTH_KEY", "")
K100_CACHE_PATH = "k100_index_cache.csv"
BATCH_SIZE = 50
BATCH_DELAY = 15
ABORT_THRESHOLD = 10

_KST = timezone(timedelta(hours=9))
_now = datetime.now(_KST)
TODAY_FDR = _now.strftime("%Y-%m-%d")


def main():
    if not KRX_AUTH_KEY:
        print("[오류] KRX_AUTH_KEY 환경변수가 설정되지 않았습니다.")
        return

    try:
        from pykrx_openapi import KRXOpenAPI
    except ImportError:
        print("[오류] pykrx-openapi 미설치: pip install pykrx-openapi")
        return

    collect_start = (datetime.today() - timedelta(days=400 * 7 // 5 + 30)).strftime("%Y-%m-%d")
    all_dates = pd.bdate_range(start=collect_start, end=TODAY_FDR)

    # ── 캐시 로드 ──
    cache: dict = {}
    if os.path.exists(K100_CACHE_PATH):
        try:
            cache_df = pd.read_csv(K100_CACHE_PATH, index_col=0, parse_dates=True,
                                   encoding="utf-8-sig")
            cache = cache_df.iloc[:, 0].dropna().to_dict()
            print(f"[캐시 로드] 기존 {len(cache)}일")
        except Exception as e:
            print(f"[캐시 로드 실패] {e}")

    # ── 미수집 날짜 ──
    missing = [d for d in all_dates if d not in cache]
    print(f"[수집 대상] 미수집 {len(missing)}일 / 전체 {len(all_dates)}일")

    if not missing:
        print("[완료] 모든 날짜 수집 완료. 추가 작업 없음.")
        return

    # ── 배치 수집 ──
    first_row_printed = False
    new_data: dict = {}
    aborted = False

    batches = [missing[i:i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"[배치 수집] {total_batches}배치 × 최대 {BATCH_SIZE}건 (배치 간 {BATCH_DELAY}초 대기)\n")

    for batch_idx, batch in enumerate(batches, start=1):
        if aborted:
            break

        print(f"── 배치 [{batch_idx}/{total_batches}] 시작: {len(batch)}건 ──")
        batch_start = _time.time()
        consecutive_empty = 0

        for d in batch:
            if aborted:
                break

            date_str = d.strftime("%Y%m%d")
            try:
                _time.sleep(0.5)
                api = KRXOpenAPI(api_key=KRX_AUTH_KEY)
                result = api.get_kospi_daily_trade(bas_dd=date_str)
                rows = result.get("OutBlock_1", [])

                if not first_row_printed and rows:
                    print(f"  [진단] 응답 필드: {list(rows[0].keys())}")
                    print(f"  [진단] 전체 지수 목록 ({date_str}):")
                    for r in rows:
                        nm = _get_index_name(r)
                        cl = _get_close_price(r)
                        print(f"    - {nm}: {cl}")
                    first_row_printed = True

                if not rows:
                    consecutive_empty += 1
                    if consecutive_empty >= ABORT_THRESHOLD:
                        print(f"  [조기 중단] 연속 {consecutive_empty}회 빈 응답 — API 한도 소진 추정")
                        aborted = True
                    continue

                consecutive_empty = 0
                close_val = _find_kospi100_close(rows)
                if close_val is not None:
                    new_data[d] = close_val

            except Exception as e:
                print(f"  [{date_str}] 오류: {e}")
                consecutive_empty += 1
                if consecutive_empty >= ABORT_THRESHOLD:
                    print(f"  [조기 중단] 연속 {consecutive_empty}회 오류")
                    aborted = True

        elapsed = _time.time() - batch_start
        print(f"  배치 [{batch_idx}/{total_batches}] 완료 — "
              f"소요 {elapsed:.0f}초, 이번 배치 {len(new_data)}일 누적\n")

        # ── 배치마다 캐시 저장 + git push ──
        if new_data:
            cache.update(new_data)
            _save_cache(cache, collect_start)
            _git_push(batch_idx, total_batches, len(cache))

        if batch_idx < total_batches and not aborted:
            print(f"  다음 배치까지 {BATCH_DELAY}초 대기...\n")
            _time.sleep(BATCH_DELAY)

    cache.update(new_data)
    print(f"\n[수집 결과] 이번 실행 신규: {len(new_data)}일 / 전체 캐시: {len(cache)}일")

    if cache:
        _save_cache(cache, collect_start)
        _git_push_final(len(cache))


def _get_index_name(row: dict) -> str:
    for key in ("idxNm", "idx_nm", "IDX_NM", "idxCd", "idx_cd",
                "itmNm", "itm_nm", "ISU_NM", "isuNm"):
        val = row.get(key)
        if val:
            return str(val)
    return str(list(row.values())[:2])


def _get_close_price(row: dict) -> float | None:
    for key in ("clpr", "tddClsprc", "clsPrc", "cls_prc", "CLSPRC",
                "endPrc", "closePrice", "close"):
        val = row.get(key)
        if val is not None:
            try:
                return float(str(val).replace(",", ""))
            except (ValueError, TypeError):
                continue
    return None


def _find_kospi100_close(rows: list) -> float | None:
    for r in rows:
        nm = _get_index_name(r).upper()
        if "100" in nm and ("KOSPI" in nm or "코스피" in nm):
            return _get_close_price(r)
    return None


def _save_cache(cache: dict, start_cutoff: str):
    series = pd.Series(cache, dtype=float).sort_index()
    series = series[series.index >= pd.Timestamp(start_cutoff)]
    series.to_csv(K100_CACHE_PATH, header=["k100_close"], encoding="utf-8-sig")
    print(f"  캐시 저장: {len(series)}일 → {K100_CACHE_PATH}")


def _git_push(batch_idx: int, total_batches: int, total_days: int):
    _sp.run(["git", "add", K100_CACHE_PATH], check=False)
    result = _sp.run(
        ["git", "commit", "-m",
         f"K100 지수 캐시 수집: 배치 {batch_idx}/{total_batches} ({total_days}일)"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        _sp.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        _sp.run(["git", "push", "origin", "main"], check=False)
        print(f"  git push 완료")


def _git_push_final(total_days: int):
    _sp.run(["git", "add", K100_CACHE_PATH], check=False)
    result = _sp.run(
        ["git", "commit", "-m", f"K100 지수 캐시 수집 완료 ({total_days}일)"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        _sp.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        _sp.run(["git", "push", "origin", "main"], check=False)
        print(f"  최종 git push 완료")


if __name__ == "__main__":
    main()
