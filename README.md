# Priorización de leads - Motos y Servicios

Pipeline automatizado que ingiere leads, los normaliza y deduplica, extrae señales de conversaciones con DeepSeek, calcula un score explicable y publica la lista priorizada en Streamlit.

## Arquitectura

`data/raw -> ingesta -> normalización -> deduplicación -> Supabase (maestros y leads) -> DeepSeek -> lead_enriquecido -> lead_score -> Streamlit`

El score suma intención Alta/Media (40/20), cita (25), capacidad de pago declarada (20) y primer contacto en máximo 24 horas (15). Las reglas se encuentran en `pipeline/scoring.py` y se persisten con justificación.

## Configuración

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Complete `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` y `DEEPSEEK_API_KEY` en `.env`. Aplique `db/schema.sql` antes de la primera carga.

## Ejecución

```bash
python -m pipeline.probar_pipeline
streamlit run dashboard/app.py
pytest -q
```

GitHub Actions ejecuta el pipeline diariamente. Configure `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` y `DEEPSEEK_API_KEY` como secretos. `data/raw/` se ignora porque contiene PII: para CI real, entréguelo como artefacto seguro o desde almacenamiento privado.

## Seguridad y multiempresa

El DDL activa RLS. Para una URL pública segura, el dashboard debe usar el JWT de un usuario autenticado cuyo `app_metadata.empresa_id` limite las filas de Supabase. Un filtro de Streamlit no sustituye RLS. Nunca exponga `SUPABASE_SERVICE_ROLE_KEY` al navegador.

## Limitaciones conocidas

La publicación pública requiere las credenciales de Streamlit Cloud, Render o un proveedor similar. El histórico se conserva para evaluar y calibrar las reglas en una siguiente iteración.
