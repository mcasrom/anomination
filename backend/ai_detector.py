import os
import base64
import json
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

GROQ_VISION_MODEL = "llama-3.2-90b-vision-preview"
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-3-flash-preview"]

DETECT_VISION_PROMPT = (
    "Analiza esta imagen de un documento de identidad (DNI, NIE, pasaporte, carnet de conducir, "
    "tarjeta sanitaria, residencia, empadronamiento). "
    "Identifica todos los campos visibles y sus coordenadas exactas.\n"
    "IMPORTANTE: coordenadas RELATIVAS (0.0 a 1.0) respecto al ancho y alto de la imagen. "
    "Cada caja debe rodear EXACTAMENTE el texto de ese campo.\n"
    "Marca como sensitive=True los campos con datos personales que NO deberían compartirse:\n"
    "- Numeros de documento (DNI, NIE, pasaporte, licencia, tarjeta sanitaria)\n"
    "- Direccion completa, Domicilio\n"
    "- Fecha de nacimiento, Lugar de nacimiento\n"
    "- Firma, Fotografia\n"
    "- Nombre de padres\n"
    "- Datos bancarios, importes (en facturas)\n"
    "Marca como sensitive=False los campos necesarios para identificación basica como nombre, "
    "tipo de documento, fecha de validez, nacionalidad (si no es sensible).\n"
    "Devuelve SOLO JSON valido con esta estructura EXACTA:\n"
    "{\n"
    '  "document_type": "dni|nie|passport|driving_license|residence_card|health_card|padron|invoice|contract|other",\n'
    '  "document_name": "nombre descriptivo en español",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "fields": [\n'
    '    {"key": "full_name", "label": "Nombre completo", "value": "texto visible", "sensitive": false, '
    '"box": {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 0.0}}\n'
    "  ],\n"
    '  "summary": "breve descripción"\n'
    "}\n"
    "Posibles keys: full_name, dni_number, nie_number, card_number, passport_number, license_number, "
    "health_number, support_number, address, dob, gender, nationality, expiration_date, issue_date, "
    "signature, father_name, mother_name, pob, height, eye_color, issuing_authority, categories, "
    "previous_address, photo, document_type."
)

TEXT_DETECT_PROMPT = (
    "Analiza el siguiente texto OCR extraído de un documento de identidad. "
    "Identifica el tipo de documento y qué campos contiene. "
    "Devuelve SOLO JSON válido con esta estructura:\n"
    "{\n"
    '  "document_type": "dni|nie|passport|driving_license|residence_card|health_card|padron|invoice|contract|other",\n'
    '  "document_name": "nombre descriptivo en español",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "fields": [\n'
    '    {"key": "full_name", "label": "Nombre completo", "value": "texto extraído", "sensitive": true}\n'
    "  ],\n"
    '  "summary": "breve descripción"\n'
    "}\n"
    "Texto OCR:\n"
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


def _groq_chat_completion(prompt: str, image_bytes: bytes = None, mime_type: str = "image/png",
                          ocr_text: str = None) -> dict:
    if image_bytes is not None:
        model = GROQ_VISION_MODEL
        b64 = base64.b64encode(image_bytes).decode()
        msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
            ]
        }
    elif ocr_text is not None:
        model = GROQ_TEXT_MODEL
        msg = {"role": "user", "content": prompt + "\n" + ocr_text}
    else:
        return {"error": "No input provided", "document_type": None, "confidence": 0}

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [msg],
            "temperature": 0.2,
            "max_tokens": 2048,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
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


def _gemini_chat_completion(image_bytes: bytes, prompt: str, mime_type: str, model_name: str = None) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    if model_name is None:
        model_name = GEMINI_MODEL
    model = genai.GenerativeModel(
        model_name,
        generation_config={"response_mime_type": "application/json"},
        safety_settings={
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
        }
    )
    response = model.generate_content([
        {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}},
        prompt,
    ])
    if not response.candidates:
        if response.prompt_feedback:
            raise ValueError(f"Bloqueado por safety filters: {response.prompt_feedback}")
        raise ValueError("No candidates returned")
    text = response.candidates[0].content.parts[0].text
    return _parse_json_response(text)


def _gemini_chat_with_fallback(image_bytes: bytes, prompt: str, mime_type: str) -> dict:
    models_to_try = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]
    last_error = ""
    for mn in models_to_try:
        try:
            return _gemini_chat_completion(image_bytes, prompt, mime_type, model_name=mn)
        except Exception as e:
            err = str(e)
            last_error = err
            if "quota" in err.lower() or "resource_exhausted" in err.lower():
                continue
            raise
    raise ValueError(f"Todos los modelos agotados. {last_error}")


# -- Public API --

def ai_available():
    return _groq_available() or _gemini_available()


def detect_document_with_ai(image_bytes: bytes, mime_type: str = "image/png",
                             ocr_text: str = None):
    last_error = ""
    if _gemini_available():
        try:
            return _gemini_chat_with_fallback(image_bytes, DETECT_VISION_PROMPT, mime_type)
        except Exception as e:
            last_error = str(e)
            if ocr_text and _groq_available():
                return _groq_chat_completion(TEXT_DETECT_PROMPT, ocr_text=ocr_text)

    if _groq_available():
        try:
            return _groq_chat_completion(DETECT_VISION_PROMPT, image_bytes=image_bytes, mime_type=mime_type)
        except Exception:
            if ocr_text:
                return _groq_chat_completion(TEXT_DETECT_PROMPT, ocr_text=ocr_text)

    return {"error": last_error or "No hay proveedor de IA disponible (sin API key configurada)."}


def suggest_redactions_with_ai(image_bytes: bytes, mime_type: str = "image/png",
                                ocr_text: str = None):
    if _groq_available():
        try:
            return _groq_chat_completion(REDACT_PROMPT, image_bytes=image_bytes, mime_type=mime_type)
        except Exception:
            if ocr_text:
                try:
                    return _groq_chat_completion(REDACT_PROMPT, ocr_text=ocr_text)
                except Exception:
                    pass

    if _gemini_available():
        try:
            return _gemini_chat_with_fallback(image_bytes, REDACT_PROMPT, mime_type)
        except Exception:
            pass

    return None
