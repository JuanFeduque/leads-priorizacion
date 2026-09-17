"""
pipeline/probar_pipeline.py
───────────────────────────
Script de ejecución para validar y procesar el flujo completo del pipeline:
Ingesta -> Normalización -> Supabase -> Enriquecimiento IA (DeepSeek) -> Persistencia en Supabase.
"""

from pipeline.ingesta import cargar_datos_crudos
from pipeline.normalizacion import normalizar_leads
from pipeline.carga_supabase import cargar_leads_supabase, guardar_leads_enriquecidos_en_supabase
from pipeline.extraccion_ia import procesar_todas_las_conversaciones

def test():
    # 1. Probar Ingesta
    leads_raw, conversaciones, catalogo, asesores, historico = cargar_datos_crudos()
    print(f"✅ Leads cargados: {len(leads_raw)}")
    print(f"✅ Conversaciones cargadas: {len(conversaciones)}")

    # 2. Probar Normalización
    leads_limpios = normalizar_leads(leads_raw, catalogo)
    print(f"✅ Leads tras normalización y limpieza de basura: {len(leads_limpios)}")

    # 3. Sincronizar y cargar leads en Supabase
    print("\n⏳ Sincronizando leads normalizados con Supabase...")
    resultado = cargar_leads_supabase(leads_limpios, tamano_lote=250)
    print(f"🚀 ¡Carga de leads a la nube completada! Lotes enviados: {resultado.lotes_enviados}")

    # 4. Procesamiento masivo con Inteligencia Artificial (DeepSeek) del 100% de los chats
    print(f"\n🧠 Iniciando análisis masivo con DeepSeek para las {len(conversaciones)} conversaciones...")
    resultados_ia = procesar_todas_las_conversaciones(conversaciones, tamano_lote=20)

    # 5. Guardar el enriquecimiento de la IA en Supabase
    if resultados_ia:
        print("\n⏳ Sincronizando enriquecimiento de IA con Supabase...")
        guardar_leads_enriquecidos_en_supabase(resultados_ia)
        print("\n🎉 ¡Flujo de extremo a extremo completado con éxito!")
    else:
        print("\n⚠️ No se obtuvieron resultados de la IA para guardar.")

if __name__ == "__main__":
    test()