"""A subset of the eval questions must execute to the expected results."""

import pytest

from text_to_sql_agent.agent import run_agent
from text_to_sql_agent.evaluate import load_questions, results_match
from text_to_sql_agent.schema import execute_readonly
from text_to_sql_agent.validator import validate_sql

SUBSET_IDS = {1, 2, 3, 7, 11, 17, 20}


@pytest.mark.parametrize(
    "item",
    [q for q in load_questions() if q["id"] in SUBSET_IDS],
    ids=lambda q: f"Q{q['id']}",
)
def test_eval_subset(db_path, item):
    result = run_agent(item["question"], db_path=db_path)
    assert result.success, f"agent failed on {item['question']}: {result.errors}"
    _cols, reference_rows = execute_readonly(
        db_path, validate_sql(item["reference_sql"]))
    assert results_match(result.rows, reference_rows), (
        f"{item['question']}\nagent: {result.rows}\nref: {reference_rows}")


def test_eval_has_twenty_questions():
    assert len(load_questions()) == 20
