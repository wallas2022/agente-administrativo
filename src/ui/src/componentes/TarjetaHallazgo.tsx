import { useState } from "react";
import { clienteApi } from "../api/cliente";
import { EstadoBadge } from "./EstadoBadge";
import { SeveridadBadge } from "./SeveridadBadge";
import "./TarjetaHallazgo.css";

export interface Hallazgo {
  id: string;
  severidad: string;
  ubicacion: string;
  descripcion: string;
  correccion_sugerida?: string | null;
  monto?: number | null;
  moneda?: string | null;
  estado: string;
  fuente_citada?: string | null;
}

const RESUELTOS = new Set(["aceptado", "rechazado"]);

// ortografia.revision (Bloque O2) formatea descripcion como «texto marcado»:
// mensaje -- se detecta ese patrón para mostrar el error tachado → la
// sugerencia, en vez del párrafo genérico de CU-01 (causa/corrección).
const PATRON_ERROR_ORTOGRAFICO = /^«(.+?)»:\s*([\s\S]*)$/;

function interpretarErrorOrtografico(
  descripcion: string,
): { error: string; explicacion: string } | null {
  const coincidencia = PATRON_ERROR_ORTOGRAFICO.exec(descripcion);
  if (!coincidencia) return null;
  return { error: coincidencia[1], explicacion: coincidencia[2] };
}

export function TarjetaHallazgo({
  hallazgo,
  puedeDecidir,
  alDecidir,
}: {
  hallazgo: Hallazgo;
  puedeDecidir: boolean;
  alDecidir: (hallazgoId: string, resultado: string) => void;
}) {
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const infoOrtografica = interpretarErrorOrtografico(hallazgo.descripcion);

  async function decidir(resultado: "aceptado" | "rechazado" | "deshecho") {
    setEnviando(true);
    setError(null);
    try {
      const { error: errorRespuesta } = await clienteApi.POST("/hallazgos/{hallazgo_id}/decision", {
        params: { path: { hallazgo_id: hallazgo.id } },
        body: { resultado },
      });
      if (errorRespuesta) {
        setError("No se pudo registrar la decisión");
        return;
      }
      alDecidir(hallazgo.id, resultado);
    } catch {
      setError("No se pudo conectar con el servidor");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <article className="tarjeta-hallazgo">
      <header className="tarjeta-hallazgo__cabecera">
        <SeveridadBadge severidad={hallazgo.severidad} />
        <span className="tarjeta-hallazgo__ubicacion">{hallazgo.ubicacion}</span>
        <EstadoBadge estado={hallazgo.estado} />
      </header>

      {infoOrtografica ? (
        <>
          <p className="tarjeta-hallazgo__ortografia">
            <s>{infoOrtografica.error}</s>
            {hallazgo.correccion_sugerida && (
              <>
                {" → "}
                <strong>{hallazgo.correccion_sugerida}</strong>
              </>
            )}
          </p>
          {infoOrtografica.explicacion && (
            <p className="tarjeta-hallazgo__explicacion-breve">{infoOrtografica.explicacion}</p>
          )}
        </>
      ) : (
        <>
          <p className="tarjeta-hallazgo__descripcion">{hallazgo.descripcion}</p>

          {hallazgo.monto != null && (
            <p className="tarjeta-hallazgo__monto">
              Monto: {hallazgo.moneda ?? ""} {hallazgo.monto.toFixed(2)}
            </p>
          )}

          {hallazgo.correccion_sugerida && (
            <div className="tarjeta-hallazgo__explicacion">
              <h3>Explicación y corrección sugerida</h3>
              <p>{hallazgo.correccion_sugerida}</p>
            </div>
          )}
        </>
      )}

      {hallazgo.fuente_citada && (
        <p className="tarjeta-hallazgo__fuente">Fuente: {hallazgo.fuente_citada}</p>
      )}

      {error && (
        <p className="tarjeta-hallazgo__error" role="alert">
          {error}
        </p>
      )}

      {puedeDecidir && (
        <div className="tarjeta-hallazgo__acciones">
          {RESUELTOS.has(hallazgo.estado) ? (
            <button type="button" disabled={enviando} onClick={() => decidir("deshecho")}>
              Deshacer
            </button>
          ) : (
            <>
              <button
                type="button"
                className="tarjeta-hallazgo__aceptar"
                disabled={enviando}
                onClick={() => decidir("aceptado")}
              >
                Aceptar
              </button>
              <button
                type="button"
                className="tarjeta-hallazgo__rechazar"
                disabled={enviando}
                onClick={() => decidir("rechazado")}
              >
                Rechazar
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}
