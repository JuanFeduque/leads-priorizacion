"""Reglas explicables de priorización comercial y persistencia de lead_score."""
from __future__ import annotations

from typing import Any
import pandas as pd


def _presente(valor: Any) -> bool:
    return valor is not None and not pd.isna(valor) and str(valor).strip().casefold() not in {"", "no informa", "n/a", "na"}


def calcular_scores(leads: pd.DataFrame, enriquecidos: pd.DataFrame) -> pd.DataFrame:
    """Devuelve el contrato de ``lead_score`` a partir de leads e IA."""
    ia = enriquecidos.drop_duplicates("lead_id", keep="last") if not enriquecidos.empty else enriquecidos
    datos = leads[["lead_id", "fecha_registro", "fecha_primer_contacto"]].merge(ia, on="lead_id", how="left")
    filas = []
    for _, fila in datos.iterrows():
        intencion = {"alta": 40, "media": 20}.get(str(fila.get("intencion_compra", "")).casefold(), 0)
        pago = 20 if _presente(fila.get("monto_cuota_inicial")) or _presente(fila.get("forma_pago_declarada")) else 0
        cita = 25 if fila.get("pidio_cita") is True else 0
        registro = pd.to_datetime(fila["fecha_registro"], errors="coerce", utc=True)
        contacto = pd.to_datetime(fila["fecha_primer_contacto"], errors="coerce", utc=True)
        rapido = pd.notna(registro) and pd.notna(contacto) and pd.Timedelta(0) <= contacto - registro <= pd.Timedelta(hours=24)
        tiempo = 15 if rapido else 0
        score = intencion + pago + cita + tiempo
        prioridad = "Alta" if score >= 75 else "Media" if score >= 40 else "Baja"
        factores = []
        if intencion: factores.append(f"intención +{intencion}")
        if cita: factores.append("cita +25")
        if pago: factores.append("capacidad de pago +20")
        if tiempo: factores.append("contacto <=24h +15")
        filas.append({"lead_id": fila["lead_id"], "score": score, "prioridad": prioridad,
                      "justificacion": ", ".join(factores) or "Sin señales comerciales detectadas.",
                      "factor_tiempo_resp": tiempo, "factor_intencion": intencion,
                      "factor_forma_pago": pago, "factor_engagement": cita, "version_modelo": "reglas-v1"})
    return pd.DataFrame(filas)
