"""
pipeline/extraccion_ia.py
─────────────────────────
Procesa las conversaciones en formato JSON, une los chats por lead y utiliza 
Google Gemini (Capa Gratuita de AI Studio) con Structured Outputs (Pydantic) 
para extraer los datos comerciales requeridos.
"""

import os
import json
from typing import List, Optional
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Cargar variables de entorno (para la API Key de Google)
load_dotenv()

# Inicializar cliente de Google GenAI (requiere GEMINI_API_KEY en el .env)
# Puedes obtenerla gratis en aistudio.google.com
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ──────────────────────────────────────────────
# 1. Definición del Esquema Estricto (Pydantic)
# ──────────────────────────────────────────────
class LeadEnriquecidoSchema(BaseModel):
    intencion_compra: str = Field(description="Clasificar en: Alta, Media, Baja o Solo cotización")
    forma_pago_declarada: str = Field(description="Clasificar en: Contado, Crédito o No informa")
    monto_cuota_inicial: Optional[float] = Field(description="Monto numérico mencionado como cuota inicial, o null si no aplica")
    pidio_cita: bool = Field(description="True si el cliente solicitó explícitamente una cita o visita, False de lo contrario")
    objeciones: List[str] = Field(description="Lista de objeciones principales del cliente (ej. precio alto, falta de financiación)")
    marcas_competencia: List[str] = Field(description="Otras marcas de motos mencionadas por el cliente")
    urgencia: str = Field(description="Clasificar en: Inmediata, Esta semana o Explorando")
    resumen_conversacion: str = Field(description="Breve resumen de 1 o 2 líneas de la negociación")


# ──────────────────────────────────────────────
# 2. Prompt del Sistema y Lógica de Extracción
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """
Eres un analista comercial experto en el sector de venta de motocicletas en Colombia. 
Tu tarea es analizar transcripciones de chats de WhatsApp entre clientes potenciales (leads) 
y asesores de una comercializadora multimarca. 

Extrae estrictamente la información solicitada en el formato JSON requerido. 
No inventes datos que no estén explícitamente mencionados o implícitos en la conversación.
"""

def extraer_info_conversacion(mensajes_chat: list) -> Optional[dict]:
    """Envía la transcripción de una conversación al modelo gratuito de Gemini."""
    
    # Formatear los mensajes del chat en un texto legible para la IA
    historial_texto = ""
    for msg in mensajes_chat:
        emisor = msg.get("emisor", "desconocido")
        hora = msg.get("hora", "")
        texto = msg.get("texto", "")
        historial_texto += f"[{hora}] {emisor}: {texto}\n"

    user_prompt = f"Analiza la siguiente conversación de WhatsApp y extrae los datos:\n\n{historial_texto}"

    try:
        # Usamos gemini-1.5-flash (rápido, inteligente y totalmente gratis en su capa standard)
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                # Forzar salida en formato JSON estructurado usando el esquema de Pydantic
                response_mime_type="application/json",
                response_schema=LeadEnriquecidoSchema,
                temperature=0.1, # Baja temperatura para que sea determinista y objetivo
            ),
        )
        
        # El response.text ya viene validado y formateado como JSON puro según el esquema Pydantic
        datos_extraidos = json.loads(response.text)
        return datos_extraidos

    except Exception as e:
        print(f"❌ Error procesando conversación con Gemini: {e}")
        return None


def procesar_todas_las_conversaciones(conversaciones_list: list, leads_df) -> list:
    """Recorre las conversaciones asociándolas a los leads consolidados."""
    print("🤖 [IA Gratuita - Gemini] Iniciando extracción de conversaciones...")
    resultados = []

    # Para pruebas rápidas o control de costos/tiempo, puedes limitar el bucle (ej. [:10])
    for idx, conv in enumerate(conversaciones_list):
        lead_id = conv.get("lead_id")
        mensajes = conv.get("mensajes", [])

        if not mensajes:
            continue

        print(f"   Procesando conversación {idx+1}/{len(conversaciones_list)} (Lead: {lead_id})...")
        
        # Llamada a Gemini
        info_ia = extraer_info_conversacion(mensajes)
        
        if info_ia:
            info_ia["lead_id"] = lead_id
            resultados.append(info_ia)

    print(f"✅ [IA] Extracción completada. {len(resultados)} conversaciones procesadas con éxito.")
    return resultados