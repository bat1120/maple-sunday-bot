import io
import json
import math

import pytest
import requests
from PIL import Image

from maple_sunday_bot.images import MAX_ASPECT_RATIO
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


def _png_bytes(width, height, color="white"):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeSession:
    def __init__(self, fail=False, statuses=None, image_response=None):
        self.calls = []
        # 매 post() 호출을 통째로 기록한다 (json/data/files 전부) — multipart 전송이
        # 실제로 조립됐는지(첨부 키, payload_json)까지 검증하려면 json만으로는 부족하다.
        self.requests = []
        self._fail = fail
        # statuses가 주어지면 post() 호출마다 하나씩 순서대로 꺼내 쓴다
        # (성공 후 실패처럼, 호출마다 다른 결과를 내야 하는 경우용).
        self._statuses = list(statuses) if statuses is not None else None
        # image_response가 주어지면 get()이 그 바이트를 담은 200 응답을 돌려준다
        # (이미지 다운로드/분할 성공 경로를 실제로 태우는 테스트용).
        # 기본값(None)에서는 이 파일의 테스트가 네트워크를 타지 않도록 get()이
        # 항상 실패해 images.fetch_and_slice가 ImageError를 내고, run()이
        # URL 임베드 폴백으로 넘어간다.
        self._image_response = image_response

    def get(self, url, timeout=None):
        if self._image_response is not None:
            class _Response:
                status_code = 200
                content = self._image_response

            return _Response()
        raise requests.ConnectionError("테스트에서는 이미지 다운로드를 허용하지 않는다")

    def post(self, url, json=None, data=None, files=None, timeout=None):
        self.calls.append(json)
        self.requests.append(
            {"url": url, "json": json, "data": data, "files": files, "timeout": timeout}
        )
        if self._statuses is not None:
            status_code = self._statuses.pop(0)
        else:
            status_code = 500 if self._fail else 204
        outer_status = status_code

        class _Response:
            status_code = outer_status

        return _Response()


def test_새_썬데이_공지를_발송하고_기록한다_다운로드_실패시_URL_임베드로_폴백한다(tmp_path):
    # 이 테스트가 쓰는 기본 FakeSession은 get()이 항상 실패하도록 만들어져 있어
    # (네트워크 금지 원칙), 여기서 검증하는 발송 경로는 실제로는 URL 임베드
    # 폴백이다. 새 첨부 방식의 정상 경로는
    # test_이미지_다운로드가_성공하면_분할한_조각을_멀티파트_첨부로_보낸다 가 담당한다.
    # 이 테스트의 핵심은 "썬데이 아닌 공지는 상세 조회도 하지 않는다"이며, 그건
    # 첨부/폴백 어느 경로든 동일하게 성립해야 한다.
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


def test_이미지_다운로드가_성공하면_분할한_조각을_멀티파트_첨부로_보낸다(tmp_path):
    # test_이미지_분할이_실패하면_...의 반대쪽 경로 — fetch_and_slice의 다운로드가
    # 실제로 성공했을 때 run()의 전체 배선(반복 다운로드 → slices.extend →
    # build_attachment_messages → send의 multipart 경로)이 실제로 연결되어
    # 있는지를 유닛 경계를 넘어 확인한다. 각 조각의 단위 동작(자르기 계산,
    # 청크 상한 등)은 test_images.py/test_webhook.py가 이미 검증했으므로
    # 여기서는 "이어 붙였을 때 맞물리는지"만 본다.
    state_path = tmp_path / "seen.json"
    client = FakeClient(
        [_notice(1356, "스페셜 썬데이 메이플")],
        details={1356: '<img src="https://file.nexon.com/a.png">'},
    )
    width, height = 100, 300  # 300 > 100 * 1.2 → 실제로 잘려야 한다
    session = FakeSession(image_response=_png_bytes(width, height))

    sent = run(client, WEBHOOK, state_path, session=session)

    assert sent == 1
    assert load_seen(state_path) == [1356]

    assert len(session.requests) == 1
    request = session.requests[0]
    # multipart 경로는 json=이 아니라 data=payload_json + files=를 쓴다.
    assert request["json"] is None
    assert request["data"] is not None

    payload = json.loads(request["data"]["payload_json"])
    embeds = payload["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["title"] == "스페셜 썬데이 메이플"
    assert "image" not in embeds[0]  # 이미지는 임베드가 아니라 첨부로 간다

    expected_parts = math.ceil(height / (width * MAX_ASPECT_RATIO))
    files = request["files"]
    assert len(files) == expected_parts
    assert set(files.keys()) == {f"files[{i}]" for i in range(expected_parts)}
    # main.py는 공지 안에서 몇 번째 이미지인지를 "{notice_id}_{순번:02d}" 로 stem에
    # 담고, images.slice_image가 거기에 "_{조각순번:02d}.png"를 덧붙인다.
    names = [files[f"files[{i}]"][0] for i in range(expected_parts)]
    assert names == [f"1356_01_{i:02d}.png" for i in range(1, expected_parts + 1)]
    for _, blob, content_type in files.values():
        assert content_type == "image/png"


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


def test_이미지_분할이_실패하면_URL_임베드_폴백으로_보내고_발송은_성공한다(tmp_path, capsys):
    state_path = tmp_path / "seen.json"
    client = FakeClient(
        [_notice(1356, "스페셜 썬데이 메이플")],
        details={1356: '<img src="https://file.nexon.com/a.png">'},
    )
    # FakeSession.get()은 항상 실패한다 → images.fetch_and_slice가 ImageError를 내야 하고,
    # run()은 build_attachment_messages 대신 build_messages(URL 임베드)로 폴백해야 한다.
    session = FakeSession()

    sent = run(client, WEBHOOK, state_path, session=session)

    assert sent == 1
    assert len(session.calls) == 1
    payload = session.calls[0]
    embeds = payload["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["title"] == "스페셜 썬데이 메이플"
    # 폴백은 URL 임베드 방식이라 이미지가 링크로 실린다.
    assert embeds[0]["image"]["url"] == "https://file.nexon.com/a.png"
    assert load_seen(state_path) == [1356]
    # 화질 저하보다 알림 실패가 더 나쁘다는 원칙이 로그로도 드러나야 한다.
    assert "실패" in capsys.readouterr().err


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
