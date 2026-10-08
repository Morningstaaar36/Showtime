# ADR 0002: React Three Fiber instead of forking Pascal Editor

**Status:** accepted · 2026-10-08

## Context
We need a 3D venue view with editing, 6,000 animated people and GPU heatmaps, on a 16 GB laptop next to VS Code.

## Decision
Build the scene with React Three Fiber + drei (+ postprocessing for ambient occlusion). Pascal Editor (MIT) was considered but brings WebGPU and a large monorepo.

## Consequences
Small, focused scene code (`web/src/scene`): instanced people, a shader heatmap with an outlined danger contour, section-cut walls. Pascal can be revisited for richer CAD editing.
