import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import type { Usuario } from "../auth/ContextoAuth";
import { CambiarPassword } from "./CambiarPassword";

vi.mock("../api/cliente", () => ({
  clienteApi: { POST: vi.fn() },
}));

const estadoAuthMock = vi.hoisted(() => ({
  usuario: null as Usuario | null,
  recargarPerfil: vi.fn(),
}));

vi.mock("../auth/ContextoAuth", () => ({
  useAuth: () => ({
    usuario: estadoAuthMock.usuario,
    recargarPerfil: estadoAuthMock.recargarPerfil,
  }),
}));

function _usuario(sobrescribe: Partial<Usuario> = {}): Usuario {
  return {
    id: "u1",
    nombre: "Ana Lista",
    email: "analista@local",
    rol: "analista",
    area: "Contabilidad",
    permisos: ["analisis:crear"],
    debeCambiarPassword: true,
    ...sobrescribe,
  };
}

function renderizar() {
  return render(
    <MemoryRouter initialEntries={["/cambiar-password"]}>
      <Routes>
        <Route path="/cambiar-password" element={<CambiarPassword />} />
        <Route path="/" element={<div>pantalla principal</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function llenarFormulario(actual: string, nueva: string, confirmacion: string) {
  fireEvent.change(screen.getByLabelText("Contraseña actual"), { target: { value: actual } });
  fireEvent.change(screen.getByLabelText("Contraseña nueva"), { target: { value: nueva } });
  fireEvent.change(screen.getByLabelText("Confirmar contraseña nueva"), {
    target: { value: confirmacion },
  });
  fireEvent.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
}

describe("CambiarPassword", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.POST).mockReset();
    estadoAuthMock.recargarPerfil.mockReset();
  });

  it("avisa que la contraseña es temporal cuando debeCambiarPassword es true", () => {
    estadoAuthMock.usuario = _usuario({ debeCambiarPassword: true });
    renderizar();
    expect(screen.getByText(/contraseña es temporal/i)).toBeInTheDocument();
  });

  it("rechaza en el cliente si la confirmación no coincide", async () => {
    estadoAuthMock.usuario = _usuario();
    renderizar();

    llenarFormulario("cambiar123", "NuevaClave99", "OtraCosa99");

    await waitFor(() =>
      expect(screen.getByText(/la confirmación no coincide/i)).toBeInTheDocument(),
    );
    expect(clienteApi.POST).not.toHaveBeenCalled();
  });

  it("al cambiar con éxito, recarga el perfil y navega a la ruta inicial", async () => {
    estadoAuthMock.usuario = _usuario({ debeCambiarPassword: true });
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: { cambiada: true },
      error: undefined,
      response: new Response(),
    } as never);
    estadoAuthMock.recargarPerfil.mockImplementation(async () => {
      estadoAuthMock.usuario = _usuario({ debeCambiarPassword: false });
    });

    renderizar();
    llenarFormulario("cambiar123", "NuevaClave99", "NuevaClave99");

    await waitFor(() => expect(estadoAuthMock.recargarPerfil).toHaveBeenCalled());
  });

  it("muestra el error del servidor si la contraseña actual es incorrecta", async () => {
    estadoAuthMock.usuario = _usuario();
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: undefined,
      error: { detail: "Contraseña actual incorrecta" },
      response: new Response(),
    } as never);

    renderizar();
    llenarFormulario("incorrecta", "NuevaClave99", "NuevaClave99");

    await waitFor(() =>
      expect(screen.getByText("Contraseña actual incorrecta")).toBeInTheDocument(),
    );
  });
});
