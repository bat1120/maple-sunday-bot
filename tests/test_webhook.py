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
