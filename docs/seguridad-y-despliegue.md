# Seguridad y despliegue

## Secretos

GitHub Actions: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DEEPSEEK_API_KEY`.

Streamlit de una empresa: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DASHBOARD_EMPRESA_ID`. La clave vive en el proceso de Streamlit, no en el navegador, y el código fija la consulta a una empresa. Para una app multiempresa, use autenticación Supabase y un JWT con `app_metadata.empresa_id`.

## RLS

`db/schema.sql` define políticas sobre `lead`, `lead_enriquecido` y `lead_score` usando `auth.jwt() -> app_metadata ->> empresa_id`. Aplique el DDL en Supabase antes de activar el dashboard multiempresa.

## CI

`.github/workflows/ci.yml` prueba cada push o PR dirigido a `main`. En `main`, cron o ejecución manual corre el ETL. El cron es 11:00 UTC, equivalente a 06:00 en Colombia. Los insumos deben estar presentes en `data/raw/` o descargarse desde un repositorio privado antes de ejecutar el job.
