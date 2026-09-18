import pandas as pd
from pipeline.deduplicacion import deduplicar_leads


def test_fusiona_telefono_y_guarda_ids_crudos():
    df = pd.DataFrame([
        {"lead_id": "LD-1", "telefono_normalizado": "3001111111", "canal": "WhatsApp", "fecha_registro": "2026-01-02"},
        {"lead_id": "LD-2", "telefono_normalizado": "3001111111", "canal": "Formulario Web", "fecha_registro": "2026-01-01"},
    ])
    resultado = deduplicar_leads(df)
    assert len(resultado) == 1
    assert resultado.iloc[0].lead_id_original == ["LD-2", "LD-1"]
    assert resultado.iloc[0].canal == "Múltiple"
