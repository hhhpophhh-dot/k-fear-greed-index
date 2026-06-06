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
- `k_fear_greed_result.csv` — 결과 저장
- `pcr_raw_data.csv` — PCR 캐시 (incremental 수집)
- `.github/workflows/update_k.yml` — GitHub Actions (timeout 60분)

## PCR (풋/콜 비율) 수집 현황

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
- `RGHT_TP_NM` 실제 값: `"CALL"` / `"PUT"` (영어, 스펙: 권리유형(CALL/PUT))
- KOSPI200 필터: `PROD_NM` 또는 `ISU_NM` 에 "KOSPI200" 포함 여부

### 수집 로직
- 배치 크기: 50건, 요청 간 딜레이 0.5초, 배치 간 15초 대기, max_workers=2
- 신규 데이터 있을 때만 캐시 저장 + git push (중단 시 보존 목적)
- PCR 수집 → 주가강도 순서로 실행

### 현재 캐시 상태 (2026-06-06 기준)
- 캐시: 389일 (2024-10-24 ~ 2026-06-01)
- **미수집: 2026-06-02, 06-04, 06-05** (3일) → 풋콜_비율 NaN
- 원인: API 일일 한도 소진으로 최근 날짜 수집 미완료
- 다음 워크플로우 실행 시 자동 수집 예정

## GitHub Actions
- 워크플로우: `update_k.yml`, timeout 60분
- MCP를 통한 트리거: `mcp__github__actions_run_trigger` 사용
- MCP 연결이 끊겼을 경우: PAT(Personal Access Token)으로 curl API 호출 가능
  - `curl -s -H "Authorization: token <PAT>" "https://api.github.com/repos/hhhpophhh-dot/k-fear-greed-index/actions/workflows/update_k.yml/dispatches" -X POST -d '{"ref":"main"}'`

## 주요 결정 사항
- K100 지수 관련 코드는 이 대화에서 수정하지 않음
- PCR 외 항목(주가강도 등)은 pykrx 라이브러리 사용 (KRX Open API와 별개)
- 캐시 파일은 git에 커밋하여 워크플로우 재시작 시에도 보존

## 과거 주요 버그 및 수정 이력
1. **API 필드명 오류** (수정 완료): pykrx 스타일 camelCase → 실제 UPPERCASE_UNDERSCORE
   - `itmNm` → `PROD_NM`, `rghtTpCd` → `RGHT_TP_NM`, `acmlTrdvol` → `ACC_TRDVOL`
   - `"C"/"P"` → `"CALL"/"PUT"` (실제 API 영어값)
2. **캐시 조건 버그** (수정 완료): 신규 데이터 없어도 캐시 덮어쓰기 → `if new_data:` 조건 추가
3. **실행 순서** (수정 완료): 주가강도 먼저 실행 → PCR 먼저 실행
4. **워크플로우 타임아웃** (수정 완료): 30분 → 60분
