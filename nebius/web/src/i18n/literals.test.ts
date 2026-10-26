import { readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

/** No UI text is written in a component: every string a person sees comes from en.json through
 * t(), so copy is in one place and can be translated. Checked with the TypeScript parser:
 * text between tags, the attributes people read (aria-label, placeholder, title, alt), and
 * strings shown from inside {…} or passed to toast(). Class names and ids are not text. */
const READ_ATTRS = new Set(["aria-label", "placeholder", "title", "alt", "aria-description", "thumbLabel"]);
const NOT_TEXT_ATTRS = /^(className|class|key|href|to|id|type|variant|tone|size|side|align|role|data-|style|name|value|accept|autoComplete|inputMode|method)/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "ui" ? [] : files(p); // shadcn primitives: no copy
    return f.endsWith(".tsx") && !f.includes(".test.") ? [p] : [];
  });
}

const words = (s: string) => /[A-Za-z]{2,}.*\s+.*[A-Za-z]{2,}/.test(s) || /^[A-Z][a-z]{2,}/.test(s.trim());
const isClassList = (s: string) =>
  s.trim().split(/\s+/).every((w) => /^[a-z0-9:\-/[\].%()_!>#&*=,'"]+$/i.test(w) && (/[-/:[]/.test(w) || /^(absolute|relative|flex|grid|block|hidden|inline|isolate|truncate|tabular|italic|underline)$/.test(w)));

function shown(node: ts.Node): boolean {
  let p = node.parent;
  while (p && (ts.isConditionalExpression(p) || ts.isBinaryExpression(p) || ts.isParenthesizedExpression(p))) p = p.parent;
  if (p && ts.isJsxExpression(p)) {
    const attr = p.parent && ts.isJsxAttribute(p.parent) ? p.parent.name.getText() : null;
    return attr === null || READ_ATTRS.has(attr) || !NOT_TEXT_ATTRS.test(attr);
  }
  return !!p && ts.isCallExpression(p) && /^toast(\.\w+)?$/.test(p.expression.getText()) && p.arguments[0] === node;
}

function literals(file: string): string[] {
  const src = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const out: string[] = [];
  const at = (n: ts.Node) => `${basename(file)}:${src.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  const visit = (n: ts.Node) => {
    if (ts.isJsxText(n) && /[A-Za-z]{2,}/.test(n.text) && /[a-z]/.test(n.text)) out.push(`${at(n)} text "${n.text.trim().slice(0, 60)}"`);
    if (ts.isJsxAttribute(n) && READ_ATTRS.has(n.name.getText()) && n.initializer && ts.isStringLiteral(n.initializer) && /[A-Za-z]{2,}/.test(n.initializer.text)) {
      out.push(`${at(n)} ${n.name.getText()}="${n.initializer.text.slice(0, 60)}"`);
    }
    if ((ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) && shown(n) && words(n.text) && !isClassList(n.text)) out.push(`${at(n)} "${n.text.slice(0, 60)}"`);
    if (ts.isTemplateExpression(n) && shown(n)) {
      const text = n.getText().replace(/\$\{[^}]*\}/g, "");
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

  it("the check finds text written in a component", () => {
    const probe = join(__dirname, "__probe_literals.tsx");
    const sample = 'export const A = () => <button aria-label="Close it" title={ok ? "Saved" : "Not saved"}>Delete the plan</button>;\n';
    writeFileSync(probe, sample);
    try {
      expect(literals(probe).length).toBe(4);
    } finally {
      rmSync(probe);
    }
  });
});
