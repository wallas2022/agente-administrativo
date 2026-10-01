/** Diferencia por palabra entre dos textos (CU-02, interruptor "Ver
 * cambios"): devuelve los tokens del texto ACTUALIZADO, marcando cuáles no
 * estaban en el original -- LCS clásico sobre tokens de palabra/espacio
 * (no una librería de diff: evita agregar una dependencia nueva solo para
 * esto). Las palabras eliminadas del original no se muestran (la vista
 * "Ver cambios" resalta lo nuevo sobre el texto final, no un diff de ida y
 * vuelta completo).
 */

export interface SegmentoDiferencia {
  texto: string;
  cambiado: boolean;
}

function tokenizar(texto: string): string[] {
  return texto.match(/\S+|\s+/g) ?? [];
}

export function resaltarDiferencias(original: string, actualizado: string): SegmentoDiferencia[] {
  const a = tokenizar(original);
  const b = tokenizar(actualizado);
  const n = a.length;
  const m = b.length;

  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const segmentos: SegmentoDiferencia[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      segmentos.push({ texto: b[j], cambiado: false });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      i++;
    } else {
      segmentos.push({ texto: b[j], cambiado: true });
      j++;
    }
  }
  while (j < m) {
    segmentos.push({ texto: b[j], cambiado: true });
    j++;
  }
  return segmentos;
}
