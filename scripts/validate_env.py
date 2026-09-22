from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.deployment import validate_production_settings
from app.config import settings


def main() -> int:
    issues = validate_production_settings()
    print(f"environment={settings.app_env}")
    if not issues:
        print("environment_valid=true")
        return 0
    print("environment_valid=false")
    for issue in issues:
        print(f"ERROR {issue.code}: {issue.message}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
