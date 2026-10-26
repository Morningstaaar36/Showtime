import { describe, expect, it } from "vitest";
import { acceptFor, typesText } from "./importTypes";

const kinds = [
  { label: "Showtime project", extensions: [".showtime.zip"] },
  { label: "Venue JSON", extensions: [".json"] },
  { label: "DXF drawing", extensions: [".dxf"] },
];

describe("what the import accepts, from the server's importers", () => {
  it("builds the file picker's accept list (a browser matches the last extension)", () => {
    expect(acceptFor(kinds)).toBe(".zip,.json,.dxf");
  });
  it("names every type for the hint", () => {
    expect(typesText(kinds)).toBe(".showtime.zip, .json, .dxf");
  });
});
