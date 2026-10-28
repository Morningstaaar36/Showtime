import { readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

/** No UI text is written in a component: every string a person sees comes from en.json through
 * t(), so copy is in one place and can be translated. Checked with the TypeScript parser:
 * text between tags (units such as " m" too), the attributes people read (aria-label,
 * placeholder, title, alt, units, and props such as label or body), strings shown from inside
 * {…} or passed to toast() (also when joined with +), text fields of objects ({ label: "…" }),
 * tables of labels, messages handed to submit() or notify(), template strings with words in
 * them, and sentences kept in arrays or passed to a function. Class names, ids, paths and CSS
 * values are not text. */
const READ_ATTRS = new Set(["aria-label", "placeholder", "title", "alt", "aria-description", "thumbLabel"]);
/** Units are short ("m", " s") but still read, so any letter counts. */
const UNIT_ATTRS = new Set(["unit", "suffix", "prefix"]);
const NOT_TEXT_ATTRS = /^(className|class|key|href|to|id|type|variant|tone|size|side|align|role|data-|style|name|value|accept|autoComplete|inputMode|method|preserveAspectRatio|viewBox|d$|fill|stroke)/;
/** Object fields that end up on screen wherever the object is built. */
const TEXT_PROPS = /^(name|label|caption|message|title|description|hint|body|headline|lead|tip|text)$/;
/** Calls whose string argument is the message a person sees after a change. */
const MESSAGE_CALLS = /^(submit\w*|notify|announce)$/;
/** Tables named for what they hold (KIND_LABEL, STEP_TITLES): every value in them is read. */
const LABEL_TABLES = /(LABELS?|CAPTIONS?|TITLES?)$/;

function files(dir: string, ext = ".tsx"): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "ui" || f === "types" ? [] : files(p, ext); // shadcn primitives, generated types: no copy
    return f.endsWith(ext) && !f.includes(".test.") ? [p] : [];
  });
}

/** Modules whose sentences are not UI text: the example analysis script (Python run in the
 * sandbox), the names of 3D meshes and the node names written into an exported GLB. */
const NOT_UI_MODULES = new Set(["analysis.ts", "building.ts", "exportGlb.ts"]);

/** Sentences in plain modules (labels and messages built outside components). */
function moduleSentences(file: string): string[] {
  if (NOT_UI_MODULES.has(basename(file))) return [];
  const src = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const out: string[] = [];
  const at = (n: ts.Node) => `${basename(file)}:${src.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  const visit = (n: ts.Node) => {
    let text: string | null = null;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) text = n.text;
    else if (ts.isTemplateExpression(n)) text = n.getText().slice(1, -1).replace(/\$\{[^}]*\}/g, "").trim();
    // an import path or a key is not a sentence; "Why is this red?" is
    if (text && sentence(text) && !(n.parent && ts.isImportDeclaration(n.parent))) out.push(`${at(n)} "${text.slice(0, 60)}"`);
    else {
      const found = anywhere(n);
      if (found) out.push(`${at(n)} ${found}`);
    }
    ts.forEachChild(n, visit);
  };
  visit(src);
  return out;
}

const words = (s: string) => /[A-Za-z]{2,}.*\s+.*[A-Za-z]{2,}/.test(s) || /^[A-Z][a-z]{2,}/.test(s.trim());
// "Open-air" and "What-if" have a hyphen like a class name, but class names are not capitalised
const isClassList = (s: string) =>
  s.trim().split(/\s+/).every((w) => /^[a-z0-9:\-/[\].%()_!>#&*=,'"]+$/i.test(w) && !/^[A-Z][a-z]/.test(w)
    && (/[-/:[]/.test(w) || /^(absolute|relative|flex|grid|block|hidden|inline|isolate|truncate|tabular|italic|underline)$/.test(w)));

/** A sentence: a capitalised word followed by more ("Find your place", "Exit 3 is closed."). */
const sentence = (s: string) => /^[A-Z][a-z]+(\s+\S+)+$/.test(s.trim());

/** Static text of a template string, ${…} parts removed. */
const templateText = (n: ts.TemplateExpression | ts.NoSubstitutionTemplateLiteral) =>
  n.getText().slice(1, -1).replace(/\$\{[^}]*\}/g, " ");
/** Two or more words of letters ("metres wide"), not a path, URL, query, CSS value or transform. */
const templateWords = (s: string) =>
  s.split(/\s+/).filter((w) => /^[A-Za-z’']{2,}[.,:;!?…]?$/.test(w)).length >= 2
  && !isClassList(s) && !/[/?=&]|https?:|\b(translate|calc|rotate|scale|rgba?|hsla?|var)\(/.test(s)
  && !s.trim().split(/\s+/).every((w) => /^(-?[\d.]*(px|em|rem|vh|vw|deg|ms|s|fr|%)?|solid|dashed|auto|none|[,()]+)$/.test(w));

/** Where a value ends up: up through ?: branches, joins with + and fallbacks (?? || &&), not
 * through conditions or comparisons ({kind === "exit" && …} shows nothing of "exit"). */
function reach(node: ts.Node): { child: ts.Node; p: ts.Node | undefined } {
  let child = node;
  let p = node.parent;
  const passes = (q: ts.Node) =>
    ts.isParenthesizedExpression(q) || ts.isAsExpression(q)
    || (ts.isConditionalExpression(q) && q.condition !== child)
    || (ts.isBinaryExpression(q) && [ts.SyntaxKind.PlusToken, ts.SyntaxKind.QuestionQuestionToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.AmpersandAmpersandToken].includes(q.operatorToken.kind)
      && !(q.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken && q.left === child));
  while (p && passes(p)) { child = p; p = p.parent; }
  return { child, p };
}

/** The name of the call a value is passed to, if any. */
function callee(node: ts.Node): string | null {
  const { child, p } = reach(node);
  if (!p || !ts.isCallExpression(p) || !p.arguments.includes(child as ts.Expression)) return null;
  return ts.isPropertyAccessExpression(p.expression) ? p.expression.name.text : p.expression.getText();
}

/** Chart text handed to Recharts as data: label={{ value: "danger" }} on a reference line, and
 * the [value, name] pair a tooltip formatter returns. */
function chartText(n: ts.Node): boolean {
  const { child, p } = reach(n);
  if (!p) return false;
  const attrOf = (o: ts.Node) => {
    let q = o.parent;
    while (q && (ts.isParenthesizedExpression(q) || ts.isArrowFunction(q) || ts.isJsxExpression(q))) q = q.parent;
    return q && ts.isJsxAttribute(q) ? q.name.getText() : null;
  };
  if (ts.isPropertyAssignment(p) && p.name.getText() === "value" && attrOf(p.parent) === "label") return true;
  return ts.isArrayLiteralExpression(p) && p.elements.includes(child as ts.Expression) && attrOf(p) === "formatter";
}

/** Checks that hold in every file, component or module: text fields of objects, tables of
 * labels, units given as defaults, messages passed to submit()/notify(), and template strings
 * with words. "" when the node is not text. */
function anywhere(n: ts.Node): string {
  const isString = ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n);
  if (!isString && !ts.isTemplateExpression(n)) return "";
  const text = isString ? n.text : templateText(n);
  const short = text.trim().slice(0, 60);
  const { p } = reach(n);
  if (p && ts.isPropertyAssignment(p) && TEXT_PROPS.test(p.name.getText().replace(/["']/g, "")) && words(text) && !isClassList(text)) {
    return `${p.name.getText()}: "${short}"`;
  }
  const table = p && (ts.isPropertyAssignment(p) || ts.isArrayLiteralExpression(p)) ? p.parent : undefined;
  if (table && (ts.isObjectLiteralExpression(table) || ts.isArrayLiteralExpression(table)) && /[A-Za-z]{2,}/.test(text)) {
    let decl: ts.Node = table.parent;
    while (ts.isAsExpression(decl) || ts.isSatisfiesExpression(decl)) decl = decl.parent;
    if (ts.isVariableDeclaration(decl) && LABEL_TABLES.test(decl.name.getText())) return `in ${decl.name.getText()} "${short}"`;
  }
  if (p && (ts.isParameter(p) || ts.isBindingElement(p)) && UNIT_ATTRS.has(p.name.getText()) && /[A-Za-z]/.test(text)) return `${p.name.getText()} = "${short}"`;
  if (chartText(n) && /[A-Za-z]{2,}/.test(text)) return `chart "${short}"`;
  const call = callee(n);
  if (call && MESSAGE_CALLS.test(call) && words(text)) return `${call}("${short}")`;
  const attr = shownIn(n);
  if (!ts.isStringLiteral(n) && templateWords(text) && !(attr && NOT_TEXT_ATTRS.test(attr))) return n.getText().slice(0, 60);
  return "";
}

function shown(node: ts.Node): boolean {
  const { child, p } = reach(node);
  if (p && ts.isJsxExpression(p)) {
    const attr = p.parent && ts.isJsxAttribute(p.parent) ? p.parent.name.getText() : null;
    return attr === null || READ_ATTRS.has(attr) || !NOT_TEXT_ATTRS.test(attr);
  }
  const isToast = (n: ts.Node | undefined): n is ts.CallExpression => !!n && ts.isCallExpression(n) && /^toast(\.\w+)?$/.test(n.expression.getText());
  // toast("…", { description: "…", action: { label: "…" } })
  if (p && ts.isPropertyAssignment(p) && /^(description|title|label)$/.test(p.name.getText())) {
    let o: ts.Node | undefined = p.parent;
    while (o && (ts.isObjectLiteralExpression(o) || ts.isPropertyAssignment(o))) o = o.parent;
    if (isToast(o)) return true;
  }
  return isToast(p) && p.arguments[0] === child;
}

/** The JSX attribute a value is shown in, or null between tags ({blocked ? " · blocked" : ""}). */
function shownIn(node: ts.Node): string | null {
  const { p } = reach(node);
  return p && ts.isJsxExpression(p) && p.parent && ts.isJsxAttribute(p.parent) ? p.parent.name.getText() : null;
}

function literals(file: string): string[] {
  const src = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const out: string[] = [];
  const at = (n: ts.Node) => `${basename(file)}:${src.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  const visit = (n: ts.Node) => {
    const before = out.length;
    // a unit between tags ("{width} m") is text too
    if (ts.isJsxText(n) && /[A-Za-z]/.test(n.text) && /[a-z]/.test(n.text)) out.push(`${at(n)} text "${n.text.trim().slice(0, 60)}"`);
    if (ts.isJsxAttribute(n) && n.initializer && ts.isStringLiteral(n.initializer)) {
      const attr = n.name.getText();
      const text = n.initializer.text;
      if (UNIT_ATTRS.has(attr) ? /[A-Za-z]/.test(text)
        : READ_ATTRS.has(attr) ? /[A-Za-z]{2,}/.test(text) : !NOT_TEXT_ATTRS.test(attr) && words(text) && !isClassList(text)) {
        out.push(`${at(n)} ${attr}="${text.slice(0, 60)}"`);
      }
    }
    if (ts.isStringLiteral(n) && ts.isArrayLiteralExpression(n.parent) && sentence(n.text)) out.push(`${at(n)} in a list "${n.text.slice(0, 60)}"`);
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n)) {
      const text = ts.isTemplateExpression(n) ? n.getText().slice(1, -1).replace(/\$\{[^}]*\}/g, "") : n.text;
      const joined = !!n.parent && ts.isBinaryExpression(n.parent) && n.parent.operatorToken.kind === ts.SyntaxKind.PlusToken && /[A-Za-z]{3,}/.test(text);
      const attr = shownIn(n);
      // between tags or as a unit even one word is read; in other props it takes more to be text
      const read = attr === null ? /[A-Za-z]{2,}/.test(text) : UNIT_ATTRS.has(attr) ? /[A-Za-z]/.test(text) : words(text);
      if (shown(n) && (read || joined) && !isClassList(text)) out.push(`${at(n)} ${ts.isTemplateExpression(n) ? n.getText().slice(0, 60) : `"${text.slice(0, 60)}"`}`);
      else if (ts.isStringLiteral(n) && sentence(text) && callee(n)) out.push(`${at(n)} ${callee(n)}("${text.slice(0, 60)}")`);
    }
    if (out.length === before) {
      const found = anywhere(n);
      if (found) out.push(`${at(n)} ${found}`);
    }
    ts.forEachChild(n, visit);
  };
  visit(src);
  return out;
}

describe("strings", () => {
  it("no component writes UI text itself: it comes from en.json", () => {
    const found = files(join(__dirname, "..")).flatMap(literals);
    expect(found, `move these into src/i18n/en.json and use t():\n${found.join("\n")}`).toEqual([]);
  });

  it("no module builds UI sentences itself", () => {
    const found = files(join(__dirname, ".."), ".ts").filter((f) => !f.endsWith(".d.ts")).flatMap(moduleSentences);
    expect(found, `move these into src/i18n/en.json and use t():\n${found.join("\n")}`).toEqual([]);
  });

  it("the check finds text written in a component", () => {
    const probe = join(__dirname, "__probe_literals.tsx");
    const sample = 'export const A = () => <button aria-label="Close it" title={ok ? "Saved" : "Not saved"}>Delete the plan</button>;\n'
      + 'export const B = () => <Card body="Runs in the sandbox" onClick={() => toast(name + " started")} />;\n'
      + 'const TIPS = ["Why is this red?", "exit_1"];\n'
      + 'export const C = () => toast.success(done, { description: "Shown from the last run." });\n'
      // text fields of objects, anywhere: a sentence or one capitalised word
      + 'const PRESETS = [{ id: "rain", label: "Rain", hint: "Slower walking in the wet" }];\n'
      // template strings with words, but not class lists, paths, CSS values or keys
      + 'const wide = (n: number) => `${n} metres wide`;\n'
      + 'const NOT_TEXT = [`${a}px ${b}px`, `translate(${x}px, ${y}px)`, `/api/v1/runs?limit=${n}`, `flex ${on ? "gap-2" : ""}`, t(`help.${k}_body`)];\n'
      // sentences with digits, hyphens or punctuation
      + 'const EXAMPLES = ["Add a 3 m exit on the east wall", "Block the south-west gate"];\n'
      // the message handed to submit() or notify()
      + 'const D = () => { submitOps([op], "Added exit"); notify("Saved"); };\n'
      // units
      + 'export const E = () => <><NumberField unit="people" /><Stat unit=" s" />{w} m</>;\n'
      // chart labels
      + 'export const F = () => <><Tooltip formatter={(v) => [fmt(v), "Peak"]} /><ReferenceLine label={{ value: "danger", fill: "var(--danger)" }} /></>;\n';
    writeFileSync(probe, sample);
    try {
      expect(literals(probe).length).toBe(20);
    } finally {
      rmSync(probe);
    }
  });
});
