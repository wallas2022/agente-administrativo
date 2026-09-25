import "./EtapasAnalisis.css";

// docs/03-diseno/estados/estados-analisis.md
const ETIQUETAS_RESULTADO: Record<string, string> = {
  con_hallazgos: "Con hallazgos",
  en_revision: "En revisión",
  fallido: "Fallido",
};

const ORDEN: readonly string[] = ["cargado", "procesando", "resultado"];

function etapaDe(estado: string): string {
  if (estado === "cargado") return "cargado";
  if (estado === "procesando") return "procesando";
  return "resultado"; // con_hallazgos | en_revision | fallido
}

export function EtapasAnalisis({ estado }: { estado: string }) {
  const etapaActual = etapaDe(estado);
  const indiceActual = ORDEN.indexOf(etapaActual);

  return (
    <ol className="etapas-analisis">
      {ORDEN.map((etapa, indice) => {
        const completada = indice < indiceActual;
        const activa = indice === indiceActual;
        const esFallido = etapa === "resultado" && estado === "fallido";
        return (
          <li
            key={etapa}
            className={
              "etapas-analisis__paso" +
              (completada ? " etapas-analisis__paso--completada" : "") +
              (activa ? " etapas-analisis__paso--activa" : "") +
              (esFallido ? " etapas-analisis__paso--fallido" : "")
            }
          >
            <span className="etapas-analisis__punto" />
            <span className="etapas-analisis__etiqueta">
              {etapa === "cargado" && "Cargado"}
              {etapa === "procesando" && "Procesando"}
              {etapa === "resultado" &&
                (activa ? (ETIQUETAS_RESULTADO[estado] ?? "Resultado") : "Resultado")}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
