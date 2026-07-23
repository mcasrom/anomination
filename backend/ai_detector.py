import os
import base64
import io

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def gemini_available():
    if not GEMINI_API_KEY:
        return False
    try:
        import google.generativeai as genai
        return True
    except ImportError:
        return False

def detect_document_with_ai(image_bytes: bytes, mime_type: str = "image/png"):
    if not gemini_available():
        return None

    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash-lite")

    prompt = (
        "Analiza esta imagen de un documento de identidad, factura o documento oficial. "
        "Identifica el tipo de documento y extrae los campos visibles. "
        "Devuelve SOLO JSON válido con esta estructura exacta:\n"
        "{\n"
        '  "document_type": "dni|nie|passport|driving_license|residence_card|health_card|padron|invoice|contract|other",\n'
        '  "document_name": "nombre descriptivo en español",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "fields": [\n'
        '    {"key": "nombre_campo", "label": "Nombre del campo", "value": "valor extraido", "sensitive": true/false}\n'
        "  ],\n"
        '  "sensitive_fields": ["lista de keys sensibles"],\n'
        '  "summary": "breve descripción"\n'
        "}\n"
        "Si es una factura: marca como sensibles importes, datos bancarios, direcciones completas, números de factura.\n"
        "Si es DNI/NIE/pasaporte: marca número de documento, dirección, fecha nacimiento, firma como sensibles."
    )

    try:
        response = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}
        ])
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        import json
        result = json.loads(text.strip())
        return result
    except Exception as e:
        return {"error": str(e), "document_type": None, "confidence": 0}


def suggest_redactions_with_ai(image_bytes: bytes, mime_type: str = "image/png"):
    if not gemini_available():
        return None

    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash-lite")

    prompt = (
        "Analiza esta imagen de un documento. Quiero anonimizar/redactar datos sensibles "
        "según el principio de minimización de datos (RGPD Art. 5).\n"
        "Devuelve SOLO JSON válido con esta estructura:\n"
        "{\n"
        '  "fields_to_redact": ["key1", "key2"],\n'
        '  "redaction_reasons": {"key1": "motivo en español"},\n'
        '  "preserved_fields": ["key3"],\n'
        '  "summary": "explicación breve"\n'
        "}\n"
        "Incluye solo los campos que realmente aparecen en el documento."
    )

    try:
        response = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}
        ])
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        import json
        return json.loads(text.strip())
    except Exception:
        return None
