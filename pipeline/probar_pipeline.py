# probar_pipeline.py
from pipeline.ingesta import cargar_datos_crudos
from pipeline.normalizacion import normalizar_leads
from pipeline.carga_supabase import cargar_leads_supabase
from pipeline.extraccion_ia import procesar_todas_las_conversaciones  # <--- 1. Importamos la IA

def test():
    # 1. Probar Ingesta
    leads_raw, conversaciones, catalogo, asesores, historico = cargar_datos_crudos()
    print(f"✅ Leads cargados: {len(leads_raw)}")
    print(f"✅ Conversaciones cargadas: {len(conversaciones)}")

    # 2. Probar Normalización
    leads_limpios = normalizar_leads(leads_raw, catalogo)
    print(f"✅ Leads tras normalización y limpieza de basura: {len(leads_limpios)}")

    # 3. Sincronizar y cargar en Supabase
    print("\n⏳ Sincronizando leads normalizados con Supabase...")
    resultado = cargar_leads_supabase(leads_limpios, tamano_lote=250)
    print(f"🚀 ¡Carga a la nube completada! Lotes enviados: {resultado.lotes_enviados}")

    # 4. PROBAR LA EXTRACCIÓN CON IA 🧠
    print("\n🧠 Iniciando prueba de Inteligencia Artificial...")
    
    # Tomamos solo los primeros 10 chats para hacer una prueba rápida de 1 solo lote
    conversaciones_prueba = conversaciones[:10] 
    
    resultados_ia = procesar_todas_las_conversaciones(conversaciones_prueba, tamano_lote=10)
    
    if resultados_ia:
        print(f"\n🎉 ¡Análisis exitoso! Se procesaron {len(resultados_ia)} conversaciones.")
        print("\n🔍 Ejemplo de cómo la IA entendió al primer cliente:")
        # Imprimimos el primer resultado formateado bonito
        import json
        print(json.dumps(resultados_ia[0], indent=2, ensure_ascii=False))
    else:
        print("\n⚠️ No se obtuvieron resultados de la IA.")

if __name__ == "__main__":
    test()