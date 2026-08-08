# 썬데이 메이플 알림 봇

메이플스토리 [썬데이 메이플](https://maplestory.nexon.com/News/Event) 이벤트 공지가 올라오면
디스코드 채널로 제목·링크·기간·본문 이미지를 보내준다.

GitHub Actions cron이 30분마다 한 번 돌기 때문에 서버가 필요 없다.

## 설정

### 1. 넥슨 오픈 API 키 발급

[openapi.nexon.com](https://openapi.nexon.com) 로그인 → 애플리케이션 등록(메이플스토리/한국) → API 키 복사

### 2. 디스코드 웹훅 생성

알림받을 채널 → 채널 편집 → 연동 → 웹후크 → 새 웹후크 → URL 복사

### 3. GitHub Secrets 등록

리포 Settings → Secrets and variables → Actions 에 두 개를 넣는다.

| 이름 | 값 |
|---|---|
| `NEXON_API_KEY` | 1번에서 받은 키 |
| `DISCORD_WEBHOOK_URL` | 2번에서 받은 URL |

### 4. 최초 1회 초기화

이 단계를 건너뛰면 과거 썬데이 공지가 한꺼번에 발송된다. 이 리포지토리에서는 이미 한 번
실행되어 `state/seen.json`이 커밋되어 있으므로 다시 할 필요는 없다. 아래는 참고용 절차다
(다시 실행해도 해는 없지만 불필요하다).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
$env:NEXON_API_KEY = "발급받은키"
.venv/Scripts/python -m maple_sunday_bot.main --bootstrap
git add state/seen.json && git commit -m "chore: 초기 상태 기록" && git push
```

## 운영

- 리포는 **public**을 권장한다. private이면 Actions 무료 사용량(월 2000분)에 30분 주기가 근접하므로,
  `.github/workflows/check.yml`의 cron을 `0 * * * *`(1시간)로 바꾼다.
- 바로 확인하고 싶으면 Actions 탭 → "썬데이 메이플 공지 확인" → Run workflow.
- 공지 게시부터 알림까지 최대 1시간 정도 걸릴 수 있다. GitHub cron이 혼잡 시 지연되기 때문이다.
- 알림을 두 번 받았다면 전송 성공 후 상태 커밋이 실패한 경우다. 드물고, 다음 회차부터 정상이다.

## 테스트

```bash
.venv/Scripts/python -m pytest -v
```

네트워크를 타지 않는다. `tests/fixtures/`에 저장된 실제 API 응답 샘플을 쓴다.

## 구조

| 파일 | 책임 |
|---|---|
| `notice.py` | 공지 모델, 썬데이 판별, 이미지 추출 (네트워크 없음) |
| `state.py` | 발송 이력 읽기/쓰기 (네트워크 없음) |
| `nexon.py` | 넥슨 오픈 API 호출과 재시도 |
| `webhook.py` | 디스코드 메시지 조립과 전송 |
| `main.py` | 위 넷을 조립하는 진입점 |
