import { useEffect, useRef, useState } from "react";
import { clienteApi, obtenerTokenActual, URL_BASE_API } from "../api/cliente";
import { EstadoBadge } from "../componentes/EstadoBadge";
import { TarjetaHallazgo, type Hallazgo } from "../componentes/TarjetaHallazgo";
import { resaltarDiferencias } from "../utils/diffPalabras";
import "./ResultadoRedaccion.css";

// Estados en los que el documento todavía no terminó la fase 1 (worker) --
// disparar la fase 2 antes de eso no tendría nada que leer todavía.
const ESTADOS_FASE1_EN_CURSO = new Set(["cargado", "procesando"]);

// Mismos prefijos que api/main.py (_PREFIJO_DESCRIPCION_MEJORA_FASE2 /
// _PREFIJO_DESCRIPCION_DESCARTE_FASE2) -- se usan acá solo para separar,
// de la lista genérica de /hallazgos, los que son de la fase 2 (ya
// representados por las tarjetas de comparación) de los de la fase 1
// (RD-01 a RD-04, EST-001, que sí se listan abajo con TarjetaHallazgo).
const PREFIJO_MEJORA_FASE2 = "Mejora de redacción sugerida (acción: ";
const PREFIJO_DESCARTE_FASE2 = "Sugerencia descartada por la guardia de integridad";

const OPCION_BASE = "__base__";
const OPCION_EDITADO = "__editado__";

interface OpcionEvento {
  estilo: string;
  texto: string;
  motivos: string[];
  aprobada_guardia: boolean;
  razon_descarte: string | null;
}

interface ParrafoEstado {
  indice: number;
  ubicacion: string;
  listo: boolean; // true cuando llegó el evento "parrafo_fin"
  omitido: boolean;
  hallazgoId: string | null;
  parrafoOriginal: string;
  parrafoBase: string;
  fuenteCitada: string | null;
  opciones: OpcionEvento[]; // se van agregando conforme llegan eventos "opcion"
  eleccion: string; // estilo de una opción aprobada, OPCION_BASE u OPCION_EDITADO
  textoEditado: string;
  guardando: boolean;
  errorGuardado: string | null;
}

interface Analisis {
  id: string;
  nombre_documento?: string | null;
  estado: string;
  puede_decidir: boolean;
}

function textoFinalDe(p: ParrafoEstado): string {
  if (p.eleccion === OPCION_EDITADO) return p.textoEditado;
  if (p.eleccion === OPCION_BASE) return p.parrafoBase;
  const opcion = p.opciones.find((o) => o.estilo === p.eleccion && o.aprobada_guardia);
  return opcion ? opcion.texto : p.parrafoBase;
}

function eleccionPorDefecto(opciones: OpcionEvento[]): string {
  const primeraAprobada = opciones.find((o) => o.aprobada_guardia);
  return primeraAprobada ? primeraAprobada.estilo : OPCION_BASE;
}

type ManejadorEvento = (nombreEvento: string, datos: Record<string, unknown>) => void;

/** CU-02 (RF-12): consume la ruta SSE de la fase 2 (mejora por párrafo,
 * generada de a una opción por vez -- Bloque 3, rendimiento). No usa
 * `EventSource` nativo porque necesita mandar el header `Authorization`
 * (ver docstring de la ruta en api/main.py). */
async function consumirMejoraRedaccionStream(
  analisisId: string,
  onEvento: ManejadorEvento,
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
      const lineaEvento = bloque.split("\n").find((linea) => linea.startsWith("event: "));
      const lineaDatos = bloque.split("\n").find((linea) => linea.startsWith("data: "));
      if (lineaEvento && lineaDatos) {
        try {
          const datos = JSON.parse(lineaDatos.slice("data: ".length)) as Record<string, unknown>;
          onEvento(lineaEvento.slice("event: ".length), datos);
        } catch {
          // Evento mal formado: se ignora, no detiene el resto del stream.
        }
      }
      indiceSeparador = buffer.indexOf("\n\n");
    }
  }
}

export function ResultadoRedaccion({ analisisId }: { analisisId: string }) {
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [parrafos, setParrafos] = useState<ParrafoEstado[]>([]);
  const [hallazgosEstilo, setHallazgosEstilo] = useState<Hallazgo[]>([]);
  const [mejorando, setMejorando] = useState(true);
  const [totalParrafos, setTotalParrafos] = useState<number | null>(null);
  const [parrafoEnCurso, setParrafoEnCurso] = useState<number | null>(null);
  const [segundosTranscurridos, setSegundosTranscurridos] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [verCambios, setVerCambios] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const disparadoRef = useRef(false);
  const inicioParrafoActualRef = useRef<number | null>(null);

  // Bloque 6 (UX): "Párrafo n de N · generando… (Ns)" en vez de un mensaje
  // fijo -- el segundero solo corre mientras hay un párrafo en curso.
  useEffect(() => {
    if (!mejorando || parrafoEnCurso === null) return;
    const intervalo = setInterval(() => {
      if (inicioParrafoActualRef.current !== null) {
        setSegundosTranscurridos(Math.round((Date.now() - inicioParrafoActualRef.current) / 1000));
      }
    }, 1000);
    return () => clearInterval(intervalo);
  }, [mejorando, parrafoEnCurso]);

  useEffect(() => {
    let cancelado = false;
    let temporizador: ReturnType<typeof setTimeout> | undefined;

    function manejarEvento(nombreEvento: string, datos: Record<string, unknown>) {
      if (cancelado) return;
      if (nombreEvento === "inicio") {
        setTotalParrafos(datos.total_parrafos as number);
        return;
      }
      if (nombreEvento === "parrafo_inicio") {
        const indice = datos.indice as number;
        setParrafoEnCurso(indice);
        inicioParrafoActualRef.current = Date.now();
        setSegundosTranscurridos(0);
        setParrafos((actual) => [
          ...actual,
          {
            indice,
            ubicacion: datos.ubicacion as string,
            listo: false,
            omitido: false,
            hallazgoId: null,
            parrafoOriginal: "",
            parrafoBase: "",
            fuenteCitada: null,
            opciones: [],
            eleccion: OPCION_BASE,
            textoEditado: "",
            guardando: false,
            errorGuardado: null,
          },
        ]);
        return;
      }
      if (nombreEvento === "opcion") {
        const indice = datos.indice as number;
        const opcion: OpcionEvento = {
          estilo: datos.estilo as string,
          texto: datos.texto as string,
          motivos: datos.motivos as string[],
          aprobada_guardia: datos.aprobada_guardia as boolean,
          razon_descarte: (datos.razon_descarte as string | null) ?? null,
        };
        setParrafos((actual) =>
          actual.map((p) => {
            if (p.indice !== indice) return p;
            const opcionesActualizadas = [...p.opciones, opcion];
            return {
              ...p,
              hallazgoId: (datos.hallazgo_id as string | null) ?? p.hallazgoId,
              opciones: opcionesActualizadas,
              eleccion: eleccionPorDefecto(opcionesActualizadas),
            };
          }),
        );
        return;
      }
      if (nombreEvento === "parrafo_fin") {
        const indice = datos.indice as number;
        setParrafos((actual) =>
          actual.map((p) => {
            if (p.indice !== indice) return p;
            const parrafoBase = datos.parrafo_base as string;
            return {
              ...p,
              listo: true,
              omitido: datos.omitido as boolean,
              hallazgoId: (datos.hallazgo_id as string | null) ?? p.hallazgoId,
              parrafoOriginal: datos.parrafo_original as string,
              parrafoBase,
              fuenteCitada: (datos.fuente_citada as string | null) ?? null,
              textoEditado: parrafoBase,
            };
          }),
        );
      }
    }

    async function verificarEIniciar() {
      const { data, error: errorAnalisis } = await clienteApi.GET("/analisis/{analisis_id}", {
        params: { path: { analisis_id: analisisId } },
      });
      if (cancelado) return;
      if (errorAnalisis || !data) {
        setError("No se pudo consultar el análisis");
        return;
      }
      setAnalisis(data);

      if (ESTADOS_FASE1_EN_CURSO.has(data.estado)) {
        temporizador = setTimeout(verificarEIniciar, 3000);
        return;
      }
      if (disparadoRef.current || data.estado === "fallido") {
        setMejorando(false);
        return;
      }
      disparadoRef.current = true;

      try {
        await consumirMejoraRedaccionStream(analisisId, manejarEvento);
      } catch {
        if (!cancelado) setError("No se pudo mejorar la redacción");
      }

      // Corre tanto si el stream terminó bien como si falló (sin `finally`,
      // que con un `return` adentro puede tapar la excepción del `catch`).
      if (cancelado) return;
      setMejorando(false);
      setParrafoEnCurso(null);
      const [respuestaHallazgos, respuestaAnalisis] = await Promise.all([
        clienteApi.GET("/analisis/{analisis_id}/hallazgos", {
          params: { path: { analisis_id: analisisId } },
        }),
        clienteApi.GET("/analisis/{analisis_id}", { params: { path: { analisis_id: analisisId } } }),
      ]);
      if (cancelado) return;
      if (respuestaHallazgos.data) {
        setHallazgosEstilo(
          respuestaHallazgos.data.filter(
            (h) =>
              !h.descripcion.startsWith(PREFIJO_MEJORA_FASE2) &&
              !h.descripcion.startsWith(PREFIJO_DESCARTE_FASE2),
          ),
        );
      }
      if (respuestaAnalisis.data) setAnalisis(respuestaAnalisis.data);
    }

    verificarEIniciar().catch(() => {
      if (!cancelado) setError("No se pudo conectar con el servidor");
    });

    return () => {
      cancelado = true;
      if (temporizador) clearTimeout(temporizador);
    };
  }, [analisisId]);

  async function guardarEleccion(indice: number, eleccion: string, comentario: string) {
    const parrafo = parrafos.find((p) => p.indice === indice);
    if (!parrafo) return;

    setParrafos((actual) =>
      actual.map((p) => (p.indice === indice ? { ...p, eleccion, guardando: true, errorGuardado: null } : p)),
    );

    // Sin hallazgo_id (p. ej. ninguna opción llegó a aprobarse) no hay nada
    // que decidir -- el párrafo ya quedó fijo en su formato corregido. Sin
    // permiso para decidir (Analista, no Revisor/Administrador), tampoco se
    // intenta: el backend lo rechazaría con 403 de todas formas.
    if (!parrafo.hallazgoId || !analisis?.puede_decidir) {
      setParrafos((actual) => actual.map((p) => (p.indice === indice ? { ...p, guardando: false } : p)));
      return;
    }

    const { error: errorDecision } = await clienteApi.POST("/hallazgos/{hallazgo_id}/decision", {
      params: { path: { hallazgo_id: parrafo.hallazgoId } },
      body: { resultado: "aceptado", comentario },
    });

    setParrafos((actual) =>
      actual.map((p) =>
        p.indice === indice
          ? { ...p, guardando: false, errorGuardado: errorDecision ? "No se pudo guardar en bitácora" : null }
          : p,
      ),
    );
  }

  function elegirOpcion(indice: number, estilo: string) {
    void guardarEleccion(indice, estilo, `Opción elegida: ${estilo}`);
  }

  function usarOriginalConFormato(indice: number) {
    void guardarEleccion(indice, OPCION_BASE, "Se conservó el párrafo con el formato corregido");
  }

  function guardarEdicion(indice: number, texto: string) {
    setParrafos((actual) =>
      actual.map((p) => (p.indice === indice ? { ...p, textoEditado: texto } : p)),
    );
    void guardarEleccion(indice, OPCION_EDITADO, `Editado manualmente: ${texto}`);
  }

  function actualizarEstadoHallazgoEstilo(hallazgoId: string, resultado: string) {
    setHallazgosEstilo((actual) =>
      actual.map((h) => (h.id === hallazgoId ? { ...h, estado: resultado } : h)),
    );
  }

  function usarEstiloEnTodo(estilo: string) {
    const afectados = parrafos.filter((p) => p.opciones.some((o) => o.estilo === estilo && o.aprobada_guardia));
    for (const p of afectados) {
      elegirOpcion(p.indice, estilo);
    }
  }

  async function copiarTextoFinal() {
    const textoFinal = parrafos.filter((p) => p.listo).map(textoFinalDe).join("\n\n");
    try {
      await navigator.clipboard.writeText(textoFinal);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      setError("No se pudo copiar al portapapeles");
    }
  }

  if (error) {
    return (
      <div className="resultado-redaccion">
        <p className="resultado-redaccion__error" role="alert">
          {error}
        </p>
      </div>
    );
  }

  if (!analisis) {
    return (
      <div className="resultado-redaccion">
        <p>Cargando…</p>
      </div>
    );
  }

  const parrafosListos = parrafos.filter((p) => p.listo);
  const estilosDisponibles = [
    ...new Set(parrafosListos.flatMap((p) => p.opciones.map((o) => o.estilo))),
  ];
  const textoFinal = parrafosListos.map(textoFinalDe).join("\n\n");

  return (
    <div className="resultado-redaccion">
      <h1>Mejorar redacción — Resultado</h1>
      <p className="resultado-redaccion__documento">
        {analisis.nombre_documento} <EstadoBadge estado={analisis.estado} />
      </p>

      {mejorando && (
        <p className="resultado-redaccion__mensaje" role="status">
          {parrafoEnCurso !== null
            ? `Párrafo ${parrafoEnCurso + 1} de ${totalParrafos ?? "…"} · generando… (${segundosTranscurridos}s)`
            : "Mejorando redacción…"}
        </p>
      )}

      {estilosDisponibles.length > 0 && (
        <div className="resultado-redaccion__selector-global">
          <span>Usar en todo el documento:</span>
          {estilosDisponibles.map((estilo) => (
            <button key={estilo} type="button" onClick={() => usarEstiloEnTodo(estilo)}>
              {estilo}
            </button>
          ))}
        </div>
      )}

      <div className="resultado-redaccion__lista">
        {parrafos.map((parrafo) => {
          if (!parrafo.listo) {
            return (
              <article key={parrafo.indice} className="resultado-redaccion__parrafo">
                <header>
                  <span className="resultado-redaccion__ubicacion">{parrafo.ubicacion}</span>
                </header>
                <p className="resultado-redaccion__nota">Generando…</p>
                {parrafo.opciones.map((opcion) => (
                  <p key={opcion.estilo}>
                    <strong>{opcion.estilo}:</strong> {opcion.texto}
                  </p>
                ))}
              </article>
            );
          }

          if (parrafo.omitido) {
            return (
              <article key={parrafo.indice} className="resultado-redaccion__parrafo">
                <header>
                  <span className="resultado-redaccion__ubicacion">{parrafo.ubicacion}</span>
                </header>
                <p className="resultado-redaccion__nota">
                  Sin cambios (párrafo corto, sin hallazgos): {parrafo.parrafoBase}
                </p>
              </article>
            );
          }

          const textoElegido = textoFinalDe(parrafo);
          return (
            <article key={parrafo.indice} className="resultado-redaccion__parrafo">
              <header>
                <span className="resultado-redaccion__ubicacion">{parrafo.ubicacion}</span>
                {parrafo.fuenteCitada && (
                  <span className="resultado-redaccion__cita">{parrafo.fuenteCitada}</span>
                )}
              </header>

              <div className="resultado-redaccion__original">
                <h3>Original</h3>
                <p>{parrafo.parrafoOriginal}</p>
              </div>

              <div className="resultado-redaccion__opciones">
                <label
                  className={
                    "resultado-redaccion__opcion" +
                    (parrafo.eleccion === OPCION_BASE ? " resultado-redaccion__opcion--elegida" : "")
                  }
                >
                  <input
                    type="radio"
                    name={`parrafo-${parrafo.indice}`}
                    checked={parrafo.eleccion === OPCION_BASE}
                    onChange={() => usarOriginalConFormato(parrafo.indice)}
                  />
                  <strong>Sin cambio</strong> (formato corregido): {parrafo.parrafoBase}
                </label>

                {parrafo.opciones.map((opcion) => (
                  <label
                    key={opcion.estilo}
                    className={
                      "resultado-redaccion__opcion" +
                      (parrafo.eleccion === opcion.estilo ? " resultado-redaccion__opcion--elegida" : "") +
                      (!opcion.aprobada_guardia ? " resultado-redaccion__opcion--descartada" : "")
                    }
                  >
                    <input
                      type="radio"
                      name={`parrafo-${parrafo.indice}`}
                      checked={parrafo.eleccion === opcion.estilo}
                      disabled={!opcion.aprobada_guardia}
                      onChange={() => elegirOpcion(parrafo.indice, opcion.estilo)}
                    />
                    <strong>{opcion.estilo}:</strong> {opcion.texto}
                    {opcion.motivos.length > 0 && (
                      <ul className="resultado-redaccion__motivos">
                        {opcion.motivos.map((motivo) => (
                          <li key={motivo}>{motivo}</li>
                        ))}
                      </ul>
                    )}
                    {!opcion.aprobada_guardia && (
                      <p className="resultado-redaccion__descarte">
                        Descartada por la guardia de integridad: {opcion.razon_descarte}
                      </p>
                    )}
                  </label>
                ))}

                <label
                  className={
                    "resultado-redaccion__opcion" +
                    (parrafo.eleccion === OPCION_EDITADO ? " resultado-redaccion__opcion--elegida" : "")
                  }
                >
                  <input
                    type="radio"
                    name={`parrafo-${parrafo.indice}`}
                    checked={parrafo.eleccion === OPCION_EDITADO}
                    onChange={() => guardarEdicion(parrafo.indice, parrafo.textoEditado)}
                  />
                  <strong>Editar a mano</strong>
                </label>
                {parrafo.eleccion === OPCION_EDITADO && (
                  <textarea
                    rows={3}
                    value={parrafo.textoEditado}
                    onChange={(e) =>
                      setParrafos((actual) =>
                        actual.map((p) =>
                          p.indice === parrafo.indice ? { ...p, textoEditado: e.target.value } : p,
                        ),
                      )
                    }
                    onBlur={() => guardarEdicion(parrafo.indice, parrafo.textoEditado)}
                  />
                )}
              </div>

              {verCambios && (
                <div className="resultado-redaccion__cambios">
                  <h3>Cambios respecto al original</h3>
                  <p>
                    {resaltarDiferencias(parrafo.parrafoOriginal, textoElegido).map((segmento, i) =>
                      segmento.cambiado ? (
                        <mark key={i}>{segmento.texto}</mark>
                      ) : (
                        <span key={i}>{segmento.texto}</span>
                      ),
                    )}
                  </p>
                </div>
              )}

              {parrafo.guardando && <p className="resultado-redaccion__nota">Guardando…</p>}
              {parrafo.errorGuardado && (
                <p className="resultado-redaccion__error" role="alert">
                  {parrafo.errorGuardado}
                </p>
              )}
            </article>
          );
        })}
      </div>

      {parrafosListos.length > 0 && (
        <section className="resultado-redaccion__texto-final">
          <header>
            <h2>Texto final</h2>
            <div>
              <button type="button" onClick={() => setVerCambios((v) => !v)}>
                {verCambios ? "Ocultar cambios" : "Ver cambios"}
              </button>
              <button type="button" onClick={copiarTextoFinal}>
                {copiado ? "¡Copiado!" : "Copiar"}
              </button>
            </div>
          </header>
          <pre>{textoFinal}</pre>
        </section>
      )}

      {hallazgosEstilo.length > 0 && (
        <section className="resultado-redaccion__hallazgos-estilo">
          <h2>Hallazgos de estilo (EST-001)</h2>
          <div className="resultado-redaccion__lista">
            {hallazgosEstilo.map((h) => (
              <TarjetaHallazgo
                key={h.id}
                hallazgo={h}
                puedeDecidir={analisis.puede_decidir}
                alDecidir={actualizarEstadoHallazgoEstilo}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
