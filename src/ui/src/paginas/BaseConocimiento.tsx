import { useEffect, useState, type FormEvent } from "react";
import { clienteApi, obtenerTokenActual, URL_BASE_API } from "../api/cliente";
import { useAuth } from "../auth/ContextoAuth";
import "./BaseConocimiento.css";

type Fuente = {
  id: string;
  fuente_id: string;
  titulo: string;
  tipo: string;
  prioridad: number;
  version: string;
  vigente_desde: string;
  estado: string;
  dueno: string;
};

type Termino = {
  id: string;
  termino: string;
  definicion: string;
};

type FragmentoVistaPrevia = { contenido: string; seccion?: string | null; pagina?: number | null };

type ErrorImportacion = {
  hoja: string;
  fila: number | null;
  columna: string | null;
  mensaje: string;
};

type ReportePlantilla = {
  es_valido: boolean;
  errores: ErrorImportacion[];
  resumen?: Record<string, number>;
  cargado?: Record<string, number> | null;
};

// RF-16 (Bloque K5): el Curador gestiona (lee y escribe) las fuentes de su
// área; Administrador y Auditor solo pueden leer (todas las áreas) -- el
// backend ya lo exige, esto solo evita que quien no tiene acceso vea
// formularios/llamadas que van a terminar en 403.
const ROLES_CON_ACCESO = new Set(["curador", "administrador", "auditor"]);

const FORM_FUENTE_VACIO = {
  fuente_id: "",
  titulo: "",
  tipo: "",
  version: "",
  vigente_desde: "",
  dueno: "",
};

async function subirArchivo(
  ruta: string,
  cuerpo: FormData,
): Promise<{ ok: boolean; datos: unknown }> {
  const respuesta = await fetch(`${URL_BASE_API}${ruta}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${obtenerTokenActual() ?? ""}` },
    body: cuerpo,
  });
  const datos = await respuesta.json().catch(() => null);
  return { ok: respuesta.ok, datos };
}

export function BaseConocimiento() {
  const { usuario } = useAuth();
  const puedeEscribir = usuario?.rol === "curador";
  const tieneAcceso = usuario != null && ROLES_CON_ACCESO.has(usuario.rol);

  const [fuentes, setFuentes] = useState<Fuente[] | null>(null);
  const [glosario, setGlosario] = useState<Termino[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargandoAccion, setCargandoAccion] = useState<string | null>(null);
  const [vistaPrevia, setVistaPrevia] = useState<{
    fuenteId: string;
    fragmentos: FragmentoVistaPrevia[];
  } | null>(null);

  async function cargarFuentes() {
    const { data, error: errorRespuesta } = await clienteApi.GET("/curaduria/fuentes");
    if (!errorRespuesta && data) setFuentes(data);
  }

  async function cargarGlosario() {
    const { data, error: errorRespuesta } = await clienteApi.GET("/curaduria/glosario");
    if (!errorRespuesta && data) setGlosario(data);
  }

  useEffect(() => {
    if (!tieneAcceso) return;
    void cargarFuentes();
    void cargarGlosario();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tieneAcceso]);

  // --- subir nueva fuente ------------------------------------------------

  const [formFuente, setFormFuente] = useState(FORM_FUENTE_VACIO);
  const [archivoFuente, setArchivoFuente] = useState<File | null>(null);
  const [subiendoFuente, setSubiendoFuente] = useState(false);

  async function manejarSubirFuente(evento: FormEvent) {
    evento.preventDefault();
    if (!archivoFuente) {
      setError("Selecciona el archivo de la fuente");
      return;
    }
    setSubiendoFuente(true);
    setError(null);
    try {
      const cuerpo = new FormData();
      for (const [clave, valor] of Object.entries(formFuente)) cuerpo.append(clave, valor);
      cuerpo.append("archivo", archivoFuente);
      const { ok, datos } = await subirArchivo("/curaduria/fuentes", cuerpo);
      if (!ok) {
        const detalle = (datos as { detail?: string } | null)?.detail;
        setError(detalle ?? "No se pudo cargar la fuente");
        return;
      }
      setFormFuente(FORM_FUENTE_VACIO);
      setArchivoFuente(null);
      await cargarFuentes();
    } catch {
      setError("No se pudo conectar con el servidor");
    } finally {
      setSubiendoFuente(false);
    }
  }

  async function verVistaPrevia(fuente: Fuente) {
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.GET(
      "/curaduria/fuentes/{fuente_id}/vista-previa",
      { params: { path: { fuente_id: fuente.id } } },
    );
    if (errorRespuesta || !data) {
      setError("No se pudo generar la vista previa de esta fuente");
      return;
    }
    setVistaPrevia({ fuenteId: fuente.fuente_id, fragmentos: data.fragmentos });
  }

  async function aprobar(fuente: Fuente) {
    setCargandoAccion(fuente.id);
    setError(null);
    try {
      const { error: errorRespuesta } = await clienteApi.POST(
        "/curaduria/fuentes/{fuente_id}/aprobar",
        { params: { path: { fuente_id: fuente.id } } },
      );
      if (errorRespuesta) {
        setError("No se pudo aprobar la fuente (revise que el archivo tenga texto extraíble)");
        return;
      }
      await cargarFuentes();
    } finally {
      setCargandoAccion(null);
    }
  }

  async function marcarObsoleta(fuente: Fuente) {
    setCargandoAccion(fuente.id);
    setError(null);
    try {
      const { error: errorRespuesta } = await clienteApi.POST(
        "/curaduria/fuentes/{fuente_id}/marcar-obsoleta",
        { params: { path: { fuente_id: fuente.id } } },
      );
      if (errorRespuesta) {
        setError("No se pudo marcar la fuente como obsoleta");
        return;
      }
      await cargarFuentes();
    } finally {
      setCargandoAccion(null);
    }
  }

  // --- glosario ------------------------------------------------------------

  const [nuevoTermino, setNuevoTermino] = useState({ termino: "", definicion: "" });

  async function agregarTermino(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    const { error: errorRespuesta } = await clienteApi.POST("/curaduria/glosario", {
      body: nuevoTermino,
    });
    if (errorRespuesta) {
      setError("No se pudo agregar el término");
      return;
    }
    setNuevoTermino({ termino: "", definicion: "" });
    await cargarGlosario();
  }

  async function eliminarTermino(id: string) {
    setError(null);
    const { error: errorRespuesta } = await clienteApi.DELETE("/curaduria/glosario/{termino_id}", {
      params: { path: { termino_id: id } },
    });
    if (errorRespuesta) {
      setError("No se pudo eliminar el término");
      return;
    }
    await cargarGlosario();
  }

  // --- importar plantilla ---------------------------------------------------

  const [archivoPlantilla, setArchivoPlantilla] = useState<File | null>(null);
  const [reportePlantilla, setReportePlantilla] = useState<ReportePlantilla | null>(null);
  const [procesandoPlantilla, setProcesandoPlantilla] = useState(false);

  async function enviarPlantilla(accion: "validar" | "importar") {
    if (!archivoPlantilla) {
      setError("Selecciona la plantilla (.xlsx)");
      return;
    }
    setProcesandoPlantilla(true);
    setError(null);
    try {
      const cuerpo = new FormData();
      cuerpo.append("archivo", archivoPlantilla);
      const { ok, datos } = await subirArchivo(`/curaduria/plantilla/${accion}`, cuerpo);
      if (!ok) {
        const detalle = (datos as { detail?: string } | null)?.detail;
        setError(detalle ?? "No se pudo procesar la plantilla");
        return;
      }
      const reporte = datos as ReportePlantilla;
      setReportePlantilla(reporte);
      if (accion === "importar" && reporte.es_valido) {
        await cargarFuentes();
        await cargarGlosario();
      }
    } catch {
      setError("No se pudo conectar con el servidor");
    } finally {
      setProcesandoPlantilla(false);
    }
  }

  if (!tieneAcceso) {
    return (
      <div className="base-conocimiento">
        <h1>Base de conocimiento</h1>
        <p>Su rol no tiene acceso a esta sección.</p>
      </div>
    );
  }

  return (
    <div className="base-conocimiento">
      <h1>Base de conocimiento</h1>
      {error && (
        <p className="base-conocimiento__error" role="alert">
          {error}
        </p>
      )}

      <section className="base-conocimiento__seccion">
        <h2>Fuentes</h2>

        {puedeEscribir && (
          <form className="base-conocimiento__form" onSubmit={manejarSubirFuente}>
            <input
              aria-label="fuente_id"
              placeholder="fuente_id (p. ej. POL-002)"
              value={formFuente.fuente_id}
              onChange={(e) => setFormFuente({ ...formFuente, fuente_id: e.target.value })}
              required
            />
            <input
              aria-label="Título"
              placeholder="Título"
              value={formFuente.titulo}
              onChange={(e) => setFormFuente({ ...formFuente, titulo: e.target.value })}
              required
            />
            <input
              aria-label="Tipo"
              placeholder="Tipo (p. ej. política (Word))"
              value={formFuente.tipo}
              onChange={(e) => setFormFuente({ ...formFuente, tipo: e.target.value })}
              required
            />
            <input
              aria-label="Versión"
              placeholder="Versión"
              value={formFuente.version}
              onChange={(e) => setFormFuente({ ...formFuente, version: e.target.value })}
              required
            />
            <input
              aria-label="Vigente desde"
              type="date"
              value={formFuente.vigente_desde}
              onChange={(e) => setFormFuente({ ...formFuente, vigente_desde: e.target.value })}
              required
            />
            <input
              aria-label="Dueño"
              placeholder="Dueño"
              value={formFuente.dueno}
              onChange={(e) => setFormFuente({ ...formFuente, dueno: e.target.value })}
              required
            />
            <input
              aria-label="Archivo"
              type="file"
              accept=".pdf,.docx,.md"
              onChange={(e) => setArchivoFuente(e.target.files?.[0] ?? null)}
              required
            />
            <button type="submit" disabled={subiendoFuente}>
              {subiendoFuente ? "Subiendo…" : "Subir nueva fuente"}
            </button>
          </form>
        )}

        {fuentes === null ? (
          <p>Cargando…</p>
        ) : fuentes.length === 0 ? (
          <p className="base-conocimiento__vacio">Todavía no hay fuentes registradas.</p>
        ) : (
          <table className="base-conocimiento__tabla">
            <thead>
              <tr>
                <th>fuente_id</th>
                <th>Título</th>
                <th>Versión</th>
                <th>Estado</th>
                <th>Dueño</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {fuentes.map((f) => (
                <tr key={f.id}>
                  <td>{f.fuente_id}</td>
                  <td>{f.titulo}</td>
                  <td>{f.version}</td>
                  <td>
                    <span
                      className={`base-conocimiento__estado base-conocimiento__estado--${f.estado}`}
                    >
                      {f.estado}
                    </span>
                  </td>
                  <td>{f.dueno}</td>
                  <td className="base-conocimiento__acciones">
                    <button type="button" onClick={() => verVistaPrevia(f)}>
                      Vista previa
                    </button>
                    {puedeEscribir && f.estado === "borrador" && (
                      <button
                        type="button"
                        disabled={cargandoAccion === f.id}
                        onClick={() => aprobar(f)}
                      >
                        {cargandoAccion === f.id ? "Aprobando…" : "Aprobar"}
                      </button>
                    )}
                    {puedeEscribir && f.estado === "vigente" && (
                      <button
                        type="button"
                        disabled={cargandoAccion === f.id}
                        onClick={() => marcarObsoleta(f)}
                      >
                        Marcar obsoleta
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {vistaPrevia && (
          <div className="base-conocimiento__vista-previa">
            <h3>Vista previa — {vistaPrevia.fuenteId}</h3>
            {vistaPrevia.fragmentos.map((f, indice) => (
              <article key={indice} className="base-conocimiento__fragmento">
                <p className="base-conocimiento__fragmento-meta">
                  {f.seccion ?? (f.pagina != null ? `Página ${f.pagina}` : "(sin sección)")}
                </p>
                <p>{f.contenido}</p>
              </article>
            ))}
            <button type="button" onClick={() => setVistaPrevia(null)}>
              Cerrar
            </button>
          </div>
        )}
      </section>

      <section className="base-conocimiento__seccion">
        <h2>Glosario</h2>

        {puedeEscribir && (
          <form className="base-conocimiento__form" onSubmit={agregarTermino}>
            <input
              aria-label="Término"
              placeholder="Término"
              value={nuevoTermino.termino}
              onChange={(e) => setNuevoTermino({ ...nuevoTermino, termino: e.target.value })}
              required
            />
            <input
              aria-label="Definición"
              placeholder="Definición"
              value={nuevoTermino.definicion}
              onChange={(e) => setNuevoTermino({ ...nuevoTermino, definicion: e.target.value })}
              required
            />
            <button type="submit">Agregar término</button>
          </form>
        )}

        {glosario === null ? (
          <p>Cargando…</p>
        ) : glosario.length === 0 ? (
          <p className="base-conocimiento__vacio">Todavía no hay términos en el glosario.</p>
        ) : (
          <ul className="base-conocimiento__glosario">
            {glosario.map((t) => (
              <li key={t.id}>
                <span>
                  <strong>{t.termino}</strong>: {t.definicion}
                </span>
                {puedeEscribir && (
                  <button type="button" onClick={() => eliminarTermino(t.id)}>
                    Eliminar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {puedeEscribir && (
        <section className="base-conocimiento__seccion">
          <h2>Importar plantilla</h2>
          <p className="base-conocimiento__ayuda">
            Sube <code>Plantilla_Base_Conocimiento_SFC.xlsx</code> completa (Inventario de
            fuentes, Catálogo de cuentas, Reglas contables, Glosario, Checklist de cierre).
            "Validar" solo revisa; "Importar" carga todo como borrador si no hay errores.
          </p>
          <input
            aria-label="Plantilla"
            type="file"
            accept=".xlsx"
            onChange={(e) => setArchivoPlantilla(e.target.files?.[0] ?? null)}
          />
          <div className="base-conocimiento__acciones-plantilla">
            <button
              type="button"
              disabled={procesandoPlantilla}
              onClick={() => enviarPlantilla("validar")}
            >
              {procesandoPlantilla ? "Procesando…" : "Validar"}
            </button>
            <button
              type="button"
              disabled={procesandoPlantilla}
              onClick={() => enviarPlantilla("importar")}
            >
              {procesandoPlantilla ? "Procesando…" : "Importar"}
            </button>
          </div>

          {reportePlantilla &&
            (reportePlantilla.es_valido ? (
              <p className="base-conocimiento__reporte-ok">
                {reportePlantilla.cargado
                  ? `Importada: ${reportePlantilla.cargado.fuentes} fuentes, ` +
                    `${reportePlantilla.cargado.cuentas} cuentas, ` +
                    `${reportePlantilla.cargado.reglas} reglas, ` +
                    `${reportePlantilla.cargado.glosario} términos de glosario, ` +
                    `${reportePlantilla.cargado.checklist} actividades de checklist.`
                  : `Válida: ${reportePlantilla.resumen?.fuentes ?? 0} fuentes, ` +
                    `${reportePlantilla.resumen?.cuentas ?? 0} cuentas, ` +
                    `${reportePlantilla.resumen?.reglas ?? 0} reglas, ` +
                    `${reportePlantilla.resumen?.glosario ?? 0} términos de glosario, ` +
                    `${reportePlantilla.resumen?.checklist ?? 0} actividades de checklist.`}
              </p>
            ) : (
              <ul className="base-conocimiento__reporte-errores">
                {reportePlantilla.errores.map((err, indice) => (
                  <li key={indice}>
                    {err.hoja}
                    {err.fila != null ? `, fila ${err.fila}` : ""}
                    {err.columna ? `, columna '${err.columna}'` : ""}: {err.mensaje}
                  </li>
                ))}
              </ul>
            ))}
        </section>
      )}
    </div>
  );
}
