"""
pipeline/probar_pipeline.py
───────────────────────────
Script de ejecución para validar y procesar el flujo completo del pipeline:
Ingesta -> Normalización -> Supabase -> Enriquecimiento IA (DeepSeek) -> Persistencia en Supabase.
"""

from pipeline.ingesta import cargar_datos_crudos
import pandas as pd
from pipeline.normalizacion import normalizar_leads
from pipeline.deduplicacion import deduplicar_leads
from pipeline.carga_supabase import cargar_leads_supabase, cargar_registros_supabase, guardar_leads_enriquecidos_en_supabase
from pipeline.extraccion_ia import procesar_todas_las_conversaciones
from pipeline.scoring import calcular_scores


def _maestros(leads, catalogo, asesores):
    """Prepara dependencias de FK desde los archivos fuente."""
    empresas = [{"empresa_id": e, "nombre": e} for e in sorted(leads["empresa_id"].dropna().unique())]
    puntos = (leads[["punto_venta_id", "empresa_id", "ciudad"]].dropna(subset=["punto_venta_id"])
              .drop_duplicates("punto_venta_id").rename(columns={"ciudad": "nombre"}).to_dict("records"))
    asesores_limpios = asesores.copy()
    asesores_limpios["activo"] = asesores_limpios["activo"].astype(str).str.casefold().isin({"si", "sí", "true", "1"})
    motos = catalogo.assign(puntos_venta_disponibles=lambda d: d["puntos_venta_disponibles"].fillna("").str.split("|"))
    return empresas, puntos, asesores_limpios.to_dict("records"), motos.to_dict("records")


def _conversaciones_pendientes(conversaciones: list, cliente) -> list:
    """Devuelve solo chats cuyo lead consolidado aún no tiene enriquecimiento.

    Las conversaciones llegan con IDs crudos; la base conserva el UUID y el
    arreglo ``lead_id_original``. Se resuelven ambos para no pagar IA dos veces
    por un mismo lead consolidado.
    """
    leads_db = cliente.table("lead").select("lead_id,lead_id_original").limit(5000).execute().data or []
    uuid_por_original = {
        str(identificador): lead["lead_id"]
        for lead in leads_db
        for identificador in (lead.get("lead_id_original") or [])
    }
    enriquecidos = cliente.table("lead_enriquecido").select("lead_id").limit(5000).execute().data or []
    ya_procesados = {fila["lead_id"] for fila in enriquecidos if fila.get("lead_id")}
    pendientes, omitidas = [], 0
    vistos: set[str] = set()
    for conversacion in conversaciones:
        uuid = uuid_por_original.get(str(conversacion.get("lead_id", "")))
        if not uuid or uuid in ya_procesados or uuid in vistos:
            omitidas += 1
            continue
        pendientes.append(conversacion)
        vistos.add(uuid)
    print(f"[IA] Pendientes: {len(pendientes)}; omitidas ya enriquecidas/sin lead: {omitidas}.")
    return pendientes

def test():
    # 1. Probar Ingesta
    leads_raw, conversaciones, catalogo, asesores, historico = cargar_datos_crudos()
    print(f"✅ Leads cargados: {len(leads_raw)}")
    print(f"✅ Conversaciones cargadas: {len(conversaciones)}")

    # 2. Probar Normalización
    leads_limpios = normalizar_leads(leads_raw, catalogo)
    print(f"✅ Leads tras normalización y limpieza de basura: {len(leads_limpios)}")

    # 3. Consolidar duplicados y cargar dependencias de claves foráneas.
    leads_consolidados = deduplicar_leads(leads_limpios)
    empresas, puntos, asesores_registros, motos = _maestros(leads_consolidados, catalogo, asesores)
    cargar_registros_supabase("empresa", empresas, conflicto="empresa_id")
    cargar_registros_supabase("punto_venta", puntos, conflicto="punto_venta_id")
    cargar_registros_supabase("asesor", asesores_registros, conflicto="asesor_id")
    cargar_registros_supabase("moto_catalogo", motos, conflicto="sku")

    # 4. Sincronizar leads consolidados.
    print("\n⏳ Sincronizando leads normalizados con Supabase...")
    resultado = cargar_leads_supabase(leads_consolidados, tamano_lote=250)
    print(f"🚀 ¡Carga de leads a la nube completada! Lotes enviados: {resultado.lotes_enviados}")

    # 5. Procesamiento incremental: solo conversaciones sin enriquecimiento.
    from pipeline.carga_supabase import crear_cliente_desde_entorno
    cliente = crear_cliente_desde_entorno()
    conversaciones_pendientes = _conversaciones_pendientes(conversaciones, cliente)
    print(f"\n🧠 Iniciando análisis DeepSeek para {len(conversaciones_pendientes)} conversaciones pendientes...")
    resultados_ia = procesar_todas_las_conversaciones(conversaciones_pendientes, tamano_lote=20)

    # 6. Guardar el enriquecimiento y score explicable.
    if resultados_ia:
        print("\n⏳ Sincronizando enriquecimiento de IA con Supabase...")
        guardar_leads_enriquecidos_en_supabase(resultados_ia)
        # La función de IA emite IDs crudos; para el score se recuperan los UUIDs
        # persistidos por el mismo mecanismo que usa el cargador enriquecido.
        enriquecidos = pd.DataFrame(cliente.table("lead_enriquecido").select("*").limit(2000).execute().data or [])
        leads_db = pd.DataFrame(cliente.table("lead").select("lead_id,fecha_registro,fecha_primer_contacto").limit(2000).execute().data or [])
        scores = calcular_scores(leads_db, enriquecidos)
        cargar_registros_supabase("lead_score", scores.to_dict("records"), conflicto="lead_id")
        print("\n🎉 ¡Flujo de extremo a extremo completado con éxito!")
    else:
        print("\nℹ️ No hay conversaciones nuevas que enriquecer.")

if __name__ == "__main__":
    test()
