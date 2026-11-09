#!/usr/bin/env bash
set -e
source /opt/ros/noetic/setup.bash
source /bridge_ws/devel/setup.bash
children=()
cleanup() { trap - EXIT INT TERM; kill "${children[@]}" 2>/dev/null || true; wait || true; }
trap cleanup EXIT INT TERM
roscore & children+=("$!")
for attempt in {1..60}; do
    if rosparam list >/dev/null 2>&1; then break; fi
    sleep 0.5
done
rosparam list >/dev/null
# The ROS 2 adapter connects through localhost on the host network.
roslaunch rosbridge_server rosbridge_websocket.launch address:=127.0.0.1 port:="${ROSBRIDGE_PORT:-9090}" &
children+=("$!")
args=(seed "${Seed:-123}")
if [[ "${SIM_RENDER:-0}" != 1 ]]; then args+=(-RenderOffscreen); fi
/usr/local/LinuxNoEditor/RMUA.sh "${args[@]}" & children+=("$!")
wait -n "${children[@]}"
