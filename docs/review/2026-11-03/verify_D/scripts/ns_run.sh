#!/bin/sh
# Run a command in a private mount namespace where <copy_dir> is bind-mounted over <target_dir>, so absolute paths in a
# copied sandbox config resolve to the copy (the config hash, which includes the paths, is unchanged) and every write
# lands in the copy. usage: ns_run.sh <copy_dir> <target_dir> <cmd...>
set -e
COPY=$1; TARGET=$2; shift 2
exec unshare --mount --propagation private /bin/sh -c 'mount --bind "$0" "$1" && shift 2 && cd /tmp && exec "$@"' "$COPY" "$TARGET" x "$@"
