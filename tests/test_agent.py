from text_to_sql_agent.agent import run_agent
from text_to_sql_agent.llm import MockLLM
from text_to_sql_agent.schema import execute_readonly


class FlakyLLM:
    """Returns a broken query first, a correct one once it sees the error."""

    def __init__(self):
        self.calls = 0
        self.seen_errors = []

    def generate(self, question, schema_text, error=None, previous_sql=None):
        self.calls += 1
        if error is not None:
            self.seen_errors.append(error)
            return "SELECT COUNT(*) AS customer_count FROM customers"
        # Deliberately bad: no such column exists in customers.
        return "SELECT customer_name FROM customers"


def test_self_correction_recovers_from_bad_sql(db_path):
    llm = FlakyLLM()
    result = run_agent("How many customers are there?", db_path=db_path,
                       llm=llm, max_attempts=3)
    assert result.success
    assert result.attempts == 2
    assert llm.calls == 2
    assert llm.seen_errors, "the error must be fed back to the generator"
    assert "no such column" in llm.seen_errors[0]
    assert result.rows == [(500,)]


def test_agent_gives_up_after_max_attempts(db_path):
    class AlwaysBadLLM:
        def generate(self, question, schema_text, error=None, previous_sql=None):
            return "SELECT nope FROM customers"

    result = run_agent("anything", db_path=db_path, llm=AlwaysBadLLM(),
                       max_attempts=2)
    assert not result.success
    assert result.attempts == 2


def test_write_attempt_is_blocked_by_validator(db_path):
    class EvilLLM:
        def generate(self, question, schema_text, error=None, previous_sql=None):
            return "DELETE FROM customers"

    result = run_agent("remove everyone", db_path=db_path, llm=EvilLLM(),
                       max_attempts=1)
    assert not result.success
    _cols, rows = execute_readonly(db_path, "SELECT COUNT(*) FROM customers")
    assert rows == [(500,)]  # untouched


def test_end_to_end_active_subscribers_per_plan(db_path):
    result = run_agent("how many active subscribers per plan?",
                       db_path=db_path, llm=MockLLM())
    assert result.success
    assert result.attempts == 1
    assert result.sql is not None and "active" in result.sql
    _cols, expected = execute_readonly(
        db_path,
        "SELECT p.plan_name, COUNT(*) FROM subscriptions s "
        "JOIN plans p ON p.plan_id = s.plan_id WHERE s.status = 'active' "
        "GROUP BY p.plan_name ORDER BY p.plan_name")
    assert result.rows == expected
    assert len(result.rows) == 5


def test_mock_llm_typo_correction():
    llm = MockLLM()
    bad = "SELECT customer_name FROM customers"
    fixed = llm.generate("anything", "", error="no such column: customer_name",
                         previous_sql=bad)
    assert fixed == "SELECT full_name FROM customers"
