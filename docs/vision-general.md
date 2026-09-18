# Visión general

Motos y Servicios recibe leads desde WhatsApp, Meta Ads y formularios web. El sistema convierte esos registros y sus conversaciones en una lista diaria priorizada para el equipo comercial.

## Objetivo

Reducir el tiempo hasta el primer contacto y priorizar personas con señales verificables de compra. El producto no decide automáticamente una venta: ofrece una prioridad explicable para el asesor.

## Alcance actual

1. Lee cinco fuentes sintéticas de `data/raw/`.
2. Normaliza teléfono, fechas, ciudad y marca; descarta pruebas y datos inválidos.
3. Consolida registros de una persona por teléfono y, opcionalmente, correo.
4. Extrae señales cualitativas con DeepSeek.
5. Persiste entidades maestras, leads, enriquecimientos y puntajes en Supabase.
6. Muestra el resultado en Streamlit, filtrado por empresa.

## Supuestos y límites

- El histórico se conserva para calibrar reglas futuras; la versión actual usa reglas transparentes, no un modelo entrenado.
- El enriquecimiento solo es tan confiable como la conversación disponible. Ausencia de conversación no significa desinterés.
- Los archivos del assessment son sintéticos. En producción, las fuentes deben llegar desde almacenamiento privado, no desde Git.
