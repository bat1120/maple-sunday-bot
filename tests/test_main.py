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
