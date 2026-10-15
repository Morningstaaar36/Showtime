import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import type { SimulatorValidation } from "@/api/types";
import { SimulatorCheck } from "@/pages/Help";
import fixture from "./fixtures/validation.json";
import { validationRows } from "./ValidationChart";

const data = fixture as SimulatorValidation;
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let cleanup: (() => void) | null = null;
afterEach(() => cleanup?.());

function render(node: React.ReactNode): HTMLElement {
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => root.render(node));
  cleanup = () => { act(() => root.unmount()); el.remove(); };
  return el;
}

describe("validation chart (T-N10-2)", () => {
  it("rows are sorted by width with the min-max band", () => {
    const rows = validationRows(data);
    expect(rows.map((r) => r.b)).toEqual([0.9, 1.2, 2.5]);
    expect(rows[0].range[0]).toBeLessThanOrEqual(rows[0].median);
    expect(rows[0].range[1]).toBeGreaterThanOrEqual(rows[0].median);
  });

  it("renders the chart, the error in words and the limits from the JSON", () => {
    const el = render(<SimulatorCheck data={data} chartWidth={600} />);
    const chart = el.querySelector("[data-testid=validation-chart]");
    expect(chart?.querySelector("svg")).not.toBeNull();
    // one measured point and one median dot per width
    expect(chart?.querySelectorAll(".recharts-scatter-symbol").length).toBe(3);
    expect(chart?.querySelectorAll(".recharts-line-dot, .recharts-dot").length).toBeGreaterThanOrEqual(3);
    expect(el.querySelector("[data-testid=validation-verdict]")?.textContent).toContain("55% lower");
    expect(el.textContent).toContain("No pushing forces");
    expect(el.textContent).toContain("10.34735/ped.2006.2");
    expect(el.querySelectorAll("tbody tr").length).toBe(3);
  });
});
