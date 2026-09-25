import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { descargarArchivo } from "../api/descargas";
import { clienteApi } from "../api/cliente";
import { EstadoBadge } from "../componentes/EstadoBadge";
import { TarjetaHallazgo, type Hallazgo } from "../componentes/TarjetaHallazgo";
import "./Hallazgos.css";

type Analisis = {
  id: string;
  documento_id: string;
  nombre_documento?: string | null;
  estado: string;
  total_debe?: number | null;
  total_haber?: number | null;
  moneda?: string | null;
  puede_decidir: boolean;
  tiene_version_corregida: boolean;
};

// alta primero, luego media, luego baja; cualquier otro valor al final.
const ORDEN_SEVERIDAD: Record<string, number> = { alta: 0, media: 1, baja: 2 };

/** Pantalla 3 (bloque U4): totales, lista de hallazgos y decisión (RF-14,
 * PP-09 — el botón de decidir solo aparece si `analisis.puede_decidir`,
 * calculado por el servidor). */
export function Hallazgos() {
  const { analisisId } = useParams<{ analisisId: string }>();
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [hallazgos, setHallazgos] = useState<Hallazgo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [descargando, setDescargando] = useState(false);

  useEffect(() => {
    if (!analisisId) return;
    Promise.all([
      clienteApi.GET("/analisis/{analisis_id}", { params: { path: { analisis_id: analisisId } } }),
      clienteApi.GET("/analisis/{analisis_id}/hallazgos", {
        params: { path: { analisis_id: analisisId } },
      }),
    ])
      .then(([respuestaAnalisis, respuestaHallazgos]) => {
        if (respuestaAnalisis.error || !respuestaAnalisis.data) {
          setError("No se pudo consultar el análisis");
          return;
        }
        setAnalisis(respuestaAnalisis.data);
        if (!respuestaHallazgos.error && respuestaHallazgos.data) {
          setHallazgos(respuestaHallazgos.data);
        }
      })
      .catch(() => setError("No se pudo conectar con el servidor"));
  }, [analisisId]);

  function actualizarEstadoHallazgo(hallazgoId: string, resultado: string) {
    setHallazgos(
      (actual) => actual?.map((h) => (h.id === hallazgoId ? { ...h, estado: resultado } : h)) ?? null,
    );
  }

  async function manejarDescarga() {
    if (!analisis) return;
    setDescargando(true);
    try {
      await descargarArchivo(`/documentos/${analisis.documento_id}/version-corregida`);
    } catch {
      setError("No se pudo descargar el documento corregido");
    } finally {
      setDescargando(false);
    }
  }

  if (error) {
    return (
      <div>
        <h1>Hallazgos</h1>
        <p className="hallazgos__error" role="alert">
          {error}
        </p>
      </div>
    );
  }

  if (!analisis || !hallazgos) {
    return (
      <div>
        <h1>Hallazgos</h1>
        <p>Cargando…</p>
      </div>
    );
  }

  const diferencia = (analisis.total_debe ?? 0) - (analisis.total_haber ?? 0);
  const hallazgosOrdenados = [...hallazgos].sort(
    (a, b) => (ORDEN_SEVERIDAD[a.severidad] ?? 99) - (ORDEN_SEVERIDAD[b.severidad] ?? 99),
  );

  return (
    <div className="hallazgos">
      <h1>Hallazgos</h1>
      <p className="hallazgos__documento">
        {analisis.nombre_documento} <EstadoBadge estado={analisis.estado} />
      </p>

      <div className="hallazgos__totales">
        <div>
          <span className="hallazgos__total-etiqueta">Debe</span>
          <span className="hallazgos__total-valor">
            {analisis.moneda ?? ""} {(analisis.total_debe ?? 0).toFixed(2)}
          </span>
        </div>
        <div>
          <span className="hallazgos__total-etiqueta">Haber</span>
          <span className="hallazgos__total-valor">
            {analisis.moneda ?? ""} {(analisis.total_haber ?? 0).toFixed(2)}
          </span>
        </div>
        <div>
          <span className="hallazgos__total-etiqueta">Diferencia</span>
          <span
            className={
              "hallazgos__total-valor" +
              (Math.abs(diferencia) > 0.005 ? " hallazgos__total-valor--alerta" : "")
            }
          >
            {analisis.moneda ?? ""} {diferencia.toFixed(2)}
          </span>
        </div>
      </div>

      {analisis.tiene_version_corregida && (
        <button
          type="button"
          className="hallazgos__boton-descarga"
          onClick={manejarDescarga}
          disabled={descargando}
        >
          {descargando ? "Descargando…" : "Descargar Excel marcado"}
        </button>
      )}

      {hallazgosOrdenados.length === 0 ? (
        <p className="hallazgos__mensaje">Este análisis no tiene hallazgos.</p>
      ) : (
        <div className="hallazgos__lista">
          {hallazgosOrdenados.map((h) => (
            <TarjetaHallazgo
              key={h.id}
              hallazgo={h}
              puedeDecidir={analisis.puede_decidir}
              alDecidir={actualizarEstadoHallazgo}
            />
          ))}
        </div>
      )}
    </div>
  );
}
