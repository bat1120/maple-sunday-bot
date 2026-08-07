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
