import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { clienteApi } from "../api/cliente";
import { PanelAnalisisRecientes } from "../componentes/PanelAnalisisRecientes";
import { dependenciasReales } from "../subida/dependenciasReales";
import { extensionDe, subirDocumento, type ProgresoSubida } from "../subida/subirDocumento";
import "./NuevoAnalisis.css";

const TIPOS_REVISION = [
  { valor: "contable", etiqueta: "Excel contable", habilitado: true },
  { valor: "ortografia", etiqueta: "Revisión ortográfica", habilitado: true },
  { valor: "redaccion", etiqueta: "Redacción", habilitado: false },
  { valor: "actualizacion_normativa", etiqueta: "Actualización normativa", habilitado: false },
  { valor: "control", etiqueta: "Control", habilitado: false },
  { valor: "ocr", etiqueta: "OCR", habilitado: false },
] as const;

const EXTENSIONES_ACEPTADAS: Record<string, string[]> = {
  contable: ["xlsx"],
  ortografia: ["docx", "pptx", "xlsx", "pdf"],
};

// CU-05 no tiene período de cierre (RN-03 es exclusivo de CU-01 contable) --
// el backend también lo hace opcional salvo para "contable" (ver
// api/esquemas.py, SolicitudCompletarCarga.periodo_cierre).
function requierePeriodoCierre(tipoRevision: string): boolean {
  return tipoRevision === "contable";
}

// Mismo patrón que SolicitudCompletarCarga.periodo_cierre en el backend. Se
// valida también acá porque <input type="month"> no es soportado igual en
// todos los navegadores (p. ej. Safari lo degrada a texto libre) — sin esto,
// un valor mal formado llega a la API y el usuario solo ve un error 422
// genérico en vez de una pista clara de qué corregir.
const PATRON_PERIODO_CIERRE = /^\d{4}-(0[1-9]|1[0-2])$/;

type FuenteConocimiento = { id: string; nombre: string; version: string; vigente_desde: string };

// Nombre de archivo sintético para el texto pegado (CU-05, RF-10) -- se
// reutiliza toda la subida por partes ya construida para CU-01 en vez de
// inventar un endpoint nuevo; el worker distingue el .txt por su extensión.
const NOMBRE_TEXTO_PEGADO = "texto-pegado.txt";

export function NuevoAnalisis() {
  const navegar = useNavigate();
  const [tipoRevision, setTipoRevision] = useState<string>("contable");
  const [periodoCierre, setPeriodoCierre] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [modoOrtografia, setModoOrtografia] = useState<"archivo" | "texto">("archivo");
  const [textoPegado, setTextoPegado] = useState("");
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
    clienteApi.GET("/fuentes-conocimiento").then(({ data, error: errorRespuesta }) => {
      if (!errorRespuesta && data) setFuentes(data);
    });
  }, []);

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

    const usaTextoPegado = tipoRevision === "ortografia" && modoOrtografia === "texto";
    let archivoAEnviar: File | null = archivo;

    if (usaTextoPegado) {
      if (!textoPegado.trim()) {
        setError("Pega el texto que quieres revisar");
        return;
      }
      archivoAEnviar = new File([textoPegado], NOMBRE_TEXTO_PEGADO, { type: "text/plain" });
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
    if (!usaTextoPegado && archivoAEnviar) {
      const extensionesValidas = EXTENSIONES_ACEPTADAS[tipoRevision] ?? [];
      if (!extensionesValidas.includes(extensionDe(archivoAEnviar.name))) {
        setError(`El archivo debe ser: ${extensionesValidas.map((e) => `.${e}`).join(", ")}`);
        return;
      }
    }

    setSubiendo(true);
    setProgreso(null);
    try {
      const resultado = await subirDocumento(
        archivoAEnviar as File,
        {
          tipoRevision,
          periodoCierre: requierePeriodoCierre(tipoRevision) ? periodoCierre : undefined,
          onProgreso: setProgreso,
        },
        dependenciasReales,
      );
      setActualizarPanelEn((n) => n + 1);
      navegar(`/analisis/${resultado.analisisId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar el análisis");
    } finally {
      setSubiendo(false);
    }
  }

  const porcentaje = progreso ? Math.round((progreso.bytesSubidos / progreso.bytesTotales) * 100) : 0;

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

          {tipoRevision === "ortografia" && (
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

          {tipoRevision === "ortografia" && modoOrtografia === "texto" ? (
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
              Documento
              <input
                type="file"
                accept={(EXTENSIONES_ACEPTADAS[tipoRevision] ?? [])
                  .map((ext) => `.${ext}`)
                  .join(",")}
                onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              />
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
                  {f.nombre} (v{f.version})
                </label>
              ))}
            </fieldset>
          )}

          {subiendo && progreso && (
            <div className="nuevo-analisis__progreso">
              <progress value={progreso.bytesSubidos} max={progreso.bytesTotales} />
              <span>
                {porcentaje}% — parte {progreso.parteActual} de {progreso.totalPartes}
              </span>
            </div>
          )}

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
