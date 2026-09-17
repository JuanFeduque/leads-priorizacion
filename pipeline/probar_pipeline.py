# probar_pipeline.py
from pipeline.ingesta import cargar_datos_crudos
from pipeline.normalizacion import normalizar_leads
from pipeline.carga_supabase import cargar_leads_supabase  # <--- 1. Importamos tu cargador


def test():
    # 1. Probar Ingesta
    leads_raw, conversaciones, catalogo, asesores, historico = cargar_datos_crudos()
    print(f"✅ Leads cargados: {len(leads_raw)}")
    print(f"✅ Catálogo cargado: {len(catalogo)} referencias")

    # 2. Probar Normalización
    leads_limpios = normalizar_leads(leads_raw, catalogo)
    print(f"✅ Leads tras normalización y limpieza de basura: {len(leads_limpios)}")
    
    # Muestra las primeras filas para confirmar que el teléfono quedó a 10 dígitos y la ciudad limpia
    print(leads_limpios[["telefono_normalizado", "ciudad_normalizada", "marca_detectada"]].head(5))

    # 3. Sincronizar y cargar en Supabase 🚀
    print("\n⏳ Sincronizando leads normalizados con Supabase...")
    resultado = cargar_leads_supabase(leads_limpios, tamano_lote=250)
    print(f"🚀 ¡Carga a la nube completada con éxito!")
    print(f"   - Registros preparados: {resultado.registros_preparados}")
    print(f"   - Lotes enviados: {resultado.lotes_enviados}")

if __name__ == "__main__":
    test()