import pytest

from text_to_sql_agent.validator import ValidationError, validate_sql


@pytest.mark.parametrize("sql", [
    "INSERT INTO customers VALUES (1, 'x')",
    "insert into customers values (1, 'x')",
    "UPDATE customers SET full_name = 'x'",
    "DELETE FROM customers WHERE customer_id = 1",
    "DROP TABLE customers",
    "ALTER TABLE customers ADD COLUMN nickname TEXT",
    "CREATE TABLE t (a INTEGER)",
    "REPLACE INTO customers VALUES (1)",
    "PRAGMA foreign_keys = ON",
    "VACUUM",
])
def test_rejects_writes_and_ddl(sql):
    with pytest.raises(ValidationError):
        validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM customers; SELECT * FROM plans",
    "SELECT 1; DROP TABLE customers",
    "SELECT * FROM customers;;",
])
def test_rejects_multiple_statements(sql):
    with pytest.raises(ValidationError):
        validate_sql(sql)


def test_rejects_empty():
    with pytest.raises(ValidationError):
        validate_sql("   ")


def test_plain_select_passes_and_gets_limit():
    out = validate_sql("SELECT full_name FROM customers")
    assert out.startswith("SELECT")
    assert out.endswith("LIMIT 100")


def test_trailing_semicolon_is_tolerated():
    out = validate_sql("SELECT 1;")
    assert ";" not in out


def test_existing_small_limit_is_kept():
    out = validate_sql("SELECT plan_name FROM plans LIMIT 5")
    assert out.endswith("LIMIT 5")


def test_oversized_limit_is_clamped():
    out = validate_sql("SELECT plan_name FROM plans LIMIT 99999")
    assert out.endswith("LIMIT 1000")


def test_keyword_inside_string_literal_is_allowed():
    out = validate_sql("SELECT * FROM support_tickets WHERE category = 'delete me'")
    assert "LIMIT 100" in out


def test_with_select_is_allowed():
    out = validate_sql("WITH t AS (SELECT 1 AS a) SELECT * FROM t")
    assert out.endswith("LIMIT 100")
