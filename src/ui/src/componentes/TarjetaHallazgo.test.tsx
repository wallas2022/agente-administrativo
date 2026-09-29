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

  it("un caso 'en_validacion' no muestra botones de decisión ni la fuente interna de LanguageTool", () => {
    render(
      <TarjetaHallazgo
        hallazgo={hallazgoOrtografico({ estado: "en_validacion", fuente_citada: "DE_TILDE" })}
        puedeDecidir={true}
        alDecidir={() => {}}
      />,
    );

    expect(screen.getByText("Verificando con IA…")).toBeInTheDocument();
    expect(screen.queryByText("Aceptar")).not.toBeInTheDocument();
    expect(screen.queryByText("Rechazar")).not.toBeInTheDocument();
    expect(screen.queryByText(/Fuente:/)).not.toBeInTheDocument();
  });

  it("un caso 'descartado' no muestra botones de decisión", () => {
    render(
      <TarjetaHallazgo
        hallazgo={hallazgoOrtografico({ estado: "descartado" })}
        puedeDecidir={true}
        alDecidir={() => {}}
      />,
    );

    expect(screen.getByText(/El LLM descartó este caso/)).toBeInTheDocument();
    expect(screen.queryByText("Aceptar")).not.toBeInTheDocument();
    expect(screen.queryByText("Deshacer")).not.toBeInTheDocument();
  });

  it("un caso 'confirmado' se puede aceptar o rechazar igual que uno pendiente", () => {
    render(
      <TarjetaHallazgo
        hallazgo={hallazgoOrtografico({ estado: "confirmado" })}
        puedeDecidir={true}
        alDecidir={() => {}}
      />,
    );

    expect(screen.getByText("Aceptar")).toBeInTheDocument();
    expect(screen.getByText("Rechazar")).toBeInTheDocument();
  });

  it("muestra 'Regla aplicada' y 'Referencia' por separado (Bloque K4)", () => {
    render(
      <TarjetaHallazgo
        hallazgo={hallazgoContable({
          fuente_citada: "Regla aplicada: POL-001 §3 (v2026-01)",
          referencia_citada: "Referencia: EST-001, cap. §2",
        })}
        puedeDecidir={false}
        alDecidir={() => {}}
      />,
    );

    expect(screen.getByText("Regla aplicada: POL-001 §3 (v2026-01)")).toBeInTheDocument();
    expect(screen.getByText("Referencia: EST-001, cap. §2")).toBeInTheDocument();
  });

  it("sin fuente_citada no muestra 'Regla aplicada' aunque haya referencia", () => {
    render(
      <TarjetaHallazgo
        hallazgo={hallazgoContable({
          fuente_citada: null,
          referencia_citada: "Referencia: EST-001, cap. §2",
        })}
        puedeDecidir={false}
        alDecidir={() => {}}
      />,
    );

    expect(screen.queryByText(/Regla aplicada/)).not.toBeInTheDocument();
    expect(screen.getByText("Referencia: EST-001, cap. §2")).toBeInTheDocument();
  });
});
