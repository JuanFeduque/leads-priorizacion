"""Carga por lotes de leads normalizados a Supabase.

El módulo usa ``supabase-py`` y asigna un UUID determinista a cada persona.
Por eso emplea ``upsert`` sobre ``lead_id``: una re-ejecución del ETL no crea
duplicados y es segura incluso después de un fallo de red incierto.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
from uuid import NAMESPACE_URL, UUID, uuid5

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client


TABLA_LEAD = "lead"
_CAMPOS_REQUERIDOS = ("fecha_registro", "canal", "empresa_id", "nombre_cliente", "estado_gestion")


@dataclass(frozen=True)
class ResultadoCarga:
    """Resumen de una carga exitosa."""

    registros_preparados: int
    lotes_enviados: int
    tamano_lote: int


def _es_vacio(valor: Any) -> bool:
    if valor is None:
        return True
    if isinstance(valor, str):
        return not valor.strip()
    return isinstance(valor, float) and math.isnan(valor)


def _a_json(valor: Any) -> Any:
    """Convierte tipos de Pandas/NumPy a valores serializables por PostgREST."""
    if _es_vacio(valor) or valor is pd.NA or valor is pd.NaT:
        return None
    if isinstance(valor, (pd.Timestamp, datetime, date)):
        return valor.isoformat()
    if hasattr(valor, "item"):  # Escalares de NumPy
        return _a_json(valor.item())
    if isinstance(valor, (list, tuple, set)):
        return [_a_json(item) for item in valor if not _es_vacio(item)]
    return valor.strip() if isinstance(valor, str) else valor


def _obtener(fila: pd.Series, *columnas: str) -> Any:
    """Retorna el primer valor útil entre nombres alternativos de columna."""
    for columna in columnas:
        if columna in fila.index and not _es_vacio(fila[columna]):
            return fila[columna]
    return None


def _ids_originales(fila: pd.Series) -> list[str]:
    valor = _obtener(fila, "lead_id_original")
    if isinstance(valor, (list, tuple, set)):
        ids = [str(item).strip() for item in valor if not _es_vacio(item)]
    elif valor is not None:
        ids = [str(valor).strip()]
    else:
        lead_id_crudo = _obtener(fila, "lead_id")
        ids = [str(lead_id_crudo).strip()] if lead_id_crudo is not None else []
    if not ids:
        raise ValueError("Cada fila debe tener lead_id o lead_id_original.")
    return list(dict.fromkeys(ids))


def _uuid_del_lead(fila: pd.Series, ids_originales: list[str]) -> str:
    """Usa un UUID consolidado existente o crea uno estable desde IDs crudos."""
    posible_uuid = _obtener(fila, "lead_id")
    if posible_uuid is not None:
        try:
            return str(UUID(str(posible_uuid)))
        except ValueError:
            pass
    semilla = "motos-servicios/leads:" + "|".join(sorted(ids_originales))
    return str(uuid5(NAMESPACE_URL, semilla))


def _es_descartado(fila: pd.Series) -> bool:
    valor = _obtener(fila, "es_descartado")
    if isinstance(valor, bool):
        return valor
    if valor is not None:
        return str(valor).strip().casefold() in {"true", "1", "si", "sí"}
    estado = _obtener(fila, "estado_gestion")
    return str(estado).strip().casefold() == "descartado" if estado is not None else False


def preparar_registros_lead(leads: pd.DataFrame) -> list[dict[str, Any]]:
    """Mapea un DataFrame limpio al contrato de la tabla ``lead``."""
    registros: list[dict[str, Any]] = []
    for indice, fila in leads.iterrows():
        ids = _ids_originales(fila)
        registro = {
            "lead_id": _uuid_del_lead(fila, ids),
            "lead_id_original": ids,
            "fecha_registro": _a_json(_obtener(fila, "fecha_registro")),
            "fecha_primer_contacto": _a_json(_obtener(fila, "fecha_primer_contacto")),
            "canal": _a_json(_obtener(fila, "canal")),
            "campania": _a_json(_obtener(fila, "campania")),
            "empresa_id": _a_json(_obtener(fila, "empresa_id")),
            "punto_venta_id": _a_json(_obtener(fila, "punto_venta_id")),
            "nombre_cliente": _a_json(_obtener(fila, "nombre_cliente")),
            "telefono_normalizado": _a_json(_obtener(fila, "telefono_normalizado")),
            "telefono_original": _a_json(_obtener(fila, "telefono_original", "telefono")),
            "email": _a_json(_obtener(fila, "email")),
            "ciudad": _a_json(_obtener(fila, "ciudad_normalizada", "ciudad")),
            "modelo_interes_texto": _a_json(_obtener(fila, "modelo_interes_texto")),
            "sku_match": _a_json(_obtener(fila, "sku_match")),
            "estado_gestion": _a_json(_obtener(fila, "estado_gestion")),
            "es_descartado": _es_descartado(fila),
        }
        faltantes = [campo for campo in _CAMPOS_REQUERIDOS if _es_vacio(registro[campo])]
        if faltantes:
            raise ValueError(f"Fila {indice}: faltan campos requeridos para lead: {faltantes}")
        registros.append(registro)
    return registros


def crear_cliente_desde_entorno() -> Client:
    """Crea un cliente de backend leyendo el archivo ``.env`` del proyecto."""
    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    clave = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not clave:
        raise RuntimeError(
            "Defina SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en .env. "
            "La clave service_role es solo para el ETL de backend."
        )
        
    # Validamos que efectivamente sea la clave secreta y no la pública
    if "publishable" in clave.lower():
        raise RuntimeError(
            "❌ ERROR DE CREDENCIALES: Estás usando la 'Publishable key' en tu .env. "
            "Debes usar la 'Secret key' (la que empieza por sb_secret_) para que el proceso "
            "de backend tenga permisos de administrador y pueda insertar masivamente saltando el RLS."
        )
        
    return create_client(url, clave)


def _lotes(registros: list[dict[str, Any]], tamano: int) -> Iterable[list[dict[str, Any]]]:
    for inicio in range(0, len(registros), tamano):
        yield registros[inicio : inicio + tamano]


def cargar_leads_supabase(
    leads: pd.DataFrame,
    *,
    tamano_lote: int = 250,
    cliente: Client | None = None,
) -> ResultadoCarga:
    """Inserta/actualiza leads en Supabase por lotes."""
    if tamano_lote <= 0:
        raise ValueError("tamano_lote debe ser mayor que cero.")
    registros = preparar_registros_lead(leads)
    if not registros:
        return ResultadoCarga(registros_preparados=0, lotes_enviados=0, tamano_lote=tamano_lote)

    cliente = cliente or crear_cliente_desde_entorno()
    enviados = 0
    for lote in _lotes(registros, tamano_lote):
        # ``lead_id`` es la PK determinista, por lo que upsert hace la carga idempotente.
        cliente.table(TABLA_LEAD).upsert(lote, on_conflict="lead_id", returning="minimal").execute()
        enviados += 1
        
    return ResultadoCarga(registros_preparados=len(registros), lotes_enviados=enviados, tamano_lote=tamano_lote)