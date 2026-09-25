import { useEffect, useState } from "react";
import { clienteApi } from "../api/cliente";

export type RespuestaAnalisis = {
  id: string;
  documento_id: string;
  nombre_documento?: string | null;
  tipo_revision: string;
  estado: string;
  fecha_inicio: string;
  fecha_fin?: string | null;
  periodo_cierre?: string | null;
};

export type BitacoraEntrada = {
  id: string;
  accion: string;
  fecha_hora: string;
  detalle?: string | null;
};

// docs/03-diseno/estados/estados-analisis.md: el worker solo transiciona
// entre estos dos mientras procesa; al salir de aquí, deja de tener sentido
// seguir consultando cada pocos segundos.
const ESTADOS_EN_PROCESO = new Set(["cargado", "procesando"]);

export interface EstadoAnalisisEnVivo {
  analisis: RespuestaAnalisis | null;
  bitacora: BitacoraEntrada[];
  error: string | null;
}

export function useAnalisisEnVivo(
  analisisId: string,
  intervaloMs = 3000,
): EstadoAnalisisEnVivo {
  const [analisis, setAnalisis] = useState<RespuestaAnalisis | null>(null);
  const [bitacora, setBitacora] = useState<BitacoraEntrada[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    let temporizador: ReturnType<typeof setTimeout> | undefined;

    async function consultar() {
      // Un error de red en una ronda de sondeo (transitorio: el análisis
      // puede tardar minutos) no debe apagar el sondeo para siempre -- solo
      // un estado terminal recibido con éxito lo detiene. Por eso cada ronda
      // reprograma la siguiente incluso si esta falla (try/finally), en vez
      // de dejar que un rechazo sin capturar corte la cadena de setTimeout.
      let siguienteRonda = true;
      try {
        const [respuestaAnalisis, respuestaBitacora] = await Promise.all([
          clienteApi.GET("/analisis/{analisis_id}", {
            params: { path: { analisis_id: analisisId } },
          }),
          clienteApi.GET("/analisis/{analisis_id}/bitacora", {
            params: { path: { analisis_id: analisisId } },
          }),
        ]);
        if (cancelado) return;

        if (respuestaAnalisis.error || !respuestaAnalisis.data) {
          setError("No se pudo consultar el estado del análisis");
        } else {
          setAnalisis(respuestaAnalisis.data);
          setError(null);
          if (!respuestaBitacora.error && respuestaBitacora.data) {
            setBitacora(respuestaBitacora.data);
          }
          siguienteRonda = ESTADOS_EN_PROCESO.has(respuestaAnalisis.data.estado);
        }
      } catch {
        if (!cancelado) setError("No se pudo conectar con el servidor");
      } finally {
        if (!cancelado && siguienteRonda) {
          temporizador = setTimeout(consultar, intervaloMs);
        }
      }
    }

    consultar();

    return () => {
      cancelado = true;
      if (temporizador) clearTimeout(temporizador);
    };
  }, [analisisId, intervaloMs]);

  return { analisis, bitacora, error };
}
