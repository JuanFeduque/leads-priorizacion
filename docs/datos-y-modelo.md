# Datos y modelo

## Fuentes

| Archivo | Uso |
|---|---|
| `leads.csv` | Lead, canal, contacto, empresa, punto de venta e interés |
| `conversaciones.json` | Mensajes vinculados a `lead_id` crudo |
| `catalogo_motos.csv` | Catálogo y disponibilidad por punto de venta |
| `asesores.csv` | Asesores y capacidad diaria |
| `historico_cierres.csv` | Validación y futura calibración |

## Tablas Supabase

`empresa -> punto_venta -> asesor` describe la estructura comercial. `moto_catalogo` contiene productos. `lead` es la entidad principal; `lead_enriquecido` y `lead_score` tienen relación 1:1 con ella.

## Identidad y deduplicación

`pipeline/deduplicacion.py` usa `telefono_normalizado` como identificador principal y email normalizado como enlace complementario. La unión es transitiva. Por ejemplo, si A y B comparten teléfono, y B y C comparten email, los tres registros terminan en un solo lead.

El UUID determinista se deriva del conjunto ordenado de IDs crudos. Esto permite reejecutar cargas sin crear duplicados. Nunca reconstruya el UUID desde un único `LD-XXXX` si podría existir una fusión; consulte `lead.lead_id_original`.
