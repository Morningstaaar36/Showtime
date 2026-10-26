#!/usr/bin/env bash
# Exit 0 when the app will use the local model (LLM_PROVIDER=local, the default), so setup
# downloads llama.cpp and the GGUF only then. Usage: needs_local_model.sh [path/to/.env]
f="${1:-.env}"
line="$(grep -E '^[[:space:]]*LLM_PROVIDER=' "$f" 2>/dev/null | tail -n 1)"
value="$(printf '%s' "${line#*=}" | sed -e 's/#.*//' -e 's/["'\'' ]//g')"
[ -z "$value" ] || [ "$value" = "local" ]
