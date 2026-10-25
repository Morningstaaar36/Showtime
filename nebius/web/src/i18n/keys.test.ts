import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import en from "./en.json";

/** Every t("literal.key") in the app names a string that exists: a missing one would show the
 * raw key on screen ("evidence_panel.origin_dataset"). Keys built at run time are not checked. */
function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return files(p);
    return /\.(ts|tsx)$/.test(f) && !/\.test\.tsx?$/.test(f) ? [p] : [];
  });
}

function has(dict: unknown, key: string): boolean {
  let node = dict as Record<string, unknown> | string | undefined;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null || !(part in node)) return false;
    node = (node as Record<string, unknown>)[part] as Record<string, unknown> | string;
  }
  return typeof node === "string";
}

describe("strings", () => {
  it("every literal key used in the app exists in en.json", () => {
    const root = join(__dirname, "..");
    const missing = new Set<string>();
    for (const f of files(root)) {
      for (const m of readFileSync(f, "utf8").matchAll(/\bt\(\s*"([a-z0-9_]+(?:\.[a-z0-9_]+)+)"/g)) {
        if (!has(en, m[1])) missing.add(`${m[1]} (${f.slice(root.length + 1)})`);
      }
    }
    expect([...missing]).toEqual([]);
  });
});
