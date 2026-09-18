import pandas as pd
from pipeline.scoring import calcular_scores


def test_score_completo_es_100_y_alta():
    leads = pd.DataFrame([{"lead_id": "u1", "fecha_registro": "2026-09-01T10:00:00Z", "fecha_primer_contacto": "2026-09-01T12:00:00Z"}])
    ia = pd.DataFrame([{"lead_id": "u1", "intencion_compra": "Alta", "pidio_cita": True, "forma_pago_declarada": "Contado", "monto_cuota_inicial": None}])
    resultado = calcular_scores(leads, ia).iloc[0]
    assert resultado.score == 100
    assert resultado.prioridad == "Alta"
