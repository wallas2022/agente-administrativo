import { useCallback, useEffect, useState, type FormEvent } from "react";
import { clienteApi } from "../api/cliente";
import { GraficoBarras } from "../componentes/GraficoBarras";
import { GraficoLinea } from "../componentes/GraficoLinea";
import "./Dashboard.css";

type Tarjetas = {
  tokens_entrada: number;
  tokens_salida: number;
  tokens_totales: number;
  llamadas: number;
  tokens_por_segundo_promedio?: number | null;
  pct_timeouts: number;
};

type PuntoSerie = {
  fecha: string;
  tokens_entrada: number;
  tokens_salida: number;
  llamadas: number;
};

type ItemRanking = {
  caso_uso?: string | null;
  modelo?: string | null;
  tokens_totales: number;
  duracion_llm_total_ms: number;
  llamadas: number;
  duracion_media_analisis_ms?: number | null;
};

type RespuestaConsumo = {
  tarjetas: Tarjetas;
  serie_diaria: PuntoSerie[];
  ranking_caso_uso: ItemRanking[];
  ranking_modelo: ItemRanking[];
};

function formatearMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const segundos = ms / 1000;
  if (segundos < 60) return `${segundos.toFixed(1)} s`;
  const minutos = Math.floor(segundos / 60);
  const resto = Math.round(segundos % 60);
  return `${minutos} min ${resto} s`;
}

/** HU-26, HU-28: tarjetas de consumo, serie diaria y ranking por caso de uso
 * y por modelo, con gráficos SVG propios (sin librerías nuevas). */
export function DashboardConsumo() {
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [areaId, setAreaId] = useState("");
  const [casoUso, setCasoUso] = useState("");
  const [modelo, setModelo] = useState("");
  const [datos, setDatos] = useState<RespuestaConsumo | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buscar = useCallback(async () => {
    setCargando(true);
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.GET("/admin/dashboard/consumo", {
      params: {
        query: {
          desde: desde || undefined,
          hasta: hasta || undefined,
          area_id: areaId || undefined,
          caso_uso: casoUso || undefined,
          modelo: modelo || undefined,
        },
      },
    });
    setCargando(false);
    if (errorRespuesta || !data) {
      setError("No se pudo cargar el consumo");
      return;
    }
    setDatos(data as RespuestaConsumo);
  }, [desde, hasta, areaId, casoUso, modelo]);

  useEffect(() => {
    buscar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function manejarEnvio(evento: FormEvent) {
    evento.preventDefault();
    buscar();
  }

  return (
    <div className="dashboard__tab">
      <form className="dashboard__filtros" onSubmit={manejarEnvio}>
        <label>
          Desde
          <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </label>
        <label>
          Hasta
          <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
        </label>
        <label>
          ID de área
          <input
            type="text"
            placeholder="opcional"
            value={areaId}
            onChange={(e) => setAreaId(e.target.value)}
          />
        </label>
        <label>
          Caso de uso
          <input
            type="text"
            placeholder="p. ej. contable"
            value={casoUso}
            onChange={(e) => setCasoUso(e.target.value)}
          />
        </label>
        <label>
          Modelo
          <input
            type="text"
            placeholder="p. ej. gpt-oss:20b"
            value={modelo}
            onChange={(e) => setModelo(e.target.value)}
          />
        </label>
        <button type="submit" disabled={cargando}>
          {cargando ? "Buscando…" : "Buscar"}
        </button>
      </form>

      {error && (
        <p className="dashboard__error" role="alert">
          {error}
        </p>
      )}

      {datos && datos.tarjetas.llamadas === 0 && !error && (
        <p className="dashboard__vacio">Todavía no hay datos de consumo para estos filtros.</p>
      )}

      {datos && datos.tarjetas.llamadas > 0 && (
        <>
          <div className="dashboard__tarjetas">
            <div className="dashboard__tarjeta">
              <span className="dashboard__tarjeta-valor">
                {datos.tarjetas.tokens_totales.toLocaleString("es-GT")}
              </span>
              <span className="dashboard__tarjeta-etiqueta">Tokens totales</span>
            </div>
            <div className="dashboard__tarjeta">
              <span className="dashboard__tarjeta-valor">
                {datos.tarjetas.llamadas.toLocaleString("es-GT")}
              </span>
              <span className="dashboard__tarjeta-etiqueta">Llamadas</span>
            </div>
            <div className="dashboard__tarjeta">
              <span className="dashboard__tarjeta-valor">
                {datos.tarjetas.tokens_por_segundo_promedio ?? "—"}
              </span>
              <span className="dashboard__tarjeta-etiqueta">Tokens/s promedio</span>
            </div>
            <div className="dashboard__tarjeta">
              <span className="dashboard__tarjeta-valor">{datos.tarjetas.pct_timeouts}%</span>
              <span className="dashboard__tarjeta-etiqueta">Timeouts</span>
            </div>
          </div>

          <GraficoLinea
            titulo="Tokens por día"
            puntos={datos.serie_diaria.map((p) => ({
              etiqueta: p.fecha,
              valor: p.tokens_entrada + p.tokens_salida,
            }))}
          />
          <table className="dashboard__tabla">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Tokens entrada</th>
                <th>Tokens salida</th>
                <th>Llamadas</th>
              </tr>
            </thead>
            <tbody>
              {datos.serie_diaria.map((p) => (
                <tr key={p.fecha}>
                  <td>{p.fecha}</td>
                  <td>{p.tokens_entrada}</td>
                  <td>{p.tokens_salida}</td>
                  <td>{p.llamadas}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <GraficoBarras
            titulo="Tokens totales por caso de uso"
            datos={datos.ranking_caso_uso.map((r) => ({
              etiqueta: r.caso_uso ?? "—",
              valor: r.tokens_totales,
            }))}
          />
          <table className="dashboard__tabla">
            <thead>
              <tr>
                <th>Caso de uso</th>
                <th>Tokens</th>
                <th>Duración LLM</th>
                <th>Llamadas</th>
                <th>Duración media del análisis</th>
              </tr>
            </thead>
            <tbody>
              {datos.ranking_caso_uso.map((r) => (
                <tr key={r.caso_uso}>
                  <td>{r.caso_uso}</td>
                  <td>{r.tokens_totales}</td>
                  <td>{formatearMs(r.duracion_llm_total_ms)}</td>
                  <td>{r.llamadas}</td>
                  <td>{formatearMs(r.duracion_media_analisis_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <GraficoBarras
            titulo="Tokens totales por modelo"
            datos={datos.ranking_modelo.map((r) => ({
              etiqueta: r.modelo ?? "—",
              valor: r.tokens_totales,
            }))}
          />
          <table className="dashboard__tabla">
            <thead>
              <tr>
                <th>Modelo</th>
                <th>Tokens</th>
                <th>Duración LLM</th>
                <th>Llamadas</th>
                <th>Duración media del análisis</th>
              </tr>
            </thead>
            <tbody>
              {datos.ranking_modelo.map((r) => (
                <tr key={r.modelo}>
                  <td>{r.modelo}</td>
                  <td>{r.tokens_totales}</td>
                  <td>{formatearMs(r.duracion_llm_total_ms)}</td>
                  <td>{r.llamadas}</td>
                  <td>{formatearMs(r.duracion_media_analisis_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
