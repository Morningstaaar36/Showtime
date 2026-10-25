#!/bin/sh
# Run the API as the owner of the mounted runs/ folder (the host user), with the group of the
# Docker socket so it can start sandboxes. Nothing to configure: both are read from the mounts,
# so `docker compose up` works with or without make. HOST_UID / HOST_GID override the owner.
set -e
if [ "$(id -u)" = "0" ]; then
  uid="${HOST_UID:-$(stat -c %u /app/runs 2>/dev/null || echo 0)}"
  gid="${HOST_GID:-$(stat -c %g /app/runs 2>/dev/null || echo 0)}"
  groups="$gid"
  if [ -S /var/run/docker.sock ]; then
    groups="$gid,$(stat -c %g /var/run/docker.sock)"
  fi
  if [ "$uid" != "0" ]; then
    exec setpriv --reuid="$uid" --regid="$gid" --groups="$groups" --inh-caps=-all -- "$@"
  fi
fi
exec "$@"
