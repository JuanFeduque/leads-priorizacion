"""Carga por lotes de leads normalizados a Supabase.

El módulo usa ``supabase-py`` y asigna un UUID determinista a cada persona.
Por eso emplea ``upsert`` sobre ``lead_id``: una re-ejecución del ETL no crea
duplicados y es segura incluso después de un fallo de red incierto.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable
from uuid import NAMESPACE_URL, UUID, uuid5

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client


TABLA_LEAD = "lead"
TABLA_LEAD_ENRIQUECIDO = "lead_enriquecido"
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


def _lista_de_textos(valor: Any, campo: str, indice: int) -> list[str]:
    """Normaliza campos PostgreSQL ``TEXT[]`` provenientes de DeepSeek."""
    if _es_vacio(valor) or valor is pd.NA:
        return []
    if isinstance(valor, str):
        texto = valor.strip()
        # Variantes habituales con las que un LLM expresa ausencia de datos.
        if texto.casefold() in {"ninguna", "ninguno", "no", "n/a", "na", "sin objeciones", "sin competencia"}:
            return []
        return [texto]
    if not isinstance(valor, (list, tuple, set)):
        raise ValueError(f"Resultado IA {indice}: '{campo}' debe ser texto o una lista de textos.")
    return [str(item).strip() for item in valor if not _es_vacio(item)]


def _es_uuid(valor: Any) -> str | None:
    """Devuelve un UUID canónico o ``None`` cuando el valor es un ID legible."""
    if _es_vacio(valor):
        return None
    try:
        return str(UUID(str(valor)))
    except (ValueError, AttributeError, TypeError):
        return None


def _buscar_uuids_por_id_original(cliente: Client, ids_originales: set[str]) -> dict[str, str]:
    """Obtiene IDs consolidados desde ``lead.lead_id_original`` en pocas consultas.

    No se recalcula el UUID a partir del código crudo: un ``LD-XXXX`` puede
    pertenecer a un lead deduplicado cuyo UUID se creó usando varios IDs.
    """
    resultado: dict[str, str] = {}
    ids = sorted(ids_originales)
    # Evita URLs de filtros excesivamente largas en lotes de IA grandes.
    for inicio in range(0, len(ids), 100):
        bloque = ids[inicio : inicio + 100]
        respuesta = (
            cliente.table(TABLA_LEAD)
            .select("lead_id,lead_id_original")
            .overlaps("lead_id_original", bloque)
            .execute()
        )
        for lead in respuesta.data or []:
            lead_uuid = _es_uuid(lead.get("lead_id"))
            if lead_uuid is None:
                raise RuntimeError("La tabla lead contiene un lead_id no válido como UUID.")
            for id_original in lead.get("lead_id_original") or []:
                codigo = str(id_original).strip()
                if codigo not in ids_originales:
                    continue
                previo = resultado.get(codigo)
                if previo and previo != lead_uuid:
                    raise RuntimeError(f"El ID original '{codigo}' está asociado a más de un lead.")
                resultado[codigo] = lead_uuid
    return resultado


def guardar_leads_enriquecidos_en_supabase(resultados_ia: list[dict[str, Any]]) -> int:
    """Sincroniza análisis de DeepSeek con ``lead_enriquecido``.

    El ``lead_id`` puede ser un UUID o un ID original legible como ``LD-01329``.
    Los IDs legibles se resuelven contra ``lead.lead_id_original`` antes del
    upsert; así se respeta el UUID de un lead eventualmente deduplicado. Los
    campos opcionales ausentes se guardan como ``NULL`` (o listas vacías para
    ``TEXT[]``). La operación es idempotente gracias a la restricción única.

    Returns:
        Número de registros enviados a Supabase.

    Raises:
        ValueError: si un resultado no tiene ``lead_id`` o sus campos de arrays
            tienen tipo inválido. Los IDs legibles que no existen en ``lead``
            se omiten con una advertencia para no detener el lote.
        Exception: cualquier error de credenciales o de sincronización del SDK.
    """
    if not isinstance(resultados_ia, list):
        raise TypeError("resultados_ia debe ser una lista de diccionarios.")
    if not resultados_ia:
        print("[Supabase] No hay leads enriquecidos para sincronizar.")
        return 0

    procesado_at = datetime.now(timezone.utc).isoformat()
    registros: list[dict[str, Any]] = []
    try:
        ids_legibles: set[str] = set()
        for indice, resultado in enumerate(resultados_ia):
            if not isinstance(resultado, dict):
                raise TypeError(f"Resultado IA {indice} debe ser un diccionario.")
            lead_id_entrada = resultado.get("lead_id")
            if _es_vacio(lead_id_entrada):
                # Normalmente extraccion_ia.py lo completa por posición; si la
                # fuente tampoco tenía ID, no se debe detener todo el lote.
                print(f"[Supabase] Advertencia: se descartará resultado IA {indice} sin lead_id.")
                continue
            if _es_uuid(lead_id_entrada) is None:
                ids_legibles.add(str(lead_id_entrada).strip())

        cliente = crear_cliente_desde_entorno()
        ids_resueltos = _buscar_uuids_por_id_original(cliente, ids_legibles)
        ids_faltantes = ids_legibles - set(ids_resueltos)
        if ids_faltantes:
            print(
                "[Supabase] Advertencia: se descartarán resultados IA sin lead correspondiente: "
                + ", ".join(sorted(ids_faltantes))
            )
        if ids_legibles:
            print(f"[Supabase] Se mapearon {len(ids_resueltos)} de {len(ids_legibles)} IDs legibles a UUIDs de lead.")

        for indice, resultado in enumerate(resultados_ia):
            lead_id_entrada = resultado.get("lead_id")
            if _es_vacio(lead_id_entrada):
                continue
            lead_id = _es_uuid(lead_id_entrada)
            if lead_id is None:
                lead_id = ids_resueltos.get(str(lead_id_entrada).strip())
                if lead_id is None:
                    print(f"[Supabase] Omitiendo resultado IA {indice}: lead_id '{lead_id_entrada}' no existe.")
                    continue

            registros.append(
                {
                    "lead_id": lead_id,
                    "intencion_compra": _a_json(resultado.get("intencion_compra")),
                    "forma_pago_declarada": _a_json(resultado.get("forma_pago_declarada")),
                    "monto_cuota_inicial": _a_json(resultado.get("monto_cuota_inicial")),
                    "pidio_cita": _a_json(resultado.get("pidio_cita")),
                    "objeciones": _lista_de_textos(resultado.get("objeciones"), "objeciones", indice),
                    "marcas_competencia": _lista_de_textos(
                        resultado.get("marcas_competencia"), "marcas_competencia", indice
                    ),
                    "urgencia": _a_json(resultado.get("urgencia")),
                    "resumen_conversacion": _a_json(resultado.get("resumen_conversacion")),
                    "modelo_ia": "deepseek-chat",
                    "tokens_usados": _a_json(resultado.get("tokens_usados")),
                    "procesado_at": procesado_at,
                }
            )

        if not registros:
            print("[Supabase] No hay leads enriquecidos válidos para sincronizar.")
            return 0

        print(f"[Supabase] Sincronizando {len(registros)} leads enriquecidos con DeepSeek...")
        cliente.table(TABLA_LEAD_ENRIQUECIDO).upsert(
            registros, on_conflict="lead_id", returning="minimal"
        ).execute()
    except Exception as exc:
        print(f"[Supabase] Error al sincronizar leads enriquecidos: {exc}")
        raise

    print(f"[Supabase] Sincronización exitosa: {len(registros)} leads enriquecidos guardados.")
    return len(registros)
