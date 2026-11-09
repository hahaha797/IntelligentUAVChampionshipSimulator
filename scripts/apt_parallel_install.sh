#!/usr/bin/env bash
set -euo pipefail
# APT still resolves dependencies and verifies repository/package signatures.
# Prefetch its selected archives concurrently, then let APT install normally.
uri_list="$(mktemp)"
trap 'rm -f "$uri_list"' EXIT
apt-get -y --print-uris --no-install-recommends install "$@" \
    | awk '$1 ~ /^\047/ {gsub(/\047/, "", $1); print $1, "/var/cache/apt/archives/" $2, $4}' > "$uri_list"
if [[ -s "$uri_list" ]]; then
    if ! xargs -r -P "${APT_DOWNLOAD_WORKERS:-8}" -n 3 \
        /usr/lib/apt/apt-helper download-file < "$uri_list"; then
        printf 'Some prefetches failed; APT will retry the missing archives.\n' >&2
    fi
fi
for attempt in 1 2 3; do
    if apt-get install -y --no-install-recommends -o Acquire::Retries=5 "$@"; then
        exit 0
    fi
    sleep "$attempt"
done
exit 1
