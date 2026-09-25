# Política de cierre contable (ejemplo)

**Versión:** 1.0
**Vigente desde:** 2026-01-01
**Área:** Contabilidad

> Fuente de conocimiento de ejemplo para el piloto (RF-16, CU-08). Contenido
> ilustrativo, no un documento normativo real de la organización.

## 1. Cuadre de partidas

Toda partida contable debe cuadrar: la suma de los débitos debe ser igual a la
suma de los créditos, tanto por comprobante individual como por el total de la
hoja. Un descuadre, sin importar el monto, se considera un hallazgo de
severidad alta y bloquea el cierre del período hasta corregirse (RN-01).

## 2. Cuentas contables

Toda cuenta utilizada en un asiento debe existir en el catálogo de cuentas
vigente (ver `catalogo-cuentas-contabilidad.csv`). El uso de una cuenta no
registrada en el catálogo se marca como hallazgo de severidad alta y no se
permite en el cierre (RN-02).

## 3. Período contable

Las partidas registradas en un cierre mensual deben tener fecha dentro del mes
que se está cerrando. Una partida con fecha fuera del período (mes anterior o
posterior) se marca como hallazgo de severidad media, salvo que corresponda a
un ajuste de cierre debidamente documentado (RN-03).

## 4. Duplicados

Dos o más partidas con la misma cuenta, el mismo monto y la misma fecha dentro
del mismo comprobante o documento se consideran un posible duplicado y se
marcan como hallazgo de severidad media para revisión manual (RN-04).

## 5. Moneda

Los registros contables pueden expresarse en quetzales (Q) o dólares
estadounidenses (USD). Cuando un mismo comprobante mezcla ambas monedas, debe
existir un tipo de cambio explícito registrado en el documento. La ausencia de
tipo de cambio ante una mezcla de moneda es un hallazgo de severidad alta; el
sistema **no calcula ni infiere** un tipo de cambio automáticamente — esa
decisión corresponde a una persona (RN-05, RNF-03).

## 6. Fórmulas

Las celdas de totales y subtotales deben mantener su fórmula de cálculo
(`=SUMA(...)` u equivalente). Un valor de total ingresado manualmente en lugar
de calculado por fórmula no puede verificarse automáticamente contra el
detalle de la hoja y se marca como hallazgo de severidad media.
