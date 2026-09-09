/**
 * exposureBadges — RED: module does not exist yet.
 *
 * Contract: backend exposure rules (TOXIC_FLOW, GAMMA_FLIP, VEX_WALL,
 * CHARM_PIN, LIQUIDITY_STRESS) map to badge descriptors with heuristic
 * copy. Unknown/missing rules map to null — never invent a badge.
 */
import { exposureBadgeFor, EXPOSURE_RULES } from "./exposureBadges";

describe("exposureBadgeFor", () => {
  test("TOXIC_FLOW maps with heuristic disclaimer", () => {
    const b = exposureBadgeFor("TOXIC_FLOW");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("TOXIC_FLOW");
    expect(b.label).toBe("TOXIC FLOW");
    expect(b.title).toMatch(/heuristic/i);
  });

  test("GAMMA_FLIP maps with proximity disclaimer", () => {
    const b = exposureBadgeFor("GAMMA_FLIP");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("GAMMA_FLIP");
    expect(b.label).toBe("GAMMA FLIP");
    expect(b.title).toMatch(/proximity|flip/i);
  });

  test("VEX_WALL maps", () => {
    const b = exposureBadgeFor("VEX_WALL");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("VEX_WALL");
    expect(b.label).toBe("VEX WALL");
  });

  test("CHARM_PIN maps", () => {
    const b = exposureBadgeFor("CHARM_PIN");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("CHARM_PIN");
    expect(b.label).toBe("CHARM PIN");
  });

  test("LIQUIDITY_STRESS maps", () => {
    const b = exposureBadgeFor("LIQUIDITY_STRESS");
    expect(b).not.toBeNull();
    expect(b.rule).toBe("LIQUIDITY_STRESS");
    expect(b.label).toBe("LIQUIDITY STRESS");
  });

  test("unknown rule maps to null — never invent a badge", () => {
    expect(exposureBadgeFor("FOLLOW")).toBeNull();
    expect(exposureBadgeFor("SOURCE")).toBeNull();
    expect(exposureBadgeFor("CHARM_PINNING")).toBeNull();
    expect(exposureBadgeFor("SOMETHING_NEW")).toBeNull();
  });

  test("missing/empty input maps to null", () => {
    expect(exposureBadgeFor(null)).toBeNull();
    expect(exposureBadgeFor(undefined)).toBeNull();
    expect(exposureBadgeFor("")).toBeNull();
  });

  test("lookup is case-insensitive (backend kinds are lowercase)", () => {
    expect(exposureBadgeFor("toxic_flow")).not.toBeNull();
    expect(exposureBadgeFor("gamma_flip")).not.toBeNull();
  });

  test("EXPOSURE_RULES lists exactly the five wired rules", () => {
    expect([...EXPOSURE_RULES].sort()).toEqual(
      ["CHARM_PIN", "GAMMA_FLIP", "LIQUIDITY_STRESS", "TOXIC_FLOW", "VEX_WALL"].sort()
    );
  });

  test("E4-48 D2: vex_wall_broken rows do not claim defending", () => {
    const b = exposureBadgeFor("VEX_WALL", {
      key: "exposure:vex_wall_broken:SPY::65000",
    });
    expect(b).not.toBeNull();
    expect(b.label).toBe("VEX WALL");
    expect(b.title.toLowerCase()).toContain("released");
    expect(b.title.toLowerCase()).not.toContain("defending");
  });

  test("E4-48 D2: kind string form works; formed rows keep defending copy", () => {
    const broken = exposureBadgeFor("VEX_WALL", "vex_wall_broken");
    expect(broken.title.toLowerCase()).toContain("released");
    const formed = exposureBadgeFor("VEX_WALL", {
      key: "exposure:vex_wall_formed:SPY::65000",
    });
    expect(formed.title.toLowerCase()).toContain("defending");
    const bare = exposureBadgeFor("VEX_WALL");
    expect(bare.title.toLowerCase()).toContain("defending");
  });

  test("E4-48 D2: context_json string form carries the kind", () => {
    const b = exposureBadgeFor("VEX_WALL", {
      rule: "VEX_WALL",
      context_json: JSON.stringify({ magnitude: 1, kind: "vex_wall_broken" }),
    });
    expect(b.title.toLowerCase()).toContain("released");
  });

  test("E4-48 D3: gamma_flip_approach rows do not claim a regime flip", () => {
    const b = exposureBadgeFor("GAMMA_FLIP", {
      key: "exposure:gamma_flip_approach:SPY::65000",
    });
    expect(b).not.toBeNull();
    expect(b.label).toBe("GAMMA FLIP");
    expect(b.title.toLowerCase()).toContain("pressing");
    expect(b.title.toLowerCase()).not.toContain("flipped from positive");
  });
});
