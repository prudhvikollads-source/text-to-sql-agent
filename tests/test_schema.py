from text_to_sql_agent.schema import introspect_schema

EXPECTED_TABLES = {
    "customers", "plans", "subscriptions", "invoices",
    "usage_records", "support_tickets",
}


def test_all_tables_present(db_path):
    schema = introspect_schema(db_path)
    assert set(schema) == EXPECTED_TABLES


def test_customers_columns(db_path):
    schema = introspect_schema(db_path)
    names = [name for name, _type in schema["customers"]["columns"]]
    assert names == ["customer_id", "full_name", "email", "country", "city",
                     "signup_date"]


def test_row_counts_are_substantial(db_path):
    schema = introspect_schema(db_path)
    assert schema["customers"]["row_count"] == 500
    assert schema["plans"]["row_count"] == 5
    assert schema["support_tickets"]["row_count"] == 450
    total = sum(info["row_count"] for info in schema.values())
    assert total > 3000


def test_plans_seed_content(db_path):
    from text_to_sql_agent.schema import execute_readonly

    _cols, rows = execute_readonly(
        db_path, "SELECT plan_name, monthly_price FROM plans ORDER BY plan_id")
    assert rows[0] == ("Basic", 15.0)
    assert rows[-1] == ("Family", 99.0)
