import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { clienteApi, registrarProveedorToken } from "../api/cliente";

export interface Usuario {
  email: string;
  rol: string;
}

interface EstadoAuth {
  usuario: Usuario | null;
  cargando: boolean;
  error: string | null;
  iniciarSesion: (email: string, password: string) => Promise<void>;
  cerrarSesion: () => void;
}

const ContextoAuth = createContext<EstadoAuth | null>(null);

export function ProveedorAuth({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // El cliente de API (fuera de React) lee el token vigente por esta función,
  // así el token nunca se persiste (no localStorage/sessionStorage/cookies):
  // se pierde al recargar la página, como pide el requisito de seguridad.
  useEffect(() => {
    registrarProveedorToken(() => token);
  }, [token]);

  const iniciarSesion = useCallback(async (email: string, password: string) => {
    setCargando(true);
    setError(null);
    try {
      const { data, error: errorRespuesta } = await clienteApi.POST("/auth/login", {
        body: { email, password },
      });
      if (errorRespuesta || !data) {
        setError("Credenciales inválidas");
        return;
      }
      setToken(data.access_token);
      setUsuario({ email, rol: data.rol });
    } catch {
      setError("No se pudo conectar con el servidor");
    } finally {
      setCargando(false);
    }
  }, []);

  const cerrarSesion = useCallback(() => {
    setToken(null);
    setUsuario(null);
  }, []);

  const valor = useMemo(
    () => ({ usuario, cargando, error, iniciarSesion, cerrarSesion }),
    [usuario, cargando, error, iniciarSesion, cerrarSesion],
  );

  return <ContextoAuth.Provider value={valor}>{children}</ContextoAuth.Provider>;
}

export function useAuth(): EstadoAuth {
  const contexto = useContext(ContextoAuth);
  if (!contexto) {
    throw new Error("useAuth debe usarse dentro de <ProveedorAuth>");
  }
  return contexto;
}
