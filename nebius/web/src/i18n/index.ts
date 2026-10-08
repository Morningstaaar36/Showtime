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
