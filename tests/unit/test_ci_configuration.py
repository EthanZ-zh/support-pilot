from pathlib import Path


def test_ci_alembic_and_pytest_use_the_same_isolated_database() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    database_url = (
        "postgresql+psycopg://support_pilot:support_pilot@localhost:54330/support_pilot_test"
    )

    assert f"SUPPORT_PILOT_DATABASE_URL: {database_url}" in workflow
    assert f"SUPPORT_PILOT_TEST_DATABASE_URL: {database_url}" in workflow
