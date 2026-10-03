from insta360_flatten.core import execute, make_plan


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_flattens_videos_and_removes_subdirs(tmp_path):
    _touch(tmp_path / "VID_001" / "VID_001.mp4", b"a")
    _touch(tmp_path / "VID_001" / "thumb.jpg")
    _touch(tmp_path / "VID_002" / "VID_002.INSV", b"b")
    _touch(tmp_path / "VID_002" / "deep" / "VID_001.mp4", b"c")
    _touch(tmp_path / "keep.txt")

    plan = make_plan(tmp_path)
    assert len(plan.videos) == 3
    assert len(plan.subdirs) == 2
    assert plan.other_files == 1

    result = execute(plan)
    assert not result.errors
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["VID_001 (1).mp4", "VID_001.mp4", "VID_002.INSV", "keep.txt"]
    assert {(tmp_path / n).read_bytes() for n in names if n != "keep.txt"} == {b"a", b"b", b"c"}


def test_existing_top_level_video_not_overwritten(tmp_path):
    _touch(tmp_path / "a.mp4", b"orig")
    _touch(tmp_path / "d" / "a.mp4", b"new")
    execute(make_plan(tmp_path))
    assert (tmp_path / "a.mp4").read_bytes() == b"orig"
    assert (tmp_path / "a (1).mp4").read_bytes() == b"new"


def test_no_subdirs_is_noop(tmp_path):
    _touch(tmp_path / "a.mp4")
    plan = make_plan(tmp_path)
    assert plan.subdirs == [] and plan.videos == []
