# Scoring comercial

El score está entre 0 y 100 y se calcula en `pipeline/scoring.py`.

| Señal | Puntos |
|---|---:|
| Intención Alta / Media / Baja | 40 / 20 / 0 |
| Solicitó cita | 25 |
| Declaró cuota inicial o forma de pago | 20 |
| Primer contacto en máximo 24 horas | 15 |

Clasificación: Alta `>=75`, Media `40-74`, Baja `<40`. El tablero representa estas categorías como Caliente, Tibio y Frío. `lead_score.justificacion` registra los factores aportados para que un asesor pueda explicar la prioridad.

Para cambiar los pesos, modifique el código, agregue o ajuste una prueba en `tests/` y documente el motivo comercial en este archivo.
