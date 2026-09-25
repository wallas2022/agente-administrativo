import "./SeveridadBadge.css";

const ETIQUETAS: Record<string, string> = {
  alta: "Alto",
  media: "Medio",
  baja: "Bajo",
};

/** Hallazgo.severidad hoy es alta/media/baja (ver
 * validadores/contable/reglas.py) — se muestra con el vocabulario del
 * sistema de diseño (Alto/Medio/Bajo). */
export function SeveridadBadge({ severidad }: { severidad: string }) {
  return (
    <span className={`severidad-badge severidad-badge--${severidad}`}>
      {ETIQUETAS[severidad] ?? severidad}
    </span>
  );
}
