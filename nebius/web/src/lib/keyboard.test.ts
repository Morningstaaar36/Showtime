import { describe, expect, it } from "vitest";
import { isTypingTarget } from "./keyboard";

function make(html: string, selector: string): Element {
  const host = document.createElement("div");
  host.innerHTML = html;
  document.body.appendChild(host);
  return host.querySelector(selector)!;
}

describe("isTypingTarget", () => {
  it("skips form controls and editable text", () => {
    expect(isTypingTarget(make("<input />", "input"))).toBe(true);
    expect(isTypingTarget(make("<textarea></textarea>", "textarea"))).toBe(true);
    expect(isTypingTarget(make("<select><option>a</option></select>", "select"))).toBe(true);
    expect(isTypingTarget(make("<div contenteditable='true'><span>x</span></div>", "span"))).toBe(true);
  });
  it("lets shortcuts through elsewhere", () => {
    expect(isTypingTarget(make("<button>b</button>", "button"))).toBe(false);
    expect(isTypingTarget(make("<div contenteditable='false'>x</div>", "div"))).toBe(false);
    expect(isTypingTarget(document.body)).toBe(false);
    expect(isTypingTarget(window)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});
