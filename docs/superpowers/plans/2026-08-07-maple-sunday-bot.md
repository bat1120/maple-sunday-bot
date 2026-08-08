# 썬데이 메이플 알림 봇 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 메이플스토리 썬데이 메이플 이벤트 공지가 올라오면 디스코드 채널에 제목·링크·기간·본문 이미지 전체를 자동으로 보낸다.

**Architecture:** 상주 프로세스 없이 GitHub Actions cron이 30분마다 파이썬 스크립트를 1회 실행한다. 넥슨 오픈 API로 이벤트 공지 목록을 받아 "썬데이"가 든 제목만 골라내고, 이미 보낸 공지는 리포에 커밋되는 `state/seen.json`으로 걸러낸다. 새 공지는 상세 본문 HTML에서 이미지 URL을 뽑아 디스코드 웹훅 임베드로 보낸다.

**Tech Stack:** Python 3.10+, `requests`, `pytest`, GitHub Actions, Discord Webhook, NEXON Open API

## Global Constraints

- Python `>=3.10` (`X | None` 타입 문법 사용). GitHub Actions 러너는 3.12.
- 런타임 의존성은 `requests>=2.31` **하나뿐**. 개발 의존성은 `pytest>=8.0` 하나뿐.
- **테스트는 네트워크를 타지 않는다.** HTTP를 쓰는 모듈은 `session` 객체를 주입받고, 테스트는 가짜 session을 넣는다. `responses`/`requests-mock` 같은 라이브러리를 새로 추가하지 않는다.
- 소스 레이아웃은 `src/maple_sunday_bot/`. 패키지 내부 import는 절대 경로(`from maple_sunday_bot.notice import ...`)를 쓴다.
- 시크릿/환경변수 이름은 정확히 `NEXON_API_KEY`, `DISCORD_WEBHOOK_URL`.
- 넥슨 API Base URL: `https://open.api.nexon.com`, 인증 헤더 이름: `x-nxopen-api-key`.
- `state/seen.json`은 최근 **100건**만 유지한다 (`MAX_SEEN = 100`).
- 디스코드 메시지 하나에 임베드는 최대 **10개** (`MAX_EMBEDS_PER_MESSAGE = 10`).
- 임베드 색상은 주황색 `0xFF8C00` (`EMBED_COLOR`).
- 리포지토리는 **public**, cron은 **30분 주기**(`*/30 * * * *`).
- 커밋 메시지는 한국어, Conventional Commits 접두사(`feat:`, `test:`, `chore:`, `docs:`) 사용.
- 모듈 이름을 `discord.py`로 짓지 않는다 (실제 `discord` 라이브러리와 헷갈린다). 웹훅 모듈 이름은 `webhook.py`.

---

## 사전 준비 (사람이 직접 하는 일)

Task 1~3은 준비 없이 바로 진행할 수 있다. **Task 4 시작 전**에 A가, **Task 6 검증 전**에 B가 필요하다.

**A. 넥슨 오픈 API 키 발급** (Task 4 전에 필요)
1. https://openapi.nexon.com 접속 → 넥슨 계정으로 로그인
2. 상단 "API KEY 발급" 또는 콘솔 → 애플리케이션 등록 (게임: 메이플스토리 / 지역: 한국)
3. 발급된 키를 로컬 환경변수로 설정
   - PowerShell: `$env:NEXON_API_KEY = "발급받은키"`
4. 나중에 GitHub 리포 → Settings → Secrets and variables → Actions → New repository secret 에 `NEXON_API_KEY`로 등록

**B. 디스코드 웹훅 생성** (Task 6 실제 발송 검증 전에 필요)
1. 알림받을 채널 → 채널 편집 → 연동 → 웹후크 → 새 웹후크
2. URL 복사
3. 로컬 환경변수: `$env:DISCORD_WEBHOOK_URL = "복사한URL"`
4. GitHub Secrets에 `DISCORD_WEBHOOK_URL`로 등록

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `pyproject.toml` | 패키지 메타데이터, 의존성, pytest 설정 |
| `src/maple_sunday_bot/__init__.py` | 빈 파일 (패키지 표시) |
| `src/maple_sunday_bot/notice.py` | `Notice` 데이터 모델, 썬데이 판별, 본문 이미지 추출, 기간 문자열 포맷. **네트워크 없음** |
| `src/maple_sunday_bot/state.py` | `seen.json` 읽기/쓰기, 100건 절삭. **네트워크 없음** |
| `src/maple_sunday_bot/nexon.py` | 넥슨 오픈 API 호출, 재시도, 응답 → `Notice` 변환 |
| `src/maple_sunday_bot/webhook.py` | `Notice` + 이미지 → 디스코드 메시지 페이로드 조립, 전송 |
| `src/maple_sunday_bot/main.py` | 위 넷을 조립하는 진입점, CLI 플래그, 환경변수 읽기 |
| `scripts/fetch_fixtures.py` | 실제 API 응답을 fixture로 1회 저장하는 개발용 스크립트 |
| `tests/fixtures/*.json`, `*.html` | 실제 API 응답 샘플 |
| `tests/test_*.py` | 모듈별 단위 테스트 + `main` 통합 테스트 |
| `.github/workflows/check.yml` | 30분 cron + 수동 실행, 상태 파일 자동 커밋 |
| `README.md` | 설치·설정·운영 방법 |

`notice.py`와 `state.py`는 순수 로직이라 가짜 데이터만으로 완전히 테스트된다. HTTP는 `nexon.py`와 `webhook.py` 두 곳에만 있고, 둘 다 `session`을 주입받아 테스트에서 가짜로 바꿔치기한다.

---

### Task 1: 프로젝트 스캐폴딩 + 썬데이 판별

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/maple_sunday_bot/__init__.py`
- Create: `src/maple_sunday_bot/notice.py`
- Test: `tests/test_notice.py`

**Interfaces:**
- Consumes: 없음 (첫 번째 태스크)
- Produces:
  - `maple_sunday_bot.notice.Notice` — frozen dataclass. 필드: `notice_id: int`, `title: str`, `url: str`, `date: str`, `date_event_start: str | None`, `date_event_end: str | None`
  - `maple_sunday_bot.notice.is_sunday(title: str) -> bool`

- [ ] **Step 1: 프로젝트 뼈대 파일 생성**

`pyproject.toml`:

```toml
[project]
name = "maple-sunday-bot"
version = "0.1.0"
description = "메이플스토리 썬데이 메이플 공지를 디스코드로 알려주는 봇"
requires-python = ">=3.10"
dependencies = ["requests>=2.31"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.venv/
venv/
.env
```

`src/maple_sunday_bot/__init__.py` 는 빈 파일로 생성한다.

- [ ] **Step 2: 가상환경 만들고 설치**

Run:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -e ".[dev]"
```

Expected: `Successfully installed maple-sunday-bot-0.1.0 ...` 로 끝난다.

이후 모든 명령은 `.venv/Scripts/python`을 쓴다.

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_notice.py`:

```python
import pytest

from maple_sunday_bot.notice import Notice, is_sunday


@pytest.mark.parametrize(
    "title",
    [
        "썬데이 메이플",
        "스페셜 썬데이 메이플",
        "썬데이메이플",
        "[안내] 8월 9일 썬데이 메이플 안내",
        "  스페셜  썬데이   메이플  ",
    ],
)
def test_썬데이_공지_제목을_통과시킨다(title):
    assert is_sunday(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "메이플 히어로즈 이벤트",
        "썬데이 이벤트",  # '메이플'이 안 붙으면 다른 이벤트다
        "몬스터파크 메이플 이벤트",
        "",
    ],
)
def test_썬데이_공지가_아닌_제목은_거른다(title):
    assert is_sunday(title) is False


def test_Notice는_이벤트_기간이_없어도_만들_수_있다():
    notice = Notice(
        notice_id=1356,
        title="스페셜 썬데이 메이플",
        url="https://maplestory.nexon.com/News/Event/1356",
        date="2026-08-07T10:00+09:00",
        date_event_start=None,
        date_event_end=None,
    )
    assert notice.notice_id == 1356
```

- [ ] **Step 4: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_notice.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'maple_sunday_bot.notice'`

- [ ] **Step 5: 최소 구현 작성**

`src/maple_sunday_bot/notice.py`:

```python
"""공지 데이터 모델과 순수 파싱 로직. 네트워크를 타지 않는다."""

from __future__ import annotations

import re
from dataclasses import dataclass

# 제목 표기가 "썬데이 메이플" / "스페셜 썬데이 메이플" / "썬데이메이플" 로 갈려서
# 공백을 모두 지운 뒤 부분 문자열로 확인한다.
_SUNDAY_KEYWORD = "썬데이메이플"


@dataclass(frozen=True)
class Notice:
    """이벤트 공지 하나."""

    notice_id: int
    title: str
    url: str
    date: str
    date_event_start: str | None
    date_event_end: str | None


def is_sunday(title: str) -> bool:
    """제목이 썬데이 메이플 공지인지 판별한다."""
    return _SUNDAY_KEYWORD in re.sub(r"\s+", "", title)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_notice.py -v`

Expected: PASS — 10 passed

- [ ] **Step 7: 커밋**

```bash
git add pyproject.toml .gitignore src/ tests/
git commit -m "feat: 프로젝트 뼈대와 썬데이 공지 판별 로직 추가"
```

---

### Task 2: 본문 이미지 추출과 이벤트 기간 포맷

**Files:**
- Modify: `src/maple_sunday_bot/notice.py`
- Modify: `tests/test_notice.py`

**Interfaces:**
- Consumes: `maple_sunday_bot.notice.Notice` (Task 1)
- Produces:
  - `maple_sunday_bot.notice.extract_images(html: str) -> list[str]` — 본문 HTML에서 이미지 URL을 등장 순서대로, 중복 제거해서 반환. `//host/...`는 `https://host/...`로 정규화. `http`/`https`가 아닌 것(`data:` 등)은 버린다.
  - `maple_sunday_bot.notice.event_period(notice: Notice) -> str` — `"2026.08.09 ~ 2026.08.09"`. 시작/종료 중 하나라도 없으면 `""`.

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_notice.py` 파일 **끝에** 아래를 붙인다. 상단 import 줄도 함께 고친다:

```python
from maple_sunday_bot.notice import Notice, event_period, extract_images, is_sunday
```

```python
def test_본문에서_이미지_URL을_순서대로_뽑는다():
    html = """
    <div class="contents">
      <p>안내드립니다.</p>
      <img src="https://file.nexon.com/NxFile/download/FileDownloader.aspx?oidFile=AAA" />
      <img src='https://file.nexon.com/NxFile/download/FileDownloader.aspx?oidFile=BBB'>
    </div>
    """
    assert extract_images(html) == [
        "https://file.nexon.com/NxFile/download/FileDownloader.aspx?oidFile=AAA",
        "https://file.nexon.com/NxFile/download/FileDownloader.aspx?oidFile=BBB",
    ]


def test_같은_이미지가_두_번_나오면_한_번만_남긴다():
    html = '<img src="https://a.com/1.png"><img src="https://a.com/1.png">'
    assert extract_images(html) == ["https://a.com/1.png"]


def test_프로토콜_생략된_주소는_https로_바꾼다():
    html = '<img src="//file.nexon.com/x.png">'
    assert extract_images(html) == ["https://file.nexon.com/x.png"]


def test_http가_아닌_이미지는_버린다():
    html = '<img src="data:image/png;base64,AAAA"><img src="/local/x.png">'
    assert extract_images(html) == []


def test_이미지가_없으면_빈_리스트다():
    assert extract_images("<p>텍스트만 있습니다</p>") == []
    assert extract_images("") == []


def _notice(start, end):
    return Notice(
        notice_id=1,
        title="썬데이 메이플",
        url="https://example.com/1",
        date="2026-08-07T10:00+09:00",
        date_event_start=start,
        date_event_end=end,
    )


def test_이벤트_기간을_사람이_읽는_형태로_만든다():
    notice = _notice("2026-08-09T00:00+09:00", "2026-08-09T23:59+09:00")
    assert event_period(notice) == "2026.08.09 ~ 2026.08.09"


def test_기간_정보가_없으면_빈_문자열이다():
    assert event_period(_notice(None, None)) == ""
    assert event_period(_notice("2026-08-09T00:00+09:00", None)) == ""
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_notice.py -v`

Expected: FAIL — `ImportError: cannot import name 'event_period' from 'maple_sunday_bot.notice'`

- [ ] **Step 3: 구현 추가**

`src/maple_sunday_bot/notice.py` 파일 끝에 추가한다:

```python
_IMG_SRC = re.compile(r"""<img[^>]+?src\s*=\s*["']([^"']+)["']""", re.IGNORECASE)


def extract_images(html: str) -> list[str]:
    """본문 HTML에서 이미지 URL을 등장 순서대로, 중복 없이 뽑는다."""
    urls: list[str] = []
    for raw in _IMG_SRC.findall(html or ""):
        url = raw.strip()
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith(("http://", "https://")):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def _to_date(value: str) -> str:
    """'2026-08-09T00:00+09:00' -> '2026.08.09'. 넥슨 응답은 항상 ISO8601이라 앞 10자만 쓴다."""
    return value[:10].replace("-", ".")


def event_period(notice: Notice) -> str:
    """디스코드에 보여줄 이벤트 기간 문자열. 정보가 불완전하면 빈 문자열."""
    if not notice.date_event_start or not notice.date_event_end:
        return ""
    return f"{_to_date(notice.date_event_start)} ~ {_to_date(notice.date_event_end)}"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_notice.py -v`

Expected: PASS — 17 passed

- [ ] **Step 5: 커밋**

```bash
git add src/maple_sunday_bot/notice.py tests/test_notice.py
git commit -m "feat: 본문 이미지 추출과 이벤트 기간 포맷 추가"
```

---

### Task 3: 발송 이력 저장

**Files:**
- Create: `src/maple_sunday_bot/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `maple_sunday_bot.state.MAX_SEEN` — `int`, 값 `100`
  - `maple_sunday_bot.state.load_seen(path: Path) -> list[int]` — 파일이 없거나 깨졌으면 `[]`
  - `maple_sunday_bot.state.save_seen(path: Path, seen: list[int]) -> None` — 앞에서부터 `MAX_SEEN`개만 저장. 부모 디렉터리가 없으면 만든다.
  - 리스트 순서 규약: **최신이 앞(index 0)**

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_state.py`:

```python
import json

from maple_sunday_bot.state import MAX_SEEN, load_seen, save_seen


def test_파일이_없으면_빈_목록이다(tmp_path):
    assert load_seen(tmp_path / "없는파일.json") == []


def test_저장한_것을_그대로_읽어온다(tmp_path):
    path = tmp_path / "state" / "seen.json"
    save_seen(path, [1356, 1352, 1350])
    assert load_seen(path) == [1356, 1352, 1350]


def test_부모_디렉터리가_없어도_만들어_저장한다(tmp_path):
    path = tmp_path / "a" / "b" / "seen.json"
    save_seen(path, [1])
    assert path.exists()


def test_최대_개수를_넘으면_앞에서부터_잘라_저장한다(tmp_path):
    path = tmp_path / "seen.json"
    save_seen(path, list(range(MAX_SEEN + 50)))
    saved = load_seen(path)
    assert len(saved) == MAX_SEEN
    assert saved[0] == 0  # 최신이 앞이므로 앞쪽이 살아남는다


def test_파일이_깨져_있으면_빈_목록으로_취급한다(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{ 이건 JSON이 아님", encoding="utf-8")
    assert load_seen(path) == []


def test_사람이_읽을_수_있는_JSON으로_저장한다(tmp_path):
    path = tmp_path / "seen.json"
    save_seen(path, [1356])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"seen": [1356]}
    assert path.read_text(encoding="utf-8").endswith("\n")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_state.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'maple_sunday_bot.state'`

- [ ] **Step 3: 구현 작성**

`src/maple_sunday_bot/state.py`:

```python
"""이미 알림을 보낸 공지 ID를 파일에 기록한다. 목록은 최신이 앞에 온다."""

from __future__ import annotations

import json
from pathlib import Path

MAX_SEEN = 100


def load_seen(path: Path) -> list[int]:
    """기록된 notice_id 목록을 읽는다. 파일이 없거나 깨졌으면 빈 목록."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    seen = data.get("seen") if isinstance(data, dict) else None
    if not isinstance(seen, list):
        return []
    return [item for item in seen if isinstance(item, int)]
```

> **Superseded (commit `522f637`):** 실제 구현은 `except (OSError, json.JSONDecodeError)`가 아니라
> `except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError)`를 쓴다 — `OSError`를 그대로
> 두면 "읽을 수 없는 경로"(권한 오류 등 진짜 I/O 실패) 같은 것도 조용히 빈 목록으로 삼켜버리기 때문이다.
> 이 계획 코드로 되돌리지 말 것.

```python


def save_seen(path: Path, seen: list[int]) -> None:
    """최신 MAX_SEEN개만 남겨 저장한다. 깃 diff가 보기 좋도록 들여쓰기와 끝 개행을 넣는다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"seen": seen[:MAX_SEEN]}, ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_state.py -v`

Expected: PASS — 6 passed

- [ ] **Step 5: 커밋**

```bash
git add src/maple_sunday_bot/state.py tests/test_state.py
git commit -m "feat: 발송 이력 저장 모듈 추가"
```

---

### Task 4: 넥슨 오픈 API 클라이언트

**사전 준비 A(넥슨 API 키 발급)가 끝나 있어야 한다.**

**Files:**
- Create: `scripts/fetch_fixtures.py`
- Create: `tests/fixtures/notice_event_list.json`
- Create: `tests/fixtures/notice_event_detail.json`
- Create: `src/maple_sunday_bot/nexon.py`
- Test: `tests/test_nexon.py`

**Interfaces:**
- Consumes: `maple_sunday_bot.notice.Notice` (Task 1)
- Produces:
  - `maple_sunday_bot.nexon.NexonApiError(Exception)`
  - `maple_sunday_bot.nexon.NexonClient(api_key: str, session=None, sleep=time.sleep)`
    - `.get_event_notices() -> list[Notice]`
    - `.get_event_notice_detail(notice_id: int) -> str` — 본문 HTML 문자열
  - `session`은 `.get(url, headers=..., params=..., timeout=...)`를 갖고, 반환 객체는 `.status_code`와 `.json()`을 갖는다.

- [ ] **Step 1: 실제 응답을 fixture로 저장하는 스크립트 작성**

`scripts/fetch_fixtures.py`:

```python
"""실제 넥슨 API 응답을 tests/fixtures/ 에 저장한다. 개발 중 한 번만 실행하면 된다.

사용법:
    $env:NEXON_API_KEY = "..."
    .venv/Scripts/python scripts/fetch_fixtures.py
"""

import json
import os
import sys
from pathlib import Path

import requests

BASE_URL = "https://open.api.nexon.com"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def fetch(path: str, params: dict | None = None) -> dict:
    response = requests.get(
        BASE_URL + path,
        headers={"x-nxopen-api-key": os.environ["NEXON_API_KEY"]},
        params=params or {},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    if "NEXON_API_KEY" not in os.environ:
        print("NEXON_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    FIXTURES.mkdir(parents=True, exist_ok=True)

    listing = fetch("/maplestory/v1/notice-event")
    (FIXTURES / "notice_event_list.json").write_text(
        json.dumps(listing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("목록 응답 최상위 키:", list(listing.keys()))

    items = next(v for v in listing.values() if isinstance(v, list))
    print("목록 항목 키:", list(items[0].keys()))

    notice_id = items[0][next(k for k in items[0] if "id" in k.lower())]
    detail = fetch("/maplestory/v1/notice-event/detail", {"notice_id": notice_id})
    (FIXTURES / "notice_event_detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("상세 응답 키:", list(detail.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 스크립트를 실행해 실제 필드명 확인**

Run:
```bash
.venv/Scripts/python scripts/fetch_fixtures.py
```

Expected: `tests/fixtures/notice_event_list.json`과 `notice_event_detail.json`이 생기고, 콘솔에 키 목록이 찍힌다.

**여기서 계획과 실제 필드명이 다를 수 있다.** 이 계획은 아래 이름을 가정한다:

| 위치 | 가정한 이름 |
|---|---|
| 목록 응답 최상위 | `event_notice` (리스트) |
| 목록 항목 | `title`, `url`, `notice_id`, `date`, `date_event_start`, `date_event_end` |
| 상세 응답 | `title`, `url`, `contents`, `date` |

콘솔 출력이 다르면 **Step 5의 `nexon.py` 안 키 문자열만** 실제 값으로 바꾼다. 구조·함수 시그니처·테스트 흐름은 그대로 둔다. `date_event_start`/`date_event_end`가 아예 없는 경우엔 `_to_notice`에서 `.get()`이 `None`을 반환하므로 코드 수정 없이 동작한다.

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_nexon.py`:

```python
import json
from pathlib import Path

import pytest

from maple_sunday_bot.nexon import NexonApiError, NexonClient

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class FakeSession:
    """미리 정해둔 응답을 순서대로 돌려주고, 호출 내역을 기록한다."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "params": params})
        return self._responses.pop(0)


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _client(responses, sleeps=None):
    session = FakeSession(responses)
    slept = sleeps if sleeps is not None else []
    return NexonClient("테스트키", session=session, sleep=slept.append), session


def test_이벤트_공지_목록을_Notice로_바꾼다():
    client, session = _client([FakeResponse(200, _load("notice_event_list.json"))])

    notices = client.get_event_notices()

    assert len(notices) > 0
    first = notices[0]
    assert isinstance(first.notice_id, int)
    assert first.title
    assert first.url.startswith("http")


def test_API_키를_헤더에_넣는다():
    client, session = _client([FakeResponse(200, _load("notice_event_list.json"))])

    client.get_event_notices()

    assert session.calls[0]["headers"]["x-nxopen-api-key"] == "테스트키"


def test_상세_조회는_본문_HTML을_돌려준다():
    client, session = _client([FakeResponse(200, _load("notice_event_detail.json"))])

    html = client.get_event_notice_detail(1356)

    assert isinstance(html, str)
    assert session.calls[0]["params"]["notice_id"] == 1356


def test_429가_오면_기다렸다_다시_시도한다():
    slept = []
    client, session = _client(
        [
            FakeResponse(429),
            FakeResponse(200, _load("notice_event_list.json")),
        ],
        sleeps=slept,
    )

    notices = client.get_event_notices()

    assert len(notices) > 0
    assert len(session.calls) == 2
    assert slept == [1.0]


def test_서버_오류가_계속되면_세_번_시도하고_포기한다():
    slept = []
    client, session = _client([FakeResponse(500) for _ in range(3)], sleeps=slept)

    with pytest.raises(NexonApiError) as excinfo:
        client.get_event_notices()

    assert len(session.calls) == 3
    assert slept == [1.0, 2.0]
    assert "500" in str(excinfo.value)


def test_400은_재시도하지_않고_바로_실패한다():
    client, session = _client([FakeResponse(400)])

    with pytest.raises(NexonApiError):
        client.get_event_notices()

    assert len(session.calls) == 1
```

- [ ] **Step 4: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_nexon.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'maple_sunday_bot.nexon'`

- [ ] **Step 5: 구현 작성**

`src/maple_sunday_bot/nexon.py`:

```python
"""넥슨 오픈 API 클라이언트. HTTP 경계를 이 파일 안에만 둔다."""

from __future__ import annotations

import time
from typing import Any

import requests

from maple_sunday_bot.notice import Notice

BASE_URL = "https://open.api.nexon.com"
API_KEY_HEADER = "x-nxopen-api-key"
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
RETRY_STATUS = {429, 500, 502, 503, 504}


class NexonApiError(Exception):
    """넥슨 API 호출이 최종적으로 실패했을 때."""


class NexonClient:
    def __init__(self, api_key: str, session=None, sleep=time.sleep):
        self._api_key = api_key
        self._session = session if session is not None else requests.Session()
        self._sleep = sleep

    def get_event_notices(self) -> list[Notice]:
        """이벤트 공지 목록을 최신순으로 가져온다."""
        data = self._get("/maplestory/v1/notice-event")
        items = data.get("event_notice") or []
        return [_to_notice(item) for item in items]

    def get_event_notice_detail(self, notice_id: int) -> str:
        """공지 본문 HTML을 가져온다. 본문이 비어 있으면 빈 문자열."""
        data = self._get(
            "/maplestory/v1/notice-event/detail", {"notice_id": notice_id}
        )
        return data.get("contents") or ""

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """재시도를 포함한 GET. 지수 백오프로 1초, 2초 쉰다."""
        url = BASE_URL + path
        headers = {API_KEY_HEADER: self._api_key}
        last_error = ""

        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._session.get(
                    url, headers=headers, params=params or {}, timeout=TIMEOUT_SECONDS
                )
            except requests.RequestException as exc:
                last_error = f"요청 실패: {exc}"
            else:
                if response.status_code == 200:
                    return response.json()
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUS:
                    break

            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(2.0**attempt)

        raise NexonApiError(f"{url} 호출 실패 — {last_error}")
```

> **Superseded (commit `f79500b`):** 실제 `_get`는 `try`/`except requests.RequestException` 바로 뒤에 있는
> `else` 블록에서 상태 코드를 검사하지 않는다 — `except`에 `ValueError`도 함께 잡고, 상태 코드 200인데
> `response.json()`이 파싱에 실패하는 경우도 같은 재시도 경로를 타도록 `try` 블록 안에서
> `response.status_code == 200`이면 바로 `return response.json()`한다. 위 코드처럼 `else`에서만
> 상태 코드를 보면 "200인데 JSON이 깨짐" 케이스가 재시도되지 않고 그대로 예외가 터진다.
>
> **Superseded (최종 리뷰 수정, finding 3):** `get_event_notices`는 `[_to_notice(item) for item in items]`로
> 전체를 한 번에 매핑하지 않는다 — 항목 하나가 깨져도(`KeyError`/`TypeError`/`ValueError`) 전체 목록을
> 포기하면 안 되므로, 반복문에서 항목별로 `try/except`로 감싸 건너뛰고 stderr에 남긴다. `_to_notice`도
> `item.get("title", "")`가 아니라 `item.get("title") or ""`처럼 `None` 값을 방어한다. 이 계획 코드로
> 되돌리지 말 것.

```python
def _to_notice(item: dict[str, Any]) -> Notice:
    return Notice(
        notice_id=int(item["notice_id"]),
        title=item.get("title", ""),
        url=item.get("url", ""),
        date=item.get("date", ""),
        date_event_start=item.get("date_event_start"),
        date_event_end=item.get("date_event_end"),
    )
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_nexon.py -v`

Expected: PASS — 6 passed

fixture의 실제 키 이름이 달랐다면 `_to_notice`와 `get_event_notices`/`get_event_notice_detail`의 키 문자열을 고친 뒤 다시 돌린다.

- [ ] **Step 7: 전체 테스트 확인 후 커밋**

Run: `.venv/Scripts/python -m pytest -v`

Expected: PASS — 29 passed

```bash
git add scripts/ tests/fixtures/ src/maple_sunday_bot/nexon.py tests/test_nexon.py
git commit -m "feat: 넥슨 오픈 API 클라이언트와 재시도 로직 추가"
```

---

### Task 5: 디스코드 웹훅 전송

**Files:**
- Create: `src/maple_sunday_bot/webhook.py`
- Test: `tests/test_webhook.py`

**Interfaces:**
- Consumes: `maple_sunday_bot.notice.Notice`, `maple_sunday_bot.notice.event_period` (Task 1, 2)
- Produces:
  - `maple_sunday_bot.webhook.MAX_EMBEDS_PER_MESSAGE` — `int`, 값 `10`
  - `maple_sunday_bot.webhook.EMBED_COLOR` — `int`, 값 `0xFF8C00`
  - `maple_sunday_bot.webhook.WebhookError(Exception)`
  - `maple_sunday_bot.webhook.build_messages(notice: Notice, images: list[str]) -> list[dict]`
  - `maple_sunday_bot.webhook.send(webhook_url: str, messages: list[dict], session=None) -> None`
  - `session`은 `.post(url, json=..., timeout=...)`를 갖고, 반환 객체는 `.status_code`를 갖는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_webhook.py`:

```python
import pytest

from maple_sunday_bot.notice import Notice
from maple_sunday_bot.webhook import (
    EMBED_COLOR,
    MAX_EMBEDS_PER_MESSAGE,
    WebhookError,
    build_messages,
    send,
)

NOTICE = Notice(
    notice_id=1356,
    title="스페셜 썬데이 메이플",
    url="https://maplestory.nexon.com/News/Event/1356",
    date="2026-08-07T10:00+09:00",
    date_event_start="2026-08-09T00:00+09:00",
    date_event_end="2026-08-09T23:59+09:00",
)


def _images(count):
    return [f"https://file.nexon.com/{i}.png" for i in range(count)]


def test_이미지가_없어도_제목과_링크는_보낸다():
    messages = build_messages(NOTICE, [])

    assert len(messages) == 1
    embeds = messages[0]["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["title"] == "스페셜 썬데이 메이플"
    assert embeds[0]["url"] == NOTICE.url
    assert embeds[0]["color"] == EMBED_COLOR
    assert "image" not in embeds[0]


def test_이벤트_기간을_설명에_넣는다():
    messages = build_messages(NOTICE, [])

    assert messages[0]["embeds"][0]["description"] == "2026.08.09 ~ 2026.08.09"


def test_기간_정보가_없으면_설명을_넣지_않는다():
    notice = Notice(
        notice_id=1,
        title="썬데이 메이플",
        url="https://example.com/1",
        date="2026-08-07T10:00+09:00",
        date_event_start=None,
        date_event_end=None,
    )

    assert "description" not in build_messages(notice, [])[0]["embeds"][0]


def test_이미지_한_장은_첫_임베드에_붙인다():
    messages = build_messages(NOTICE, _images(1))

    embeds = messages[0]["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["image"]["url"] == "https://file.nexon.com/0.png"


def test_이미지_여러_장은_임베드를_늘려_전부_보여준다():
    messages = build_messages(NOTICE, _images(3))

    embeds = messages[0]["embeds"]
    assert len(embeds) == 3
    assert [e["image"]["url"] for e in embeds] == _images(3)
    # 제목은 첫 임베드에만 있다
    assert "title" in embeds[0]
    assert "title" not in embeds[1]


def test_임베드가_열_개를_넘으면_메시지를_나눈다():
    messages = build_messages(NOTICE, _images(12))

    assert len(messages) == 2
    assert len(messages[0]["embeds"]) == MAX_EMBEDS_PER_MESSAGE
    assert len(messages[1]["embeds"]) == 2
    sent_images = [e["image"]["url"] for m in messages for e in m["embeds"]]
    assert sent_images == _images(12)


class FakeSession:
    def __init__(self, status_codes):
        self._status_codes = list(status_codes)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        outer = self

        class _Response:
            status_code = outer._status_codes.pop(0)

        return _Response()


def test_메시지를_순서대로_전부_POST한다():
    session = FakeSession([204, 204])

    send("https://discord.com/api/webhooks/x", build_messages(NOTICE, _images(12)), session)

    assert len(session.calls) == 2
    assert session.calls[0]["url"] == "https://discord.com/api/webhooks/x"


def test_전송이_실패하면_예외를_던진다():
    session = FakeSession([500])

    with pytest.raises(WebhookError) as excinfo:
        send("https://discord.com/api/webhooks/x", build_messages(NOTICE, []), session)

    assert "500" in str(excinfo.value)
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_webhook.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'maple_sunday_bot.webhook'`

- [ ] **Step 3: 구현 작성**

`src/maple_sunday_bot/webhook.py`:

```python
"""디스코드 웹훅 페이로드 조립과 전송.

디스코드 임베드는 하나당 이미지가 한 장만 보이므로, 이미지 개수만큼 임베드를 만든다.
한 메시지에 임베드는 10개까지라 넘치면 메시지를 나눈다.
"""

from __future__ import annotations

import requests

from maple_sunday_bot.notice import Notice, event_period

MAX_EMBEDS_PER_MESSAGE = 10
EMBED_COLOR = 0xFF8C00
TIMEOUT_SECONDS = 15
OK_STATUS = {200, 204}


class WebhookError(Exception):
    """디스코드 웹훅 전송이 실패했을 때."""


def build_messages(notice: Notice, images: list[str]) -> list[dict]:
    """공지 하나를 보내기 위한 웹훅 메시지 페이로드 목록을 만든다."""
    head: dict = {
        "title": notice.title,
        "url": notice.url,
        "color": EMBED_COLOR,
    }
    period = event_period(notice)
    if period:
        head["description"] = period
    if images:
        head["image"] = {"url": images[0]}

    embeds = [head] + [{"image": {"url": url}} for url in images[1:]]

    return [
        {"embeds": embeds[i : i + MAX_EMBEDS_PER_MESSAGE]}
        for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE)
    ]


def send(webhook_url: str, messages: list[dict], session=None) -> None:
    """메시지를 순서대로 전송한다. 하나라도 실패하면 WebhookError."""
    session = session if session is not None else requests.Session()

    for index, message in enumerate(messages, start=1):
        try:
            response = session.post(webhook_url, json=message, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            raise WebhookError(f"{index}번째 메시지 전송 실패: {exc}") from exc
        if response.status_code not in OK_STATUS:
            raise WebhookError(
                f"{index}번째 메시지 전송 실패: HTTP {response.status_code}"
            )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_webhook.py -v`

Expected: PASS — 8 passed

- [ ] **Step 5: 커밋**

```bash
git add src/maple_sunday_bot/webhook.py tests/test_webhook.py
git commit -m "feat: 디스코드 웹훅 메시지 조립과 전송 추가"
```

---

### Task 6: 진입점 조립과 bootstrap 모드

**Files:**
- Create: `src/maple_sunday_bot/main.py`
- Create: `state/seen.json`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: Task 1~5의 모든 공개 함수
- Produces:
  - `maple_sunday_bot.main.DEFAULT_STATE_PATH` — `Path("state/seen.json")`
  - `maple_sunday_bot.main.run(client, webhook_url, state_path, bootstrap=False, session=None) -> int` — 발송한 공지 수를 반환. `bootstrap=True`면 발송 없이 기록만 하고 `0`을 반환
  - `maple_sunday_bot.main.main(argv: list[str] | None = None) -> int` — 종료 코드

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_main.py`:

```python
import pytest

from maple_sunday_bot.main import run
from maple_sunday_bot.nexon import NexonApiError
from maple_sunday_bot.notice import Notice
from maple_sunday_bot.state import load_seen, save_seen
from maple_sunday_bot.webhook import WebhookError

WEBHOOK = "https://discord.com/api/webhooks/x"


def _notice(notice_id, title):
    return Notice(
        notice_id=notice_id,
        title=title,
        url=f"https://maplestory.nexon.com/News/Event/{notice_id}",
        date="2026-08-07T10:00+09:00",
        date_event_start="2026-08-09T00:00+09:00",
        date_event_end="2026-08-09T23:59+09:00",
    )


class FakeClient:
    def __init__(self, notices, details=None, detail_error=False):
        self._notices = notices
        self._details = details or {}
        self._detail_error = detail_error
        self.detail_calls = []

    def get_event_notices(self):
        return self._notices

    def get_event_notice_detail(self, notice_id):
        self.detail_calls.append(notice_id)
        if self._detail_error:
            raise NexonApiError("상세 조회 실패")
        return self._details.get(notice_id, "")


class FakeSession:
    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        outer = self

        class _Response:
            status_code = 500 if outer._fail else 204

        return _Response()


def test_새_썬데이_공지를_발송하고_기록한다(tmp_path):
    state_path = tmp_path / "seen.json"
    client = FakeClient(
        [_notice(1356, "스페셜 썬데이 메이플"), _notice(1355, "메이플 히어로즈")],
        details={1356: '<img src="https://file.nexon.com/a.png">'},
    )
    session = FakeSession()

    sent = run(client, WEBHOOK, state_path, session=session)

    assert sent == 1
    assert client.detail_calls == [1356]  # 썬데이가 아닌 공지는 상세 조회도 안 한다
    assert len(session.calls) == 1
    assert session.calls[0]["embeds"][0]["image"]["url"] == "https://file.nexon.com/a.png"
    assert load_seen(state_path) == [1356]


def test_이미_보낸_공지는_다시_보내지_않는다(tmp_path):
    state_path = tmp_path / "seen.json"
    save_seen(state_path, [1356])
    client = FakeClient([_notice(1356, "스페셜 썬데이 메이플")])
    session = FakeSession()

    sent = run(client, WEBHOOK, state_path, session=session)

    assert sent == 0
    assert session.calls == []
    assert load_seen(state_path) == [1356]


def test_최신_공지가_목록_앞에_기록된다(tmp_path):
    state_path = tmp_path / "seen.json"
    save_seen(state_path, [1350])
    client = FakeClient([_notice(1356, "썬데이 메이플")])

    run(client, WEBHOOK, state_path, session=FakeSession())

    assert load_seen(state_path) == [1356, 1350]


def test_상세_조회가_실패해도_제목과_링크는_보낸다(tmp_path):
    state_path = tmp_path / "seen.json"
    client = FakeClient([_notice(1356, "썬데이 메이플")], detail_error=True)
    session = FakeSession()

    sent = run(client, WEBHOOK, state_path, session=session)

    assert sent == 1
    embeds = session.calls[0]["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["title"] == "썬데이 메이플"
    assert load_seen(state_path) == [1356]


def test_전송에_실패하면_기록하지_않는다(tmp_path):
    state_path = tmp_path / "seen.json"
    client = FakeClient([_notice(1356, "썬데이 메이플")])

    with pytest.raises(WebhookError):
        run(client, WEBHOOK, state_path, session=FakeSession(fail=True))

    assert load_seen(state_path) == []


def test_bootstrap은_발송_없이_기록만_한다(tmp_path):
    state_path = tmp_path / "seen.json"
    client = FakeClient(
        [_notice(1356, "썬데이 메이플"), _notice(1350, "스페셜 썬데이 메이플")]
    )
    session = FakeSession()

    sent = run(client, WEBHOOK, state_path, bootstrap=True, session=session)

    assert sent == 0
    assert session.calls == []
    assert client.detail_calls == []
    assert load_seen(state_path) == [1356, 1350]


def test_새_공지가_없으면_아무것도_하지_않는다(tmp_path):
    state_path = tmp_path / "seen.json"
    client = FakeClient([_notice(1355, "메이플 히어로즈")])
    session = FakeSession()

    assert run(client, WEBHOOK, state_path, session=session) == 0
    assert session.calls == []
```

> **Superseded (최종 리뷰 수정 커밋들):** 실제 `tests/test_main.py`의 테스트 목록은 위보다 많다. 최종
> 리뷰에서 배치 내부 순서(최신이 앞 유지), 배치 중간 실패 시 부분 기록, CLI 계약(`main()`의 반환값),
> 새 공지가 없을 때 로그 한 줄이 남는지 등을 검증하는 테스트가 추가됐다. 이 목록을 "완전한 테스트
> 스펙"으로 여기고 나머지를 지우지 말 것 — 실제 `tests/test_main.py` 파일이 최신 기준이다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `.venv/Scripts/python -m pytest tests/test_main.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'maple_sunday_bot.main'`

- [ ] **Step 3: 구현 작성**

`src/maple_sunday_bot/main.py`:

```python
"""진입점. 어떤 순서로 무엇을 할지만 담당한다."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from maple_sunday_bot import webhook as webhook_module
from maple_sunday_bot.nexon import NexonApiError, NexonClient
from maple_sunday_bot.notice import extract_images, is_sunday
from maple_sunday_bot.state import load_seen, save_seen

DEFAULT_STATE_PATH = Path("state/seen.json")


def run(client, webhook_url, state_path, bootstrap=False, session=None) -> int:
    """새 썬데이 공지를 찾아 발송한다. 발송한 공지 수를 반환한다."""
    seen = load_seen(state_path)
    fresh = [
        n
        for n in client.get_event_notices()
        if is_sunday(n.title) and n.notice_id not in seen
    ]

    if not fresh:
        return 0

    if bootstrap:
        save_seen(state_path, [n.notice_id for n in fresh] + seen)
        print(f"bootstrap: {len(fresh)}건을 발송 없이 기록했습니다.")
        return 0

    sent_count = 0
    for notice in fresh:
        try:
            images = extract_images(client.get_event_notice_detail(notice.notice_id))
        except NexonApiError as exc:
            # 이미지 누락보다 알림 누락이 나쁘다. 제목과 링크만이라도 보낸다.
            print(f"본문 조회 실패({notice.notice_id}): {exc}", file=sys.stderr)
            images = []

        webhook_module.send(
            webhook_url, webhook_module.build_messages(notice, images), session
        )
        # 전송 성공 직후에 기록한다. 여기서 죽으면 다음 회차에 다시 보낸다.
        seen = [notice.notice_id] + seen
        save_seen(state_path, seen)
        sent_count += 1
        print(f"발송 완료: [{notice.notice_id}] {notice.title}")

    return sent_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="썬데이 메이플 공지 알림 봇")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="발송하지 않고 현재 썬데이 공지를 전부 '이미 봄'으로 기록한다 (최초 1회)",
    )
    parser.add_argument(
        "--state", default=str(DEFAULT_STATE_PATH), help="상태 파일 경로"
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("NEXON_API_KEY")
    if not api_key:
        print("NEXON_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url and not args.bootstrap:
        print("DISCORD_WEBHOOK_URL 환경변수가 없습니다.", file=sys.stderr)
        return 1

    try:
        run(
            NexonClient(api_key),
            webhook_url or "",
            Path(args.state),
            bootstrap=args.bootstrap,
        )
    except Exception as exc:
        print(f"실패: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest -v`

Expected: PASS — 44 passed

- [ ] **Step 5: bootstrap으로 초기 상태 만들기**

사전 준비 A가 끝나 있어야 한다.

Run:
```bash
.venv/Scripts/python -m maple_sunday_bot.main --bootstrap
```

Expected: `bootstrap: N건을 발송 없이 기록했습니다.` 가 찍히고 `state/seen.json`이 생긴다.

파일을 열어 `notice_id`가 들어있는지 눈으로 확인한다.

- [ ] **Step 6: 실제 디스코드 발송 검증**

사전 준비 B가 끝나 있어야 한다. `seen.json`에서 가장 최근 ID **하나만 지우고** 다시 돌려서, 실제 메시지가 오는지 본다.

Run:
```bash
.venv/Scripts/python -m maple_sunday_bot.main
```

Expected: `발송 완료: [....] ...` 가 찍히고, 디스코드 채널에 제목·링크·기간·이미지가 담긴 메시지가 도착한다. 이미지가 전부 보이는지 확인한다.

- [ ] **Step 7: 커밋**

```bash
git add src/maple_sunday_bot/main.py tests/test_main.py state/seen.json
git commit -m "feat: 진입점과 bootstrap 모드 추가"
```

---

### Task 7: GitHub Actions 워크플로우와 README

**Files:**
- Create: `.github/workflows/check.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: `python -m maple_sunday_bot.main` (Task 6)
- Produces: 없음 (최종 태스크)

- [ ] **Step 1: 워크플로우 작성**

`.github/workflows/check.yml`:

```yaml
name: 썬데이 메이플 공지 확인

on:
  schedule:
    # 30분마다. GitHub 러너가 혼잡하면 지연될 수 있다.
    - cron: "*/30 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: check
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: 의존성 설치
        run: pip install -e .

      - name: 공지 확인 및 발송
        env:
          NEXON_API_KEY: ${{ secrets.NEXON_API_KEY }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: python -m maple_sunday_bot.main

      - name: 발송 이력 커밋
        run: |
          if [[ -z "$(git status --porcelain state/seen.json)" ]]; then
            echo "변경 없음"
            exit 0
          fi
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add state/seen.json
          git commit -m "chore: 발송 이력 갱신"
          git push
```

`concurrency`는 두 실행이 겹쳐 같은 공지를 두 번 보내거나 push가 충돌하는 걸 막는다.

`발송 이력 커밋` 스텝에 `if: always()`를 붙이지 않는 게 중요하다. 발송 스텝이 실패하면 상태를 커밋하지 않고 다음 회차에 재시도해야 한다.

> **Superseded (최종 리뷰 수정, finding 2):** 이 판단은 뒤집혔다 — 실제 워크플로우는 이 스텝에
> `if: always()`를 **붙인다**. `save_seen`은 전송 성공 직후에만 호출되므로, 배치 중간에 실패해도
> 그 전까지 성공한 공지의 기록은 이미 `state/seen.json`에 있다. 이 스텝을 건너뛰면 그 기록이 러너와
> 함께 사라져 다음 회차에 같은 공지를 다시 보내려다 또 실패하는 무한 재시도/스팸이 된다. 목록 조회
> 자체가 실패하거나 아무것도 못 보냈으면 파일이 안 바뀌므로 `git status --porcelain` 가드가 그대로
> 걸러낸다 — 그래서 `if: always()`는 안전하고, 이전 판단보다 낫다. 이 계획 문구로 되돌리지 말 것.

- [ ] **Step 2: README 작성**

`README.md`:

````markdown
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

이 단계를 건너뛰면 과거 썬데이 공지가 한꺼번에 발송된다.

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
````

- [ ] **Step 3: 워크플로우 문법 확인**

Run: `.venv/Scripts/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/check.yml',encoding='utf-8')); print('OK')"`

Expected: `OK`

(`yaml` 모듈이 없으면 `pip install pyyaml`로 임시 설치해 확인하고, 확인 후 `pip uninstall -y pyyaml`로 지운다. 프로젝트 의존성에는 넣지 않는다.)

- [ ] **Step 4: 전체 테스트 확인**

Run: `.venv/Scripts/python -m pytest -v`

Expected: PASS — 44 passed

- [ ] **Step 5: 커밋 및 푸시**

```bash
git add .github/ README.md
git commit -m "chore: GitHub Actions 워크플로우와 README 추가"
```

- [ ] **Step 6: 리포 생성 후 푸시, 실제 동작 확인**

GitHub에 public 리포를 만들고 푸시한 뒤, Secrets 두 개를 등록한다.
Actions 탭 → "썬데이 메이플 공지 확인" → Run workflow 로 수동 실행한다.

Expected: 워크플로우가 초록색으로 끝난다. 새 공지가 없으면 아무 메시지도 오지 않는 게 정상이다.

---

## 완료 기준 확인

- [ ] `pytest`가 전부 통과하고, 네트워크 없이 돈다
- [ ] `--bootstrap` 실행 후 `state/seen.json`에 현재 썬데이 공지가 들어있다
- [ ] 실제 디스코드 채널에 제목·링크·기간·이미지 전체가 담긴 메시지가 도착했다
- [ ] 같은 공지로 다시 실행해도 두 번 발송되지 않는다
- [ ] GitHub Actions 수동 실행이 성공한다
- [ ] Secrets 두 개 외에 사용자가 할 일이 없다
