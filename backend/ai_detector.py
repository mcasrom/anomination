import os
import base64
import json
import urllib.request
import urllib.error

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

GROQ_MODEL = "llama-3.2-90b-vision-preview"
GEMINI_MODEL = "gemini-flash-lite-latest"

DETECT_PROMPT = (
    "Analiza esta imagen de un documento de identidad (DNI, NIE, pasaporte, carnet de conducir, "
    "tarjeta sanitaria, residencia, empadronamiento) o factura/documento oficial. "
    "Identifica el tipo de documento y las coordenadas de cada campo visible. "
    "Devuelve SOLO JSON válido con esta estructura EXACTA:\n"
    "{\n"
    '  "document_type": "dni|nie|passport|driving_license|residence_card|health_card|padron|invoice|contract|other",\n'
    '  "document_name": "nombre descriptivo en español",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "fields": [\n'
    '    {"key": "full_name", "label": "Nombre completo", "value": "texto visible", "sensitive": false, '
    '"box": {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 0.0}}\n'
    "  ],\n"
    '  "sensitive_fields": ["lista de keys marcadas como sensitive"],\n'
    '  "summary": "breve descripción"\n'
    "}\n"
    "IMPORTANTE: cada field DEBE incluir 'box' con coordenadas RELATIVAS (0-1) que correspondan "
    "a la posición real del campo en la imagen (x1,y1 esquina sup-izq, x2,y2 esquina inf-der).\n"
    "Marca como sensitive=True los campos que contengan datos personales excesivos según RGPD:\n"
    "- DNI/NIE/pasaporte: número de documento, dirección, fecha nacimiento, firma, sexo, nacionalidad, "
    "nombre de padres, lugar de nacimiento\n"
    "- Facturas: importes, datos bancarios, direcciones, números de factura\n"
    "- Contratos: datos personales no esenciales, firmas"
)

REDACT_PROMPT = (
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


def _parse_json_response(text: str) -> dict:
    t = text.strip()
    if t.startswith("```json"):
        t = t[7:]
    elif t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    return json.loads(t.strip())


# -- Groq provider --

def _groq_available():
    return bool(GROQ_API_KEY)


def _groq_chat_completion(image_bytes: bytes, prompt: str, mime_type: str) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    body = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
                ]
            }
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return _parse_json_response(data["choices"][0]["message"]["content"])


# -- Gemini provider (fallback) --

def _gemini_available():
    if not GEMINI_API_KEY:
        return False
    try:
        import google.generativeai as genai
        return True
    except ImportError:
        return False


def _gemini_chat_completion(image_bytes: bytes, prompt: str, mime_type: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    response = model.generate_content([
        prompt,
        {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}
    ])
    return _parse_json_response(response.text)


# -- Public API --

def ai_available():
    return _groq_available() or _gemini_available()


def detect_document_with_ai(image_bytes: bytes, mime_type: str = "image/png"):
    if _groq_available():
        try:
            return _groq_chat_completion(image_bytes, DETECT_PROMPT, mime_type)
        except Exception as e:
            fallback_err = f"Groq error: {e}"

    if _gemini_available():
        try:
            return _gemini_chat_completion(image_bytes, DETECT_PROMPT, mime_type)
        except Exception as e:
            return {"error": f"Gemini error: {e}", "document_type": None, "confidence": 0}

    if _groq_available():
        return {"error": fallback_err, "document_type": None, "confidence": 0}
    return None


def suggest_redactions_with_ai(image_bytes: bytes, mime_type: str = "image/png"):
    if _groq_available():
        try:
            return _groq_chat_completion(image_bytes, REDACT_PROMPT, mime_type)
        except Exception:
            pass

    if _gemini_available():
        try:
            return _gemini_chat_completion(image_bytes, REDACT_PROMPT, mime_type)
        except Exception:
            pass

    return None
