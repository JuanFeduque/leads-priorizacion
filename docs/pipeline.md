# Pipeline

El punto de entrada es `python -m pipeline.probar_pipeline`.

1. `ingesta.cargar_datos_crudos()` lee las fuentes.
2. `normalizacion.normalizar_leads()` limpia valores y crea campos normalizados.
3. `deduplicacion.deduplicar_leads()` genera una persona por identidad.
4. `carga_supabase` carga primero maestros y luego `lead` por lotes de 250.
5. `extraccion_ia.procesar_todas_las_conversaciones()` manda lotes de chats a DeepSeek. Si la IA omite un ID, el módulo lo recupera por posición de conversación dentro del lote.
6. `guardar_leads_enriquecidos_en_supabase()` convierte IDs crudos a UUID, elimina no encontrados, deduplica el lote por UUID y hace upsert.
7. `scoring.calcular_scores()` produce filas de `lead_score` con justificación.

## Idempotencia

Los upserts usan las claves únicas de cada tabla. Antes del upsert de `lead_enriquecido`, se conserva el último resultado por `lead_id`; evita el error PostgreSQL 21000.

## Contrato de IA

Campos esperados: `lead_id`, `intencion_compra`, `forma_pago_declarada`, `monto_cuota_inicial`, `pidio_cita`, `objeciones`, `marcas_competencia`, `urgencia` y `resumen_conversacion`. Los dos arrays aceptan texto plano y se normalizan a lista.
