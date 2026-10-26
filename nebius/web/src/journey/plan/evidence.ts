/** The test's evidence: every source the attacks were grounded in, grouped by where it came
 * from (a live web search or the incident dataset), each once, with what it supports. */
import type { Attack } from "@/api/types";

export type Origin = "tavily" | "dataset";

export interface EvidenceItem {
  url: string;
  title: string;
  year: number | null;
  /** the sentence from the source that the attack rests on */
  sentence: string;
  origin: Origin;
  /** titles of the attacks it grounds */
  attacks: string[];
}

export function evidenceGroups(attacks: Attack[], human: (s: string) => string = (s) => s): Record<Origin, EvidenceItem[]> {
  const byUrl = new Map<string, EvidenceItem>();
  for (const a of attacks) {
    const src = a.inspired_by;
    if (!src?.source_url) continue;
    const url = String(src.source_url);
    const item = byUrl.get(url) ?? {
      url, title: src.incident, year: src.year ?? null, sentence: src.evidence ?? "",
      origin: (src.origin === "tavily" ? "tavily" : "dataset") as Origin, attacks: [],
    };
    item.attacks.push(human(a.title));
    byUrl.set(url, item);
  }
  const all = [...byUrl.values()];
  return { tavily: all.filter((e) => e.origin === "tavily"), dataset: all.filter((e) => e.origin === "dataset") };
}

/** "Stadium crush (2023)", but "Venezuela crush 2018" as it is: the year once. */
export function withYear(title: string, year: number | null | undefined): string {
  return year && !title.includes(String(year)) ? `${title} (${year})` : title;
}
