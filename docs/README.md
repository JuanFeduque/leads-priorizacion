# Documentación técnica

Esta carpeta describe el sistema para operadores, evaluadores y agentes de IA. Empiece por [visión general](vision-general.md), continúe con [arquitectura](arquitectura.md) y consulte [operación](operacion.md) para ejecutar o desplegar.

| Documento | Propósito |
|---|---|
| [vision-general.md](vision-general.md) | Problema, alcance, decisiones y flujo de negocio |
| [arquitectura.md](arquitectura.md) | Componentes, fronteras de confianza y recorrido de datos |
| [datos-y-modelo.md](datos-y-modelo.md) | Archivos fuente, tablas, claves e identidad de leads |
| [pipeline.md](pipeline.md) | Etapas, módulos, contratos e idempotencia |
| [scoring.md](scoring.md) | Reglas de prioridad y explicación del puntaje |
| [seguridad-y-despliegue.md](seguridad-y-despliegue.md) | Secretos, RLS, GitHub Actions y Streamlit |
| [operacion.md](operacion.md) | Comandos, diagnóstico y recuperación de errores |

## Contexto mínimo para otra IA

- El ID crudo de un canal se llama `LD-XXXX`; no es la clave primaria de la base.
- `lead.lead_id` es un UUID determinista. `lead_id_original` conserva uno o varios IDs crudos tras deduplicación.
- Las respuestas de DeepSeek pueden traer IDs crudos; `carga_supabase.py` los resuelve contra `lead_id_original` antes de escribir `lead_enriquecido`.
- El proceso de backend puede usar `SUPABASE_SERVICE_ROLE_KEY`. Un navegador nunca debe usarla.
- Cualquier cambio de reglas comerciales debe actualizar `pipeline/scoring.py`, sus pruebas y `scoring.md`.
