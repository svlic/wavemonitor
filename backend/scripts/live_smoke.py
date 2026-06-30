#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (default skips live providers):
#      uv run backend/scripts/live_smoke.py
# 3. Explicitly enable live checks only when external calls are intended:
#      RUN_LIVE_SMOKE=1 uv run backend/scripts/live_smoke.py
# 4. Or make executable and run:
#      chmod +x backend/scripts/live_smoke.py && ./backend/scripts/live_smoke.py
# ──────────────────

from __future__ import annotations

import os
from typing import Final

SKIP_MESSAGE: Final[str] = "SKIPPED live smoke: set RUN_LIVE_SMOKE=1 to call live providers."
LIVE_MESSAGE: Final[str] = "RUN_LIVE_SMOKE=1 set; live provider smoke checks are not implemented in Todo 9."


def main() -> int:
    """Gate live provider checks behind RUN_LIVE_SMOKE=1."""
    if os.environ.get("RUN_LIVE_SMOKE") != "1":
        print(SKIP_MESSAGE)
        return 0
    print(LIVE_MESSAGE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
