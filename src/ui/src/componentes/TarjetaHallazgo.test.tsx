import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TarjetaHallazgo, type Hallazgo } from "./TarjetaHallazgo";

vi.mock("../api/cliente", () => ({
  clienteApi: { POST: vi.fn() },
}));

function hallazgoContable(overrides: Partial<Hallazgo> = {}): Hallazgo {
  return {
    id: "h-1",
    severidad: "alta",
    ubicacion: "Partidas!A3",
    descripcion: "La cuenta '9999' no existe en el catálogo de cuentas vigente",
    correccion_sugerida: "Verifica el código de cuenta en el catálogo vigente.",
    estado: "pendiente",
    ...overrides,
  };
}

function hallazgoOrtografico(overrides: Partial<Hallazgo> = {}): Hallazgo {
  return {
    id: "h-2",
    severidad: "media",
    ubicacion: "Párrafo 3",
    descripcion: "«aprovado»: Se ha encontrado un posible error ortográfico.",
    correccion_sugerida: "aprobado",
    estado: "pendiente",
    ...overrides,
  };
}

describe("TarjetaHallazgo", () => {
  it("muestra la descripción y corrección de un hallazgo contable como texto plano", () => {
    render(
      <TarjetaHallazgo hallazgo={hallazgoContable()} puedeDecidir={false} alDecidir={() => {}} />,
    );

    expect(screen.getByText(/no existe en el catálogo/)).toBeInTheDocument();
    expect(screen.getByText("Explicación y corrección sugerida")).toBeInTheDocument();
    expect(screen.queryByText("aprovado")).not.toBeInTheDocument();
  });

  it("muestra un hallazgo ortográfico como error tachado → sugerencia", () => {
    render(
      <TarjetaHallazgo
        hallazgo={hallazgoOrtografico()}
        puedeDecidir={false}
        alDecidir={() => {}}
      />,
    );

    expect(screen.getByText("aprovado")).toBeInTheDocument();
    expect(screen.getByText("aprovado").tagName).toBe("S");
    expect(screen.getByText("aprobado")).toBeInTheDocument();
    expect(screen.getByText(/posible error ortográfico/)).toBeInTheDocument();
    expect(screen.queryByText("Explicación y corrección sugerida")).not.toBeInTheDocument();
  });

  it("un hallazgo ortográfico sin corrección sugerida no muestra la flecha", () => {
    render(
      <TarjetaHallazgo
        hallazgo={hallazgoOrtografico({ correccion_sugerida: null })}
        puedeDecidir={false}
        alDecidir={() => {}}
      />,
    );

    expect(screen.getByText("aprovado")).toBeInTheDocument();
    expect(screen.queryByText("aprobado")).not.toBeInTheDocument();
  });
});
