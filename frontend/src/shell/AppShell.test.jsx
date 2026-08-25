/**
 * @jest-environment jsdom
 */
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import AppShell from "./AppShell";

test("renders rail + children, and routes nav clicks via onNavigate", () => {
  const onNavigate = jest.fn();
  render(<AppShell page="trinity" onNavigate={onNavigate}><div>PAGE BODY</div></AppShell>);
  expect(screen.getByText("PAGE BODY")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Solstice/ }));
  expect(onNavigate).toHaveBeenCalledWith("heatseeker");
});
