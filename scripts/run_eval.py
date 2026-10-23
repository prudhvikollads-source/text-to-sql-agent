#!/usr/bin/env python3
"""Run the eval harness (adds src/ to sys.path for a source checkout)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from text_to_sql_agent.evaluate import main

if __name__ == "__main__":
    raise SystemExit(main())
