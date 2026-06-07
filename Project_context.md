# 프로젝트 컨텍스트

## 목표
1. CNN 탐욕공포지수 분석
2. K-탐욕공포지수 도출 (종가 기준 일 1회 산출)
3. 시각화
4. **[신규] 탭 2: KOSPI100 기반 K-탐욕공포지수 추가** — 대형주 시장 심리 별도 산출
   - 탭 1: 현행 KOSPI 전체 지수 (유지)
   - 탭 2: KOSPI100 구성 종목 기반 지수 (신규)
   - ※ 풋/콜 비율 인자 추가는 KOSPI100 탭 작업 완료 후 재검토

## 현재 상황
GitHub Actions 자동화 + GitHub Pages 배포 완료 (2026-06-01)
배포 URL: https://hhhpophhh-dot.github.io/k-fear-greed-index/

**워크플로우 구조 (2026-06-03 확정)**
| 파일 | 실행 방식 | 용도 |
|---|---|---|
| update.yml | 매일 19:00 KST 자동 + 수동 | K + K100 합본 (일상 운영) |
| update_k.yml | 수동만 | K지수 단독 테스트/수정 |
| update_k100.yml | 수동만 | K100지수 단독 테스트/수정 |

**스크립트 구조 (2026-06-03 확정)**
- `k_fear_greed_index.py` — KOSPI 전체 K지수 전용
- `k_fear_greed_k100.py` — KOSPI100 K100지수 전용 (공통 함수 import)
- `index.html` — 두 CSV 탭으로 표시 (시각화 합본)

**현재 미해결 과제 (각 세션에서 별도 진행)**
- K지수: 풋/콜 비율 캐시(pcr_raw_data.csv) 391일 수집 완료, 매일 1~2일씩 자동 추가 수집 중 (정상 운영)
  - 풋콜 없는 기간: 2024-12-17 ~ 2025-11-05 (213행) — 초기 미수집 구간, 소급 수집 불필요
  - 풋콜 있는 기간: 2025-11-06 ~ 현재 (140행+) — 7인자 정상 활성화
- K100지수 (`update_k100.yml`): KOSPI100 지수 시계열 API 미확보 (네이버 모바일/PC, Stooq 모두 실패) — 보류 중

## 이미 결정된 사항
- 결정 1: 산출 주기 = 종가 기준 1일 1회 (이유: 실시간 데이터 수집 어려움, KOSPI 장 마감 15:30 이후 산출)
- 결정 2: 주가 폭 = 거래량 기반 McClellan Summation Index (이유: KOSPI는 삼성전자 등 대형주 비중 과대, 종목 수 기반은 시장 실제 흐름과 괴리 발생)
- 결정 3: 정크본드 스프레드 = 회사채 BBB- 3년물 - 국고채 3년물 (이유: 한국 정크본드 시장 미발달, BBB-가 현실적 최선. 명칭은 "신용스프레드"로 표기)
- 결정 4: 데이터 수집 방법 = FinanceDataReader + pykrx(개별 종목) + ECOS API
  - 사유: pykrx 1.2.8 업그레이드로 지수 API(get_index_ohlcv_by_date 등)는 KRX 로그인 필수가 됨
  - 개별 종목 API(get_market_ohlcv_by_date)는 로그인 없이 여전히 작동 → 유지
  - KOSPI 지수 시계열, 종목 목록: FinanceDataReader(FDR)로 대체
- 결정 5: 풋/콜 비율 = KRX Open API(openapi.krx.co.kr) 정상 운영 중 (2026-06-07 확정)
  - 데이터 수집: pykrx-openapi 라이브러리, `get_options_daily_trade()` → OutBlock_1
  - 캐시 방식: pcr_raw_data.csv에 원시 P/C 비율 저장, 마지막 캐시 날짜 이후 날짜만 API 호출 (1~2회/일)
  - 수집 대상: pd.bdate_range → KOSPI FDR 실제 거래일 기준으로 변경 (공휴일 API 낭비 방지)
  - Fallback: 데이터 부족 시 6개 인자로 자동 계속 실행

## K-탐욕공포지수 인자 (6+1개 목표)

| 인자 | 대체 지표 | 수집 방법 | 비고 |
|------|-----------|-----------|------|
| 주가 모멘텀 | KOSPI 종가 vs 125일 MA | **FDR (KS11)** | pykrx 지수 API 로그인 필요로 FDR 대체 |
| 주가 강도 | 52주 신고가/신저가 종목 수 비율 | **FDR 종목목록 + pykrx 개별 종목** | 종목 목록: FDR StockListing / OHLCV: pykrx (로그인 불필요) |
| 주가 폭 | McClellan Summation Index (거래량 기반) | **pykrx 개별 종목 루프** | 날짜별 전체 API 폐쇄 → 종목별 루프로 전환, 동일 데이터 재사용 |
| 풋/콜 비율 | KOSPI200 옵션 P/C 비율 | **KRX Open API (pykrx-openapi)** | 캐시(pcr_raw_data.csv) 도입, 한도 소진 시 인자 제외 fallback |
| 신용스프레드 | 회사채 BBB- 3년물 - 국고채 3년물 | 한국은행 ECOS API | 항목코드: 국고채 010200000 / BBB- 010320000 |
| 시장 변동성 | ~~VKOSPI~~ → **KOSPI 20일 실현변동성** | **FDR (KS11)** | VKOSPI 공개 API 없음 → std(20일 수익률)×√252×100 으로 대체 |
| 안전자산 수요 | KOSPI 20일 수익률 - 국고채 3년물 20일 금리변화 | **FDR (KS11) + ECOS API** | pykrx 지수 API 폐쇄 → FDR 대체 |

### 데이터 수집 실행 시점
- 매일 **19:00 KST** 자동 실행 (GitHub Actions cron: 10:00 UTC)
- pykrx KRX 데이터 반영: 장마감(15:30) 후 16:00~17:00 완료 → 19:00 실행으로 여유 확보

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
- [x] GitHub Actions 자동화 (.github/workflows/update.yml, 평일 19:00 KST 스케줄 / 10:00 UTC)
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
- UI: 인자별 바 하단에 계산 방식 설명 추가 후 → 최하단 카드로 이동
- 주가 강도 이상 현상 조사 및 결론
  - 6/1 진단 결과: pykrx 마지막 날짜 2026-06-01 확인, 신고가 35개 / 신저가 251개 / 비율 12.2%
  - 정규화 점수 0.79 = 역사적 하위 0.8 퍼센타일 → 코드 버그 아님
  - 원인: KOSPI는 대형주(삼성전자 등) 주도로 신고가, 나머지 종목 26%는 52주 신저가 → 지수-개별종목 괴리 정확히 반영
- 신고가/신저가 종목 수 CSV 저장 추가 (신고가_종목수, 신저가_종목수 컬럼)
- UI: 주가 강도 바에 신고가/신저가 종목 수 및 비율 inline 표시

[Sub 9 - 안전자산 수요 항상 90+ 이상 문제 분석 (2026-06-02)]
- 증상: 안전자산_수요가 80~100 범위에 고착, 유효한 변동 신호를 주지 못함
- 원인 1: 공식이 사실상 KOSPI 20일 수익률만 측정
  - 채권 항목 treasury_ret_proxy = -treasury_chg_20 / 100 → 채권 기여분 전체의 2~5%에 불과
  - 듀레이션(2.8년) 적용해도 5.6%로 여전히 미미 → 채권 term이 사실상 무의미
- 원인 2: KOSPI 이례적 강세장 (2025~2026)
  - KOSPI 20일 수익률 최근값: +24~+31% (연간 수준의 상승을 20일만에 달성)
  - 과거 252일 중 86.1%가 양(+)의 20일 수익률 → 정규화 시 상위 퍼센타일 고착
- 결론: 코드 버그 아님. 현재 지표는 사실상 "KOSPI 단기 모멘텀" 재측정에 가까워 주가 모멘텀과 중복
- 개선 방향 (추후 검토)
  - A안: 채권 수익률을 가격 기준으로 환산 (-듀레이션 × 금리변화) 하여 비중 정상화
  - B안: 20일 수익률 대신 상대강도(주식/채권 수익률 비율)로 변경
  - C안: 현행 유지하되 설명에 "KOSPI 단기 강세 반영" 명시
- **확정: C안 (현행 유지)** — 지표 의미를 있는 그대로 인정, A/B안 개선은 보류

[Sub 10 - UI 개선: 업데이트 시각 표시 + 풋/콜 비율 제외 사유 안내 (2026-06-02)]
- Python 스크립트 실행 시각(KST HH:MM)을 CSV 최신 행 `업데이트_시각` 컬럼에 기록
- index.html: 기준일 표시 아래 `(업데이트: HH:MM KST)` 추가
- 하단 인자 설명 카드에 풋/콜 비율 항목 추가 (취소선 + 회색 처리)
  - 내용: "KRX 옵션 데이터 API가 브라우저 세션 인증을 요구해 공개 수집 불가"
- Python 스크립트 실행 시각(KST HH:MM)을 CSV 최신 행 `업데이트_시각` 컬럼에 기록
- index.html: 기준일 표시 아래 `(업데이트: HH:MM KST)` 추가
- 하단 인자 설명 카드에 풋/콜 비율 항목 추가 (취소선 + 회색 처리)
  - 내용: "KRX 옵션 데이터 API가 브라우저 세션 인증을 요구해 공개 수집 불가"

[Sub 11 - CNN Fear & Greed Index 비교 위젯 추가 (2026-06-02)]
- Python: CNN 비공식 API(production.dataviz.cnn.io/index/fearandgreed/graphdata)에서 현재값 조회
  - 첫 시도: User-Agent만 설정 → HTTP 418 봇 차단 실패
  - 헤더 보강(Accept, Referer, Origin 추가) → 정상 조회 성공
  - CSV 최신 행에 `CNN_탐욕공포지수`, `CNN_등급`(영문) 컬럼 저장
- index.html: 게이지 하단 CNN 비교 위젯 추가
  - 수치 흰색, 등급 한글+색상(K-지수와 동일 팔레트), 영문 병기
  - CNN 조회 실패 시 위젯 숨김(display:none) 처리
- 모바일 레이아웃 한 줄 처리
  - 헤더: white-space:nowrap + h1 크기 축소(1.35→1.1rem), 부제목 ellipsis
  - 신고가/신저가 라인: 글자 축소(0.68rem) + white-space:nowrap
  - 인자 설명 카드: grid→flex 전환, dd는 ellipsis

[Sub 12 - 풋/콜 비율 인자 추가 시도 및 작업 중 (2026-06-02)]
- KRX Open API(openapi.krx.co.kr) 방식으로 풋/콜 비율 재추가 시도
  - pykrx-openapi 라이브러리 사용: `get_options_daily_trade(bas_dd)` → OutBlock_1
  - 인증: AUTH_KEY 헤더 (브라우저 세션 불필요) → GitHub Secret KRX_AUTH_KEY 등록
- 발생한 문제들
  1. K-지수 계산 버그: `result.mean(axis=1)`이 신고가/신저가 원시 카운트도 평균에 포함 → `result[list(factors.keys())].mean()`으로 수정
  2. 순차 API 호출 60분 타임아웃: 400일 × 9초 → 4 병렬 워커(ThreadPoolExecutor)로 전환
  3. KRX Open API 일일 호출 한도 초과: 오늘 3회 실행 × ~400회 = ~1,200회 → 한도(1,000~2,000회) 소진 후 빈 응답
- 최종 구조
  - `pcr_raw_data.csv` 캐시 도입: 최초 1회 전체 수집, 이후 신규 날짜(1~2회/일)만 호출
  - 데이터 부족 시 graceful fallback: 경고 출력 후 6개 인자로 계속 실행
  - 워크플로우에서 `pcr_raw_data.csv`도 git commit 대상에 추가
- 현황: 2026-06-03 일일 한도 리셋 후 첫 캐시 수집 예정. 성공 시 7개 인자로 전환
- 추가 버그: 빈 dict → pd.Series 시 RangeIndex 생성 → Timestamp 비교 TypeError → `if pcr_cache:` 조건으로 수정

[Sub 13 - KOSPI100 탭 추가 (2026-06-02)]
- 결정: 지수 시계열 = 네이버 금융 모바일 API (C안), 구성 종목 = FDR 시가총액 상위 100개 (A안)
- 구현 내용
  - `get_naver_kospi100_close()`: `m.stock.naver.com/api/index/KOSPI100/price` 호출, JSON 파싱
  - `get_kospi100_tickers()`: FDR StockListing('KOSPI')에서 Marcap 상위 100개 필터링
  - `calc_k_fear_greed_index(universe)`: `universe='all'`(KOSPI 전체) / `universe='k100'`(KOSPI100) 파라미터 추가
    - 각 calc 함수에 `_close`, `_stock_data` 옵션 파라미터 추가 → 기본값은 기존 동작 유지
    - 전 종목 캐시(_kospi_stock_cache) 공유 → KOSPI100은 추가 수집 없이 필터링만
    - KOSPI100 실패 시 graceful fallback (전체 지수 저장은 영향 없음)
  - `_save_result()` 헬퍼 함수로 CSV 저장 로직 공통화
  - 출력 파일: `k_fear_greed_result_k100.csv` 별도 생성
- index.html: 탭 UI 추가 (KOSPI 전체 / KOSPI 100 버튼), 탭 전환 시 해당 CSV 자동 로드
- update.yml: `k_fear_greed_result_k100.csv` git commit 대상 추가
- 현황: 워크플로우 실행 중 (네이버 API 응답 구조 첫 실행 시 로그 출력 예정)
  - 주의: 네이버 API 응답 키가 예상(`localTradedAt`, `closePrice`)과 다를 경우 수정 필요
  - 풋/콜 비율은 여전히 KRX API 한도 소진으로 fallback(6인자) 동작 예정

[Sub 17 - 스크립트 및 워크플로우 분리 (2026-06-03)]
- k_fear_greed_index.py: KOSPI 전체 전용으로 단순화, K100 관련 코드 완전 제거
- k_fear_greed_k100.py: KOSPI100 전용 신규 파일, 공통 함수 import 방식
  - get_kospi100_index_close(): 네이버 모바일/PC/Stooq 순차 시도 구조 유지
  - get_kospi100_tickers(): FDR 시총 상위 100개
  - calc_k100_fear_greed_index(): K100 전용 산출 함수
- 워크플로우 3개로 분리
  - update.yml: 매일 스케줄 자동실행 (K + K100, K100은 continue-on-error)
  - update_k.yml: 수동 전용, K지수만 (timeout 30분)
  - update_k100.yml: 수동 전용, K100지수만 (timeout 30분)
- 이후 K지수/K100지수 개선 작업은 세션 분리하여 별도 진행

[Sub 16 - KOSPI100 지수 API 대안 탐색 및 보류 (2026-06-03)]
- 네이버 모바일 API(m.stock.naver.com): 3년/2년/90일 청크 모두 409 → GitHub Actions IP 차단 추정
- 네이버 PC API(api.stock.naver.com/index/KOSPI100/basicIndicesByTradedAt): 404 엔드포인트 없음
- Stooq(FDR): ^ksp100, KSP100.PL, KS100.WA 모두 실패
- FDR 직접 조회: KQ11은 KOSDAQ 지수, KOSPI100 심볼 미지원
- **결론**: 무료 공개 API로 KOSPI100 지수 시계열 수집 불가 → 탭 보류
- KOSPI100 탭 버튼 display:none 처리, 코드는 graceful fallback 유지

[Sub 15 - 풋/콜 비율 개선 및 KOSPI100 API 수정 (2026-06-03)]
- 풋/콜 비율 지수 산출 완전 배제 (pcr_raw_data.csv ≥20행 존재 시에만 활성화)
  - has_pcr 조건 강화: KRX_AUTH_KEY + 캐시파일 존재 + 유효 데이터 ≥20일
  - 캐시 미존재(첫 실행) → API 호출 없이 즉시 건너뜀 → 실행시간 ~15분 단축
  - 조기 중단 안전장치: 연속 빈 응답 10회 시 ThreadPoolExecutor 중단
- KOSPI100 네이버 API 409 수정: 3년 단일 요청 → 1년 단위 청크 분할 요청 + 중복 제거
- index.html PCR 동적 표시
  - hasPCR = CSV에 풋콜_비율 유효값 존재 여부로 자동 판단
  - PCR 없음: 인자바 숨김, 테이블 풋/콜 컬럼 숨김(.hide-pcr), 설명 카드 취소선 표시
  - PCR 있음: 자동으로 모든 UI 표시, 설명 카드 취소선 해제
- 하단 경고 배너 제거 (desc-card excluded로 대체)

[Sub 14 - 워크플로우 버그 수정 및 실행시간 분석 (2026-06-03)]
- GitHub → 로컬 동기화 (git pull): Sub 8~13 모바일 작업 반영 (6개 파일, +962줄)
- 워크플로우 버그 수정 2건
  1. `UnboundLocalError: cache_series` — `pcr_cache`가 비어있을 때 if 블록 밖 print가 미할당 변수 참조
     → print를 `if pcr_cache:` 블록 안으로 이동, else 절 추가
  2. `git add` 실패 (exit 128) — `k_fear_greed_result_k100.csv`, `pcr_raw_data.csv` 미생성 시 pathspec 오류
     → for 루프로 파일 존재 여부 확인 후 조건부 add
- 실행시간 분석: 현재 ~25분 소요 (원래 K지수만 있을 때는 ~10분)
  - K지수 전 종목(~948개) pykrx 수집: ~10분 (변화 없음)
  - 풋/콜 비율 KRX OpenAPI 날짜 순회: ~15분 (주범 — 데이터 0건임에도 시간 소요)
  - K100지수: ~1분 (캐시 재사용, 추가 부담 미미)
- **다음 과제**: 풋/콜 비율 수집에 최대 시간 제한 또는 skip 로직 추가 → 실행시간 단축 검토
- 로컬-GitHub 동기화 가이드 확정: Claude Code 세션 시작 시 `git pull origin main` 실행

[Sub 18 - PCR 수집 안정화 및 코드 정비 (2026-06-07)]
- PCR 수집 정상화: 캐시 391일 확보 (2024-10-24~2026-06-04), 7인자 활성화 기간 2025-11-06~현재 (140행+)
  - 초기 6인자 구간(2024-12-17~2025-11-05, 213행): pcr_raw는 있으나 정규화 윈도우(252거래일) 미달로 점수 미산출 — 정상 동작
- 버그 수정 3건
  1. 공휴일 데이터 CSV 포함: ECOS API가 공휴일에도 채권 금리 반환 → FDR KOSPI 거래일 인덱스로 필터링
  2. PCR abort 후 API 계속 호출: `with ThreadPoolExecutor` → `executor.shutdown(cancel_futures=True)` 로 미실행 future 즉시 취소
  3. PCR 캐시 이전 날짜 재시도: `missing = all_dates not in cache` → `last_cached 이후만` 으로 변경 (33일→3일)
- PCR 수집 대상: `pd.bdate_range` → KOSPI FDR 실제 거래일 기준 (공휴일 API 낭비 방지)
- GitHub Actions: `checkout@v4→v5`, `setup-python@v5→v6` 업그레이드 (Node.js 20 deprecated, 6/16 강제 전환 전 대응)
- 휴장일 조기 종료 추가: 기준일이 FDR KOSPI 거래일 인덱스에 없으면 즉시 exit(0) — 수동 실행 시 공휴일 KRX 서버 오류 방지
