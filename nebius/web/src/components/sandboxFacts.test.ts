import { describe, expect, it } from "vitest";
import type { SandboxIsolation } from "@/api/types";
import { sandboxFacts } from "./sandboxFacts";

const docker: SandboxIsolation = {
  kind: "container", network_off: true, memory: "2g", cpus: 2, read_only: true,
  process_limit: 256, non_root: true, per_job_limits: true, summary: "",
};

describe("sandbox facts for the header badge", () => {
  it("lists every guarantee of a local container in plain words", () => {
    expect(sandboxFacts(docker, 240).map((f) => f.text)).toEqual([
      "A fresh one for every run", "No network", "Memory capped at 2 GB", "2 CPU",
      "Read-only system", "At most 256 processes", "No admin rights", "Stopped after 240 s",
    ]);
  });
  it("does not claim a network limit a cloud sandbox cannot set", () => {
    const cloud = { ...docker, kind: "cloud" as const, network_off: null, memory: null, cpus: null, read_only: false, process_limit: null, non_root: false, per_job_limits: false };
    const facts = sandboxFacts(cloud, 240);
    expect(facts.find((f) => f.key === "net")).toMatchObject({ ok: false });
    expect(facts.some((f) => f.key === "mem")).toBe(false);
  });
  it("shows nothing for no sandbox", () => {
    expect(sandboxFacts({ ...docker, kind: "none" })).toEqual([]);
    expect(sandboxFacts(undefined)).toEqual([]);
  });
});
