"""`make setup` downloads the local model (llama.cpp and a 6 GB GGUF) only when the app will use
it: with a hosted model in .env, setup takes minutes, not a large download."""

from __future__ import annotations

import subprocess
from pathlib import Path

from api.core.settings import ROOT_DIR

SCRIPT = ROOT_DIR / "scripts" / "needs_local_model.sh"


def _needs(tmp_path: Path, env: str | None) -> bool:
    f = tmp_path / ".env"
    if env is not None:
        f.write_text(env)
    out = subprocess.run(["bash", str(SCRIPT), str(f)], capture_output=True, text=True)
    return out.returncode == 0


def test_the_local_model_is_needed_only_for_the_local_provider(tmp_path: Path) -> None:
    assert _needs(tmp_path, "LLM_PROVIDER=local\n")
    assert _needs(tmp_path, "LLM_PROVIDER=local   # local | nebius\n")
    assert not _needs(tmp_path, "LLM_PROVIDER=openai\nOPENAI_COMPAT_API_KEY=x\n")
    assert not _needs(tmp_path, 'LLM_PROVIDER="nebius"\n')
    assert _needs(tmp_path, "# no provider line: the default is local\n")
    assert _needs(tmp_path, None)  # no .env yet
