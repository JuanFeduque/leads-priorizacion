"""
pipeline/normalizacion.py
─────────────────────────
Limpia y estandariza los datos crudos (teléfonos, fechas, ciudades, marcas)
y descarta los registros identificados como basura o pruebas.
"""

import re
import pandas as pd
from rapidfuzz import process, fuzz

def _limpiar_telefono(telefono: str) -> str:
    """Extrae los últimos 10 dígitos del teléfono, ignorando prefijos o símbolos."""
    if pd.isna(telefono):
        return None
    digitos = re.sub(r"\D", "", str(telefono))
    return digitos[-10:] if len(digitos) >= 10 else None

def _normalizar_ciudad(ciudad: str) -> str:
    """Estandariza nombres de ciudades usando reglas manuales detectadas."""
    if pd.isna(ciudad):
        return None
    c = ciudad.strip().lower()
    reemplazos = [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")]
    for orig, repl in reemplazos:
        c = c.replace(orig, repl)
    
    c = re.sub(r"[\.,;]", "", c)
    c = re.sub(r"\s*(d c|dc)$", "", c).strip()
    
    abrevs = {
        "b/quilla": "barranquilla", "bquilla": "barranquilla", "baq": "barranquilla",
        "b/manga": "bucaramanga", "bmanga": "bucaramanga", "bga": "bucaramanga",
        "sta marta": "santa marta", "s marta": "santa marta",
        "cali valle": "cali", "mde": "medellin", "med": "medellin", "ctg": "cartagena"
    }
    return abrevs.get(c, c).upper()

def normalizar_leads(leads_raw: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    """Aplica todas las transformaciones de limpieza al DataFrame de leads."""
    print("🧹 [Normalización] Iniciando limpieza de leads...")
    df = leads_raw.copy()
    
    # 1. Filtrar registros de prueba o basura explícitos
    mask_prueba = df["nombre_cliente"].str.lower().str.contains("prueba", na=False)
    df = df[~mask_prueba].copy()
    
    # 2. Normalizar Teléfonos
    df["telefono_normalizado"] = df["telefono"].apply(_limpiar_telefono)
    # Descartar leads sin un teléfono válido de 10 dígitos
    df = df.dropna(subset=["telefono_normalizado"])
    
    # 3. Normalizar Ciudades
    df["ciudad_normalizada"] = df["ciudad"].apply(_normalizar_ciudad)
    
    # 4. Normalizar Fechas a ISO
    # Pandas `to_datetime` con `mixed` maneja las inconsistencias detectadas
    df["fecha_registro"] = pd.to_datetime(df["fecha_registro"], format="mixed", dayfirst=True, errors="coerce")
    df = df.dropna(subset=["fecha_registro"]) # Descartar fechas inválidas absolutas
    
    if "fecha_primer_contacto" in df.columns:
        df["fecha_primer_contacto"] = pd.to_datetime(df["fecha_primer_contacto"], format="mixed", dayfirst=True, errors="coerce")
    
    # 5. Fuzzy Matching para el Modelo de Interés (Typos)
    # Extraemos las marcas únicas del catálogo oficial
    marcas_oficiales = catalogo["marca"].str.upper().unique().tolist()
    
    def _mapear_marca(texto_interes):
        if pd.isna(texto_interes):
            return None
        primera_palabra = str(texto_interes).split()[0].upper()
        # Busca el mejor match; si el score es mayor a 75, lo asume como typo válido
        match = process.extractOne(primera_palabra, marcas_oficiales, scorer=fuzz.ratio)
        if match and match[1] >= 75:
            return match[0] # Retorna la marca oficial corregida
        return None

    df["marca_detectada"] = df["modelo_interes_texto"].apply(_mapear_marca)
    
    print(f"✅ [Normalización] Finalizada. Leads útiles restantes: {len(df)}")
    return df