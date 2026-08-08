import json
from pathlib import Path

import pytest

from maple_sunday_bot.notice import Notice, event_period, extract_images, is_sunday

FIXTURES = Path(__file__).parent / "fixtures"


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


def test_HTML_엔티티로_이스케이프된_주소는_풀어서_반환한다():
    html = '<img src="https://file.nexon.com/x.aspx?a=1&amp;b=2">'
    assert extract_images(html) == ["https://file.nexon.com/x.aspx?a=1&b=2"]


def test_실제_상세_응답_fixture에서_이미지_URL을_뽑는다():
    detail = json.loads((FIXTURES / "notice_event_detail.json").read_text(encoding="utf-8"))

    assert extract_images(detail["contents"]) == [
        "https://lwi.nexon.com/maplestory/2026/0723_board/260809_3805XUHQ13Y7NIM7.png",
    ]


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
