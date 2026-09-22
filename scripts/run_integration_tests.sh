#!/usr/bin/env bash
set -euo pipefail
export REQUIRE_INTEGRATION=true
pytest -m integration -q
