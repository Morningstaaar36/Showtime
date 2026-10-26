import en from "./en.json";

type Dict = { [k: string]: string | Dict };

const dict: Dict = en as Dict;

/** Look up a UI string by dotted key and fill `{name}` placeholders. All copy lives in en.json. */
export function t(key: string, vars?: Record<string, string | number>): string {
  let node: string | Dict | undefined = dict;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) break;
    node = node[part];
  }
  let s = typeof node === "string" ? node : key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
  }
  return s;
}

/** A group of items in en.json (e.g. the example sentences under one key), in file order, each
 * with its own fields; [] when the key is not a group. */
export function tItems(key: string): Record<string, string>[] {
  let node: string | Dict | undefined = dict;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return [];
    node = node[part];
  }
  if (typeof node !== "object" || node === null) return [];
  return Object.values(node).filter((v): v is Dict => typeof v === "object" && v !== null)
    .map((item) => Object.fromEntries(Object.entries(item).filter(([, v]) => typeof v === "string")) as Record<string, string>);
}
