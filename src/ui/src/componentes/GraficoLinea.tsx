import "./Graficos.css";

export interface PuntoLinea {
  etiqueta: string;
  valor: number;
}

interface Props {
  titulo: string;
  puntos: PuntoLinea[];
  formatearValor?: (valor: number) => string;
}

const ANCHO = 320;
const ALTO = 120;
const PADDING = 24;

/** Línea simple en SVG propio para series temporales (P-13 Bloque 4).
 * Accesible igual que GraficoBarras: `role="img"` + `aria-label` con el
 * resumen de los puntos -- la tabla equivalente la arma quien use este
 * componente (normalmente con más columnas de las que caben en el gráfico). */
export function GraficoLinea({ titulo, puntos, formatearValor }: Props) {
  const formatear = formatearValor ?? ((v: number) => v.toLocaleString("es-GT"));
  const resumen = puntos.map((p) => `${p.etiqueta}: ${formatear(p.valor)}`).join(", ");
  const maximo = Math.max(1, ...puntos.map((p) => p.valor));
  const anchoUtil = ANCHO - PADDING * 2;
  const altoUtil = ALTO - PADDING * 2;

  const coordenadas = puntos.map((p, i) => ({
    x: PADDING + (puntos.length > 1 ? (i / (puntos.length - 1)) * anchoUtil : anchoUtil / 2),
    y: PADDING + altoUtil - (p.valor / maximo) * altoUtil,
  }));

  return (
    <figure className="grafico">
      <figcaption className="grafico__titulo">{titulo}</figcaption>
      {puntos.length === 0 ? (
        <p className="grafico__vacio">Todavía no hay datos.</p>
      ) : (
        <svg
          role="img"
          aria-label={`${titulo}: ${resumen}`}
          viewBox={`0 0 ${ANCHO} ${ALTO}`}
          width="100%"
          height={ALTO}
        >
          <polyline
            points={coordenadas.map((c) => `${c.x},${c.y}`).join(" ")}
            className="grafico__linea"
            fill="none"
          />
          {coordenadas.map((c, i) => (
            <circle key={puntos[i].etiqueta} cx={c.x} cy={c.y} r={3} className="grafico__punto" />
          ))}
        </svg>
      )}
    </figure>
  );
}
