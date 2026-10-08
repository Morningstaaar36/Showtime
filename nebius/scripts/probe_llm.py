"""Probe the OpenAI-compatible LLM server: plain chat, JSON-schema call, reasoning toggle, speed.

Usage: uv run --project api python scripts/probe_llm.py [base_url] [model]
"""

from __future__ import annotations

import json
import os
import sys
import time

from openai import OpenAI

BASE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
)
MODEL = (
    sys.argv[2]
    if len(sys.argv) > 2
    else os.environ.get("LOCAL_LLM_MODEL", "nemotron-nano-9b-v2-q4_k_m")
)

SCHEMA = {
    "type": "object",
    "properties": {
        "ops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["move", "add_exit"]},
                    "target": {"type": "string"},
                    "dx": {"type": "number"},
                    "dy": {"type": "number"},
                },
                "required": ["op"],
            },
        }
    },
    "required": ["ops"],
}


def main() -> int:
    client = OpenAI(base_url=BASE, api_key=os.environ.get("NEBIUS_API_KEY") or "local")
    ok = True

    t0 = time.time()
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "/no_think"},
            {"role": "user", "content": "In one sentence: why do crowd crushes happen?"},
        ],
        temperature=0.2,
        max_tokens=120,
    )
    dt = time.time() - t0
    text = r.choices[0].message.content or ""
    toks = r.usage.completion_tokens if r.usage else 0
    print(f"[chat]   {dt:.1f}s  {toks} tokens  {toks / max(dt, 1e-6):.0f} tok/s")
    print("         ", text.strip()[:200].replace("\n", " "))
    if "<think>" in text:
        print("         WARNING: reasoning text leaked with /no_think")

    t0 = time.time()
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "/no_think\nReturn only JSON."},
            {"role": "user", "content": "Move the stage 10 m south (negative y)."},
        ],
        temperature=0.0,
        max_tokens=200,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "patch", "schema": SCHEMA, "strict": True},
        },
    )
    dt = time.time() - t0
    raw = r.choices[0].message.content or ""
    try:
        data = json.loads(raw)
        print(f"[json]   {dt:.1f}s  valid JSON: {data}")
    except json.JSONDecodeError:
        ok = False
        print(f"[json]   {dt:.1f}s  INVALID JSON: {raw[:200]}")

    t0 = time.time()
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "/think"},
            {"role": "user", "content": "Is 3 people per m² dangerous? Answer briefly."},
        ],
        temperature=0.2,
        max_tokens=400,
    )
    dt = time.time() - t0
    msg = r.choices[0].message
    reasoning = getattr(msg, "reasoning_content", None) or ""
    print(
        f"[think]  {dt:.1f}s  reasoning chars={len(reasoning)}  "
        f"answer={(msg.content or '').strip()[:120]!r}"
    )
    if r.usage:
        print(
            f"         usage: prompt={r.usage.prompt_tokens} completion={r.usage.completion_tokens}"
        )
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
