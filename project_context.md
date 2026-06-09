# K-탐욕공포지수 프로젝트 컨텍스트

## 프로젝트 개요
CNN 탐욕공포지수를 KOSPI에 적용한 K-탐욕공포지수 개발 및 시각화

## 현재 인자 구성 (7개)
| 인자 | 설명 | 방향 |
|------|------|------|
| 주가_모멘텀 | KOSPI vs MA125 | ↑탐욕 |
| 주가_강도 | 52주 신고가 비율 | ↑탐욕 |
| 주가_폭 | McClellan Summation | ↑탐욕 |
| 풋콜_비율 | KOSPI200 P/C 비율 | ↓탐욕(invert) |
| 신용스프레드 | BBB- 스프레드 | ↓탐욕(invert) |
| 시장_변동성 | 20일 실현변동성 | ↓탐욕(invert) |
| 안전자산_수요 | 주식-채권 상대수익 | ↑탐욕 |

## 주요 파일
- `k_fear_greed_index.py` — 메인 산출 코드
- `k_fear_greed_result.csv` — 결과 저장 (매 실행 시 전체 재생성)
- `pcr_raw_data.csv` — PCR 캐시 (incremental 수집, git 커밋 보존)
- `.github/workflows/update.yml` — GitHub Actions 메인 워크플로우 (K + K100 통합)

## PCR (풋/콜 비율) 수집

### API 정보
- KRX Open API (`data-dbg.krx.co.kr/svc/apis/drv/opt_bydd_trd`)
- 환경변수: `KRX_AUTH_KEY` (GitHub Secret)
- 유량제한: 10,000건/day
- 라이브러리: `pykrx-openapi`, `get_options_daily_trade()`

### 실제 API 응답 필드 (확인 완료)
```
['BAS_DD', 'PROD_NM', 'RGHT_TP_NM', 'ISU_CD', 'ISU_NM', 'TDD_CLSPRC',
 'CMPPREVDD_PRC', 'TDD_OPNPRC', 'TDD_HGPRC', 'TDD_LWPRC', 'IMP_VOLT',
 'NXTDD_BAS_PRC', 'ACC_TRDVOL', 'ACC_TRDVAL', 'ACC_OPNINT_QTY']
```
- `RGHT_TP_NM` 실제 값: `"CALL"` / `"PUT"` (영어)
- KOSPI200 필터: `PROD_NM` 또는 `ISU_NM` 에 "KOSPI200" 포함 여부

### 수집 로직
- 배치 크기: 50건, 요청 간 딜레이 0.5초, 배치 간 15초 대기, max_workers=2
- **캐시 gap 검사**: `cached_set` 기반으로 전체 목표 날짜 중 누락된 날짜 전부 수집 (last_cached 이후만이 아님)
- **abort**: `consecutive_empty >= PCR_ABORT_THRESHOLD` 시 `executor.shutdown(wait=False, cancel_futures=True)`로 완전 중단
- **trading day 기준**: `get_kospi_close().index` (bdate_range 아님) → 실제 거래일만 수집 대상

### 캐시 상태 (2026-06-09 기준)
- 캐시: 391일 (2024-10-24 ~ 2026-06-04)
- 미수집: 2026-06-05, 06-08 → 다음 실행 시 cached_set 로직으로 자동 수집
- 정상 동작: 첫 252거래일 이전은 풋콜_비율 NaN (rolling normalize window)

## GitHub Actions 스케줄

### update.yml (메인 — K + K100 통합)
```yaml
cron: '0 0 * * 2-6'   # KST 화~토 09:00 (UTC 00:00)
```
- **전날 데이터를 다음날 09:00 KST에 수집** (KRX API 익일 08:00 업데이트 기준)
- CUTOFF_HOUR=17이므로 09:00 실행 시 자동으로 전날 기준 사용
- 예: 화요일 09:00 실행 → 월요일 데이터 수집

### update_k.yml, update_k100.yml
- workflow_dispatch 전용 (수동 실행만, 스케줄 없음)

## 주요 데이터 처리 규칙
- **거래일 필터**: `result = result[result.index.isin(_index_close.index)]` → 공휴일·주말 데이터 자동 제거
- **주말 조기 종료**: `if _base.weekday() >= 5: sys.exit(0)` (공휴일은 result 필터에서 자동 처리)
- **KOSPI 종목 목록**: pykrx `get_market_ticker_list` — 실패 시 최대 7일 이내 날짜로 재시도, 모두 실패 시 RuntimeError

## index.html 전일값 표시
- 인자값이 NaN인 경우 직전 거래일 값으로 forward-fill (JS `applyForwardFill()`)
- forward-fill된 값은 "전일" 배지로 표시 (CSS `.est-badge`)
- 팩터바 및 테이블 모두 적용

## 과거 주요 버그 및 수정 이력
1. **API 필드명 오류** (수정 완료): `itmNm` → `PROD_NM`, `"C"/"P"` → `"CALL"/"PUT"`
2. **캐시 조건 버그** (수정 완료): 신규 데이터 없어도 캐시 덮어쓰기 → `if new_data:` 조건 추가
3. **PCR gap 미재시도** (수정 완료): `last_cached` 이후만 수집 → `cached_set` 전체 gap 검사로 변경
4. **PCR abort 미작동** (수정 완료): `executor.shutdown(wait=False, cancel_futures=True)` 추가
5. **공휴일 데이터 포함** (수정 완료): ECOS 채권금리 공휴일에도 반환 → 거래일 필터로 제거
6. **FDR 종목 목록 404** (수정 완료): `fdr.StockListing("KOSPI")` → pykrx 7일 재시도로 대체
7. **스케줄 당일 수집 불가** (수정 완료): 같은 날 19:00 KST → 다음날 09:00 KST로 변경
8. **워크플로우 actions 버전** (수정 완료): checkout@v4→v5, setup-python@v5→v6
