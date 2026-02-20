#!/usr/bin/env python3
"""
Dry Run - Generate schedule without pushing to QGenda (DEFAULT mode)

Usage:
  python scripts/run_dry_run.py --start 2026-03-01 --end 2026-06-30

Outputs to outputs/ directory.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.dry_run import main

if __name__ == "__main__":
    main()
