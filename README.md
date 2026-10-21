# LICING · Asistente de Mercado Público para el Hotel Plaza San Francisco

Aplicación de apoyo al equipo comercial para consultar licitaciones y revisar oportunidades de alojamiento, eventos y catering. La decisión de participar corresponde al hotel.

## Arquitectura actual

- **Frontend:** React + Vite, con dashboard, oportunidades, fichas y módulos del prototipo.
- **Backend único:** Python + FastAPI, basado en **LICING Core**, en `licing/backend/licing-core/`.
- **Hosting:** React y Core se publican en **Vercel**; Docker se utiliza únicamente como herramienta local opcional. [Guía de despliegue](licing/docs/VERCEL.md).
- **Licitaciones:** PostgreSQL de Core, con respuestas originales, registros normalizados, ítems e historial de ingestas. SQLAlchemy y migraciones Alembic.
- **Usuarios:** Supabase Auth y perfiles en `public.usuario`, dentro del mismo proyecto **Usuarios/Licitaciones** que aloja las tablas de Core. Core verifica la sesión, la cuenta activa y los permisos.

El backend anterior de LICING y su lectura de Supabase Datos se retiraron. El frontend consulta Core mediante rutas autenticadas.

## Estado funcional

Implementado: ingesta de licitaciones de Mercado Público, normalización, persistencia, controles de integridad, consultas con filtros y paginación, detalle de ítems, métricas e historial de ingestas.

El perfil del hotel, la agenda, los clientes, el seguimiento, los reportes y el análisis documental conservan sus pantallas de demostración. La integración con Compra Ágil, la evaluación comercial y el análisis con IA quedan pendientes en Core.

## Ejecutar

Para utilizar la aplicación publicada, sigue [Vercel + Supabase](licing/docs/VERCEL.md). Los pasos siguientes son solo para desarrollo local.

Desde `licing/`, configura el login y el ticket de Mercado Público usando los archivos `.env.example`. Puedes mantener el `.env` existente de Core.

```powershell
docker compose up --build
```

Frontend: http://localhost:5173 · API: http://localhost:8000/api/docs

Las instrucciones de configuración, pruebas y compatibilidad de datos están en **[licing/README.md](licing/README.md)**. El reparto de trabajo está en **[CONTRIBUTING.md](licing/CONTRIBUTING.md)**.

Los directorios de las fases conservan las evidencias académicas del proyecto.
