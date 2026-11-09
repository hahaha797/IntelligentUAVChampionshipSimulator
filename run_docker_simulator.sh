#!/usr/bin/env bash
set -e
if ! command -v docker >/dev/null; then echo 'Docker is required to run the upstream ROS 1 simulator binary.' >&2; exit 1; fi
args=(run --rm --init --name "${SIM_CONTAINER_NAME:-sim01}" --net host --gpus "${SIM_GPUS:-all}"
    -e NVIDIA_DRIVER_CAPABILITIES=all --shm-size=1g -e Seed="${1:-123}" -e ROSBRIDGE_PORT="${ROSBRIDGE_PORT:-9090}" -e SIM_RENDER="${SIM_RENDER:-0}")
if [[ "${SIM_RENDER:-0}" == 1 ]]; then
    : "${DISPLAY:?DISPLAY is required for rendering}"
    args+=(-e DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix:rw)
    if ! command -v xauth >/dev/null; then
        echo 'xauth is required for the graphical simulator.' >&2; exit 1
    fi
    auth_dir="${XDG_RUNTIME_DIR:-$HOME/.cache}/rmua2026"
    install -d -m 700 "$auth_dir"
    auth_file="$auth_dir/${SIM_CONTAINER_NAME:-sim01}.xauth"
    auth_tmp="$(mktemp "$auth_dir/xauth.XXXXXX")"
    # A wildcard family lets the container use the cookie despite its hostname.
    xauth nlist "$DISPLAY" | sed 's/^..../ffff/' | xauth -f "$auth_tmp" nmerge -
    if [[ ! -s "$auth_tmp" ]]; then
        rm -f "$auth_tmp"
        echo 'No X11 authentication cookie found for DISPLAY.' >&2; exit 1
    fi
    chmod 600 "$auth_tmp"
    mv "$auth_tmp" "$auth_file"
    args+=(-e XAUTHORITY=/tmp/.Xauthority -v "$auth_file:/tmp/.Xauthority:ro")
fi
exec docker "${args[@]}" "${SIM_IMAGE:-simulator01:humble-adapter}"
