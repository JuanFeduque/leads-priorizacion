"""Deduplicación determinista de leads normalizados.

Un teléfono normalizado es la llave de identidad principal.  Un correo válido
normalizado también une registros cuando está disponible; esto permite unir un
formulario y una conversación de WhatsApp aunque uno de los registros no tenga
teléfono.  Las coincidencias son transitivas: A--teléfono--B--correo--C forma
una única persona.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pandas as pd


def _valor_presente(valor: Any) -> bool:
    """Indica si *valor* contiene un dato útil (no nulo ni texto vacío)."""
    return valor is not None and not pd.isna(valor) and str(valor).strip() != ""


def _email_normalizado(valor: Any) -> str | None:
    """Normaliza un correo para comparar sin usar valores vacíos o inválidos."""
    if not _valor_presente(valor):
        return None
    email = str(valor).strip().casefold()
    # No pretende validar RFC completo: evita unir por textos que no son email.
    return email if email.count("@") == 1 and not email.startswith("@") else None


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _primer_valor(grupo: pd.DataFrame, columna: str) -> Any:
    """Obtiene el primer valor presente siguiendo la prioridad del grupo."""
    if columna not in grupo.columns:
        return None
    for valor in grupo[columna]:
        if _valor_presente(valor):
            return valor
    return None


def _canales(grupo: pd.DataFrame) -> list[str]:
    """Devuelve canales únicos, sin que diferencias de mayúsculas dupliquen uno."""
    if "canal" not in grupo.columns:
        return []
    vistos: set[str] = set()
    resultado: list[str] = []
    for valor in grupo["canal"]:
        if not _valor_presente(valor):
            continue
        canal = str(valor).strip()
        if canal.casefold() not in vistos:
            vistos.add(canal.casefold())
            resultado.append(canal)
    return resultado


def deduplicar_leads(
    leads_normalizados: pd.DataFrame,
    *,
    usar_email: bool = True,
    namespace_uuid: str = "motos-servicios/leads",
) -> pd.DataFrame:
    """Consolida registros que pertenecen a una misma persona.

    Args:
        leads_normalizados: Resultado de ``normalizar_leads``. Debe contener
            ``lead_id`` y, al menos, ``telefono_normalizado`` o ``email``.
        usar_email: Si es ``True``, correos válidos iguales también identifican
            a la persona. Desactívelo si una fuente reutiliza correos genéricos.
        namespace_uuid: Semilla para generar IDs consolidados reproducibles.

    Returns:
        Un DataFrame con una fila por persona. ``lead_id`` es un UUID estable y
        ``lead_id_original`` contiene todos los IDs de origen. Se añaden
        ``canales_origen`` y ``email_normalizado`` para auditoría.

    La fila principal es la de ``fecha_registro`` más antigua (y el orden de
    entrada como desempate). Sus valores se priorizan; valores faltantes se
    completan desde los demás registros del grupo. La fecha de registro se
    conserva como la mínima y la de primer contacto como la mínima disponible.
    """
    requeridas = {"lead_id"}
    faltantes = requeridas - set(leads_normalizados.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas requeridas: {sorted(faltantes)}")
    if "telefono_normalizado" not in leads_normalizados and "email" not in leads_normalizados:
        raise ValueError("Se requiere telefono_normalizado o email para deduplicar.")

    df = leads_normalizados.copy().reset_index(drop=True)
    if df.empty:
        resultado = df.drop(columns=["lead_id"], errors="ignore")
        resultado["lead_id"] = pd.Series(dtype="string")
        resultado["lead_id_original"] = pd.Series(dtype="object")
        resultado["canales_origen"] = pd.Series(dtype="object")
        resultado["email_normalizado"] = pd.Series(dtype="string")
        return resultado

    df["_orden_entrada"] = range(len(df))
    df["email_normalizado"] = df.get("email", pd.Series(index=df.index, dtype="object")).map(_email_normalizado)
    uf = _UnionFind(len(df))
    propietarios: dict[tuple[str, str], int] = {}

    for indice, fila in df.iterrows():
        llaves: list[tuple[str, str]] = []
        telefono = fila.get("telefono_normalizado")
        if _valor_presente(telefono):
            llaves.append(("telefono", str(telefono).strip()))
        if usar_email and _valor_presente(fila["email_normalizado"]):
            llaves.append(("email", str(fila["email_normalizado"])))
        for llave in llaves:
            if llave in propietarios:
                uf.union(indice, propietarios[llave])
            else:
                propietarios[llave] = indice

    grupos: dict[int, list[int]] = defaultdict(list)
    for indice in df.index:
        grupos[uf.find(indice)].append(indice)

    filas: list[dict[str, Any]] = []
    for indices in grupos.values():
        grupo = df.loc[indices].copy()
        if "fecha_registro" in grupo.columns:
            grupo["_fecha_orden"] = pd.to_datetime(grupo["fecha_registro"], errors="coerce")
            grupo = grupo.sort_values(["_fecha_orden", "_orden_entrada"], na_position="last")
        else:
            grupo = grupo.sort_values("_orden_entrada")

        principal = grupo.iloc[0].drop(labels=["_orden_entrada", "_fecha_orden"], errors="ignore").to_dict()
        for columna in df.columns:
            if columna.startswith("_") or columna in {"lead_id", "email_normalizado"}:
                continue
            if not _valor_presente(principal.get(columna)):
                principal[columna] = _primer_valor(grupo, columna)

        originales = list(dict.fromkeys(str(valor) for valor in grupo["lead_id"] if _valor_presente(valor)))
        canales = _canales(grupo)
        principal["lead_id_original"] = originales
        principal["lead_id"] = str(uuid5(NAMESPACE_URL, f"{namespace_uuid}:{'|'.join(sorted(originales))}"))
        principal["canales_origen"] = canales
        if canales:
            principal["canal"] = canales[0] if len(canales) == 1 else "Múltiple"
        principal["email_normalizado"] = _primer_valor(grupo, "email_normalizado")

        if "fecha_registro" in grupo.columns:
            # Se usa la serie ya parseada: sobre strings una comparación ``min``
            # sería alfabética y no cronológica.
            principal["fecha_registro"] = grupo["_fecha_orden"].min()
        if "fecha_primer_contacto" in grupo.columns:
            fechas = pd.to_datetime(grupo["fecha_primer_contacto"], errors="coerce")
            principal["fecha_primer_contacto"] = fechas.min() if fechas.notna().any() else pd.NaT
        filas.append(principal)

    return pd.DataFrame(filas).drop(columns=["_orden_entrada", "_fecha_orden"], errors="ignore")
