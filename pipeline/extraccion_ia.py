"""
pipeline/extraccion_ia.py
─────────────────────────
Utiliza la API de DeepSeek con Batch Prompting y Pydantic para analizar
múltiples conversaciones en una sola llamada, optimizando costo y velocidad.
"""

import os
import json
import time
from typing import List, Optional
from pydantic import BaseModel, Field
from openai import OpenAI  # Usamos la librería compatible de OpenAI
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not API_KEY:
    raise RuntimeError("❌ ERROR: No se encontró DEEPSEEK_API_KEY en el archivo .env")

# Configuramos el cliente apuntando al endpoint oficial de DeepSeek
client = OpenAI(api_key=API_KEY, base_url="https://api.deepseek.com")

# ──────────────────────────────────────────────
# 1. Esquemas Estrictos (Pydantic)
# ──────────────────────────────────────────────
class LeadEnriquecidoSchema(BaseModel):
    lead_id: str = Field(description="El ID exacto del lead que se está analizando.")
    intencion_compra: str = Field(description="Clasificar en: Alta, Media, Baja o Solo cotización")
    forma_pago_declarada: str = Field(description="Clasificar en: Contado, Crédito o No informa")
    monto_cuota_inicial: Optional[float] = Field(description="Monto numérico mencionado como cuota inicial, o null")
    pidio_cita: bool = Field(description="True si solicitó explícitamente cita/visita, False de lo contrario")
    objeciones: List[str] = Field(description="Lista de objeciones (ej. precio, reporte datacrédito)")
    marcas_competencia: List[str] = Field(description="Otras marcas mencionadas")
    urgencia: str = Field(description="Clasificar en: Inmediata, Esta semana o Explorando")
    resumen_conversacion: str = Field(description="Breve resumen de 1 o 2 líneas")

class BatchResultados(BaseModel):
    resultados: List[LeadEnriquecidoSchema] = Field(description="Lista con el análisis de cada lead enviado.")

# ──────────────────────────────────────────────
# 2. Prompt y Lógica con DeepSeek
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """
Eres un analista comercial experto en el sector de motocicletas. Recibirás un lote de transcripciones de chats de WhatsApp.
Cada chat está claramente separado e identificado con un ID DE LEAD.
Tu tarea es analizar CADA chat de forma independiente y extraer la información requerida.
Debes responder estrictamente en formato JSON válido que cumpla con la estructura solicitada, devolviendo una lista bajo la clave "resultados".
"""

def extraer_lote_conversaciones(lote_conversaciones: list) -> list:
    """Envía un bloque de conversaciones a DeepSeek."""
    
    mega_prompt = "A continuación se presentan las conversaciones a analizar:\n\n"
    for conv in lote_conversaciones:
        mega_prompt += f"=== INICIO CHAT LEAD: {conv['lead_id']} ===\n"
        for msg in conv.get("mensajes", []):
            mega_prompt += f"[{msg.get('hora', '')}] {msg.get('emisor', '')}: {msg.get('texto', '')}\n"
        mega_prompt += f"=== FIN CHAT LEAD: {conv['lead_id']} ===\n\n"

    max_reintentos = 3
    for intento in range(max_reintentos):
        try:
            # Usamos el modelo principal de DeepSeek con Structured Outputs (json_object)
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": mega_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            contenido = response.choices[0].message.content
            datos = json.loads(contenido)
            
            if isinstance(datos, dict) and "resultados" in datos:
                return datos["resultados"]
            elif isinstance(datos, list):
                return datos
            return []

        except Exception as e:
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str or "503" in error_str:
                tiempo_espera = 5 * (intento + 1)
                print(f"    ⚠️ Servidor ocupado. Reintentando en {tiempo_espera}s... (Intento {intento+1}/{max_reintentos})")
                time.sleep(tiempo_espera)
            else:
                print(f"    ❌ Error procesando lote con DeepSeek: {e}")
                return []
                
    return []

def procesar_todas_las_conversaciones(conversaciones_list: list, tamano_lote: int = 5) -> list:
    """Procesa todas las conversaciones agrupándolas en lotes."""
    chats_validos = [c for c in conversaciones_list if c.get("mensajes")]
    total = len(chats_validos)
    
    print(f"🤖 Iniciando análisis con DeepSeek (Batch Size: {tamano_lote}) para {total} chats...")
    resultados_globales = []

    lotes = [chats_validos[i:i + tamano_lote] for i in range(0, total, tamano_lote)]
    total_lotes = len(lotes)

    for idx, lote in enumerate(lotes):
        print(f"  📦 Procesando Lote {idx+1}/{total_lotes} ({len(lote)} leads)...", end=" ", flush=True)
				
        resultados_lote = extraer_lote_conversaciones(lote)
        
        if resultados_lote:
            resultados_globales.extend(resultados_lote)
            print(f"✅ {len(resultados_lote)} extraídos.")
        else:
            print("⚠️ Falló.")

        if idx < total_lotes - 1:
            time.sleep(1) # Pausa ligera entre lotes

    print(f"🚀 [IA] Extracción con DeepSeek completada. {len(resultados_globales)} registros procesados.")
    return resultados_globales