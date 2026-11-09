#!/usr/bin/env bash
set -e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$here/../IntelligentUAVChampionshipBase/basic_dev/env_ros2.bash"
exec ros2 launch rmua_simulator_bridge simulator_bridge.launch.py "$@"
