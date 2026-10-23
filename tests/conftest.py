import pytest

from text_to_sql_agent.seed import build_database


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "sample.db"
    build_database(path)
    return path
