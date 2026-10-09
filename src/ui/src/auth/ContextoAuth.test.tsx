import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { ProveedorAuth, useAuth } from "./ContextoAuth";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn(), POST: vi.fn() },
  registrarProveedorToken: vi.fn(),
}));

const PERFIL_ANALISTA = {
  id: "u1",
  nombre: "Ana Lista",
  email: "analista@local",
  rol: "analista",
  area: "Contabilidad",
  permisos: ["analisis:crear", "historial:propio", "historial:area"],
  debe_cambiar_password: false,
};

function Sonda() {
  const { usuario, error, iniciarSesion, cerrarSesion } = useAuth();
  return (
    <div>
      <span data-testid="usuario">
        {usuario ? `${usuario.email}:${usuario.rol}:${usuario.area}` : "anonimo"}
      </span>
      <span data-testid="permisos">{usuario?.permisos.join(",") ?? ""}</span>
      <span data-testid="error">{error ?? ""}</span>
      <button onClick={() => iniciarSesion("analista@local", "cambiar123")}>entrar</button>
      <button onClick={cerrarSesion}>salir</button>
    </div>
  );
}

describe("ProveedorAuth", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.POST).mockReset();
    vi.mocked(clienteApi.GET).mockReset();
  });

  it("guarda el perfil completo (rol, área, permisos) tras un login correcto", async () => {
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: { access_token: "token-de-prueba", token_type: "bearer", rol: "analista" },
      error: undefined,
      response: new Response(),
    } as never);
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: PERFIL_ANALISTA,
      error: undefined,
      response: new Response(),
    } as never);

    render(
      <ProveedorAuth>
        <Sonda />
      </ProveedorAuth>,
    );

    expect(screen.getByTestId("usuario")).toHaveTextContent("anonimo");
    await act(async () => {
      screen.getByText("entrar").click();
    });

    await waitFor(() =>
      expect(screen.getByTestId("usuario")).toHaveTextContent(
        "analista@local:analista:Contabilidad",
      ),
    );
    expect(screen.getByTestId("permisos")).toHaveTextContent("analisis:crear");
  });

  it("muestra un error y no guarda usuario si las credenciales son inválidas", async () => {
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: undefined,
      error: { detail: "Credenciales inválidas" },
      response: new Response(),
    } as never);

    render(
      <ProveedorAuth>
        <Sonda />
      </ProveedorAuth>,
    );

    await act(async () => {
      screen.getByText("entrar").click();
    });

    await waitFor(() => expect(screen.getByTestId("error")).not.toHaveTextContent(""));
    expect(screen.getByTestId("usuario")).toHaveTextContent("anonimo");
  });

  it("si /auth/me falla tras un login correcto, no deja una sesión a medias", async () => {
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: { access_token: "token-de-prueba", token_type: "bearer", rol: "analista" },
      error: undefined,
      response: new Response(),
    } as never);
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: undefined,
      error: { detail: "error" },
      response: new Response(),
    } as never);

    render(
      <ProveedorAuth>
        <Sonda />
      </ProveedorAuth>,
    );

    await act(async () => {
      screen.getByText("entrar").click();
    });

    await waitFor(() => expect(screen.getByTestId("error")).not.toHaveTextContent(""));
    expect(screen.getByTestId("usuario")).toHaveTextContent("anonimo");
  });

  it("cerrarSesion limpia el usuario", async () => {
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: { access_token: "token-de-prueba", token_type: "bearer", rol: "analista" },
      error: undefined,
      response: new Response(),
    } as never);
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: PERFIL_ANALISTA,
      error: undefined,
      response: new Response(),
    } as never);

    render(
      <ProveedorAuth>
        <Sonda />
      </ProveedorAuth>,
    );

    await act(async () => {
      screen.getByText("entrar").click();
    });
    await waitFor(() => expect(screen.getByTestId("usuario")).not.toHaveTextContent("anonimo"));

    act(() => {
      screen.getByText("salir").click();
    });
    expect(screen.getByTestId("usuario")).toHaveTextContent("anonimo");
  });
});
