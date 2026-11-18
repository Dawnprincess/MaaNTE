import numpy as np

from sources.live.capture import recorder


def test_session_layout_and_event(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "_record_root", lambda: tmp_path)
    recorder.reset()
    try:
        session_dir = recorder.start_session()
        assert session_dir is not None
        assert (session_dir / "frames").is_dir()

        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        recorder.record("r1_observe", [frame], {"round": 1})

        assert (session_dir / "events.jsonl").exists()
        assert len(list((session_dir / "frames").glob("*.png"))) == 1
    finally:
        recorder.reset()


def test_failure_is_swallowed(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(recorder, "_record_root", lambda: blocker)
    recorder.reset()
    try:
        assert recorder.start_session() is None
        # 采集失败不得向调用方抛出
        recorder.record("r1_observe", [np.zeros((2, 2, 3), dtype=np.uint8)])
    finally:
        recorder.reset()
