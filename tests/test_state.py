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
