import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { clienteApi, registrarProveedorToken } from "../api/cliente";

export interface Usuario {
  id: string;
  nombre: string;
  email: string;
  rol: string;
  area: string;
  permisos: string[];
  debeCambiarPassword: boolean;
}

interface EstadoAuth {
  usuario: Usuario | null;
  cargando: boolean;
  error: string | null;
  iniciarSesion: (email: string, password: string) => Promise<void>;
  cerrarSesion: () => void;
  recargarPerfil: () => Promise<void>;
  tienePermiso: (...permisos: string[]) => boolean;
}

const ContextoAuth = createContext<EstadoAuth | null>(null);

function aUsuario(datos: {
  id: string;
  nombre: string;
  email: string;
  rol: string;
  area: string;
  permisos: string[];
  debe_cambiar_password: boolean;
}): Usuario {
  return {
    id: datos.id,
    nombre: datos.nombre,
    email: datos.email,
    rol: datos.rol,
    area: datos.area,
    permisos: datos.permisos,
    debeCambiarPassword: datos.debe_cambiar_password,
  };
}

export function ProveedorAuth({ children }: { children: ReactNode }) {
  // Ref (no estado): el interceptor de clienteApi lee el token vigente de
  // forma síncrona en cada request -- si fuera solo estado, el primer
  // GET /auth/me tras el login se haría todavía con el token viejo (null),
  // porque React no re-renderiza entre el setToken y la llamada siguiente.
  // El token nunca se persiste (no localStorage/sessionStorage/cookies):
  // se pierde al recargar la página, como pide el requisito de seguridad.
  const tokenRef = useRef<string | null>(null);
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    registrarProveedorToken(() => tokenRef.current);
  }, []);

  const recargarPerfil = useCallback(async () => {
    const { data, error: errorRespuesta } = await clienteApi.GET("/auth/me");
    if (errorRespuesta || !data) {
      tokenRef.current = null;
      setUsuario(null);
      return;
    }
    setUsuario(aUsuario(data));
  }, []);

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
      tokenRef.current = data.access_token;
      const { data: perfil, error: errorPerfil } = await clienteApi.GET("/auth/me");
      if (errorPerfil || !perfil) {
        tokenRef.current = null;
        setError("No se pudo cargar el perfil del usuario");
        return;
      }
      setUsuario(aUsuario(perfil));
    } catch {
      setError("No se pudo conectar con el servidor");
    } finally {
      setCargando(false);
    }
  }, []);

  const cerrarSesion = useCallback(() => {
    tokenRef.current = null;
    setUsuario(null);
  }, []);

  const tienePermiso = useCallback(
    (...permisos: string[]) => {
      if (!usuario) return false;
      return permisos.some((permiso) => usuario.permisos.includes(permiso));
    },
    [usuario],
  );

  const valor = useMemo(
    () => ({ usuario, cargando, error, iniciarSesion, cerrarSesion, recargarPerfil, tienePermiso }),
    [usuario, cargando, error, iniciarSesion, cerrarSesion, recargarPerfil, tienePermiso],
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
