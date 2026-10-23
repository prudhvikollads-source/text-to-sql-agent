#!/usr/bin/env python3
"""Regenerate the bundled sample database (adds src/ to sys.path)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from text_to_sql_agent.seed import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
