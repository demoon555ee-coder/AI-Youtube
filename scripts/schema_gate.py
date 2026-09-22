from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio

from app.db.schema_gate import schema_is_current
from app.db.session import engine


async def main() -> None:
    current, applied, expected = await schema_is_current(engine)
    print(f"schema_applied={applied}\nschema_expected={expected}\nschema_current={current}")
    await engine.dispose()
    raise SystemExit(0 if current else 1)


if __name__ == "__main__":
    asyncio.run(main())
