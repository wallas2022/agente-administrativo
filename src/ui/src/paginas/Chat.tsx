import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { clienteApi, obtenerTokenActual, URL_BASE_API } from "../api/cliente";
import { MENSAJE_SIN_CONEXION, mensajeDeError } from "../utils/errores";
import { TextoConNegritas } from "../componentes/TextoConNegritas";
import "./Chat.css";

type FuenteCitada = {
  fuente_id: string;
  version: string;
  seccion?: string | null;
  pagina?: number | null;
};

type Mensaje = {
  id: string;
  rol: string;
  contenido: string;
  fecha_hora: string;
  fuentes_citadas?: FuenteCitada[] | null;
};

type Conversacion = {
  id: string;
  titulo?: string | null;
  fecha_creacion: string;
};

const EXTENSIONES_ACEPTADAS_ADJUNTO =
  ".png,.jpg,.jpeg,.tiff,.tif,.bmp,.docx,.xlsx,.pdf";

async function enviarMensajeMultipart(
  conversacionId: string,
  cuerpo: FormData,
): Promise<{ ok: boolean; datos: unknown }> {
  const respuesta = await fetch(
    `${URL_BASE_API}/chat/conversaciones/${conversacionId}/mensajes`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${obtenerTokenActual() ?? ""}` },
      body: cuerpo,
    },
  );
  const datos = await respuesta.json().catch(() => null);
  return { ok: respuesta.ok, datos };
}

function etiquetaDeFuente(f: FuenteCitada): string {
  if (f.seccion) return `${f.fuente_id} v${f.version}, ${f.seccion}`;
  if (f.pagina != null) return `${f.fuente_id} v${f.version}, pág. ${f.pagina}`;
  return `${f.fuente_id} v${f.version}`;
}

function tituloDeConversacion(c: Conversacion): string {
  return c.titulo ?? `Conversación del ${new Date(c.fecha_creacion).toLocaleString("es-GT")}`;
}

/** HU-31..34 (P-14, Bloque 3, CU-12): pantalla de inicio de todos los
 * roles -- chat sobre la Base de Conocimiento vigente, con historial de
 * conversaciones propio y adjunto opcional (imagen u documento). El
 * backend responde en una sola llamada (sin streaming): una pregunta real
 * puede tardar un par de minutos contra el LLM local sin GPU -- el aviso
 * "pensando" de abajo existe para que eso no se vea como que la pantalla
 * se colgó. */
export function Chat() {
  const [conversaciones, setConversaciones] = useState<Conversacion[] | null>(null);
  const [conversacionActualId, setConversacionActualId] = useState<string | null>(null);
  const [mensajes, setMensajes] = useState<Mensaje[] | null>(null);
  const [contenido, setContenido] = useState("");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cargandoConversacion, setCargandoConversacion] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const entradaArchivoRef = useRef<HTMLInputElement>(null);

  const cargarConversaciones = useCallback(async () => {
    const { data, error: errorRespuesta } = await clienteApi.GET("/chat/conversaciones");
    if (!errorRespuesta && data) setConversaciones(data);
  }, []);

  useEffect(() => {
    void cargarConversaciones();
  }, [cargarConversaciones]);

  async function abrirConversacion(id: string) {
    setError(null);
    setConversacionActualId(id);
    setCargandoConversacion(true);
    try {
      const { data, error: errorRespuesta } = await clienteApi.GET(
        "/chat/conversaciones/{conversacion_id}",
        { params: { path: { conversacion_id: id } } },
      );
      if (errorRespuesta || !data) {
        setError("No se pudo cargar la conversación");
        return;
      }
      setMensajes(data.mensajes);
    } finally {
      setCargandoConversacion(false);
    }
  }

  function nuevaConversacion() {
    setConversacionActualId(null);
    setMensajes([]);
    setError(null);
  }

  async function enviarMensaje(evento: FormEvent) {
    evento.preventDefault();
    if (!contenido.trim() || enviando) return;
    setError(null);

    let idConversacion = conversacionActualId;
    if (!idConversacion) {
      const { data, error: errorRespuesta } = await clienteApi.POST("/chat/conversaciones");
      if (errorRespuesta || !data) {
        setError("No se pudo crear la conversación");
        return;
      }
      idConversacion = data.id;
      setConversacionActualId(idConversacion);
      setConversaciones((actuales) => [data, ...(actuales ?? [])]);
    }

    const contenidoEnviado = contenido;
    const archivoEnviado = archivo;
    setContenido("");
    setArchivo(null);
    if (entradaArchivoRef.current) entradaArchivoRef.current.value = "";
    setMensajes((actuales) => [
      ...(actuales ?? []),
      {
        id: "optimista",
        rol: "user",
        contenido: contenidoEnviado,
        fecha_hora: new Date().toISOString(),
      },
    ]);

    setEnviando(true);
    try {
      const cuerpo = new FormData();
      cuerpo.append("contenido", contenidoEnviado);
      if (archivoEnviado) cuerpo.append("adjunto", archivoEnviado);

      const { ok, datos } = await enviarMensajeMultipart(idConversacion, cuerpo);
      if (!ok) {
        setError(mensajeDeError(datos, "No se pudo enviar el mensaje"));
        return;
      }
      await abrirConversacion(idConversacion);
      await cargarConversaciones();
    } catch {
      setError(MENSAJE_SIN_CONEXION);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="chat">
      <aside className="chat__conversaciones">
        <button type="button" className="chat__nueva" onClick={nuevaConversacion}>
          Nueva conversación
        </button>
        {conversaciones === null ? null : conversaciones.length === 0 ? (
          <p className="chat__vacio">Todavía no tienes conversaciones.</p>
        ) : (
          <ul className="chat__lista-conversaciones">
            {conversaciones.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={
                    "chat__conversacion" +
                    (c.id === conversacionActualId ? " chat__conversacion--activa" : "")
                  }
                  onClick={() => abrirConversacion(c.id)}
                >
                  {tituloDeConversacion(c)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <div className="chat__principal">
        <h1>Chat de la base de conocimiento</h1>

        <div className="chat__mensajes" aria-live="polite">
          {cargandoConversacion ? (
            <p className="chat__vacio">Cargando…</p>
          ) : mensajes === null || mensajes.length === 0 ? (
            <p className="chat__vacio">
              Escribe una pregunta sobre la base de conocimiento para empezar.
            </p>
          ) : (
            mensajes.map((m) => (
              <div key={m.id} className={"chat__mensaje chat__mensaje--" + m.rol}>
                <span className="chat__mensaje-rol">{m.rol === "user" ? "Tú" : "Asistente"}</span>
                <p className="chat__mensaje-contenido">
                  <TextoConNegritas texto={m.contenido} />
                </p>
                {m.fuentes_citadas && m.fuentes_citadas.length > 0 && (
                  <ul className="chat__fuentes">
                    {m.fuentes_citadas.map((f, i) => (
                      <li key={i}>{etiquetaDeFuente(f)}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))
          )}
          {enviando && (
            <p className="chat__pensando" role="status">
              El asistente está pensando… puede tardar un par de minutos.
            </p>
          )}
        </div>

        {error && (
          <p className="chat__error" role="alert">
            {error}
          </p>
        )}

        <form className="chat__formulario" onSubmit={enviarMensaje}>
          <label className="chat__campo-pregunta">
            Pregunta
            <textarea
              rows={2}
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              placeholder="Pregunta algo sobre la base de conocimiento…"
              disabled={enviando}
            />
          </label>
          <label className="chat__campo-adjunto">
            Adjuntar imagen o documento (opcional)
            <input
              ref={entradaArchivoRef}
              type="file"
              accept={EXTENSIONES_ACEPTADAS_ADJUNTO}
              disabled={enviando}
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
            />
          </label>
          {archivo && <span className="chat__nota-adjunto">Adjunto: {archivo.name}</span>}
          <button type="submit" disabled={enviando || !contenido.trim()}>
            {enviando ? "Enviando…" : "Enviar"}
          </button>
        </form>
      </div>
    </div>
  );
}
