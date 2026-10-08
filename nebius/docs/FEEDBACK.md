# Feedback on Nebius Token Factory, Nebius Sandboxes and NVIDIA Nemotron

Notes collected while building Showtime. Honest, specific, and meant to help.

## NVIDIA Nemotron Nano 9B v2 (local, GGUF Q4_K_M on llama.cpp)

**What worked**
- Runs comfortably on a 16 GB consumer GPU (≈ 6.4 GB VRAM at 8k context) and is fast enough
  for interactive editing.
- The `/no_think` and `/think` system-prompt switches work as documented; we use reasoning off
  for JSON-producing calls and it stays reliable.
- With grammar-constrained JSON (llama-server `response_format: json_schema`) it scored 10/10
  on our scripted venue-edit requests.

**What tripped us up**
- With discriminated unions (a list of edit operations), the model picked the wrong operation
  when the tag field was optional and listed last in the schema. Making the tag the first,
  required property raised accuracy from 6/10 to 10/10. Worth a line in the model card's
  structured-output guidance.
- llama.cpp mmaps the model by default, which counts ~4.4 GB of resident RAM on a 14 GB
  machine. `--load-mode dio` and a small `--cache-ram` fixed it. Not Nemotron-specific, but
  a "small machine" recipe next to the GGUF would save people an OOM.
- Numbers in free text: the model occasionally paraphrases a computed value ("about 300 s").
  We enforce a number check and regenerate once; a template fallback covers the rest.

## Nebius Token Factory

- OpenAI-compatible API means the same adapter serves local and cloud; only base URL, key and
  model ids change. Clear win.
- Wish: a machine-readable price list (per model, in/out per 1M tokens) so the cost meter can
  be configured without copying values from the console. Prices are configurable in `.env`.
- Status: adapter implemented and unit-tested; `make smoke-nebius` ready. *Untested with a
  live key at the time of writing* (see `docs/HANDOFF.md`).

## Nebius Sandboxes (contree-sdk 0.3.6)

- The image-as-snapshot model maps beautifully onto red-team branching: base image → venue
  image → attack child → fix child. The UI branch tree is literally the snapshot tree.
- We verified the API against the SDK source (`Contree(base_url, token)`, `images.oci`,
  `image.run(shell=..., files=..., disposable=False)`, `image.read(path)`). The docs pages for
  branching were thinner than the code; a full end-to-end example that writes input files,
  runs a command, and reads an output file back would help.
- Beta access is gated; the runner is built and tested against a fake client and marked
  "untested: no access" until a key is available.

## Tavily

- Simple client, good snippets. We cache every call on disk and cap calls per session; the
  app degrades to the incident dataset when the key is absent.
