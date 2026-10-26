import { readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

/** No UI text is written in a component: every string a person sees comes from en.json through
 * t(), so copy is in one place and can be translated. Checked with the TypeScript parser:
 * text between tags, the attributes people read (aria-label, placeholder, title, alt, and props
 * such as label or body), strings shown from inside {…} or passed to toast() (also when joined
 * with +), and lists of sentences kept in arrays. Class names and ids are not text. */
const READ_ATTRS = new Set(["aria-label", "placeholder", "title", "alt", "aria-description", "thumbLabel"]);
const NOT_TEXT_ATTRS = /^(className|class|key|href|to|id|type|variant|tone|size|side|align|role|data-|style|name|value|accept|autoComplete|inputMode|method|preserveAspectRatio|viewBox|d$|fill|stroke)/;

function files(dir: string, ext = ".tsx"): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "ui" || f === "types" ? [] : files(p, ext); // shadcn primitives, generated types: no copy
    return f.endsWith(ext) && !f.includes(".test.") ? [p] : [];
  });
}

/** Modules whose sentences are not UI text: the example analysis script (Python run in the
 * sandbox) and the names of 3D meshes. */
const NOT_UI_MODULES = new Set(["analysis.ts", "building.ts"]);

/** Sentences in plain modules (labels and messages built outside components). */
function moduleSentences(file: string): string[] {
  if (NOT_UI_MODULES.has(basename(file))) return [];
  const src = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const out: string[] = [];
  const visit = (n: ts.Node) => {
    let text: string | null = null;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) text = n.text;
    else if (ts.isTemplateExpression(n)) text = n.getText().slice(1, -1).replace(/\$\{[^}]*\}/g, "").trim();
    // an import path or a key is not a sentence; "Why is this red?" is
    if (text && sentence(text) && !(n.parent && ts.isImportDeclaration(n.parent))) {
      out.push(`${basename(file)}:${src.getLineAndCharacterOfPosition(n.getStart()).line + 1} "${text.slice(0, 60)}"`);
    }
    ts.forEachChild(n, visit);
  };
  visit(src);
  return out;
}

const words = (s: string) => /[A-Za-z]{2,}.*\s+.*[A-Za-z]{2,}/.test(s) || /^[A-Z][a-z]{2,}/.test(s.trim());
const isClassList = (s: string) =>
  s.trim().split(/\s+/).every((w) => /^[a-z0-9:\-/[\].%()_!>#&*=,'"]+$/i.test(w) && (/[-/:[]/.test(w) || /^(absolute|relative|flex|grid|block|hidden|inline|isolate|truncate|tabular|italic|underline)$/.test(w)));

function shown(node: ts.Node): boolean {
  let child = node;
  let p = node.parent;
  while (p && (ts.isConditionalExpression(p) || ts.isBinaryExpression(p) || ts.isParenthesizedExpression(p))) { child = p; p = p.parent; }
  if (p && ts.isJsxExpression(p)) {
    const attr = p.parent && ts.isJsxAttribute(p.parent) ? p.parent.name.getText() : null;
    return attr === null || READ_ATTRS.has(attr) || !NOT_TEXT_ATTRS.test(attr);
  }
  return !!p && ts.isCallExpression(p) && /^toast(\.\w+)?$/.test(p.expression.getText()) && p.arguments[0] === child;
}

/** A sentence: a capitalised word followed by more words ("Find your place"). */
const sentence = (s: string) => /^[A-Z][a-z]+(\s+[A-Za-z’'²]+)+[?.!]?$/.test(s.trim());

function literals(file: string): string[] {
  const src = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const out: string[] = [];
  const at = (n: ts.Node) => `${basename(file)}:${src.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  const visit = (n: ts.Node) => {
    if (ts.isJsxText(n) && /[A-Za-z]{2,}/.test(n.text) && /[a-z]/.test(n.text)) out.push(`${at(n)} text "${n.text.trim().slice(0, 60)}"`);
    if (ts.isJsxAttribute(n) && n.initializer && ts.isStringLiteral(n.initializer)) {
      const attr = n.name.getText();
      const text = n.initializer.text;
      if (READ_ATTRS.has(attr) ? /[A-Za-z]{2,}/.test(text) : !NOT_TEXT_ATTRS.test(attr) && words(text) && !isClassList(text)) {
        out.push(`${at(n)} ${attr}="${text.slice(0, 60)}"`);
      }
    }
    if (ts.isStringLiteral(n) && ts.isArrayLiteralExpression(n.parent) && sentence(n.text)) out.push(`${at(n)} in a list "${n.text.slice(0, 60)}"`);
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) {
      const joined = !!n.parent && ts.isBinaryExpression(n.parent) && n.parent.operatorToken.kind === ts.SyntaxKind.PlusToken && /[A-Za-z]{3,}/.test(n.text);
      if (shown(n) && (words(n.text) || joined) && !isClassList(n.text)) out.push(`${at(n)} "${n.text.slice(0, 60)}"`);
    }
    if (ts.isTemplateExpression(n) && shown(n)) {
      const text = n.getText().slice(1, -1).replace(/\$\{[^}]*\}/g, "");
      if (words(text) && !isClassList(text)) out.push(`${at(n)} ${n.getText().slice(0, 60)}`);
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
      + 'const TIPS = ["Why is this red?", "exit_1"];\n';
    writeFileSync(probe, sample);
    try {
      expect(literals(probe).length).toBe(7);
    } finally {
      rmSync(probe);
    }
  });
});
