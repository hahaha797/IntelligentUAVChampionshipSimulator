#!/usr/bin/env bash
set -e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SIM_ASSET_CACHE="${SIM_ASSET_CACHE:-$HOME/.cache/rmua2026-assets}"
# Download the large engine independently while building its compatibility runtime.
/usr/bin/python3 "$here/scripts/download_engine.py" & download_pid=$!
cleanup() {
    if [[ -n "${download_pid:-}" ]]; then kill "$download_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
common=(--network host --progress=plain
    --secret id=bootstrap_ca,src=/etc/ssl/certs/ca-certificates.crt)
docker build "${common[@]}" --target runtime -t "${SIM_RUNTIME_IMAGE:-simulator01:runtime}" "$@" "$here"
wait "$download_pid"
download_pid=
trap - EXIT INT TERM
exec docker build "${common[@]}" \
    --build-context "engine_archive=$SIM_ASSET_CACHE" \
    -t "${SIM_IMAGE:-simulator01:humble-adapter}" "$@" "$here"
