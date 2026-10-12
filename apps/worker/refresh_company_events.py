"""Lightweight daily refresh for official company calendar events."""
from __future__ import annotations

import json

from services.events.company_events import refresh_events


def main() -> int:
    result = refresh_events()
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
