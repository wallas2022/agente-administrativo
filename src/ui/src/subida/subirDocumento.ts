/** Carga por partes y reanudable de un documento (RF-03, RN-09). Lógica pura
 * (sin XHR/fetch directo) para poder probarla con dependencias falsas — la
 * implementación real de `DependenciasSubida` vive en `dependenciasReales.ts`.
 */

// 5 MB: mínimo de S3 para todas las partes salvo la última (comun/almacenamiento.py).
export const TAMANO_PARTE_BYTES = 5 * 1024 * 1024;
export const TAMANO_MAXIMO_BYTES = 1024 * 1024 * 1024; // 1 GB (RF-03, RN-09)

export interface ParteSubida {
  numeroParte: number;
  etag: string;
}

export interface ProgresoSubida {
  parteActual: number;
  totalPartes: number;
  bytesSubidos: number;
  bytesTotales: number;
}

export interface OpcionesSubida {
  tipoRevision: string;
  periodoCierre: string;
  onProgreso?: (progreso: ProgresoSubida) => void;
}

export interface ResultadoSubida {
  documentoId: string;
  analisisId: string;
}

interface EstadoReanudable {
  documentoId: string;
  uploadId: string;
  llaveAlmacenamiento: string;
}

export interface DependenciasSubida {
  iniciarCarga(input: {
    nombre_original: string;
    tipo_archivo: string;
    tamano_bytes: number;
  }): Promise<{ documento_id: string; upload_id: string; llave_almacenamiento: string }>;
  listarPartesSubidas(
    documentoId: string,
    uploadId: string,
    llaveAlmacenamiento: string,
  ): Promise<ParteSubida[]>;
  subirParte(
    documentoId: string,
    numeroParte: number,
    uploadId: string,
    llaveAlmacenamiento: string,
    datos: Blob,
    onProgresoBytes?: (bytesEnviados: number) => void,
  ): Promise<ParteSubida>;
  completarCarga(
    documentoId: string,
    uploadId: string,
    llaveAlmacenamiento: string,
    partes: ParteSubida[],
    tipoRevision: string,
    periodoCierre: string,
  ): Promise<{ documento_id: string; analisis_id: string; estado: string }>;
}

export function calcularNumeroPartes(tamanoBytes: number): number {
  if (tamanoBytes <= 0) return 1;
  return Math.ceil(tamanoBytes / TAMANO_PARTE_BYTES);
}

export function obtenerParteBytes(archivo: Blob, numeroParte: number): Blob {
  const inicio = (numeroParte - 1) * TAMANO_PARTE_BYTES;
  const fin = Math.min(inicio + TAMANO_PARTE_BYTES, archivo.size);
  return archivo.slice(inicio, fin);
}

export function extensionDe(nombreArchivo: string): string {
  const partes = nombreArchivo.split(".");
  return partes.length > 1 ? partes.at(-1)!.toLowerCase() : "";
}

/** Identifica una carga en curso para el mismo archivo (nombre + tamaño +
 * fecha de modificación), sin depender de un id que solo existe una vez
 * iniciada la carga en el servidor. */
export function claveReanudable(archivo: File, tipoRevision: string): string {
  return `agente-admin:carga:${tipoRevision}:${archivo.name}:${archivo.size}:${archivo.lastModified}`;
}

function leerEstadoReanudable(clave: string): EstadoReanudable | null {
  try {
    const bruto = localStorage.getItem(clave);
    return bruto ? (JSON.parse(bruto) as EstadoReanudable) : null;
  } catch {
    return null;
  }
}

function guardarEstadoReanudable(clave: string, estado: EstadoReanudable): void {
  try {
    localStorage.setItem(clave, JSON.stringify(estado));
  } catch {
    // Almacenamiento no disponible (privado/bloqueado): la carga sigue
    // funcionando, solo no podrá reanudarse tras recargar la página.
  }
}

function borrarEstadoReanudable(clave: string): void {
  try {
    localStorage.removeItem(clave);
  } catch {
    // ver nota en guardarEstadoReanudable
  }
}

export async function subirDocumento(
  archivo: File,
  opciones: OpcionesSubida,
  deps: DependenciasSubida,
): Promise<ResultadoSubida> {
  if (archivo.size > TAMANO_MAXIMO_BYTES) {
    throw new Error("El archivo supera el máximo permitido de 1 GB");
  }

  const clave = claveReanudable(archivo, opciones.tipoRevision);
  let estado = leerEstadoReanudable(clave);
  let partesYaSubidas: ParteSubida[] = [];

  if (estado) {
    try {
      partesYaSubidas = await deps.listarPartesSubidas(
        estado.documentoId,
        estado.uploadId,
        estado.llaveAlmacenamiento,
      );
    } catch {
      // El servidor ya no reconoce esa carga (expiró, se completó o falló
      // en otra sesión): se descarta el estado guardado y se empieza de nuevo.
      estado = null;
    }
  }

  if (!estado) {
    const inicio = await deps.iniciarCarga({
      nombre_original: archivo.name,
      tipo_archivo: extensionDe(archivo.name),
      tamano_bytes: archivo.size,
    });
    estado = {
      documentoId: inicio.documento_id,
      uploadId: inicio.upload_id,
      llaveAlmacenamiento: inicio.llave_almacenamiento,
    };
    guardarEstadoReanudable(clave, estado);
    partesYaSubidas = [];
  }

  const totalPartes = calcularNumeroPartes(archivo.size);
  const numerosYaSubidos = new Set(partesYaSubidas.map((p) => p.numeroParte));
  const partesFinales: ParteSubida[] = [...partesYaSubidas];

  let bytesSubidosAcumulado = 0;
  for (const numeroParte of numerosYaSubidos) {
    bytesSubidosAcumulado += obtenerParteBytes(archivo, numeroParte).size;
  }

  for (let numeroParte = 1; numeroParte <= totalPartes; numeroParte++) {
    if (numerosYaSubidos.has(numeroParte)) continue;

    const bytesParte = obtenerParteBytes(archivo, numeroParte);
    const parte = await deps.subirParte(
      estado.documentoId,
      numeroParte,
      estado.uploadId,
      estado.llaveAlmacenamiento,
      bytesParte,
      (bytesEnviados) => {
        opciones.onProgreso?.({
          parteActual: numeroParte,
          totalPartes,
          bytesSubidos: bytesSubidosAcumulado + bytesEnviados,
          bytesTotales: archivo.size,
        });
      },
    );
    bytesSubidosAcumulado += bytesParte.size;
    partesFinales.push(parte);
    opciones.onProgreso?.({
      parteActual: numeroParte,
      totalPartes,
      bytesSubidos: bytesSubidosAcumulado,
      bytesTotales: archivo.size,
    });
  }

  const resultado = await deps.completarCarga(
    estado.documentoId,
    estado.uploadId,
    estado.llaveAlmacenamiento,
    partesFinales.sort((a, b) => a.numeroParte - b.numeroParte),
    opciones.tipoRevision,
    opciones.periodoCierre,
  );
  borrarEstadoReanudable(clave);

  return { documentoId: resultado.documento_id, analisisId: resultado.analisis_id };
}
