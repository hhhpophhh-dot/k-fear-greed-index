# 프로젝트 컨텍스트

## 목표
1. CNN 탐욕공포지수 분석
2. K-탐욕공포지수 도출 (종가 기준 일 1회 산출)
3. 시각화

## 현재 상황
GitHub Actions 자동화 + GitHub Pages 배포 완료 (2026-06-01)
배포 URL: https://hhhpophhh-dot.github.io/k-fear-greed-index/

## 이미 결정된 사항
- 결정 1: 산출 주기 = 종가 기준 1일 1회 (이유: 실시간 데이터 수집 어려움, KOSPI 장 마감 15:30 이후 산출)
- 결정 2: 주가 폭 = 거래량 기반 McClellan Summation Index (이유: KOSPI는 삼성전자 등 대형주 비중 과대, 종목 수 기반은 시장 실제 흐름과 괴리 발생)
- 결정 3: 정크본드 스프레드 = 회사채 BBB- 3년물 - 국고채 3년물 (이유: 한국 정크본드 시장 미발달, BBB-가 현실적 최선. 명칭은 "신용스프레드"로 표기)
- 결정 4: 데이터 수집 방법 = FinanceDataReader + pykrx(개별 종목) + ECOS API
  - 사유: pykrx 1.2.8 업그레이드로 지수 API(get_index_ohlcv_by_date 등)는 KRX 로그인 필수가 됨
  - 개별 종목 API(get_market_ohlcv_by_date)는 로그인 없이 여전히 작동 → 유지
  - KOSPI 지수 시계열, 종목 목록: FinanceDataReader(FDR)로 대체
- 결정 5: 풋/콜 비율 인자 제외 → 6개 인자로 운영 확정
  - 사유: pykrx 옵션 함수 없음 / KRX 포털 API(data.krx.co.kr)는 브라우저 세션 쿠키 필요(400 LOGOUT) → 공개 API로 수집 불가

## K-탐욕공포지수 인자 확정 (6개) — 최종

| 인자 | 대체 지표 | 수집 방법 | 비고 |
|------|-----------|-----------|------|
| 주가 모멘텀 | KOSPI 종가 vs 125일 MA | **FDR (KS11)** | pykrx 지수 API 로그인 필요로 FDR 대체 |
| 주가 강도 | 52주 신고가/신저가 종목 수 비율 | **FDR 종목목록 + pykrx 개별 종목** | 종목 목록: FDR StockListing / OHLCV: pykrx (로그인 불필요) |
| 주가 폭 | McClellan Summation Index (거래량 기반) | **pykrx 개별 종목 루프** | 날짜별 전체 API 폐쇄 → 종목별 루프로 전환, 동일 데이터 재사용 |
| ~~풋/콜 비율~~ | ~~KOSPI200 옵션 P/C 비율~~ | ~~수집 불가~~ | ❌ 제외 확정 |
| 신용스프레드 | 회사채 BBB- 3년물 - 국고채 3년물 | 한국은행 ECOS API | 항목코드: 국고채 010200000 / BBB- 010320000 |
| 시장 변동성 | ~~VKOSPI~~ → **KOSPI 20일 실현변동성** | **FDR (KS11)** | VKOSPI 공개 API 없음 → std(20일 수익률)×√252×100 으로 대체 |
| 안전자산 수요 | KOSPI 20일 수익률 - 국고채 3년물 20일 금리변화 | **FDR (KS11) + ECOS API** | pykrx 지수 API 폐쇄 → FDR 대체 |

### 데이터 수집 실행 시점
- 매일 **17:00 이후** 실행 (pykrx는 장마감 후 16:00~17:00 사이 KRX 데이터 반영 완료)

## 진행 현황
- [x] CNN 탐욕공포지수 7개 인자 분석 완료
- [x] 산출 주기 결정 (종가 기준 1일 1회)
- [x] K-탐욕공포지수 인자 설계 확정
- [x] 데이터 수집 방법 결정 (pykrx + ECOS API 기본, 풋/콜 비율은 KRX 포털 API 시도)
- [x] ECOS 항목 코드 직접 확인 완료 (국고채 010200000, BBB- 010320000)
- [x] 지수 산출 코드 작성 (6개 인자, 풋/콜 비율 제외 확정)
- [x] ECOS BBB- 항목 코드 오류 수정 (010310000 → 010320000)
- [x] 출력 형식 완성 (기준일 자동 전환 17:00, 인자별 점수 + 최근 10일 테이블)
- [x] 시각화 HTML 완성 (index.html) — 게이지 + 히스토리 차트 + 인자별 바 + 10일 테이블
- [x] pykrx KRX API 오류 해결 → FDR + pykrx 개별 종목 혼용으로 실제 CSV 생성 완료
- [x] CSV-HTML 호환성 오류 수정 → 시각화 정상 동작 확인
- [x] GitHub Actions 자동화 (.github/workflows/update.yml, 평일 17:00 KST 스케줄)
- [x] 배포 완료 — GitHub Pages (https://hhhpophhh-dot.github.io/k-fear-greed-index/)

## 주요 제약 조건
- 실시간 데이터 수집 불가 → 종가 기준 1일 1회 산출
- KOSPI 장 시간: 09:00~15:30
- 한국 정크본드 시장 미발달 → BBB- 신용스프레드로 대체
- pykrx 1.2.8~: KRX 2026.02.27 정책 변경으로 지수 API(data.krx.co.kr)는 로그인 필수
  - `get_index_ohlcv_by_date`, `get_market_ohlcv(date)`, `get_market_ticker_list` → 모두 로그인 필요
  - `get_market_ohlcv_by_date(ticker)` (개별 종목) → 로그인 없이 작동 ✅
- VKOSPI 공개 API 없음 → 20일 실현변동성(KOSPI 수익률 기반)으로 대체
  - VIX(내재변동성)는 옵션 가격에서 역산한 미래 기대치 → 공포 즉각 반영 (forward-looking)
  - 실현변동성은 과거 20일 수익률 std × √252 × 100 → 공포 발생 후 1~2주 지연 (backward-looking)
  - 장기 추세에서 두 지표의 상관계수는 0.7~0.85 수준 → 현실적 대체 가능
  - 추후 VKOSPI 공개 데이터 확보 시 대체 재검토 예정

## Sub 대화 요약
[Sub 1 - CNN 탐욕공포지수 분석 및 K-지수 인자 설계]
- CNN 7개 인자 분석: 주가모멘텀, 주가강도, 주가폭, 풋콜비율, 정크본드수요, VIX, 안전자산수요
- 각 인자 0~100 정규화(과거 데이터 상대 정규화) 후 동일가중 평균
- 산출 방식: 종가 기준 1일 1회 확정
- 주가 폭: 거래량 기반 McClellan으로 확정 (KOSPI 대형주 쏠림 문제)
- 정크본드: BBB- 신용스프레드로 확정 (한국 고수익채 시장 미발달)
- 데이터 출처: KRX, pykrx, 금융투자협회, 한국은행 ECOS

[Sub 2 - 데이터 수집 방법 확정]
- 7개 인자 전부 pykrx + ECOS API로 수집 가능 확인 (크롤링 불필요)
- pykrx: 실시간 아님, 장마감 후 16:00~17:00 KRX 반영 → 매일 17:00 이후 실행
- 풋/콜 비율: pykrx에서 콜/풋 따로 요청 후 거래량 합산 계산 필요
- ECOS API(신용스프레드, 국고채): 당일 데이터가 익영업일 반영될 수 있어 코드 작성 시 확인 필요

[Sub 3 - 풋/콜 비율 제외 확정 및 코드 완성]
- pykrx 옵션 함수 없음, KRX 포털 API는 세션 쿠키 필요(400 LOGOUT) → 공개 수집 불가
- B안 확정: 풋/콜 비율 제외, 6개 인자 동일가중 평균으로 운영
- ECOS BBB- 항목 코드 오류 수정: 010310000(AA-민평) → 010320000(BBB-)
- 기준일 자동 전환 로직 추가: 17:00 이전=전일, 이후=당일 (pykrx 반영 시간 기준)
- 출력 형식: 기준일 안내 → 인자별 진행 [1/6]~[6/6] → 요약 테이블 → 최근 10일 전체 인자 점수 → CSV 저장
- 산출 파일: k_fear_greed_index.py (완성)

[Sub 4 - 시각화 HTML 구현 및 pykrx 에러 분석]
- index.html 완성: 반원 게이지, 인자별 가로 바, 60일 히스토리 라인차트, 10일 테이블
- CSV 로드 방식: fetch() 시도 → 실패 시 파일 직접 선택 fallback (file:// CORS 대응)
- 배포 구조 확정: GitHub Actions 자동화 + GitHub Pages (또는 Vercel/Netlify는 나중에 결정)
- pykrx 에러 원인: KRX 2026.02.27 API 정책 변경 → User-Agent 없는 요청 차단
  - 증상: get_index_ohlcv_by_date 내부에서 IndexTicker().get_name() 호출 시 KeyError: '지수명'
  - webio.Post/Get.read 패치 시도했으나 IndexTicker는 다른 내부 경로 사용 → 실패
  - 참고 이슈: https://github.com/sharebook-kr/pykrx/issues/276
- 해결 결과 (Sub 5에서 완료):
  - pykrx 1.2.8 분석: 지수/시장 API는 KRX 로그인 세션 필수, 개별 종목 API는 로그인 불필요
  - KRX 세션 워밍업(JSESSIONID)만으로는 data.krx.co.kr API 접근 불가 (LOGOUT 400 반환)
  - FDR(FinanceDataReader) + pykrx 개별 종목 혼용 방식으로 모든 인자 수집 성공

[Sub 5 - pykrx 오류 최종 해결 및 CSV 생성 완료]
- pykrx 1.2.8 심층 분석
  - `data.krx.co.kr` API: 2026.02.27 이후 JSESSIONID 인증 필수 (로그인 없이 400 LOGOUT)
  - 영향 받는 함수: get_index_ohlcv_by_date, get_market_ohlcv(date), get_market_ticker_list
  - 영향 없는 함수: get_market_ohlcv_by_date(ticker) — 개별 종목 API는 별도 엔드포인트
- 대체 방안 확정
  - KOSPI 지수 시계열 → FDR `DataReader('KS11', start, end)`
  - KOSPI 종목 목록 → FDR `StockListing('KOSPI')` (948개)
  - 개별 종목 OHLCV → pykrx `get_market_ohlcv_by_date(ticker)` 유지 (로그인 불필요)
  - VKOSPI → KOSPI 20일 실현변동성(연율화) 으로 대체 (VKOSPI 공개 API 존재하지 않음)
- 성능 최적화: 주가강도·주가폭에서 전 종목 데이터를 1회만 수집 후 공용 캐시 재사용
- 실행 결과 (2026-05-21 기준): K-탐욕공포지수 **48.2 (중립)**
  - 주가 모멘텀 96.0 / 주가 강도 5.6 / 주가 폭 68.9 / 신용스프레드 12.4 / 시장 변동성 13.1 / 안전자산 수요 93.2
  - CSV 784행 생성 완료 (k_fear_greed_result.csv)
- 추가 설치 라이브러리: `pip install finance-datareader yfinance`

[Sub 6 - CSV-HTML 호환성 오류 수정 및 시각화 정상화]
- 문제 1: CSV 날짜 컬럼 헤더 불일치
  - 신규 스크립트가 `result_df.to_csv()` 시 인덱스 이름 미설정 → 헤더 첫 컬럼이 `""`(빈 문자열)로 저장
  - HTML parseCSV가 `r["날짜"]` 키로 접근 → undefined → 전체 행 필터링 → 빈 화면
  - 수정: `result_df.index.name = "날짜"` 추가 → CSV 헤더 `날짜,주가_모멘텀,...` 형식으로 통일
- 문제 2: 초기 행 오염 데이터
  - 6개 인자 정규화 미달 구간(데이터 부족)에서 일부 인자만 유효한 행이 K_탐욕공포지수에 반영 → 왜곡값
  - `dropna(subset=["K_탐욕공포지수"])` → `dropna(subset=[6개 인자 컬럼])` 으로 강화
  - 결과: 6개 인자 전부 유효한 행만 저장 (784행 → 354행, 기간 2024-12-05~)
- 문제 3: 히스토리 차트 과다 데이터
  - HTML이 전체 CSV 행을 차트에 렌더링 → 제목 "최근 60일"과 실제 표시 불일치
  - `renderHistoryChart(rows.slice(-60))` 로 수정
- 최종 CSV: 354행 (2024-12-05 ~ 2026-05-22), 6개 인자 모두 유효
- 최종 K-탐욕공포지수 (2026-05-22 기준): **52.7 (중립)**

[Sub 7 - GitHub Actions 자동화 및 GitHub Pages 배포]
- gh CLI로 GitHub 저장소 생성 (k-fear-greed-index, public)
- ECOS_API_KEY를 GitHub Secret으로 등록, 코드에서 os.environ.get()으로 읽도록 수정
- .github/workflows/update.yml 생성: 평일 10:00 UTC(19:00 KST) 스케줄 + workflow_dispatch 수동 실행
  - 스케줄: 08:00 UTC(17:00 KST) → 10:00 UTC(19:00 KST)로 변경 (pykrx 반영 여유 확보)
- GitHub Pages 활성화 (main 브랜치 루트) → 배포 URL 확정
- 초기 배포 시 당일 스케줄 누락(저장소 생성이 08:00 UTC 이후) → workflow_dispatch로 수동 실행

[Sub 8 - UTC/KST 버그 수정 및 UI 개선 (2026-06-01)]
- 버그: 5/29 이후 데이터 미갱신 원인 파악
  - Actions 실행 환경(UTC)에서 datetime.now()가 UTC 반환 → UTC 10:00 < 17:00 → 전일(토요일) 기준으로 잘못 판단
  - 수정: datetime.now(timezone(timedelta(hours=9))) 으로 KST 명시 → 당일 기준 정상 처리
- UI: 인자별 바 하단에 계산 방식 설명 추가 (역방향 여부 포함)
- 주가 강도 이상 현상 확인 필요
  - 6/1 기준 주가_강도 = 0.79 (극단적 저수준), 주가 모멘텀은 100인 상황
  - 원인 분석 중 → Sub 9에서 처리 예정
