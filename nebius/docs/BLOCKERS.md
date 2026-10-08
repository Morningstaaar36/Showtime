# Blockers

| Date | Blocker | What I tried | Resolution |
| --- | --- | --- | --- |
| 2026-10-08 | `git clone` of llama.cpp and GitHub source tarballs fail (HTTP/2 stream CANCEL) | git clone --depth 1; codeload tarball; HTTP/1.1 retry | Used the official prebuilt CUDA release asset with `curl --http1.1 -C -` resume loop |
| 2026-10-08 | Docker has no NVIDIA runtime (Docker Desktop VM) | — | llama-server runs natively on the host GPU (brief §18 fallback) |
| 2026-10-08 | Docker Desktop VM has 3.3 GiB RAM (< 4 GB sim budget) | — | `SIM_MEM_LIMIT=2g`; web container serves a static build; one sim at a time |
| 2026-10-08 | API container reported "database disk image is malformed" while a host script (demo precompute) wrote the same SQLite file | Host-side `PRAGMA integrity_check` was ok; only the container view was broken | SQLite WAL needs shared memory that is not coherent across the Docker Desktop VM file share. Host scripts (precompute, calibrate) now use scratch databases in `cache/tmp/`; only one API (compose or `make dev`) may own `state/` at a time |
