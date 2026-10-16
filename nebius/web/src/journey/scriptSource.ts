/** The scenario script inside an attack (a `script` event), if it has one. */
export interface ScenarioScript {
  title: string;
  code: string;
  everyS: number;
  /** "ai" for a red-team script, "rules" for the built-in example. */
  author: "ai" | "rules";
}

/** Just the parts of an Attack this reads (its generated `events` type is a fixed tuple). */
export interface WithEvents {
  events: readonly { type: string; [k: string]: unknown }[];
  extensions?: unknown;
}

export function scriptOf(attack: WithEvents | null | undefined): ScenarioScript | null {
  const ev = attack?.events.find((e) => e.type === "script");
  if (!ev || typeof ev.code !== "string") return null;
  const by = (attack?.extensions as Record<string, unknown> | undefined)?.generated_by;
  return {
    title: typeof ev.title === "string" ? ev.title : "",
    code: ev.code,
    everyS: Number(ev.every_s ?? 1),
    author: by === "rules" ? "rules" : "ai",
  };
}
