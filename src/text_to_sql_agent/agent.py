"""The agent loop.

Pipeline: introspect schema -> generate SQL -> validate + execute ->
on failure, feed the error back to the generator and retry (up to
``max_attempts``) -> return the final SQL with its result set.

The graph is built with LangGraph when it is installed. If LangGraph is
not available, the exact same node functions are driven by a small
hand-rolled state machine, so the project still runs on a bare
standard-library Python install.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from .llm import LLM, get_llm
from .schema import execute_readonly, introspect_schema, schema_to_text
from .seed import ensure_database
from .validator import ValidationError, validate_sql


class AgentState(TypedDict, total=False):
    question: str
    schema_text: str
    sql: str
    attempts: int
    error: str | None
    previous_sql: str | None
    columns: list
    rows: list
    success: bool


@dataclass
class AgentResult:
    question: str
    sql: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    success: bool = False
    backend: str = "state-machine"


def _make_nodes(db_path: Path, llm: LLM, max_attempts: int):
    def introspect(state: AgentState) -> AgentState:
        schema = introspect_schema(db_path)
        return {"schema_text": schema_to_text(schema)}

    def generate(state: AgentState) -> AgentState:
        sql = llm.generate(
            state["question"],
            state.get("schema_text", ""),
            error=state.get("error"),
            previous_sql=state.get("previous_sql"),
        )
        return {
            "sql": sql,
            "attempts": state.get("attempts", 0) + 1,
            "previous_sql": sql,
        }

    def execute(state: AgentState) -> AgentState:
        raw_sql = state.get("sql", "")
        try:
            safe_sql = validate_sql(raw_sql)
        except ValidationError as exc:
            return {"error": f"validation failed: {exc}", "success": False,
                    "sql": raw_sql}
        try:
            columns, rows = execute_readonly(db_path, safe_sql)
        except sqlite3.Error as exc:
            return {"error": f"execution failed: {exc}", "success": False,
                    "sql": safe_sql}
        return {"columns": columns, "rows": rows, "error": None,
                "success": True, "sql": safe_sql}

    def route(state: AgentState) -> str:
        if state.get("success"):
            return "done"
        if state.get("attempts", 0) >= max_attempts:
            return "done"
        return "retry"

    return introspect, generate, execute, route


def _run_with_langgraph(question: str, db_path: Path, llm: LLM,
                        max_attempts: int) -> AgentState:
    from langgraph.graph import END, START, StateGraph

    introspect, generate, execute, route = _make_nodes(db_path, llm, max_attempts)
    builder = StateGraph(AgentState)
    builder.add_node("introspect", introspect)
    builder.add_node("generate", generate)
    builder.add_node("execute", execute)
    builder.add_edge(START, "introspect")
    builder.add_edge("introspect", "generate")
    builder.add_edge("generate", "execute")
    builder.add_conditional_edges(
        "execute", route, {"retry": "generate", "done": END}
    )
    graph = builder.compile()
    return graph.invoke({"question": question, "attempts": 0, "error": None,
                         "previous_sql": None, "success": False})


def _run_with_state_machine(question: str, db_path: Path, llm: LLM,
                            max_attempts: int) -> AgentState:
    introspect, generate, execute, route = _make_nodes(db_path, llm, max_attempts)
    state: AgentState = {"question": question, "attempts": 0, "error": None,
                         "previous_sql": None, "success": False}
    state.update(introspect(state))
    while True:
        state.update(generate(state))
        state.update(execute(state))
        if route(state) == "done":
            return state


def run_agent(question: str, db_path: str | Path | None = None,
              llm: LLM | None = None, max_attempts: int = 3) -> AgentResult:
    """Ask ``question`` against the sample database and return the result."""
    path = ensure_database(db_path)
    active_llm = llm if llm is not None else get_llm()
    errors: list[str] = []

    # Wrap execution errors are captured inside the graph; collect them by
    # observing the final state plus a light error-tracking shim on the LLM.
    try:
        final = _run_with_langgraph(question, path, active_llm, max_attempts)
        backend = "langgraph"
    except ImportError:
        final = _run_with_state_machine(question, path, active_llm, max_attempts)
        backend = "state-machine"

    if final.get("error"):
        errors.append(str(final["error"]))
    return AgentResult(
        question=question,
        sql=final.get("sql"),
        columns=list(final.get("columns", [])),
        rows=list(final.get("rows", [])),
        attempts=int(final.get("attempts", 0)),
        errors=errors,
        success=bool(final.get("success")),
        backend=backend,
    )
