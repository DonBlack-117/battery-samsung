#!/usr/bin/env python3
"""Atajo para el CLI: `python bateria.py` (igual que `python -m battery_sam.cli`)."""

import sys

from battery_sam.cli import main

if __name__ == "__main__":
    sys.exit(main())
