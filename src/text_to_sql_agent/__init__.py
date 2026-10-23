"""Text-to-SQL agent: natural-language questions over a SQLite database."""

from .agent import AgentResult, run_agent
from .validator import ValidationError, validate_sql

__all__ = ["AgentResult", "run_agent", "ValidationError", "validate_sql"]
__version__ = "0.1.0"
