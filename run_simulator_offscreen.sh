#!/usr/bin/env bash
set -e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$here/run_docker_simulator.sh" "${1:-123}" & container_pid=$!
cleanup() {
    trap - EXIT INT TERM
    kill "$container_pid" 2>/dev/null || true
    docker stop "${SIM_CONTAINER_NAME:-sim01}" >/dev/null 2>&1 || true
    if [[ -n "${bridge_pid:-}" ]]; then kill "$bridge_pid" 2>/dev/null || true; fi
    wait || true
}
trap cleanup EXIT INT TERM
"$here/run_ros2_bridge.sh" "url:=ws://127.0.0.1:${ROSBRIDGE_PORT:-9090}" & bridge_pid=$!
wait -n "$container_pid" "$bridge_pid"
