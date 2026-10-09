import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { clienteApi } from "../api/cliente";
import { useAuth } from "../auth/ContextoAuth";
import { EstadoBadge } from "../componentes/EstadoBadge";
import { rutaDeAnalisis } from "../utils/rutaAnalisis";
import "./Historial.css";

const TAMANO_PAGINA = 20;

const OPCIONES_ALCANCE = [
  { valor: "propio", etiqueta: "Mis análisis", permiso: "historial:propio" },
  { valor: "area", etiqueta: "Mi área", permiso: "historial:area" },
  { valor: "todas", etiqueta: "Todas las áreas", permiso: "historial:todas" },
] as const;

type ItemHistorial = {
  id: string;
  nombre_documento?: string | null;
  tipo_revision: string;
  estado: string;
  fecha_inicio: string;
  duracion_segundos?: number | null;
  usuario_nombre: string;
  usuario_email: string;
  area_nombre: string;
  numero_hallazgos: number;
};

function formatearDuracion(segundos: number | null | undefined): string {
  if (segundos == null) return "—";
  const minutos = Math.floor(segundos / 60);
  const resto = Math.round(segundos % 60);
  return minutos > 0 ? `${minutos} min ${resto} s` : `${resto} s`;
}

/** HU-21: alcance (según permiso), filtros de fecha/tipo/estado/archivo y
 * paginación sobre GET /historial -- con enlace al resultado de cada
 * análisis (Hallazgos, o "Agente trabajando" si aún está en proceso). */
export function Historial() {
  const { tienePermiso } = useAuth();
  const alcancesDisponibles = OPCIONES_ALCANCE.filter((o) => tienePermiso(o.permiso));

  const [alcance, setAlcance] = useState<string>(alcancesDisponibles[0]?.valor ?? "propio");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [tipoRevision, setTipoRevision] = useState("");
  const [estado, setEstado] = useState("");
  const [archivo, setArchivo] = useState("");
  const [pagina, setPagina] = useState(1);
  const [resultados, setResultados] = useState<ItemHistorial[] | null>(null);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buscar = useCallback(
    async (paginaABuscar: number) => {
      setCargando(true);
      setError(null);
      const { data, error: errorRespuesta } = await clienteApi.GET("/historial", {
        params: {
          query: {
            alcance,
            desde: fechaDesde || undefined,
            hasta: fechaHasta || undefined,
            tipo_revision: tipoRevision || undefined,
            estado: estado || undefined,
            archivo: archivo || undefined,
            pagina: paginaABuscar,
            tamano_pagina: TAMANO_PAGINA,
          },
        },
      });
      setCargando(false);
      if (errorRespuesta || !data) {
        setError("No se pudo cargar el historial");
        return;
      }
      setResultados(data.resultados);
      setTotal(data.total);
      setPagina(paginaABuscar);
    },
    [alcance, fechaDesde, fechaHasta, tipoRevision, estado, archivo],
  );

  // Cambiar de alcance actualiza de inmediato (HU-21); los demás filtros se
  // aplican al enviar el formulario, igual que Bitácora/Ajustes autoaprobados.
  useEffect(() => {
    buscar(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alcance]);

  function manejarEnvio(evento: FormEvent) {
    evento.preventDefault();
    buscar(1);
  }

  const totalPaginas = Math.max(1, Math.ceil(total / TAMANO_PAGINA));

  return (
    <div className="historial">
      <h1>Historial</h1>

      {alcancesDisponibles.length > 1 && (
        <div className="historial__alcance" role="group" aria-label="Alcance">
          {alcancesDisponibles.map((o) => (
            <button
              key={o.valor}
              type="button"
              className={
                "historial__boton-alcance" +
                (alcance === o.valor ? " historial__boton-alcance--activo" : "")
              }
              onClick={() => setAlcance(o.valor)}
            >
              {o.etiqueta}
            </button>
          ))}
        </div>
      )}

      <form className="historial__filtros" onSubmit={manejarEnvio}>
        <label>
          Desde
          <input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
        </label>
        <label>
          Hasta
          <input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
        </label>
        <label>
          Tipo de revisión
          <input
            type="text"
            placeholder="p. ej. contable"
            value={tipoRevision}
            onChange={(e) => setTipoRevision(e.target.value)}
          />
        </label>
        <label>
          Estado
          <input
            type="text"
            placeholder="p. ej. con_hallazgos"
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
          />
        </label>
        <label>
          Archivo
          <input
            type="text"
            placeholder="nombre del documento"
            value={archivo}
            onChange={(e) => setArchivo(e.target.value)}
          />
        </label>
        <button type="submit" disabled={cargando}>
          {cargando ? "Buscando…" : "Buscar"}
        </button>
      </form>

      {error && (
        <p className="historial__error" role="alert">
          {error}
        </p>
      )}

      {resultados === null ? null : resultados.length === 0 ? (
        <p className="historial__vacio">No hay análisis con esos filtros.</p>
      ) : (
        <>
          <table className="historial__tabla">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Documento</th>
                <th>Tipo</th>
                <th>Estado</th>
                <th>Usuario</th>
                <th>Área</th>
                <th>Duración</th>
                <th>Hallazgos</th>
              </tr>
            </thead>
            <tbody>
              {resultados.map((item) => (
                <tr key={item.id}>
                  <td>{new Date(item.fecha_inicio).toLocaleString("es-GT")}</td>
                  <td>
                    <Link to={rutaDeAnalisis(item)}>{item.nombre_documento ?? item.id}</Link>
                  </td>
                  <td>{item.tipo_revision}</td>
                  <td>
                    <EstadoBadge estado={item.estado} />
                  </td>
                  <td>
                    {item.usuario_nombre} ({item.usuario_email})
                  </td>
                  <td>{item.area_nombre}</td>
                  <td>{formatearDuracion(item.duracion_segundos)}</td>
                  <td>{item.numero_hallazgos}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="historial__paginacion">
            <button type="button" disabled={pagina <= 1} onClick={() => buscar(pagina - 1)}>
              Anterior
            </button>
            <span>
              Página {pagina} de {totalPaginas} ({total} en total)
            </span>
            <button
              type="button"
              disabled={pagina >= totalPaginas}
              onClick={() => buscar(pagina + 1)}
            >
              Siguiente
            </button>
          </div>
        </>
      )}
    </div>
  );
}
