import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { descargarArchivo } from "../api/descargas";
import { clienteApi, obtenerTokenActual, URL_BASE_API } from "../api/cliente";
import { EstadoBadge } from "../componentes/EstadoBadge";
import { TarjetaHallazgo, type Hallazgo } from "../componentes/TarjetaHallazgo";
import "./Hallazgos.css";

const RESUELTOS = new Set(["aceptado", "rechazado"]);

// CU-05 (RNF-04, Bloque O6): un caso todavía "en_validacion" (el LLM no ha
// terminado) o ya "descartado" (falso positivo) no es decidible -- "Aceptar
// todos" no debe tocarlos. CU-02 (RNF-03): "sin_cambio" es la guardia de
// integridad descartando una sugerencia -- tampoco hay nada que decidir.
const NO_DECIDIBLES = new Set(["en_validacion", "descartado", "sin_cambio"]);
const esDecidible = (h: Hallazgo) => !RESUELTOS.has(h.estado) && !NO_DECIDIBLES.has(h.estado);

// Estados en los que el documento todavía no terminó la fase 1 (worker) --
// disparar la fase 2 (CU-02) antes de eso no tendría nada que leer todavía.
const ESTADOS_FASE1_EN_CURSO = new Set(["cargado", "procesando"]);

/** CU-02 (RF-12): consume la ruta SSE de la fase 2 (mejora por párrafo).
 * No usa `EventSource` nativo porque necesita mandar el header
 * `Authorization` (ver docstring de la ruta en api/main.py) -- se lee el
 * `body` de `fetch` a mano, separando por el bloque en blanco que delimita
 * cada evento SSE ("\n\n"). */
async function consumirMejoraRedaccionStream(
  analisisId: string,
  onParrafo: (indice: number) => void,
): Promise<void> {
  const token = obtenerTokenActual();
  const respuesta = await fetch(`${URL_BASE_API}/analisis/${analisisId}/mejorar-stream`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!respuesta.ok || !respuesta.body) {
    throw new Error(`No se pudo mejorar la redacción (HTTP ${respuesta.status})`);
  }

  const lector = respuesta.body.getReader();
  const decodificador = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    buffer += decodificador.decode(value, { stream: true });

    let indiceSeparador = buffer.indexOf("\n\n");
    while (indiceSeparador !== -1) {
      const bloque = buffer.slice(0, indiceSeparador);
      buffer = buffer.slice(indiceSeparador + 2);
      if (bloque.startsWith("event: parrafo")) {
        const lineaDatos = bloque.split("\n").find((linea) => linea.startsWith("data: "));
        if (lineaDatos) {
          try {
            const datos = JSON.parse(lineaDatos.slice("data: ".length)) as { indice: number };
            onParrafo(datos.indice);
          } catch {
            // Evento mal formado: se ignora, no detiene el resto del stream.
          }
        }
      }
      indiceSeparador = buffer.indexOf("\n\n");
    }
  }
}

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
  const [mejorandoRedaccion, setMejorandoRedaccion] = useState(false);
  const [parrafoEnCurso, setParrafoEnCurso] = useState<number | null>(null);
  // Evita disparar la fase 2 más de una vez para el mismo análisis (p. ej.
  // si el efecto se vuelve a ejecutar) -- el endpoint ya es idempotente del
  // lado del servidor, pero no tiene sentido abrir el stream dos veces.
  const fase2DisparadaRef = useRef<string | null>(null);

  useEffect(() => {
    if (!analisisId) return;
    let cancelado = false;
    let temporizador: ReturnType<typeof setTimeout> | undefined;

    async function cargar() {
      const [respuestaAnalisis, respuestaHallazgos] = await Promise.all([
        clienteApi.GET("/analisis/{analisis_id}", {
          params: { path: { analisis_id: analisisId as string } },
        }),
        clienteApi.GET("/analisis/{analisis_id}/hallazgos", {
          params: { path: { analisis_id: analisisId as string } },
        }),
      ]);
      if (cancelado) return;

      if (respuestaAnalisis.error || !respuestaAnalisis.data) {
        setError("No se pudo consultar el análisis");
        return;
      }
      const analisisActual = respuestaAnalisis.data;
      setAnalisis(analisisActual);

      let hayEnValidacion = false;
      if (!respuestaHallazgos.error && respuestaHallazgos.data) {
        setHallazgos(respuestaHallazgos.data);
        hayEnValidacion = respuestaHallazgos.data.some((h) => h.estado === "en_validacion");
      }

      // CU-02 (RF-12): apenas la fase 1 (worker) termina, se dispara la fase
      // 2 (LLM por párrafo, streaming SSE) -- ver
      // docs/02-analisis/02-analisis-cu02-redaccion-amigable.md §2.1.
      if (
        analisisActual.tipo_revision === "redaccion" &&
        !ESTADOS_FASE1_EN_CURSO.has(analisisActual.estado) &&
        analisisActual.estado !== "fallido" &&
        fase2DisparadaRef.current !== analisisId
      ) {
        fase2DisparadaRef.current = analisisId;
        setMejorandoRedaccion(true);
        consumirMejoraRedaccionStream(analisisId as string, setParrafoEnCurso)
          .catch(() => {
            if (!cancelado) setError("No se pudo mejorar la redacción");
          })
          .finally(() => {
            if (cancelado) return;
            setMejorandoRedaccion(false);
            setParrafoEnCurso(null);
            void cargar(); // refresca hallazgos + estado del análisis tras la fase 2
          });
      }

      // CU-05 (RNF-04, Bloque O6): la validación LLM de casos dudosos corre
      // en segundo plano después de que el análisis ya está "terminado" --
      // se sigue consultando para reflejar "Confirmado"/"Descartado" sin que
      // el usuario tenga que recargar la página.
      if (hayEnValidacion) {
        temporizador = setTimeout(cargar, 5000);
      }
    }

    cargar().catch(() => {
      if (!cancelado) setError("No se pudo conectar con el servidor");
    });

    return () => {
      cancelado = true;
      if (temporizador) clearTimeout(temporizador);
    };
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
      const pendientes = hallazgos.filter(esDecidible);
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
        hallazgosOrdenados.some(esDecidible) && (
          <button
            type="button"
            className="hallazgos__boton-aceptar-todos"
            onClick={aceptarTodos}
            disabled={procesandoLote}
          >
            {procesandoLote ? "Aceptando…" : "Aceptar todos"}
          </button>
        )}

      {mejorandoRedaccion && (
        <p className="hallazgos__mensaje" role="status">
          Mejorando redacción…
          {parrafoEnCurso != null && ` (párrafo ${parrafoEnCurso + 1})`}
        </p>
      )}

      {hallazgosOrdenados.length === 0 ? (
        !mejorandoRedaccion && (
          <p className="hallazgos__mensaje">Este análisis no tiene hallazgos.</p>
        )
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
