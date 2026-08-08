import pytest

from maple_sunday_bot.main import main, run
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
    def __init__(self, fail=False, statuses=None):
        self.calls = []
        self._fail = fail
        # statuses가 주어지면 post() 호출마다 하나씩 순서대로 꺼내 쓴다
        # (성공 후 실패처럼, 호출마다 다른 결과를 내야 하는 경우용).
        self._statuses = list(statuses) if statuses is not None else None

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        if self._statuses is not None:
            status_code = self._statuses.pop(0)
        else:
            status_code = 500 if self._fail else 204
        outer_status = status_code

        class _Response:
            status_code = outer_status

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


def test_한_회차에_여러_건을_보내도_배치_내에서_최신이_앞에_온다(tmp_path):
    state_path = tmp_path / "seen.json"
    client = FakeClient(
        [
            _notice(1360, "썬데이 메이플"),
            _notice(1358, "스페셜 썬데이 메이플"),
            _notice(1355, "썬데이 메이플"),
        ]
    )
    session = FakeSession()

    sent = run(client, WEBHOOK, state_path, session=session)

    assert sent == 3
    # get_event_notices()가 최신순으로 준 순서(1360, 1358, 1355)가
    # seen.json에도 그대로(최신이 앞) 유지되어야 한다.
    assert load_seen(state_path) == [1360, 1358, 1355]


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


def test_새_공지가_없으면_아무것도_하지_않는다(tmp_path, capsys):
    state_path = tmp_path / "seen.json"
    client = FakeClient([_notice(1355, "메이플 히어로즈")])
    session = FakeSession()

    assert run(client, WEBHOOK, state_path, session=session) == 0
    assert session.calls == []
    # 조용한 정상 실행도 로그 한 줄은 남겨야 Actions 로그에서 구분된다.
    assert capsys.readouterr().out.strip() != ""


def test_배치_중간에_실패해도_그_전까지의_성공은_기록된다(tmp_path):
    state_path = tmp_path / "seen.json"
    client = FakeClient(
        [_notice(1356, "썬데이 메이플"), _notice(1350, "스페셜 썬데이 메이플")]
    )
    # 첫 번째 공지는 성공(204), 두 번째 공지는 실패(500).
    session = FakeSession(statuses=[204, 500])

    with pytest.raises(WebhookError):
        run(client, WEBHOOK, state_path, session=session)

    # 두 번째 전송이 실패해 예외가 났어도, 먼저 성공한 첫 번째는 기록되어 있어야 한다.
    assert load_seen(state_path) == [1356]


def test_NEXON_API_KEY가_없으면_1을_반환한다(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXON_API_KEY", raising=False)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)

    assert main(["--state", str(tmp_path / "seen.json")]) == 1


def test_bootstrap이_아닐때_DISCORD_WEBHOOK_URL이_없으면_1을_반환한다(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("NEXON_API_KEY", "test-key")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    assert main(["--state", str(tmp_path / "seen.json")]) == 1


def test_bootstrap일때는_DISCORD_WEBHOOK_URL이_없어도_그_이유로_실패하지_않는다(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("NEXON_API_KEY", "test-key")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    # run()까지는 도달하므로 네트워크를 타지 않도록 갈아끼운다.
    monkeypatch.setattr("maple_sunday_bot.main.run", lambda *a, **k: 0)

    result = main(["--bootstrap", "--state", str(tmp_path / "seen.json")])

    assert result == 0


def test_run에서_예외가_나면_전파하지_않고_1을_반환한다(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXON_API_KEY", "test-key")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)

    def _boom(*args, **kwargs):
        raise RuntimeError("네트워크 실패 가정")

    monkeypatch.setattr("maple_sunday_bot.main.run", _boom)

    assert main(["--state", str(tmp_path / "seen.json")]) == 1
