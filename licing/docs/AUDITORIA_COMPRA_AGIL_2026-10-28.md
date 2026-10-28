# Revisión del filtro de Compras Ágiles — 28 de octubre de 2026

Se revisaron las 81 Compras Ágiles guardadas en Core: título, descripción, ítems, códigos de producto, ubicación y vigencia. La comparación entre `ca-1` y `ca-2` se hizo en memoria, con el mismo instante de evaluación de la muestra (14:55, hora de Chile). No se guardaron nuevas clasificaciones ni se descargaron compras adicionales.

## Hallazgos y correcciones

La región del comprador se utilizaba como prueba del lugar de prestación. Un comprador de otra región podía contratar un servicio en Santiago; uno de la RM podía contratarlo fuera. Ahora esa región es solo una referencia. La ubicación explícita del servicio decide; si falta, se conserva para revisión.

La compra de vasos publicitarios quedaba en revisión pese a describir únicamente bienes promocionales. Se completó la identificación de esos bienes, impresión y encuadernación. La exclusión requiere que todas las líneas sean identificablemente ajenas y que no se solicite un servicio hotelero concreto. Una línea desconocida, una lectura incompleta o un paquete con alojamiento, salones o catering impiden ese descarte automático. La capacitación para usar un equipo tampoco convierte por sí sola una compra de CCTV en contratación de salones.

| Compra | Antes | Con las reglas corregidas | Evidencia |
| --- | --- | --- | --- |
| 2408-574-COT26 | Descartada | Revisión necesaria | Jornada de capacitación y autocuidado; remite a EETT y anexos. La región del comprador no demuestra dónde se realizará ni qué servicios incluye. |
| 615-46-COT26 | Descartada | Revisión necesaria | Capacitación en redes sociales e IA; faltan lugar y alcance de los servicios. No basta la región del comprador para descartarla. |
| 5251-1194-COT26 | Revisión necesaria | Descartada | Solo vasos reutilizables y personalización, con códigos 80141605 y 80141611; sin contratación hotelera. |

En la comparación al mismo instante: **79 descartadas, 2 para revisión y 0 oportunidades confirmadas por los tres pilares**, frente a 80 descartadas y 1 para revisión con las reglas anteriores. Los cierres posteriores cambian la vigencia: estos conteos describen la muestra, no un indicador permanente.

## Alcance de la validación

Las dos capacitaciones recuperadas no están confirmadas como negocios para el hotel: requieren revisar sus EETT. Se corrigieron descartes sin evidencia territorial suficiente, sin convertir información incompleta en una oportunidad. La compra de vasos era un falso candidato de la bandeja de revisión, no una oportunidad preseleccionada.

Las regresiones prueban compradores de distintas regiones, servicios explícitos dentro y fuera de la RM, bienes promocionales, impresión, CCTV con capacitación, paquetes con catering, líneas desconocidas, lecturas truncadas y el instante exacto de cierre. Se conserva el comportamiento del motor común de licitaciones. Sin una muestra etiquetada y sus anexos no corresponde estimar una tasa general de falsos positivos o negativos.

Las nuevas reglas se versionan como `ca-2`. Las evaluaciones persistidas se renovarán al ejecutar **Actualizar preselección**; esta auditoría no las modificó.
