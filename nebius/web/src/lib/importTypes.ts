/** What the project import accepts, from GET /importers (the registered importer plugins), so the
 * file picker and its hint never list file types by hand. */
export interface ImportKind { label: string; extensions: string[] }

const exts = (kinds: ImportKind[]) => kinds.flatMap((k) => k.extensions);

/** The file picker's accept list: browsers match a file's last extension (".showtime.zip" → ".zip"). */
export function acceptFor(kinds: ImportKind[]): string {
  return [...new Set(exts(kinds).map((e) => `.${e.split(".").pop()}`))].join(",");
}

/** Every importable type, for the hint. */
export function typesText(kinds: ImportKind[]): string {
  return exts(kinds).join(", ");
}
