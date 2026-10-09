import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { clienteApi } from "../api/cliente";
import { useAuth } from "../auth/ContextoAuth";
import { PanelAnalisisRecientes } from "../componentes/PanelAnalisisRecientes";
import { dependenciasReales } from "../subida/dependenciasReales";
import { extensionDe, subirDocumento, type ProgresoSubida } from "../subida/subirDocumento";
import "./NuevoAnalisis.css";

const TIPOS_REVISION = [
  { valor: "contable", etiqueta: "Excel contable", habilitado: true },
  { valor: "ortografia", etiqueta: "Revisión ortográfica", habilitado: true },
  { valor: "redaccion", etiqueta: "Mejorar redacción", habilitado: true },
  { valor: "ocr", etiqueta: "Imagen a texto", habilitado: true },
] as const;

const EXTENSIONES_ACEPTADAS: Record<string, string[]> = {
  contable: ["xlsx"],
  ortografia: ["docx", "pptx", "xlsx", "pdf"],
  // CU-02 (RF-07): solo PDF/Word/texto -- a diferencia de CU-05, sin Excel
  // ni PowerPoint (ver validadores/redaccion/extraccion.py).
  redaccion: ["docx", "pdf"],
  // CU-06 (RF-11): mismos formatos que soporta el motor (ver
  // src/ocr/documentos.py, EXTENSIONES_IMAGEN + PDF).
  ocr: ["png", "jpg", "jpeg", "tiff", "bmp", "pdf"],
};

// CU-06 (Bloque 3): "uno o varios archivos" -- a diferencia de los demás
// tipos, 1:1 archivo:análisis (sin soporte de "un análisis con N documentos"
// en el modelo de datos), así que varios archivos crean varios análisis
// independientes (ver manejarEnvio).
const TIPOS_CON_VARIOS_ARCHIVOS = new Set(["ocr"]);

// Tipos de revisión que, además de subir un archivo, aceptan pegar el texto
// directamente (CU-05 y CU-02 comparten el mismo "documento virtual" --
// ver docs/02-analisis/02-analisis-cu02-redaccion-amigable.md §2.5).
const TIPOS_CON_TEXTO_PEGADO = new Set(["ortografia", "redaccion"]);

// CU-05 no tiene período de cierre (RN-03 es exclusivo de CU-01 contable) --
// el backend también lo hace opcional salvo para "contable" (ver
// api/esquemas.py, SolicitudCompletarCarga.periodo_cierre).
function requierePeriodoCierre(tipoRevision: string): boolean {
  return tipoRevision === "contable";
}

// CU-02 (RF-07): tipo de documento y acción -- ver
// validadores/redaccion/reglas.py (solo "Procedimiento" activa RD-01) y
// validadores/redaccion/mejora.py (ACCIONES_VALIDAS).
const TIPOS_DOCUMENTO_REDACCION = ["Correo", "Memo", "Procedimiento", "Informe"] as const;
const ACCIONES_REDACCION = [
  { valor: "corregir", etiqueta: "Corregir" },
  { valor: "aclarar", etiqueta: "Aclarar" },
  { valor: "formalizar", etiqueta: "Formalizar" },
] as const;

// Mismo patrón que SolicitudCompletarCarga.periodo_cierre en el backend. Se
// valida también acá porque <input type="month"> no es soportado igual en
// todos los navegadores (p. ej. Safari lo degrada a texto libre) — sin esto,
// un valor mal formado llega a la API y el usuario solo ve un error 422
// genérico en vez de una pista clara de qué corregir.
const PATRON_PERIODO_CIERRE = /^\d{4}-(0[1-9]|1[0-2])$/;

type FuenteConocimiento = {
  id: string;
  fuente_id: string;
  titulo: string;
  tipo: string;
  version: string;
  vigente_desde: string;
};

// Nombre de archivo sintético para el texto pegado (CU-05, RF-10) -- se
// reutiliza toda la subida por partes ya construida para CU-01 en vez de
// inventar un endpoint nuevo; el worker distingue el .txt por su extensión.
const NOMBRE_TEXTO_PEGADO = "texto-pegado.txt";

export function NuevoAnalisis() {
  const navegar = useNavigate();
  const { tienePermiso } = useAuth();
  const puedeCrearAnalisis = tienePermiso("analisis:crear");
  const [tipoRevision, setTipoRevision] = useState<string>("contable");
  const [periodoCierre, setPeriodoCierre] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [archivosVarios, setArchivosVarios] = useState<File[]>([]);
  const [progresoLote, setProgresoLote] = useState<{ actual: number; total: number } | null>(
    null,
  );
  const [mensajeLote, setMensajeLote] = useState<string | null>(null);
  const [modoOrtografia, setModoOrtografia] = useState<"archivo" | "texto">("archivo");
  const [textoPegado, setTextoPegado] = useState("");
  const [tipoDocumentoRedaccion, setTipoDocumentoRedaccion] = useState<string>(
    TIPOS_DOCUMENTO_REDACCION[0],
  );
  const [accionRedaccion, setAccionRedaccion] = useState<string>(ACCIONES_REDACCION[0].valor);
  const [fuentes, setFuentes] = useState<FuenteConocimiento[] | null>(null);
  // [PENDIENTE] La API todavía no acepta qué fuentes consultar por análisis
  // (SolicitudCompletarCarga no tiene ese campo); la selección queda guardada
  // acá para cuando se agregue ese campo en el backend, pero hoy no se envía.
  const [fuentesSeleccionadas, setFuentesSeleccionadas] = useState<Set<string>>(new Set());
  const [progreso, setProgreso] = useState<ProgresoSubida | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actualizarPanelEn, setActualizarPanelEn] = useState(0);

  useEffect(() => {
    if (!puedeCrearAnalisis) return;
    clienteApi.GET("/fuentes-conocimiento").then(({ data, error: errorRespuesta }) => {
      if (!errorRespuesta && data) setFuentes(data);
    });
  }, [puedeCrearAnalisis]);

  function alternarFuente(id: string) {
    setFuentesSeleccionadas((actual) => {
      const nuevo = new Set(actual);
      if (nuevo.has(id)) nuevo.delete(id);
      else nuevo.add(id);
      return nuevo;
    });
  }

  async function manejarEnvio(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    setMensajeLote(null);

    const esLote = TIPOS_CON_VARIOS_ARCHIVOS.has(tipoRevision) && archivosVarios.length > 1;
    const usaTextoPegado = TIPOS_CON_TEXTO_PEGADO.has(tipoRevision) && modoOrtografia === "texto";
    let archivoAEnviar: File | null = archivo;

    if (usaTextoPegado) {
      if (!textoPegado.trim()) {
        setError("Pega el texto que quieres revisar");
        return;
      }
      archivoAEnviar = new File([textoPegado], NOMBRE_TEXTO_PEGADO, { type: "text/plain" });
    } else if (esLote) {
      // validado más abajo, junto con las extensiones del lote completo.
    } else if (!archivo) {
      setError("Selecciona un archivo");
      return;
    }

    if (requierePeriodoCierre(tipoRevision)) {
      if (!periodoCierre) {
        setError("Selecciona el período de cierre");
        return;
      }
      if (!PATRON_PERIODO_CIERRE.test(periodoCierre)) {
        setError('El período de cierre debe tener el formato "AAAA-MM", por ejemplo 2026-08');
        return;
      }
    }
    if (!usaTextoPegado) {
      const extensionesValidas = EXTENSIONES_ACEPTADAS[tipoRevision] ?? [];
      const archivosAValidar = esLote ? archivosVarios : archivoAEnviar ? [archivoAEnviar] : [];
      const archivoInvalido = archivosAValidar.find(
        (a) => !extensionesValidas.includes(extensionDe(a.name)),
      );
      if (archivoInvalido) {
        setError(`El archivo debe ser: ${extensionesValidas.map((e) => `.${e}`).join(", ")}`);
        return;
      }
    }

    setSubiendo(true);
    setProgreso(null);
    try {
      if (esLote) {
        const idsCreados: string[] = [];
        for (let i = 0; i < archivosVarios.length; i++) {
          setProgresoLote({ actual: i + 1, total: archivosVarios.length });
          const resultado = await subirDocumento(
            archivosVarios[i],
            { tipoRevision, onProgreso: setProgreso },
            dependenciasReales,
          );
          idsCreados.push(resultado.analisisId);
        }
        setActualizarPanelEn((n) => n + 1);
        setArchivosVarios([]);
        setMensajeLote(
          `Se crearon ${idsCreados.length} análisis -- revisa el panel de análisis recientes.`,
        );
      } else {
        const resultado = await subirDocumento(
          archivoAEnviar as File,
          {
            tipoRevision,
            periodoCierre: requierePeriodoCierre(tipoRevision) ? periodoCierre : undefined,
            tipoDocumento: tipoRevision === "redaccion" ? tipoDocumentoRedaccion : undefined,
            accion: tipoRevision === "redaccion" ? accionRedaccion : undefined,
            onProgreso: setProgreso,
          },
          dependenciasReales,
        );
        setActualizarPanelEn((n) => n + 1);
        navegar(`/analisis/${resultado.analisisId}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar el análisis");
    } finally {
      setSubiendo(false);
      setProgresoLote(null);
    }
  }

  const porcentaje = progreso ? Math.round((progreso.bytesSubidos / progreso.bytesTotales) * 100) : 0;

  // RF-02/RNF-02 (P-12, Bloque 2): sin analisis:crear (Revisor, Curador,
  // Auditor) no se ofrece el formulario de carga -- se queda solo con el
  // panel de análisis recientes, que es donde hoy llegan a sus análisis
  // propios/del área mientras el Historial real (Bloque 3) no existe.
  if (!puedeCrearAnalisis) {
    return (
      <div className="nuevo-analisis">
        <PanelAnalisisRecientes actualizarEn={actualizarPanelEn} />
      </div>
    );
  }

  return (
    <div className="nuevo-analisis">
      <div className="nuevo-analisis__principal">
        <h1>Nuevo análisis</h1>

        <form className="nuevo-analisis__formulario" onSubmit={manejarEnvio}>
          <fieldset className="nuevo-analisis__campo">
            <legend>Tipo de revisión</legend>
            <div className="nuevo-analisis__opciones">
              {TIPOS_REVISION.map((tipo) => (
                <label
                  key={tipo.valor}
                  className={
                    "nuevo-analisis__opcion" +
                    (!tipo.habilitado ? " nuevo-analisis__opcion--deshabilitada" : "")
                  }
                >
                  <input
                    type="radio"
                    name="tipo-revision"
                    value={tipo.valor}
                    checked={tipoRevision === tipo.valor}
                    disabled={!tipo.habilitado}
                    onChange={() => setTipoRevision(tipo.valor)}
                  />
                  {tipo.etiqueta}
                  {!tipo.habilitado && <span> (próximamente)</span>}
                </label>
              ))}
            </div>
          </fieldset>

          {requierePeriodoCierre(tipoRevision) && (
            <label className="nuevo-analisis__campo">
              Período de cierre
              {/* Sin `required`: la validación la hace manejarEnvio para mostrar
                  un mensaje consistente con los demás errores del formulario,
                  en vez del tooltip nativo del navegador. */}
              <input
                type="month"
                placeholder="2026-08"
                pattern="\d{4}-(0[1-9]|1[0-2])"
                value={periodoCierre}
                onChange={(e) => setPeriodoCierre(e.target.value)}
              />
            </label>
          )}

          {tipoRevision === "redaccion" && (
            <>
              <label className="nuevo-analisis__campo">
                Tipo de documento
                <select
                  value={tipoDocumentoRedaccion}
                  onChange={(e) => setTipoDocumentoRedaccion(e.target.value)}
                >
                  {TIPOS_DOCUMENTO_REDACCION.map((tipo) => (
                    <option key={tipo} value={tipo}>
                      {tipo}
                    </option>
                  ))}
                </select>
              </label>
              <label className="nuevo-analisis__campo">
                Acción
                <select value={accionRedaccion} onChange={(e) => setAccionRedaccion(e.target.value)}>
                  {ACCIONES_REDACCION.map((accion) => (
                    <option key={accion.valor} value={accion.valor}>
                      {accion.etiqueta}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}

          {TIPOS_CON_TEXTO_PEGADO.has(tipoRevision) && (
            <fieldset className="nuevo-analisis__campo">
              <legend>Origen del texto</legend>
              <div className="nuevo-analisis__opciones">
                <label className="nuevo-analisis__opcion">
                  <input
                    type="radio"
                    name="modo-ortografia"
                    checked={modoOrtografia === "archivo"}
                    onChange={() => setModoOrtografia("archivo")}
                  />
                  Subir un documento
                </label>
                <label className="nuevo-analisis__opcion">
                  <input
                    type="radio"
                    name="modo-ortografia"
                    checked={modoOrtografia === "texto"}
                    onChange={() => setModoOrtografia("texto")}
                  />
                  Pegar texto directamente
                </label>
              </div>
            </fieldset>
          )}

          {TIPOS_CON_TEXTO_PEGADO.has(tipoRevision) && modoOrtografia === "texto" ? (
            <label className="nuevo-analisis__campo">
              Texto a revisar
              <textarea
                rows={8}
                value={textoPegado}
                onChange={(e) => setTextoPegado(e.target.value)}
                placeholder="Pega aquí el texto que quieres revisar…"
              />
            </label>
          ) : (
            <label className="nuevo-analisis__campo">
              {TIPOS_CON_VARIOS_ARCHIVOS.has(tipoRevision) ? "Documento(s)" : "Documento"}
              <input
                type="file"
                multiple={TIPOS_CON_VARIOS_ARCHIVOS.has(tipoRevision)}
                accept={(EXTENSIONES_ACEPTADAS[tipoRevision] ?? [])
                  .map((ext) => `.${ext}`)
                  .join(",")}
                onChange={(e) => {
                  const archivos = Array.from(e.target.files ?? []);
                  setArchivo(archivos[0] ?? null);
                  setArchivosVarios(archivos);
                }}
              />
              {archivosVarios.length > 1 && (
                <span className="nuevo-analisis__nota">
                  {archivosVarios.length} archivos seleccionados -- se crea un análisis por archivo.
                </span>
              )}
            </label>
          )}

          {fuentes && fuentes.length > 0 && (
            <fieldset className="nuevo-analisis__campo">
              <legend>Fuentes de la base de conocimiento a consultar</legend>
              {fuentes.map((f) => (
                <label key={f.id} className="nuevo-analisis__opcion">
                  <input
                    type="checkbox"
                    checked={fuentesSeleccionadas.has(f.id)}
                    onChange={() => alternarFuente(f.id)}
                  />
                  {f.titulo} (v{f.version})
                </label>
              ))}
            </fieldset>
          )}

          {subiendo && progresoLote && (
            <p className="nuevo-analisis__progreso-lote" role="status">
              Archivo {progresoLote.actual} de {progresoLote.total}…
            </p>
          )}

          {subiendo && progreso && (
            <div className="nuevo-analisis__progreso">
              <progress value={progreso.bytesSubidos} max={progreso.bytesTotales} />
              <span>
                {porcentaje}% — parte {progreso.parteActual} de {progreso.totalPartes}
              </span>
            </div>
          )}

          {mensajeLote && <p className="nuevo-analisis__mensaje-lote">{mensajeLote}</p>}

          {error && (
            <p className="nuevo-analisis__error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="nuevo-analisis__boton" disabled={subiendo}>
            {subiendo ? "Subiendo…" : "Iniciar análisis"}
          </button>
        </form>
      </div>

      <PanelAnalisisRecientes actualizarEn={actualizarPanelEn} />
    </div>
  );
}
