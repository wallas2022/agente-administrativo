import { clienteApi, obtenerTokenActual, URL_BASE_API } from "../api/cliente";
import type { DependenciasSubida, ParteSubida } from "./subirDocumento";

/** FastAPI devuelve `{detail: "texto"}` o, en errores de validación (422),
 * `{detail: [{loc, msg, type}, ...]}`. Sin esto, cualquier error del servidor
 * se veía en pantalla como un mensaje genérico sin pista de la causa real. */
function descripcionError(error: unknown, mensajePorDefecto: string): string {
  const detalle = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) {
    return detalle
      .map((d: { loc?: unknown[]; msg?: string }) =>
        d.msg ? `${(d.loc ?? []).join(".")}: ${d.msg}` : JSON.stringify(d),
      )
      .join("; ");
  }
  return mensajePorDefecto;
}

/** Implementación real de `DependenciasSubida` (bloque U2). `subirParte` usa
 * XMLHttpRequest en vez del cliente tipado porque `fetch` no expone eventos
 * de progreso de subida, necesarios para la barra de progreso. */
export const dependenciasReales: DependenciasSubida = {
  async iniciarCarga(input) {
    const { data, error } = await clienteApi.POST("/documentos/iniciar", { body: input });
    if (error || !data) {
      throw new Error(descripcionError(error, "No se pudo iniciar la carga del documento"));
    }
    return data;
  },

  async listarPartesSubidas(documentoId, uploadId, llaveAlmacenamiento) {
    const { data, error } = await clienteApi.GET("/documentos/{documento_id}/partes", {
      params: {
        path: { documento_id: documentoId },
        query: { upload_id: uploadId, llave_almacenamiento: llaveAlmacenamiento },
      },
    });
    if (error || !data) {
      throw new Error(descripcionError(error, "No se pudo consultar las partes ya subidas"));
    }
    return data.map((p) => ({ numeroParte: p.numero_parte, etag: p.etag }));
  },

  subirParte(documentoId, numeroParte, uploadId, llaveAlmacenamiento, datos, onProgresoBytes) {
    return new Promise<ParteSubida>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const parametros = new URLSearchParams({
        upload_id: uploadId,
        llave_almacenamiento: llaveAlmacenamiento,
      });
      xhr.open(
        "PUT",
        `${URL_BASE_API}/documentos/${documentoId}/partes/${numeroParte}?${parametros}`,
      );
      const token = obtenerTokenActual();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      xhr.upload.onprogress = (evento) => {
        if (evento.lengthComputable) onProgresoBytes?.(evento.loaded);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const respuesta = JSON.parse(xhr.responseText) as { numero_parte: number; etag: string };
          resolve({ numeroParte: respuesta.numero_parte, etag: respuesta.etag });
        } else {
          let detalle = `HTTP ${xhr.status}`;
          try {
            detalle = descripcionError(JSON.parse(xhr.responseText), detalle);
          } catch {
            // el cuerpo no era JSON (p. ej. error 502 de un proxy) — se deja el HTTP status
          }
          reject(new Error(`Error subiendo la parte ${numeroParte}: ${detalle}`));
        }
      };
      xhr.onerror = () => reject(new Error(`Error de red subiendo la parte ${numeroParte}`));
      xhr.send(datos);
    });
  },

  async completarCarga(documentoId, uploadId, llaveAlmacenamiento, partes, tipoRevision, periodoCierre) {
    const { data, error } = await clienteApi.POST("/documentos/{documento_id}/completar", {
      params: {
        path: { documento_id: documentoId },
        query: { upload_id: uploadId, llave_almacenamiento: llaveAlmacenamiento },
      },
      body: {
        partes: partes.map((p) => ({ numero_parte: p.numeroParte, etag: p.etag })),
        tipo_revision: tipoRevision,
        periodo_cierre: periodoCierre,
      },
    });
    if (error || !data) {
      throw new Error(descripcionError(error, "No se pudo completar la carga"));
    }
    return data;
  },
};
