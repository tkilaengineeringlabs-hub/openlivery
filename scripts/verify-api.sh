#!/usr/bin/env bash
# Only the disposable verification project is addressed by this runner.
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file /dev/null -p tkila-verify -f docker-compose.verify.yml)

"${compose[@]}" build api-test
# Preserve pytest's exit status even if teardown fails. Never stop other services.
cleanup() {
  local result=$?
  trap - EXIT
  "${compose[@]}" stop db-test >/dev/null || true
  exit "$result"
}
trap cleanup EXIT
"${compose[@]}" up --force-recreate --wait --wait-timeout 120 -d db-test
if [[ $# -eq 0 ]]; then
  set -- -q
fi
# A one-off run tracks this process, not exits of other project containers.
"${compose[@]}" run --rm --no-deps api-test python -m pytest "$@"
