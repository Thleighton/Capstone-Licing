# Filtro semántico de servicios hoteleros

El componente NLI interpreta el **servicio solicitado**. Vigencia y ubicación siguen siendo pilares independientes. No decide postular ni usa el organismo comprador como evidencia de pertinencia. Funciona para licitaciones y Compras Ágiles.

Se usa `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` en ONNX, revisión `8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c`. La descarga fija la revisión y verifica SHA-256. No ejecuta código remoto. Durante las pruebas se compararon variantes pequeñas y cuantizadas; la versión completa conservó mejor los servicios válidos.

El modelo ocupa aproximadamente 1,1 GB en disco y se carga una vez por proceso. **No se incluye en Git ni se empaqueta en la función de Vercel.**

## Funcionamiento

1. Las reglas conservan los descartes confirmados y omiten inferencia para compras cerradas o bienes explícitamente ajenos.
2. Se evalúan título, descripción y cada descripción de ítem, sin fusionar líneas ni usar categorías UNSPSC genéricas como una contratación confirmada.
3. El modelo compara cada segmento con categorías de alojamiento, salones, alimentación, obras, bienes, informática, transporte, aseo, auditoría y capacitación. Las puntuaciones NLI **no son porcentajes de probabilidad de negocio**.
4. El umbral inicial de aceptación es 0,90. Para confirmar un objeto ajeno se exige además un margen de 0,20 respecto a los servicios del hotel y cobertura de todas las líneas concretas. Un paquete puede contener servicios hoteleros y otros servicios. Una ambigüedad explícita de las reglas conserva el caso para revisión. Si el modelo no concluye pero las reglas confirman una contratación explícita de un servicio del hotel, se conserva esa evidencia y se registra `contratacion_explicita`; una discrepancia fuerte entre ambos lleva a revisión. No se trata una mención aislada de «hotel» o «cóctel» como contratación explícita.
5. Los textos recortados, líneas sin descripción o respuestas dudosas quedan en revisión. Una indisponibilidad no se interpreta como oportunidad y deja la evaluación pendiente para reintentar.
6. El resultado, versión, revisión del modelo, categorías y fragmentos literales se guardan en los metadatos de la evaluación y el criterio de pertinencia existentes. No se agrega otro pilar ni una tabla de vectores.

La CPU se ejecuta fuera del bucle async. Se reutilizan la sesión ONNX y las inferencias de hasta 2048 segmentos por proceso; las consultas del listado y del dashboard no vuelven a ejecutar el modelo. La firma de evaluación incluye la configuración semántica y hace caducar resultados anteriores al cambiar de modo o versión.

## Local

Desde `licing/backend/licing-core`, usando el entorno Python del proyecto:

```powershell
python -m pip install -r requirements-semantica.txt
python scripts/preparar_semantica.py
```

En el `.env` de Core, con una ruta absoluta al directorio descargado:

```dotenv
SEMANTICA_MODO=activa
SEMANTICA_MODELO_DIR=C:/ruta/Capstone-Licing/licing/backend/licing-core/.modelos/semantica-hotel
```

Reinicia Core. La siguiente actualización de preselección usa el nuevo motor. Compras Ágiles reevalúa sus pendientes en los turnos de ingesta. La instalación no reescribe evaluaciones de producción ni descarga compras automáticamente.

Los modos son `desactivada` (solo reglas), `sombra` (registra la inferencia sin cambiar clasificación) y `activa` (participa en el pilar de servicio). Sin configuración el componente está desactivado, por lo que la instalación normal de Core no requiere paquetes de aprendizaje automático.

## Producción con Vercel

Ejecuta el modelo en un servicio CPU persistente con los requisitos semánticos instalados y los artefactos descargados:

```powershell
# Configurar SEMANTICA_MODELO_DIR y SEMANTICA_TOKEN en el servicio CPU.
uvicorn app.semantica_api:app --host 0.0.0.0 --port 8010
```

El worker no requiere credenciales de PostgreSQL, Supabase ni Mercado Público. Usa un token privado propio. Publica su endpoint con HTTPS y configura en Core/Vercel:

```dotenv
SEMANTICA_MODO=activa
SEMANTICA_URL=https://servicio-cpu.example/clasificar
SEMANTICA_TOKEN=<mismo-token-privado-del-worker>
SEMANTICA_TIMEOUT_SEGUNDOS=8
```

Core se autentica ante el worker; el navegador no recibe el token. Una versión de modelo diferente, timeout o respuesta inválida deja el caso para revisión/reintento. Configurar `SEMANTICA_MODO` por sí solo no instala el modelo en Vercel.

## Pruebas reproducibles

```powershell
python scripts/probar_semantica.py --modelo-dir .modelos/semantica-hotel --salida ../../docs/validacion-semantica.json
python scripts/probar_semantica.py --modelo-dir .modelos/semantica-hotel --casos tests/fixtures/semantica_hotel_reales.json --modalidades original --salida ../../docs/validacion-semantica-datos-reales.json
python -m pytest -q
```

El script ejecuta inferencia real sobre los ejemplos de `tests/fixtures/semantica_hotel.json` como licitaciones y Compras Ágiles. Comprueba también el pilar de servicio: un fallo de ubicación no puede esconder un falso positivo semántico. No usa la base de datos. El conjunto es de regresión y calibración inicial; sus resultados no estiman por sí solos la precisión sobre todas las compras futuras.

La suite normal usa dobles de inferencia y prueba errores, límites, credenciales, caché, contratos mixtos y preservación de los tres pilares sin descargar modelos. Los informes JSON registran qué pruebas pasaron y cuáles requieren revisión.

La validación inicial dio 64/64 escenarios de regresión (32 casos en ambas modalidades) y 10/10 casos reales. Hubo cero falsos positivos en esas baterías, incluyendo el control del tercer pilar por separado. Se ejecutó inferencia en 58 escenarios y las reglas evitaron 16 inferencias innecesarias. Los casos con lugar de prestación desconocido siguen en revisión aunque el servicio sea compatible. Una primera evaluación con carga fría del modelo tardó aproximadamente 11 s; repetirla con la caché tardó 0,013 s en este equipo. Son mediciones locales y no una garantía de tiempos en producción.

Referencias: [modelo del autor](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli), [ONNX Runtime](https://onnxruntime.ai/docs/api/python/api_summary.html).
