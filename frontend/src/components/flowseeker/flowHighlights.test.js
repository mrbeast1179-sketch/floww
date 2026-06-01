import { classificationBadge, rowHighlightClass, sideColor, typeColor } from "./flowHighlights";

test("classificationBadge maps the four literals", () => {
  expect(classificationBadge("sweep").label).toBe("SWP");
  expect(classificationBadge("block").label).toBe("BLK");
  expect(classificationBadge("unusual").label).toBe("UNU");
  expect(classificationBadge("regular")).toBeNull();
});

test("rowHighlightClass flags size>oi and volume>oi", () => {
  expect(rowHighlightClass({ size: 1000, oi: 100, volume: 0 })).toMatch(/amber|rose|sky/);
  expect(rowHighlightClass({ size: 1, oi: 100, volume: 1, vol_oi_ratio: 0 })).toBe("");
});

test("typeColor/sideColor handle case + variants", () => {
  expect(typeColor("CALL")).toContain("emerald");
  expect(typeColor("p")).toContain("rose");
  expect(sideColor("BUY")).toContain("emerald");
});
