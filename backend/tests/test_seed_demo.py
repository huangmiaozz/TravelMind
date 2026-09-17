from app.db.seed_demo import DEMO_SOURCE, DEMO_SOURCE_URL


def test_demo_seed_is_explicitly_marked_as_mock_data() -> None:
    assert DEMO_SOURCE.startswith("Mock Data")
    assert DEMO_SOURCE_URL == "about:blank"
