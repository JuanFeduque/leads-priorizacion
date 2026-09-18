# Operación y diagnóstico

## Comandos

```powershell
pip install -r requirements.txt
pytest -q
python -m pipeline.probar_pipeline
streamlit run dashboard/app.py
```

## Errores frecuentes

| Síntoma | Causa probable | Acción |
|---|---|---|
| `NaN is not JSON compliant` | Campo opcional sin normalizar | Use `cargar_registros_supabase`; convierte NaN a null |
| Error 21000 en upsert | Dos respuestas para el mismo lead | El cargador deduplica por UUID y conserva la última |
| Dashboard sin leads | RLS o empresa de dashboard incorrecta | Revise `DASHBOARD_EMPRESA_ID`, secretos y políticas |
| Enriquecimiento sin unión | ID crudo no existe en lead | Revise deduplicación y `lead_id_original` |
| CI no encuentra archivos | Fuentes ausentes en el runner | Versione datos sintéticos o descárguelos de almacenamiento privado |

## Verificaciones antes de despliegue

1. `pytest -q` pasa.
2. `db/schema.sql` está aplicado.
3. Secretos están configurados en cada plataforma.
4. La cuenta de servicio nunca aparece en código, logs ni navegador.
5. El dashboard muestra únicamente la empresa configurada o autenticada.
