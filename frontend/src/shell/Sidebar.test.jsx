/**
 * @jest-environment jsdom
 */
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import Sidebar from "./Sidebar";
import { SIDEBAR_KEY } from "./navConfig";

beforeEach(() => localStorage.clear());

test("renders nav items and reflects active page", () => {
  render(<Sidebar page="trinity" onNavigate={() => {}} />);
  // Pin to current NAV_ITEMS (Flow Alerts left the config long ago; the
  // Heatseeker entry is the stable first Decoder item).
  expect(screen.getByRole("button", { name: /Heatseeker/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Trinity/ })).toHaveAttribute("aria-current", "page");
});

test("clicking a nav item calls onNavigate with its id", () => {
  const onNavigate = jest.fn();
  render(<Sidebar page="trinity" onNavigate={onNavigate} />);
  fireEvent.click(screen.getByRole("button", { name: /Heatseeker/ }));
  expect(onNavigate).toHaveBeenCalledWith("heatseeker");
});

test("collapse toggle persists to localStorage apw.sidebarCollapsed", () => {
  render(<Sidebar page="trinity" onNavigate={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: /collapse sidebar/i }));
  expect(localStorage.getItem(SIDEBAR_KEY)).toBe("true");
});
