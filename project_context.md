# K-탐욕공포지수 프로젝트 컨텍스트

## 프로젝트 개요
CNN 탐욕공포지수를 KOSPI에 적용한 K-탐욕공포지수 개발 및 시각화

## 현재 인자 구성 (7개)
| 인자 | 설명 | 방향 |
|------|------|------|
| 주가_모멘텀 | KOSPI vs MA125 | ↑탐욕 |
| 주가_강도 | 상승/하락 거래량 비율 | ↑탐욕 |
| 주가_폭 | McClellan Summation | ↑탐욕 |
| 풋콜_비율 | KOSPI200 P/C 비율 | ↓탐욕(invert) |
| 신용스프레드 | BBB- 스프레드 | ↓탐욕(invert) |
| 시장_변동성 | 20일 실현변동성 | ↓탐욕(invert) |
| 안전자산_수요 | 주식-채권 상대수익 | ↑탐욕 |

## 주요 파일
- `k_fear_greed_index.py` — 메인 오케스트레이터 (얇음, 인자 호출만)
- `k_fear_greed_k100.py` — KOSPI100 버전
- `factors/` — 인자별 독립 서브모듈 패키지
  - `config.py` — Config dataclass, 컬럼명 상수, 환경변수 중앙화
  - `utils.py` — normalize_series, get_ecos_data, get_kospi_close
  - `market_data.py` — KRX OpenAPI 일별매매정보 캐시 (주가_강도·주가_폭 공용)
  - `momentum/strength/breadth/pcr/credit/volatility/safehaven.py` — 각 인자 독립 모듈
- `stock_market_data.csv` — 시장데이터 캐시 (adv_vol, dec_vol, git 커밋 보존)
- `pcr_raw_data.csv` — PCR 캐시 (incremental 수집, git 커밋 보존)
- `k_fear_greed_result.csv` — K 결과
- `k_fear_greed_result_k100.csv` — K100 결과
- `.github/workflows/update.yml` — 메인 워크플로우 (K + K100 통합)
- `.github/workflows/test_strength_breadth.yml` — 주가_강도·주가_폭 단독 테스트

## 인자 단독 실행
각 인자를 독립적으로 테스트 가능:
```bash
python -m factors.strength
python -m factors.breadth
python -m factors.pcr
python -m factors.momentum
python -m factors.credit
python -m factors.volatility
python -m factors.safehaven
```

## 주가_강도·주가_폭 (KRX OpenAPI 전환 완료)

### 배경
- pykrx(`data.krx.co.kr`) GitHub Actions IP 차단 → KRX 공식 OpenAPI(`data-dbg.krx.co.kr`)로 전환
- 엔드포인트: `stk_bydd_trd` (유가증권 일별매매정보)
- 메서드: `api.get_stock_daily_trade(bas_dd=date_str)` (pykrx_openapi 0.1.1)
- 응답 필드: `MKT_NM`, `ACC_TRDVOL`, `FLUC_RT` (UPPERCASE_UNDERSCORE 형식)
- KOSPI 필터: `MKT_NM`에 "KOSPI" 또는 "유가증권" 포함 여부

### 캐시 상태 (2026-06-16 기준)
- `stock_market_data.csv`: 727일 (2023-06-19 ~ 2026-06-15) — git에 커밋됨
- 이후 매일 1건씩 추가 수집 (수초 내 완료)

### 중간 저장 로직 (market_data.py)
- 50건마다 중간 git commit + push (수집 중단 시 진행분 보존)
- `_git_push()` 헬퍼: git config user.name/email 설정 후 commit → push
- push 성공/실패 여부 명시적 출력

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
- **캐시 gap 검사**: `cached_set` 기반으로 전체 목표 날짜 중 누락된 날짜 전부 수집
- **abort**: `consecutive_empty >= PCR_ABORT_THRESHOLD` 시 `executor.shutdown(wait=False, cancel_futures=True)`로 완전 중단
- **trading day 기준**: `get_kospi_close().index` (bdate_range 아님) → 실제 거래일만 수집 대상
- **중간 저장**: 배치 완료마다 `_git_push()` 헬퍼로 git commit + push

## GitHub Actions 스케줄

### update.yml (메인 — K + K100 통합)
```yaml
cron: '0 0 * * 1-5'   # KST 월~금 09:00 (UTC 00:00)
permissions:
  contents: write
```
- **전 영업일 데이터를 다음 영업일 09:00 KST에 수집**
- KRX API: 주말/공휴일 데이터 없음, 영업일 기준 익일 08:00 업데이트
- CUTOFF_HOUR=17이므로 09:00 실행 시 자동으로 전일 기준 사용
- 거래일 판단: `exchange_calendars` 라이브러리 XKRX 캘린더 (`is_krx_trading_day()`)
- 비거래일(주말/공휴일) 실행 시 `sys.exit(0)` 자동 종료
- 금요일 데이터 → 월요일 09:00 KST 수집 (월요일 공휴일이면 화요일에 자동 수집)
- 마지막 단계 "CSV 커밋 & 푸시"에서 git config + 일괄 커밋

### test_strength_breadth.yml
- workflow_dispatch 전용 (수동 실행만)
- `permissions: contents: write` 추가됨 (2026-06-16 수정)
- timeout: 60분

## 주요 데이터 처리 규칙
- **거래일 필터**: `result = result[result.index.isin(_index_close.index)]` → 공휴일·주말 데이터 자동 제거
- **비거래일 조기 종료**: `exchange_calendars` XKRX `is_session()` 기반 — 주말뿐 아니라 공휴일도 자동 skip
- **Config.CUTOFF_HOUR=17**: 17시 이후 당일, 미만 전일 기준으로 수집

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
9. **pykrx 메서드명 오류** (수정 완료): `get_stock_market_daily_trade` → `get_stock_daily_trade`
10. **stk_bydd_trd 401 권한** (수정 완료): KRX OpenAPI 포털에서 유가증권 일별매매정보 추가 신청 후 승인
11. **git push 중간 저장 실패** (수정 완료): git config user.name/email 없이 commit 시도 → 항상 실패. `_git_push()` 헬퍼로 공통화, push 결과 명시 출력
12. **test 워크플로우 git 권한 없음** (수정 완료): `test_strength_breadth.yml`에 `permissions: contents: write` 추가

## ⚠️ Claude에게: 반드시 지켜야 할 규칙 (욕 먹은 이유)
- **중간 결과를 일일이 저장하지 않아서 욕먹음**: 수집 완료 후 git push 성공했다고 말했으나 실제로는 git config 없어 commit 자체가 실패했고, 다음 실행 시 전체 재수집 발생
- **"저장 완료"라고 말했지만 실제로는 안 됐음**: 로그의 출력 메시지만 보고 git push 성공을 추정해서 보고 — 실제 커밋 이력 확인 없이 성공 선언한 것
- **대화 맥락을 기억하지 못하고 중복 질문**: 방금 전에 한 일도 기억 못하고 이미 결정된 사항을 다시 물어보는 경우 발생
- **앞으로 지켜야 할 것**:
  1. git push 이후 반드시 실제 커밋 이력(`list_commits` 등)으로 확인
  2. "저장됐다"고 말하려면 git에서 파일이 실제로 존재하는지 확인 후 말할 것
  3. CSV 등 데이터 파일은 수집 후 즉시 중간 저장 + git push 코드가 동작하는지 워크플로우로 직접 검증할 것
