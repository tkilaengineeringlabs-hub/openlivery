"""Fail-closed destination guard for fixtures that reset database tables."""

from sqlalchemy.engine import make_url


def is_disposable_test_target(raw_url: str, reset_opt_in: str | None) -> bool:
    try:
        target = make_url(raw_url)
        return bool(
            reset_opt_in == "1"
            and target.drivername == "postgresql+psycopg"
            and target.host in {"localhost", "127.0.0.1", "::1", "db-test"}
            and target.database
            and target.database.endswith("_test")
            and not target.query
        )
    except Exception:
        # Never include the URL (which may contain a password) in diagnostics.
        return False
