#!/usr/bin/env bash
# Ask for the hosted app's password and store its bcrypt hash in .env, single-quoted so Docker
# Compose does not read the "$" in the hash as variables. The password itself is never stored.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
read -rp "User name for the hosted app [organizer]: " user
user="${user:-organizer}"
read -rsp "Password: " pw && echo
[ ${#pw} -ge 10 ] || { echo "error: use at least 10 characters" >&2; exit 1; }
hash="$(docker run --rm caddy:2.8.4 caddy hash-password --plaintext "$pw")"
set_var() {  # set_var NAME VALUE: replace the line, or add it
  if grep -q "^$1=" .env; then
    python3 - "$1" "$2" <<'PY'
import re, sys
name, value = sys.argv[1], sys.argv[2]
s = open(".env").read()
s = re.sub(rf"^{name}=.*$", lambda _: f"{name}={value}", s, flags=re.M)
open(".env", "w").write(s)
PY
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}
set_var BASIC_AUTH_USER "$user"
set_var BASIC_AUTH_HASH "'$hash'"
chmod 600 .env
echo "Saved: the hosted app asks for user \"$user\" and that password."
