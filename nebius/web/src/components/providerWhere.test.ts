import { describe, expect, it } from "vitest";
import type { ProviderStatus } from "@/api/types";
import { providerWhere } from "./ProviderBadge";

const p = (x: Partial<ProviderStatus>) => ({ ok: true, detail: "", ...x }) as ProviderStatus;

describe("where the AI runs, from what the provider says it is", () => {
  it("names a hosted provider by its title, adding its label when the title does not say it", () => {
    expect(providerWhere(p({ is_cloud: true, title: "Acme Inference", label: "ACME" }))).toBe("AI runs on Acme Inference");
    expect(providerWhere(p({ is_cloud: true, title: "OpenAI-compatible API", label: "OPENROUTER" }))).toBe("AI runs on OpenAI-compatible API (OPENROUTER)");
  });
  it("works for a provider it has never heard of", () => {
    expect(providerWhere(p({ is_cloud: true, title: "Zeta Cloud", label: "ZC", provider: "zeta" }))).toBe("AI runs on Zeta Cloud (ZC)");
    expect(providerWhere(p({ is_cloud: false, provider: "anything" }))).toBe("AI runs on this computer");
  });
});
