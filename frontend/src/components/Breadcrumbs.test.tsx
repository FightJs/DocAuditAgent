import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";
import { Breadcrumbs } from "./Breadcrumbs";

test("links every non-current URL context and marks the current context", () => {
  render(<MemoryRouter><Breadcrumbs items={[
    { label: "案件列表", to: "/cases" },
    { label: "case_1", to: "/cases/case_1" },
    { label: "风险与证据" },
  ]}/></MemoryRouter>);

  expect(screen.getByRole("link", { name: "案件列表" })).toHaveAttribute("href", "/cases");
  expect(screen.getByRole("link", { name: "case_1" })).toHaveAttribute("href", "/cases/case_1");
  expect(screen.getByText("风险与证据")).toHaveAttribute("aria-current", "page");
});
