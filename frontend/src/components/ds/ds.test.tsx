import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge, ErrorText, Table } from "./index";

describe("design system primitives", () => {
  it("Badge renders its content", () => {
    render(<Badge tone="warn">needs review</Badge>);
    expect(screen.getByText("needs review")).toBeTruthy();
  });

  it("ErrorText renders Error messages with role=alert, nothing when empty", () => {
    const { rerender } = render(<ErrorText error={new Error("boom")} />);
    expect(screen.getByRole("alert").textContent).toBe("boom");
    rerender(<ErrorText error={null} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Table renders headers and rows", () => {
    render(
      <Table headers={["Name", "CIN"]}>
        <tr>
          <td>Acme</td>
          <td>U74999MH2020PTC000001</td>
        </tr>
      </Table>,
    );
    expect(screen.getByText("Name")).toBeTruthy();
    expect(screen.getByText("Acme")).toBeTruthy();
  });
});
