import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { obtenerTokenActual, URL_BASE_API } from "../api/cliente";
import { descargarArchivo } from "../api/descargas";
import { EstadoBadge } from "../componentes/EstadoBadge";
import { useAnalisisEnVivo } from "../hooks/useAnalisisEnVivo";
import { dependenciasReales } from "../subida/dependenciasReales";
import { subirDocumento } from "../subida/subirDocumento";
import "./ResultadoOcr.css";

// Mismo vocabulario que ocr.calidad (src/ocr/calidad.py): severidad "alta"
// viene de nivel "dudosa" (rojo), "media" de "revisar" (amarillo) -- ver
// pipeline_ocr._hallazgo_palabra_dudosa.
const NIVEL_POR_SEVERIDAD: Record<string, "dudosa" | "revisar"> = {
  alta: "dudosa",
  media: "revisar",
};

// `HallazgoEsquema` (api/esquemas.py) no expone `texto_original` -- igual que
// ya hace TarjetaHallazgo.tsx para los hallazgos de ortografía, la palabra se
// extrae del formato fijo que arma `pipeline_ocr._hallazgo_palabra_dudosa`:
// "Palabra reconocida con confianza {nivel} ({conf}%): «{texto}»".
const PATRON_PALABRA_DUDOSA = /«(.+)»$/;

function extraerPalabraDudosa(descripcion: string): string | null {
  return PATRON_PALABRA_DUDOSA.exec(descripcion)?.[1] ?? null;
}

/** Descarga autenticada de un recurso binario para previsualizarlo en el
 * navegador (no para disparar una descarga, a diferencia de
 * `api/descargas.ts::descargarArchivo`) -- el token va en el header
 * Authorization, así que un <img src="..."> directo a la API no sirve. */
async function obtenerBlob(rutaRelativa: string): Promise<Blob | null> {
  const token = obtenerTokenActual();
  const respuesta = await fetch(`${URL_BASE_API}${rutaRelativa}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!respuesta.ok) return null;
  return respuesta.blob();
}

/** Igual que `obtenerBlob`, pero para texto plano -- `respuesta.text()`
 * directo, sin pasar por un `Blob` intermedio (el texto reconocido no
 * necesita convertirse a un objeto binario para mostrarse/editarse). */
async function obtenerTexto(rutaRelativa: string): Promise<string | null> {
  const token = obtenerTokenActual();
  const respuesta = await fetch(`${URL_BASE_API}${rutaRelativa}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!respuesta.ok) return null;
  return respuesta.text();
}

/** Parte el texto en fragmentos, envolviendo cada palabra dudosa en un
 * <mark> con su nivel -- coincidencia exacta de texto (igual que
 * `ocr.exportar_docx`), no por posición. */
function resaltarDudosas(texto: string, nivelPorPalabra: Map<string, "dudosa" | "revisar">) {
  if (nivelPorPalabra.size === 0) return texto;
  return texto.split(/(\s+)/).map((token, i) => {
    const nivel = nivelPorPalabra.get(token.trim());
    if (!nivel) return <span key={i}>{token}</span>;
    return (
      <mark key={i} className={`resultado-ocr__dudosa resultado-ocr__dudosa--${nivel}`}>
        {token}
      </mark>
    );
  });
}

export function ResultadoOcr({ analisisId }: { analisisId: string }) {
  const navegar = useNavigate();
  const { analisis, hallazgos, error } = useAnalisisEnVivo(analisisId);
  const [urlOriginal, setUrlOriginal] = useState<string | null>(null);
  const [tipoOriginal, setTipoOriginal] = useState<string>("");
  const [texto, setTexto] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);
  const [textoEditado, setTextoEditado] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const [errorPropio, setErrorPropio] = useState<string | null>(null);
  const [encadenando, setEncadenando] = useState(false);

  const documentoId = analisis?.documento_id ?? null;
  const terminado =
    !!analisis && analisis.estado !== "cargado" && analisis.estado !== "procesando";

  // El original se puede ver apenas se conoce el documento -- no hace falta
  // esperar a que termine el OCR.
  useEffect(() => {
    if (!documentoId) return;
    let cancelado = false;
    obtenerBlob(`/documentos/${documentoId}/version-original`).then((blob) => {
      if (cancelado || !blob) return;
      setTipoOriginal(blob.type);
      setUrlOriginal(URL.createObjectURL(blob));
    });
    return () => {
      cancelado = true;
    };
  }, [documentoId]);

  // El texto reconocido solo existe una vez el análisis llega a un estado
  // terminal (publicado por pipeline_ocr.procesar_documento_ocr).
  useEffect(() => {
    if (!documentoId || !terminado || texto !== null) return;
    let cancelado = false;
    obtenerTexto(`/documentos/${documentoId}/version-corregida`).then((contenido) => {
      if (cancelado || contenido === null) return;
      setTexto(contenido);
      setTextoEditado(contenido);
    });
    return () => {
      cancelado = true;
    };
  }, [documentoId, terminado, texto]);

  const nivelPorPalabra = new Map(
    hallazgos
      .map((h) => [extraerPalabraDudosa(h.descripcion), NIVEL_POR_SEVERIDAD[h.severidad]] as const)
      .filter((par): par is [string, "dudosa" | "revisar"] => par[0] !== null && !!par[1]),
  );
  const avisoDocumentoIlegible = hallazgos.find((h) => h.ubicacion === "Documento completo");

  async function copiarTexto() {
    try {
      await navigator.clipboard.writeText(texto ?? "");
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      setErrorPropio("No se pudo copiar al portapapeles");
    }
  }

  async function guardarEdicion() {
    if (!documentoId) return;
    setGuardando(true);
    setErrorPropio(null);
    try {
      const token = obtenerTokenActual();
      const respuesta = await fetch(`${URL_BASE_API}/documentos/${documentoId}/texto-ocr`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ texto: textoEditado }),
      });
      if (!respuesta.ok) throw new Error();
      setTexto(textoEditado);
      setEditando(false);
    } catch {
      setErrorPropio("No se pudo guardar la edición");
    } finally {
      setGuardando(false);
    }
  }

  async function encadenarA(tipoRevision: "ortografia" | "redaccion") {
    if (texto === null) return;
    setEncadenando(true);
    setErrorPropio(null);
    try {
      const archivo = new File([texto], "ocr-resultado.txt", { type: "text/plain" });
      const resultado = await subirDocumento(
        archivo,
        {
          tipoRevision,
          tipoDocumento: tipoRevision === "redaccion" ? "Memo" : undefined,
          accion: tipoRevision === "redaccion" ? "corregir" : undefined,
        },
        dependenciasReales,
      );
      navegar(`/analisis/${resultado.analisisId}`);
    } catch {
      setErrorPropio("No se pudo iniciar el nuevo análisis");
      setEncadenando(false);
    }
  }

  if (error) {
    return (
      <div className="resultado-ocr">
        <p className="resultado-ocr__error" role="alert">
          {error}
        </p>
      </div>
    );
  }

  if (!analisis) {
    return (
      <div className="resultado-ocr">
        <p>Cargando…</p>
      </div>
    );
  }

  return (
    <div className="resultado-ocr">
      <h1>Imagen a texto — Resultado</h1>
      <p className="resultado-ocr__documento">
        {analisis.nombre_documento} <EstadoBadge estado={analisis.estado} />
      </p>

      {!terminado && <p className="resultado-ocr__mensaje">Procesando documento…</p>}

      {avisoDocumentoIlegible && (
        <p className="resultado-ocr__aviso" role="alert">
          {avisoDocumentoIlegible.descripcion}
        </p>
      )}

      <div className="resultado-ocr__lado-a-lado">
        <div className="resultado-ocr__panel">
          <h2>Original</h2>
          {urlOriginal ? (
            tipoOriginal.startsWith("image/") ? (
              <img src={urlOriginal} alt={analisis.nombre_documento ?? "Documento original"} />
            ) : (
              <embed src={urlOriginal} type={tipoOriginal} className="resultado-ocr__embed" />
            )
          ) : (
            <p className="resultado-ocr__mensaje">Cargando original…</p>
          )}
        </div>

        <div className="resultado-ocr__panel">
          <h2>Texto reconocido</h2>
          {texto === null ? (
            <p className="resultado-ocr__mensaje">
              {terminado ? "Cargando texto…" : "Todavía no hay texto -- el análisis sigue en curso."}
            </p>
          ) : editando ? (
            <>
              <textarea
                className="resultado-ocr__textarea"
                rows={16}
                value={textoEditado}
                onChange={(e) => setTextoEditado(e.target.value)}
              />
              <div className="resultado-ocr__acciones">
                <button type="button" onClick={guardarEdicion} disabled={guardando}>
                  {guardando ? "Guardando…" : "Guardar"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTextoEditado(texto);
                    setEditando(false);
                  }}
                  disabled={guardando}
                >
                  Cancelar
                </button>
              </div>
            </>
          ) : (
            <>
              <pre className="resultado-ocr__texto">{resaltarDudosas(texto, nivelPorPalabra)}</pre>
              <div className="resultado-ocr__acciones">
                <button type="button" onClick={() => setEditando(true)}>
                  Editar texto
                </button>
                <button type="button" onClick={copiarTexto}>
                  {copiado ? "¡Copiado!" : "Copiar"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {texto !== null && documentoId && (
        <div className="resultado-ocr__descargas">
          <h2>Descargar</h2>
          <div className="resultado-ocr__acciones">
            <button
              type="button"
              onClick={() => descargarArchivo(`/documentos/${documentoId}/version-corregida`)}
            >
              Descargar .txt
            </button>
            <button
              type="button"
              onClick={() => descargarArchivo(`/documentos/${documentoId}/ocr-docx`)}
            >
              Descargar .docx (con dudosas resaltadas)
            </button>
          </div>

          <h2>Continuar con</h2>
          <div className="resultado-ocr__acciones">
            <button type="button" onClick={() => encadenarA("ortografia")} disabled={encadenando}>
              Revisar ortografía
            </button>
            <button type="button" onClick={() => encadenarA("redaccion")} disabled={encadenando}>
              Mejorar redacción
            </button>
          </div>
        </div>
      )}

      {errorPropio && (
        <p className="resultado-ocr__error" role="alert">
          {errorPropio}
        </p>
      )}
    </div>
  );
}
