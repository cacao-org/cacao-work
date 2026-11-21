#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Olivier Guyon et al
# SPDX-License-Identifier: LGPL-3.0-or-later
"""CLI wrapper for the ALPAO 64x64 Plate DM Raw 3D RM Calibration Report."""

from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from studies.dyn_rm_64x64.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
