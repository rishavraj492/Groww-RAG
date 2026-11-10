from app.config import parse_cors_origins


def test_parse_cors_origins_defaults_when_unset():
    assert parse_cors_origins(None) == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    assert parse_cors_origins("") == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    assert parse_cors_origins("   ") == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )


def test_parse_cors_origins_splits_and_strips():
    assert parse_cors_origins(
        "https://web.up.railway.app/, http://localhost:5173"
    ) == (
        "https://web.up.railway.app",
        "http://localhost:5173",
    )
