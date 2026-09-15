"""
pipeline/ingesta.py
───────────────────
Módulo responsable de la carga inicial de datos crudos.
Lee los archivos CSV y JSON desde la carpeta data/raw/.
"""

import json
from pathlib import Path
import pandas as pd

# Definir la ruta base apuntando a data/raw
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"

def cargar_datos_crudos():
    """
    Carga los 5 archivos fuente y retorna una tupla con:
    (leads_df, conversaciones_list, catalogo_df, asesores_df, historico_df)
    """
    print("📥 [Ingesta] Cargando archivos fuente...")
    
    # 1. Leads
    leads_path = RAW_DIR / "leads.csv"
    leads = pd.read_csv(leads_path, dtype=str)
    
    # 2. Conversaciones (JSON)
    conv_path = RAW_DIR / "conversaciones.json"
    with open(conv_path, encoding="utf-8") as f:
        conversaciones = json.load(f)
        
    # 3. Catálogo de Motos
    catalogo_path = RAW_DIR / "catalogo_motos.csv"
    catalogo = pd.read_csv(catalogo_path, dtype=str)
    
    # 4. Asesores
    asesores_path = RAW_DIR / "asesores.csv"
    asesores = pd.read_csv(asesores_path, dtype=str)
    
    # 5. Histórico de Cierres
    historico_path = RAW_DIR / "historico_cierres.csv"
    historico = pd.read_csv(historico_path, dtype=str)
    
    print(f"✅ [Ingesta] OK: {len(leads)} leads crudos, {len(conversaciones)} conversaciones cargadas.")
    return leads, conversaciones, catalogo, asesores, historico

if __name__ == "__main__":
    cargar_datos_crudos()