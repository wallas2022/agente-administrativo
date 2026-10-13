import "./Graficos.css";

export interface DatoBarra {
  etiqueta: string;
  valor: number;
}

interface Props {
  titulo: string;
  datos: DatoBarra[];
  formatearValor?: (valor: number) => string;
}

const ALTO_BARRA = 28;
const ESPACIO_BARRA = 10;
const ANCHO_GRAFICO = 320;
const ANCHO_ETIQUETA = 110;

/** Barras horizontales en SVG propio, sin librerías de gráficos (P-13
 * Bloque 4). Accesible: `role="img"` + `aria-label` con el resumen de los
 * datos (texto alternativo) y una tabla equivalente visible debajo. */
export function GraficoBarras({ titulo, datos, formatearValor }: Props) {
  const formatear = formatearValor ?? ((v: number) => v.toLocaleString("es-GT"));
  const alto = Math.max(1, datos.length) * (ALTO_BARRA + ESPACIO_BARRA);
  const maximo = Math.max(1, ...datos.map((d) => d.valor));
  const anchoBarraMaxima = ANCHO_GRAFICO - ANCHO_ETIQUETA - 50;
  const resumen = datos.map((d) => `${d.etiqueta}: ${formatear(d.valor)}`).join(", ");

  return (
    <figure className="grafico">
      <figcaption className="grafico__titulo">{titulo}</figcaption>
      {datos.length === 0 ? (
        <p className="grafico__vacio">Todavía no hay datos.</p>
      ) : (
        <>
          <svg
            role="img"
            aria-label={`${titulo}: ${resumen}`}
            viewBox={`0 0 ${ANCHO_GRAFICO} ${alto}`}
            width="100%"
            height={alto}
          >
            {datos.map((d, i) => {
              const y = i * (ALTO_BARRA + ESPACIO_BARRA);
              const anchoBarra = (d.valor / maximo) * anchoBarraMaxima;
              return (
                <g key={d.etiqueta}>
                  <text
                    x={ANCHO_ETIQUETA - 6}
                    y={y + ALTO_BARRA / 2}
                    textAnchor="end"
                    dominantBaseline="middle"
                    className="grafico__etiqueta"
                  >
                    {d.etiqueta}
                  </text>
                  <rect
                    x={ANCHO_ETIQUETA}
                    y={y}
                    width={Math.max(anchoBarra, 2)}
                    height={ALTO_BARRA}
                    className="grafico__barra"
                  />
                  <text
                    x={ANCHO_ETIQUETA + anchoBarra + 6}
                    y={y + ALTO_BARRA / 2}
                    dominantBaseline="middle"
                    className="grafico__valor"
                  >
                    {formatear(d.valor)}
                  </text>
                </g>
              );
            })}
          </svg>
          <table className="grafico__tabla">
            <thead>
              <tr>
                <th>Etiqueta</th>
                <th>Valor</th>
              </tr>
            </thead>
            <tbody>
              {datos.map((d) => (
                <tr key={d.etiqueta}>
                  <td>{d.etiqueta}</td>
                  <td>{formatear(d.valor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </figure>
  );
}
