import { Fragment } from "react";

/** Muestra el texto de la IA con las marcas **así** como negritas (sin HTML crudo: React escapa el resto). */
export function TextoConNegritas({ texto }: { texto: string }) {
  const partes = texto.split("**");
  // Con un número impar de marcas la última quedaría sin cerrar: se deja como texto normal.
  const cerradas = partes.length % 2 === 1 ? partes : [...partes.slice(0, -2), `${partes.at(-2)}**${partes.at(-1)}`];
  return (
    <>
      {cerradas.map((parte, i) => (
        <Fragment key={i}>{i % 2 === 1 ? <strong>{parte}</strong> : parte}</Fragment>
      ))}
    </>
  );
}
