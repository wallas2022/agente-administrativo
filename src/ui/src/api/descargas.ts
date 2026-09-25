import { obtenerTokenActual, URL_BASE_API } from "./cliente";

/** Descarga autenticada de un archivo binario (el token va en el header
 * Authorization, así que no alcanza con un <a href> normal). */
export async function descargarArchivo(rutaRelativa: string): Promise<void> {
  const token = obtenerTokenActual();
  const respuesta = await fetch(`${URL_BASE_API}${rutaRelativa}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!respuesta.ok) {
    throw new Error("No se pudo descargar el archivo");
  }

  const nombreArchivo =
    /filename="([^"]+)"/.exec(respuesta.headers.get("content-disposition") ?? "")?.[1] ??
    "descarga";
  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombreArchivo;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}
