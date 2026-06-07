## 이 프로젝트에 대해
cnn탐욕공포지수를 KOSPI에 적용시킨 K-탐욕공포지수 개발, 시각화

## 행동 규칙
- 새 대화 시작 시 project_context.md 먼저 확인할 것
- 중요한 결정이 나오면 context 파일 업데이트 내용을 제안할 것
- Sub 대화 결론이 나오면 2~3줄 요약을 만들어줄 것
- 불확실한 부분은 추측하지 말고 물어볼 것

## 페이지 개발 규칙
- 새로운 페이지 개발 시 테스트 페이지(예: `index_test.html`)를 먼저 생성하여 개발할 것
- 개발 완료 후 최종 확인이 끝나면 그때 `index.html`(최종 페이지)에 반영할 것
- 테스트 페이지 커밋/푸시 후 GitHub Pages URL을 생성하여 직접 확인할 수 있도록 제공할 것
  - URL 형식: `https://hhhpophhh-dot.github.io/k-fear-greed-index/<테스트파일명>.html`

## 하지 말아야 할 것
- 이미 결정된 사항을 다시 질문하지 말 것
- 불필요하게 길게 답변하지 말 것

## API 연동 시 필수 확인사항
- 외부 API 필드명은 절대 추측하지 말 것. 구현 전에 반드시 API 명세서(응답 필드 목록)나 실제 샘플 응답을 받아볼 것
- KRX Open API 실제 응답 필드는 camelCase가 아닌 UPPERCASE_UNDERSCORE 형식임 (예: `ACC_TRDVOL`, `RGHT_TP_NM`, `PROD_NM`)
- pykrx 라이브러리 예제와 실제 KRX Open API 응답 필드명이 다를 수 있음 — 라이브러리 소스 기반으로 가정하지 말 것
- 새 API 엔드포인트 연동 시: "이 API의 응답 필드 명세서나 샘플 응답이 있으면 먼저 공유해 주세요" 라고 요청할 것
