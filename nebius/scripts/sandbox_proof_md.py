"""Write the result tables of docs/SANDBOX_PROOF.md from api/data/sandbox_proof.json, the file
`make sandbox-proof` records from the real sandbox, so the document cannot drift from the run.

    python scripts/sandbox_proof_md.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "api" / "data" / "sandbox_proof.json"
DOC = ROOT / "docs" / "SANDBOX_PROOF.md"
START, END = "<!-- proof:start (written by scripts/sandbox_proof_md.py) -->", "<!-- proof:end -->"
TITLES = {
    "scenario": "Scenario scripts (AI-written disasters, run inside the crowd simulation)",
    "code": "Code jobs (the analyst's code and your own scripts)",
}


def cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ") if text is not None else ""


def tables(proof: dict[str, object]) -> str:
    rows = proof["rows"]
    assert isinstance(rows, list)
    out = [
        f"Recorded {proof['recorded_at']} on Docker {proof['docker']} with `{proof['image']}` "
        f"(`{proof['command']}`)."
    ]
    for kind, title in TITLES.items():
        out += [
            "",
            f"### {title}",
            "",
            "| Attack | Static check | Inside the container (the sandbox's own words) | Result |",
            "| --- | --- | --- | --- |",
        ]
        for r in rows:
            if r["kind"] != kind:
                continue
            static = f"refused: {cell(r['static'])}" if r.get("static") else "passes (valid code)"
            out.append(
                f"| {cell(r['label'])} | {static} | {cell(r.get('inside'))} | "
                f"{cell(r.get('status'))}, {cell(r.get('runtime_s'))} s |"
            )
    return "\n".join(out)


def main() -> None:
    proof = json.loads(PROOF.read_text())
    doc = DOC.read_text()
    head, rest = doc.split(START, 1)
    _, tail = rest.split(END, 1)
    DOC.write_text(f"{head}{START}\n{tables(proof)}\n{END}{tail}")
    print(f"wrote the tables of {DOC.relative_to(ROOT)} from {PROOF.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
