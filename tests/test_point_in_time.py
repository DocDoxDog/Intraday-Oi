from src.point_in_time import validate_snapshot, validate_dataset


def test_future_data_is_rejected():
    row = {"event_time": "2026-11-20T10:00:00Z", "as_of": "2026-11-20T10:01:00Z"}
    out = validate_dataset([row])
    assert out["status"] == "FAIL"
    assert out["failed_rows"] == 1


def test_news_publication_time_is_checked():
    row = {
        "event_time": "2026-11-20T10:00:00Z",
        "news": [{"published_at": "2026-11-20T10:05:00Z"}],
    }
    assert validate_snapshot(row, row["event_time"])


def test_pit_passes():
    row = {
        "event_time": "2026-11-20T10:00:00Z",
        "as_of": "2026-11-20T10:00:00Z",
        "news": [{"published_at": "2026-11-20T09:59:00Z"}],
    }
    assert validate_dataset([row])["status"] == "PASS"
