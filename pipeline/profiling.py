"""
pipeline/profiling.py
─────────────────────
Profiling de calidad sobre los 5 archivos fuente en data/raw/.
Detecta y reporta cuantitativamente cada hallazgo conocido SIN corregir datos.

Ejecución:
    python -m pipeline.profiling
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

# Forzar UTF-8 en Windows (cmd / PowerShell usan cp1252 por defecto)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

import pandas as pd
from rapidfuzz import fuzz

# ──────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

LEADS_PATH = RAW / "leads.csv"
CONV_PATH = RAW / "conversaciones.json"
CATALOGO_PATH = RAW / "catalogo_motos.csv"
ASESORES_PATH = RAW / "asesores.csv"
HISTORICO_PATH = RAW / "historico_cierres.csv"

# Marcas canónicas del catálogo para detección de typos
MARCAS_CANONICAS = ["Bajaj", "Suzuki", "Honda", "Hero", "AKT"]

# ──────────────────────────────────────────────
# Helpers de impresión
# ──────────────────────────────────────────────
SEP = "=" * 72


def header(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def sub(title: str) -> None:
    print(f"\n  ── {title} ──")


# ──────────────────────────────────────────────
# 1. Cargar archivos
# ──────────────────────────────────────────────
def load_all() -> tuple[pd.DataFrame, list[dict], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    leads = pd.read_csv(LEADS_PATH, dtype=str)
    with open(CONV_PATH, encoding="utf-8") as f:
        conversaciones = json.load(f)
    catalogo = pd.read_csv(CATALOGO_PATH, dtype=str)
    asesores = pd.read_csv(ASESORES_PATH, dtype=str)
    historico = pd.read_csv(HISTORICO_PATH, dtype=str)
    return leads, conversaciones, catalogo, asesores, historico


# ──────────────────────────────────────────────
# 2. Capitalización inconsistente
# ──────────────────────────────────────────────
def check_capitalization(leads: pd.DataFrame) -> None:
    header("1. CAPITALIZACIÓN INCONSISTENTE")
    for col in ("canal", "estado_gestion"):
        sub(f"Columna: {col}")
        vals = leads[col].dropna()
        groups: dict[str, list[str]] = {}
        for v in vals.unique():
            key = v.strip().lower()
            groups.setdefault(key, []).append(v)
        inconsistent = {k: vs for k, vs in groups.items() if len(vs) > 1}
        if not inconsistent:
            print("    Sin inconsistencias.")
            continue
        for key, variants in sorted(inconsistent.items()):
            counts = {v: int((vals == v).sum()) for v in variants}
            total = sum(counts.values())
            detail = ", ".join(f'"{v}" ({c})' for v, c in counts.items())
            print(f'    "{key}" → {len(variants)} variantes, {total} filas: {detail}')
        print(f"    Total grupos inconsistentes: {len(inconsistent)}")


# ──────────────────────────────────────────────
# 3. Formatos de fecha mezclados
# ──────────────────────────────────────────────
DATE_PATTERNS = [
    ("DD-MM-YYYY",            r"^\d{2}-\d{2}-\d{4}$"),
    ("DD/MM/YYYY HH:MM",      r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}$"),
    ("YYYY-MM-DD HH:MM:SS",   r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$"),
    ("ISO con T",             r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"),
]


def classify_date(val: str) -> str:
    val = val.strip()
    for name, pat in DATE_PATTERNS:
        if re.match(pat, val):
            return name
    return f"Otro ({val})"


def _is_ambiguous_mdy(val: str) -> bool:
    """Detecta fechas donde el segundo campo > 12, forzando interpretación MM/DD.

    Ejemplo: "08/18/2026" — 18 no puede ser un mes, así que 08 debe ser
    el mes y 18 el día, pero el formato aparenta DD/MM.
    """
    m = re.match(r"^(\d{2})[/-](\d{2})[/-]\d{4}", val.strip())
    if not m:
        return False
    first, second = int(m.group(1)), int(m.group(2))
    # second > 12 → no puede ser un mes → fuerza que first sea el mes (MM/DD)
    return first <= 12 < second


def _is_invalid_date(val: str) -> bool:
    """Intenta parsear con pandas; si falla, es inválida."""
    try:
        pd.to_datetime(val.strip(), dayfirst=True)
        return False
    except Exception:
        try:
            pd.to_datetime(val.strip(), dayfirst=False)
            return False
        except Exception:
            return True


def check_dates(leads: pd.DataFrame) -> None:
    header("2. FORMATOS DE FECHA MEZCLADOS")
    for col in ("fecha_registro", "fecha_primer_contacto"):
        sub(f"Columna: {col}")
        vals = leads[col].dropna()
        nulos = int(leads[col].isna().sum())
        print(f"    Valores presentes: {len(vals)} | Nulos/vacíos: {nulos}")

        # Clasificar formatos
        format_counts: Counter[str] = Counter()
        ambiguous: list[str] = []
        invalid: list[str] = []

        for v in vals:
            fmt = classify_date(v)
            format_counts[fmt] += 1
            if _is_ambiguous_mdy(v):
                ambiguous.append(v)
            if _is_invalid_date(v):
                invalid.append(v)

        print(f"    Formatos detectados ({len(format_counts)}):")
        for fmt, cnt in format_counts.most_common():
            print(f"      • {fmt}: {cnt}")

        if ambiguous:
            print(f"    ⚠ Fechas ambiguas (posible MM/DD): {len(ambiguous)}")
            for a in ambiguous[:5]:
                print(f"        {a}")
            if len(ambiguous) > 5:
                print(f"        ... y {len(ambiguous) - 5} más")

        if invalid:
            print(f"    ✗ Fechas inválidas (no parseables): {len(invalid)}")
            for i in invalid:
                print(f"        {i}")


# ──────────────────────────────────────────────
# 4. Registro de prueba / basura
# ──────────────────────────────────────────────
def check_test_records(leads: pd.DataFrame) -> None:
    header("3. REGISTROS DE PRUEBA / BASURA")
    mask_name = leads["nombre_cliente"].str.strip().str.lower().str.contains(
        "prueba", na=False
    )
    mask_phone_short = leads["telefono"].apply(
        lambda x: len(re.sub(r"\D", "", str(x))) <= 6 if pd.notna(x) else False
    )
    mask_date_invalid = leads["fecha_registro"].apply(
        lambda x: _is_invalid_date(str(x)) if pd.notna(x) else False
    )

    # Registros que cumplen al menos 2 de los 3 criterios
    score = mask_name.astype(int) + mask_phone_short.astype(int) + mask_date_invalid.astype(int)
    junk = leads[score >= 2]

    print(f"    Registros detectados como prueba/basura: {len(junk)}")
    if not junk.empty:
        for _, row in junk.iterrows():
            flags = []
            if mask_name.loc[row.name]:
                flags.append(f'nombre="{row["nombre_cliente"].strip()}"')
            if mask_phone_short.loc[row.name]:
                flags.append(f'teléfono="{row["telefono"]}" ({len(re.sub(chr(92) + "D", "", str(row["telefono"])))} dígitos)')
            if mask_date_invalid.loc[row.name]:
                flags.append(f'fecha="{row["fecha_registro"]}" (inválida)')
            print(f"    → {row['lead_id']}: {', '.join(flags)}")


# ──────────────────────────────────────────────
# 5. Teléfonos: formatos inconsistentes
# ──────────────────────────────────────────────
def _digits_only(phone: str) -> str:
    return re.sub(r"\D", "", str(phone))


def check_phones(leads: pd.DataFrame) -> None:
    header("4. FORMATOS DE TELÉFONO")
    phones = leads["telefono"].dropna()
    nulos = int(leads["telefono"].isna().sum())
    print(f"    Valores presentes: {len(phones)} | Nulos/vacíos: {nulos}")

    has_plus57 = phones.str.contains(r"^\+?57\s*\d", regex=True, na=False).sum()
    has_parens = phones.str.contains(r"[()]", regex=True, na=False).sum()
    has_dash = phones.str.contains(r"-", na=False).sum()
    has_spaces = phones.str.contains(r"\d\s+\d", regex=True, na=False).sum()

    digits = phones.apply(_digits_only)
    len_counts = digits.str.len().value_counts().sort_index()

    print(f"    Con prefijo +57 o 57: {int(has_plus57)}")
    print(f"    Con paréntesis: {int(has_parens)}")
    print(f"    Con guiones: {int(has_dash)}")
    print(f"    Con espacios intermedios: {int(has_spaces)}")
    print(f"    Distribución por longitud de dígitos:")
    for length, count in len_counts.items():
        print(f"      {length} dígitos: {count}")


# ──────────────────────────────────────────────
# 6. Ciudad: variantes de texto libre
# ──────────────────────────────────────────────
def _normalize_city(city: str) -> str:
    """Normalización agresiva para agrupar variantes."""
    c = city.strip().lower()
    # Quitar tildes comunes
    for orig, repl in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")]:
        c = c.replace(orig, repl)
    # Quitar puntuación y sufijos comunes
    c = re.sub(r"[.,;:'\"-]", "", c)
    c = re.sub(r"\s*(d\.?c\.?|d\.? ?c)\s*$", "", c)  # "bogotá d.c."
    c = c.strip()
    # Abreviaturas conocidas
    abbrevs = {
        "b/quilla": "barranquilla",
        "bquilla": "barranquilla",
        "b/manga": "bucaramanga",
        "bmanga": "bucaramanga",
        "sta marta": "santa marta",
        "sta. marta": "santa marta",
        "cali valle": "cali",
        "mde": "medellin",
        "med": "medellin",
        "bga": "bucaramanga",
        "baq": "barranquilla",
        "ctg": "cartagena",
        "s marta": "santa marta",
    }
    return abbrevs.get(c, c)


def check_cities(leads: pd.DataFrame) -> None:
    header("5. CIUDAD — VARIANTES DE TEXTO LIBRE")
    cities = leads["ciudad"].dropna()
    nulos = int(leads["ciudad"].isna().sum())
    print(f"    Valores presentes: {len(cities)} | Nulos/vacíos: {nulos}")

    groups: dict[str, list[str]] = {}
    for v in cities.unique():
        key = _normalize_city(v)
        groups.setdefault(key, []).append(v)

    multi = {k: vs for k, vs in groups.items() if len(vs) > 1}
    if not multi:
        print("    Sin variantes detectadas.")
        return

    print(f"    Ciudades con múltiples variantes ortográficas: {len(multi)}")
    for key, variants in sorted(multi.items()):
        counts = {v: int((cities == v).sum()) for v in variants}
        detail = ", ".join(f'"{v}" ({c})' for v, c in sorted(counts.items(), key=lambda x: -x[1]))
        print(f'    • {key} → {len(variants)} variantes: {detail}')


# ──────────────────────────────────────────────
# 7. Typos en marca/modelo
# ──────────────────────────────────────────────
def check_brand_typos(leads: pd.DataFrame) -> None:
    header("6. MODELO_INTERES_TEXTO — TYPOS EN MARCA")
    modelos = leads["modelo_interes_texto"].dropna()
    nulos = int(leads["modelo_interes_texto"].isna().sum())
    print(f"    Valores presentes: {len(modelos)} | Nulos/vacíos: {nulos}")

    # Extraer la primera palabra como posible marca
    first_words = modelos.str.strip().str.split(r"\s+", n=1).str[0]
    unique_firsts = first_words.unique()

    typos_found: dict[str, list[tuple[str, int]]] = {}
    for word in unique_firsts:
        word_lower = word.lower().replace(".", "")
        for canon in MARCAS_CANONICAS:
            canon_lower = canon.lower().replace(".", "")
            if word_lower == canon_lower:
                break  # coincidencia exacta, no es typo
            ratio = fuzz.ratio(word_lower, canon_lower)
            if 70 <= ratio < 100 and len(word_lower) >= 3:
                count = int((first_words == word).sum())
                typos_found.setdefault(canon, []).append((word, count))
                break

    if not typos_found:
        print("    Sin typos detectados.")
        return

    total = sum(c for pairs in typos_found.values() for _, c in pairs)
    print(f"    Typos detectados: {total} filas")
    for canon, pairs in sorted(typos_found.items()):
        for typo, count in pairs:
            print(f'    • "{typo}" → probablemente "{canon}" ({count} ocurrencias)')


# ──────────────────────────────────────────────
# 8. Duplicados exactos
# ──────────────────────────────────────────────
def check_duplicates(leads: pd.DataFrame) -> None:
    header("7. LEAD_ID DUPLICADOS EXACTOS")
    dup_mask = leads.duplicated(keep=False)
    dup_rows = leads[dup_mask]
    dup_ids = dup_rows["lead_id"].unique()
    print(f"    Filas duplicadas (byte por byte): {len(dup_rows)}")
    print(f"    lead_id involucrados: {len(dup_ids)}")
    for lid in dup_ids:
        n = int((leads["lead_id"] == lid).sum())
        indices = leads.index[leads["lead_id"] == lid].tolist()
        print(f"    • {lid}: {n} apariciones (filas {indices})")


# ──────────────────────────────────────────────
# 9. Teléfonos compartidos entre leads
# ──────────────────────────────────────────────
def check_shared_phones(leads: pd.DataFrame) -> None:
    header("8. TELÉFONOS REPETIDOS ENTRE LEADS DISTINTOS")
    # Trabajar solo con leads únicos (dedup por lead_id) para no inflar
    # conteos por filas duplicadas byte-a-byte
    df = leads.drop_duplicates(subset=["lead_id"]).copy()
    df["_phone_norm"] = df["telefono"].apply(
        lambda x: _digits_only(x)[-10:] if pd.notna(x) else None
    )
    df = df.dropna(subset=["_phone_norm"])

    # Agrupar por teléfono normalizado
    phone_groups = df.groupby("_phone_norm").agg(
        n_leads=("lead_id", "nunique"),
        lead_ids=("lead_id", lambda s: list(s.unique())),
        empresas=("empresa_id", lambda s: list(s.unique())),
    )
    shared = phone_groups[phone_groups["n_leads"] > 1]

    print(f"    Teléfonos únicos (normalizados a 10 dígitos): {len(phone_groups)}")
    print(f"    Teléfonos que aparecen en >1 lead distinto: {len(shared)}")

    # Casos cross-empresa
    cross_empresa = shared[shared["empresas"].apply(lambda x: len(x) > 1)]
    print(f"    De esos, compartidos entre empresa_id distintas: {len(cross_empresa)}")

    if not cross_empresa.empty:
        print(f"\n    Detalle cross-empresa (primeros 10):")
        for phone, row in cross_empresa.head(10).iterrows():
            print(
                f"    • Tel …{phone[-4:]}: leads={row['lead_ids']}, "
                f"empresas={row['empresas']}"
            )


# ──────────────────────────────────────────────
# 10. Conversaciones huérfanas
# ──────────────────────────────────────────────
def check_orphan_conversations(leads: pd.DataFrame, conversaciones: list[dict]) -> None:
    header("9. CONVERSACIONES CON LEAD_ID INEXISTENTE")
    lead_ids = set(leads["lead_id"].unique())
    orphans = [c for c in conversaciones if c.get("lead_id") not in lead_ids]
    print(f"    Total conversaciones: {len(conversaciones)}")
    print(f"    Conversaciones huérfanas (lead_id no existe en leads.csv): {len(orphans)}")
    if orphans:
        print(f"    Detalle:")
        for c in orphans:
            print(f"    • {c['conversacion_id']} → lead_id={c['lead_id']}")


# ──────────────────────────────────────────────
# 11. Canal de conversación ≠ canal del lead
# ──────────────────────────────────────────────
def check_canal_mismatch(leads: pd.DataFrame, conversaciones: list[dict]) -> None:
    header("10. CANAL CONVERSACIÓN ≠ CANAL DEL LEAD (informativo)")
    lead_canal = dict(zip(leads["lead_id"], leads["canal"]))

    mismatches = []
    for c in conversaciones:
        lid = c.get("lead_id")
        if lid not in lead_canal:
            continue  # huérfanas, ya reportadas
        canal_lead = lead_canal[lid]
        canal_conv = c.get("canal")
        if pd.isna(canal_lead) or pd.isna(canal_conv):
            continue
        if canal_lead.strip().lower() != canal_conv.strip().lower():
            mismatches.append({
                "conversacion_id": c["conversacion_id"],
                "lead_id": lid,
                "canal_lead": canal_lead,
                "canal_conv": canal_conv,
            })

    print(f"    Conversaciones evaluadas: {len(conversaciones)}")
    print(f"    Discrepancias canal lead ≠ canal conversación: {len(mismatches)}")
    if mismatches:
        # Resumen por patrón
        patterns: Counter[tuple[str, str]] = Counter()
        for m in mismatches:
            patterns[(m["canal_lead"].strip().lower(), m["canal_conv"].strip().lower())] += 1
        print(f"    Patrones (canal_lead → canal_conv):")
        for (cl, cc), cnt in patterns.most_common():
            print(f"      • {cl} → {cc}: {cnt}")
    print(f"\n    ℹ Esto es esperado: el lead entra por un canal, el asesor contacta por WhatsApp.")


# ──────────────────────────────────────────────
# Resumen general de archivos
# ──────────────────────────────────────────────
def summary(
    leads: pd.DataFrame,
    conversaciones: list[dict],
    catalogo: pd.DataFrame,
    asesores: pd.DataFrame,
    historico: pd.DataFrame,
) -> None:
    header("RESUMEN DE ARCHIVOS CARGADOS")
    print(f"    leads.csv:             {leads.shape[0]:>6} filas × {leads.shape[1]} cols")
    print(f"    conversaciones.json:   {len(conversaciones):>6} conversaciones")
    print(f"    catalogo_motos.csv:    {catalogo.shape[0]:>6} filas × {catalogo.shape[1]} cols")
    print(f"    asesores.csv:          {asesores.shape[0]:>6} filas × {asesores.shape[1]} cols")
    print(f"    historico_cierres.csv: {historico.shape[0]:>6} filas × {historico.shape[1]} cols")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main() -> None:
    print(f"\n{'▓' * 72}")
    print("  PROFILING DE CALIDAD — leads-priorizacion")
    print(f"{'▓' * 72}")

    leads, conversaciones, catalogo, asesores, historico = load_all()
    summary(leads, conversaciones, catalogo, asesores, historico)

    check_capitalization(leads)
    check_dates(leads)
    check_test_records(leads)
    check_phones(leads)
    check_cities(leads)
    check_brand_typos(leads)
    check_duplicates(leads)
    check_shared_phones(leads)
    check_orphan_conversations(leads, conversaciones)
    check_canal_mismatch(leads, conversaciones)

    header("FIN DEL PROFILING")
    print("  Todos los hallazgos son de detección. No se modificó ningún dato.\n")


if __name__ == "__main__":
    main()
