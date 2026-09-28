import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { descargarArchivo } from "../api/descargas";
import { clienteApi } from "../api/cliente";
import { EstadoBadge } from "../componentes/EstadoBadge";
import { TarjetaHallazgo, type Hallazgo } from "../componentes/TarjetaHallazgo";
import "./Hallazgos.css";

const RESUELTOS = new Set(["aceptado", "rechazado"]);

type Analisis = {
  id: string;
  documento_id: string;
  nombre_documento?: string | null;
  tipo_revision: string;
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
  const [procesandoLote, setProcesandoLote] = useState(false);

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

  // RF-14 (CU-05): a diferencia de CU-01, el corregido no se genera durante
  // el análisis -- se regenera cada vez que cambia una decisión, reflejando
  // siempre los hallazgos "aceptados" hasta ese momento.
  async function regenerarCorregidoSiAplica(analisisActual: Analisis) {
    if (analisisActual.tipo_revision !== "ortografia") return;
    const { error: errorGenerar } = await clienteApi.POST(
      "/analisis/{analisis_id}/generar-corregido",
      { params: { path: { analisis_id: analisisActual.id } } },
    );
    if (errorGenerar) return;
    const { data } = await clienteApi.GET("/analisis/{analisis_id}", {
      params: { path: { analisis_id: analisisActual.id } },
    });
    if (data) setAnalisis(data);
  }

  function actualizarEstadoHallazgo(hallazgoId: string, resultado: string) {
    setHallazgos(
      (actual) => actual?.map((h) => (h.id === hallazgoId ? { ...h, estado: resultado } : h)) ?? null,
    );
    if (analisis) void regenerarCorregidoSiAplica(analisis);
  }

  async function aceptarTodos() {
    if (!hallazgos || !analisis) return;
    setProcesandoLote(true);
    try {
      const pendientes = hallazgos.filter((h) => !RESUELTOS.has(h.estado));
      for (const h of pendientes) {
        const { error: errorDecision } = await clienteApi.POST("/hallazgos/{hallazgo_id}/decision", {
          params: { path: { hallazgo_id: h.id } },
          body: { resultado: "aceptado" },
        });
        if (!errorDecision) {
          setHallazgos(
            (actual) => actual?.map((x) => (x.id === h.id ? { ...x, estado: "aceptado" } : x)) ?? null,
          );
        }
      }
      await regenerarCorregidoSiAplica(analisis);
    } finally {
      setProcesandoLote(false);
    }
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

      {/* CU-05 (ortografía) no tiene Debe/Haber -- RN-01/RN-03 son exclusivas
          de CU-01, así que este bloque no aplica ahí. */}
      {analisis.total_debe != null && (
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
      )}

      {analisis.tiene_version_corregida && (
        <button
          type="button"
          className="hallazgos__boton-descarga"
          onClick={manejarDescarga}
          disabled={descargando}
        >
          {descargando ? "Descargando…" : "Descargar documento corregido"}
        </button>
      )}

      {analisis.puede_decidir &&
        hallazgosOrdenados.some((h) => !RESUELTOS.has(h.estado)) && (
          <button
            type="button"
            className="hallazgos__boton-aceptar-todos"
            onClick={aceptarTodos}
            disabled={procesandoLote}
          >
            {procesandoLote ? "Aceptando…" : "Aceptar todos"}
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
