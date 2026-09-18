# Arquitectura

El job programado ejecuta `pipeline.probar_pipeline`. Carga fuentes, normaliza y consolida identidades, inserta tablas maestras antes de `lead`, extrae conversaciones con DeepSeek y persiste los enriquecimientos. Luego calcula `lead_score` con reglas auditables. Streamlit consulta datos protegidos por RLS.

## Límites de seguridad

- El ETL usa `SUPABASE_SERVICE_ROLE_KEY` exclusivamente en backend.
- El dashboard debe usar una sesión JWT de usuario con `app_metadata.empresa_id`.
- Los IDs crudos de conversaciones se convierten al UUID consolidado consultando `lead_id_original`.
