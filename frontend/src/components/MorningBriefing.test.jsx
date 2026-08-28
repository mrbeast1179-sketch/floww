/**
 * @jest-environment jsdom
 */

import React from "react";
import { render } from "@testing-library/react";
import { MorningBriefing } from "./MorningBriefing";

jest.mock("axios", () => ({
  get: jest.fn(() => Promise.reject(new Error("test"))),
  post: jest.fn(() => Promise.reject(new Error("test"))),
}));

describe("MorningBriefing", () => {
  test("renders without crashing on null/undefined props", () => {
    const { container } = render(<MorningBriefing ticker="SPY" spot={null} />);
    expect(container).toBeTruthy();
  });
});
