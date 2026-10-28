/** The sandbox's guarantees as short rows for the header badge (from GET /health). */
import type { SandboxIsolation } from "@/api/types";
import { t } from "@/i18n";

interface SandboxFact { key: string; text: string; ok: boolean }

export function sandboxFacts(iso: SandboxIsolation | undefined, timeLimitS?: number): SandboxFact[] {
  if (!iso || iso.kind === "none") return [];
  const facts: SandboxFact[] = [{ key: "fresh", text: t("common.sandbox_one_per_run"), ok: true }];
  facts.push(iso.network_off
    ? { key: "net", text: t("common.sandbox_no_network"), ok: true }
    : { key: "net", text: t("common.sandbox_network_default"), ok: false });
  if (iso.memory) facts.push({ key: "mem", text: t("common.sandbox_memory", { m: iso.memory.toUpperCase().replace(/([0-9.]+)([KMG])$/, "$1 $2B") }), ok: true });
  if (iso.cpus) facts.push({ key: "cpu", text: t("common.sandbox_cpu", { n: String(iso.cpus) }), ok: true });
  if (iso.read_only) facts.push({ key: "ro", text: t("common.sandbox_read_only"), ok: true });
  if (iso.process_limit) facts.push({ key: "pids", text: t("common.sandbox_processes", { n: String(iso.process_limit) }), ok: true });
  if (iso.non_root) facts.push({ key: "root", text: t("common.sandbox_non_root"), ok: true });
  if (timeLimitS) facts.push({ key: "time", text: t("common.sandbox_time", { s: String(Math.round(timeLimitS)) }), ok: true });
  return facts;
}
