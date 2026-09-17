"""Dashboard de priorización de leads.

Ejecución local desde la raíz del proyecto:
    streamlit run dashboard/app.py

Configure SUPABASE_URL y SUPABASE_ANON_KEY en .env (o en .streamlit/secrets.toml).
La clave de servicio es exclusiva del ETL y no debe exponerse en este dashboard.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client


RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ_PROYECTO / ".env")

st.set_page_config(page_title="Priorización de leads", page_icon="🏍️", layout="wide")


def _secreto(nombre: str) -> str | None:
    """Obtiene una configuración desde entorno o Streamlit Secrets de forma segura."""
    valor_env = os.getenv(nombre)
    if valor_env:
        return valor_env
    
    try:
        return st.secrets.get(nombre, None)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner="Cargando leads desde Supabase...")
def cargar_leads(url: str, api_key: str) -> list[dict[str, Any]]:
    """Lee leads y su enriquecimiento IA mediante la relación de PostgREST."""
    cliente = create_client(url, api_key)
    respuesta = (
        cliente.table("lead")
        .select(
            "lead_id,nombre_cliente,telefono_normalizado,telefono_original,"
            "modelo_interes_texto,empresa_id,estado_gestion,fecha_registro,fecha_primer_contacto,canal,"
            "lead_enriquecido("
            "intencion_compra,pidio_cita,objeciones,resumen_conversacion,"
            "forma_pago_declarada,monto_cuota_inicial,urgencia)"
        )
        .execute()
    )
    return respuesta.data or []


def _texto_lista(valor: Any) -> str:
    if not valor:
        return "—"
    if isinstance(valor, (list, tuple, set)):
        return ", ".join(str(item) for item in valor) or "—"
    return str(valor)


def _a_booleano(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().casefold() in {"true", "1", "sí", "si"}


def _tiene_valor(valor: Any) -> bool:
    """Distingue un dato declarado de nulos, NaN y textos de ausencia."""
    if valor is None or valor is pd.NA or valor is pd.NaT:
        return False
    if isinstance(valor, float) and pd.isna(valor):
        return False
    return str(valor).strip().casefold() not in {"", "nan", "none", "null", "n/a", "na", "no informa"}


def _puntuar_lead(fila: pd.Series) -> tuple[int, str]:
    """Calcula score comercial (0-100) y temperatura según las reglas del reto."""
    intencion = str(fila.get("Intención", "")).strip().casefold()
    puntos_intencion = {"alta": 40, "media": 20}.get(intencion, 0)
    puntos_cita = 25 if _a_booleano(fila.get("Pidió cita")) else 0
    pago_declarado = _tiene_valor(fila.get("Monto cuota inicial")) or _tiene_valor(fila.get("Forma de pago"))
    puntos_pago = 20 if pago_declarado else 0

    registro = pd.to_datetime(fila.get("Fecha de registro"), errors="coerce", utc=True)
    primer_contacto = pd.to_datetime(fila.get("Primer contacto"), errors="coerce", utc=True)
    contacto_rapido = (
        pd.notna(registro)
        and pd.notna(primer_contacto)
        and pd.Timedelta(0) <= primer_contacto - registro <= pd.Timedelta(hours=24)
    )
    puntos_velocidad = 15 if contacto_rapido else 0

    score = puntos_intencion + puntos_cita + puntos_pago + puntos_velocidad
    if score >= 75:
        temperatura = "🔥 Caliente"
    elif score >= 40:
        temperatura = "⚡ Tibio"
    else:
        temperatura = "❄️ Frío"
    return score, temperatura


def preparar_tabla(filas: list[dict[str, Any]]) -> pd.DataFrame:
    """Aplana la relación 1:1 para visualizarla cómodamente con Pandas."""
    resultado: list[dict[str, Any]] = []
    for lead in filas:
        enriquecido = lead.get("lead_enriquecido") or {}
        # Según la versión de PostgREST, la relación 1:1 puede llegar como lista.
        if isinstance(enriquecido, list):
            enriquecido = enriquecido[0] if enriquecido else {}
        resultado.append(
            {
                "lead_id": lead.get("lead_id"),
                "Empresa": lead.get("empresa_id") or "Sin empresa",
                "Estado de gestión": lead.get("estado_gestion") or "Sin estado",
                "Nombre": lead.get("nombre_cliente") or "Sin nombre",
                "Teléfono": lead.get("telefono_normalizado") or lead.get("telefono_original") or "—",
                "Modelo de interés": lead.get("modelo_interes_texto") or "—",
                "Intención": enriquecido.get("intencion_compra") or "Sin analizar",
                "Pidió cita": _a_booleano(enriquecido.get("pidio_cita")),
                "Forma de pago": enriquecido.get("forma_pago_declarada"),
                "Monto cuota inicial": enriquecido.get("monto_cuota_inicial"),
                "Objeciones": _texto_lista(enriquecido.get("objeciones")),
                "Resumen IA": enriquecido.get("resumen_conversacion") or "Sin conversación analizada",
                "Fecha de registro": lead.get("fecha_registro"),
                "Primer contacto": lead.get("fecha_primer_contacto"),
                "Canal": lead.get("canal") or "—",
            }
        )
    tabla = pd.DataFrame(resultado)
    if not tabla.empty:
        tabla[["Score", "Temperatura"]] = tabla.apply(
            lambda fila: pd.Series(_puntuar_lead(fila)), axis=1
        )
    return tabla


def main() -> None:
    st.title("🏍️ Priorización de leads")
    st.caption("Seguimiento comercial con señales extraídas de las conversaciones por IA.")

    url = _secreto("SUPABASE_URL")
    api_key = _secreto("SUPABASE_ANON_KEY")
    if not url or not api_key:
        st.error("Faltan SUPABASE_URL y SUPABASE_ANON_KEY en .env o Streamlit Secrets.")
        st.info("Ejecuta: streamlit run dashboard/app.py")
        st.stop()

    try:
        datos = preparar_tabla(cargar_leads(url, api_key))
    except Exception as exc:
        st.error("No fue posible cargar los leads desde Supabase.")
        st.exception(exc)
        st.stop()

    if datos.empty:
        st.info("No hay leads disponibles para los permisos de esta sesión.")
        return

    with st.sidebar:
        st.header("Filtros")
        empresas = sorted(datos["Empresa"].dropna().unique().tolist())
        estados = sorted(datos["Estado de gestión"].dropna().unique().tolist())
        empresa = st.selectbox("Empresa / comercializadora", ["Todas", *empresas])
        estado = st.selectbox("Estado de gestión", ["Todos", *estados])
        if st.button("Actualizar datos", use_container_width=True):
            cargar_leads.clear()
            st.rerun()

    filtrados = datos.copy()
    if empresa != "Todas":
        filtrados = filtrados[filtrados["Empresa"] == empresa]
    if estado != "Todos":
        filtrados = filtrados[filtrados["Estado de gestión"] == estado]

    total = len(filtrados)
    altas = int((filtrados["Intención"] == "Alta").sum())
    citas = int(filtrados["Pidió cita"].sum())
    metrica_1, metrica_2, metrica_3 = st.columns(3)
    metrica_1.metric("Total de leads", total)
    metrica_2.metric("Intención alta", altas)
    metrica_3.metric("Citas agendadas", citas)

    filtrados = filtrados.sort_values(["Score", "Fecha de registro"], ascending=[False, False])
    vista = filtrados.drop(
        columns=["lead_id", "Forma de pago", "Monto cuota inicial", "Primer contacto"], errors="ignore"
    )

    st.subheader("Leads priorizados")
    st.caption(f"Mostrando {len(vista)} leads según los filtros seleccionados.")
    st.dataframe(
        vista,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Pidió cita": st.column_config.CheckboxColumn("Pidió cita"),
            "Score": st.column_config.NumberColumn("Score", format="%d / 100"),
            "Resumen IA": st.column_config.TextColumn("Resumen IA", width="large"),
            "Objeciones": st.column_config.TextColumn("Objeciones", width="medium"),
        },
    )

    with st.expander("Ejecución local"):
        st.code("streamlit run dashboard/app.py", language="bash")


if __name__ == "__main__":
    main()
