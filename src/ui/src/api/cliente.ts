import createClient from "openapi-fetch";
import type { paths } from "./esquema";

const URL_BASE_API = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

let obtenerToken: () => string | null = () => null;

/** El contexto de auth registra aquí cómo leer el token vigente (en memoria),
 * para que el cliente de API pueda inyectarlo sin acoplarse a React. */
export function registrarProveedorToken(fn: () => string | null): void {
  obtenerToken = fn;
}

export const clienteApi = createClient<paths>({ baseUrl: URL_BASE_API });

clienteApi.use({
  onRequest({ request }) {
    const token = obtenerToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
});

export { URL_BASE_API };
