import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TextoConNegritas } from "./TextoConNegritas";

describe("TextoConNegritas", () => {
  it("convierte **texto** en negrita y conserva el resto", () => {
    render(
      <p data-testid="p">
        <TextoConNegritas texto={"**Causa probable**\n\nUna cuenta no existe."} />
      </p>,
    );

    expect(screen.getByText("Causa probable").tagName).toBe("STRONG");
    expect(screen.getByTestId("p")).toHaveTextContent("Causa probable Una cuenta no existe.");
    expect(screen.getByTestId("p").textContent).not.toContain("**");
  });

  it("deja como texto una marca sin cerrar y no interpreta HTML", () => {
    render(
      <p data-testid="p">
        <TextoConNegritas texto={"Total **sin cerrar <b>x</b>"} />
      </p>,
    );

    expect(screen.getByTestId("p").textContent).toBe("Total **sin cerrar <b>x</b>");
    expect(screen.queryByRole("strong")).toBeNull();
  });
});
