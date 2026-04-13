import logging

from arranger.session_logger import SessionLog, SessionLogger


def test_get_session_logs_warns_on_corrupted_json(tmp_path, caplog):
    logger = SessionLogger(base_dir=tmp_path)
    session_dir = tmp_path / "conv-1"
    session_dir.mkdir(parents=True)
    (session_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        logs = logger.get_session_logs("conv-1")

    assert logs == []
    assert "Failed to read session log" in caplog.text


def test_save_session_log_writes_atomic_json(tmp_path):
    logger = SessionLogger(base_dir=tmp_path)
    log = SessionLog(
        conversation_id="conv-1",
        version_id="v1",
        user_intent="make it brighter",
    )

    filepath = logger.save_session_log(log)

    assert filepath.exists()
    assert logger.get_session_log("conv-1", "v1").user_intent == "make it brighter"
