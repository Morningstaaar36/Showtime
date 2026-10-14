# Third-party licences

Showtime itself: Apache-2.0 (see `LICENSE`). Downloaded data and model weights are **not** committed.

| Component | Licence | Use |
| --- | --- | --- |
| JuPedSim 1.4 | LGPL-3.0-or-later | Crowd simulation (unmodified, installed in the sandbox image) |
| PedPy 1.5 | MIT | Exit-area density metrics; flow measurement for the simulator validation |
| Shapely, NumPy, SciPy, NetworkX | BSD | Geometry, numerics, flow model |
| PyniteFEA | MIT | Stage frame model |
| FastAPI, Pydantic, SQLModel, Alembic, pluggy, import-linter | MIT | API and plugin system |
| React, three.js, React Three Fiber, drei, postprocessing, React Flow, Recharts, TanStack Query, Zustand, Radix UI, lucide | MIT / ISC | Web app |
| Tailwind CSS | MIT | Styling |
| Public Sans | SIL Open Font License 1.1 | Typeface (self-hosted via Fontsource) |
| llama.cpp | MIT | Local inference server (prebuilt release) |
| NVIDIA Nemotron Nano 9B v2 (GGUF by dominguesm) | NVIDIA Open Model License | Local LLM (downloaded at setup) |
| Crowd accidents 1900–2024 (Feliciani et al.), Zenodo 10.5281/zenodo.19483010 | CC BY 4.0 | Incident dataset for the red team (downloaded at setup; cited per attack) |
| Jülich pedestrian dynamics archive: Bottleneck, Caserne (Düsseldorf, 2006), DOI 10.34735/ped.2006.2 (Forschungszentrum Jülich; experiments funded by DFG projects KL 1873/1-1 and SE 1789/1-1) | CC BY 4.0 | Simulator validation (`make validate`, `docs/VALIDATION.md`); downloaded by `scripts/get_data.sh`, never committed. Cite: Seyfried, Rupprecht, Passon, Steffen, Klingsch, Boltes, *New insights into pedestrian flow through bottlenecks*, Transportation Science 43 (2009) 395–406, doi:10.1287/trsc.1090.0263 (arXiv physics/0702004); Seyfried et al., *Enhanced empirical data for the fundamental diagram and the flow through bottlenecks*, PED 2008 (Springer 2010), arXiv:0810.1945 |
| Open-Meteo data | CC BY 4.0 (free non-commercial API) | Wind gust forecasts |
| Tavily | API terms | Optional live web evidence |
| OpenStreetMap data (via Nominatim and Overpass) | ODbL 1.0; usage policies: identify the app, ≤ 1 request/s, cache | Real-place import and map; attribution shown on the map, in the preview and in reports |
| OpenStreetMap standard tiles | ODbL data, tile usage policy (light use, attribution) | Street-map ground under real sites in the 3D view |
| MapLibre GL JS 6.11 | BSD-3-Clause | 3D map for picking a real place |
| OpenFreeMap vector tiles and styles | Free, no key; data © OpenMapTiles and OpenStreetMap contributors | Map style and fallback map data |
| mapbox-vector-tile 2.1 | MIT | Decoding vector tiles on the server (fallback map data) |
| matplotlib colormaps (cividis, inferno) | PSF-based matplotlib licence (values only) | Heatmap colours |
