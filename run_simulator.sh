#!/usr/bin/env bash
set -e
export SIM_RENDER=1
exec "$(dirname "${BASH_SOURCE[0]}")/run_simulator_offscreen.sh" "$@"
