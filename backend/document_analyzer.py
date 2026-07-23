import re
import io
import os
import json
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import pytesseract
from typing import Optional, Tuple, List, Dict

from rgpd_rules import DOCUMENT_TYPES, DocumentType


_TEMPLATES_DIR = os.path.dirname(__file__)
_TEMPLATES_PATH = os.path.join(_TEMPLATES_DIR, "field_templates.json")

_field_templates_cache = None

def load_field_templates() -> Dict[str, Dict[str, list]]:
    global _field_templates_cache
    if _field_templates_cache is not None:
        return _field_templates_cache
    if os.path.exists(_TEMPLATES_PATH):
        with open(_TEMPLATES_PATH, "r", encoding="utf-8") as f:
            _field_templates_cache = json.load(f)
    else:
        _field_templates_cache = {}
    return _field_templates_cache


def get_field_boxes_for_type(doc_type_code: str) -> Dict[str, tuple]:
    templates = load_field_templates()
    doc_template = templates.get(doc_type_code, {})
    raw = doc_template.get("fields", {})
    result = {}
    for key, coords in raw.items():
        if isinstance(coords, list) and len(coords) == 4:
            result[key] = tuple(coords)
    return result


FIELD_BOXES = {}
_templates = load_field_templates()
for _doc_code, _doc_data in _templates.items():
    for _key, _coords in _doc_data.get("fields", {}).items():
        if isinstance(_coords, list) and len(_coords) == 4:
            if _key not in FIELD_BOXES:
                FIELD_BOXES[_key] = tuple(_coords)


# ============================================================
# CONTENT-BASED FIELD DETECTION (OCR + regex)
# ============================================================
# En lugar de adivinar posiciones con templates, detectamos
# los campos por su contenido: ejecutamos OCR con bounding boxes
# y buscamos patrones (DNI, fecha, etc.) para redactar donde
# aparezcan realmente.

FIELD_LABELS = {
    "dni_number": [
        r'DNI', r'DOCUMENTO', r'IDENTIDAD', r'ID\s*[Nn][úu]',
    ],
    "nie_number": [
        r'NIE', r'EXTRANJERO',
    ],
    "passport_number": [
        r'PASAPORTE', r'PASSPORT', r'N[úu]mero\s*Pasaporte',
    ],
    "license_number": [
        r'PERMISO', r'CONDUCIR', r'LICENCIA', r'LICENSE',
    ],
    "health_number": [
        r'SANITARIA', r'SEGURIDAD\s*SOCIAL', r'SNS', r'AFILIACI[OÓ]N',
    ],
    "card_number": [
        r'SOPORTE', r'TARJETA', r'RESIDENCIA',
    ],
    "dob": [
        r'NACIMIENTO', r'BIRTH', r'F[EÉ]\.?\s*NAC',
    ],
    "address": [
        r'DOMICILIO', r'DIRECCI[OÓ]N', r'ADDRESS', r'CALLE', r'AVDA',
        r'C/', r'PLAZA', r'PASEO', r'CTRA', r'CARRETERA', r'RUA', r'CAMINO',
    ],
    "expiration_date": [
        r'CADUCIDAD', r'VALIDEZ', r'EXPIRY', r'EXPIRATION', r'F[EÉ]\.?\s*VAL',
    ],
    "issue_date": [
        r'EMISI[OÓ]N', r'EXPEDICI[OÓ]N', r'ISSUE', r'F[EÉ]CHA\s*EMISI',
    ],
    "support_number": [
        r'SOPORTE', r'N[UÚ]M\.?\s*SOP',
    ],
    "signature": [
        r'FIRMA', r'SIGNATURE',
    ],
}

VALUE_PATTERNS = {
    "dni_number": re.compile(r'\d{7,9}[A-Za-z]'),
    "nie_number": re.compile(r'[XYZ]\d{7}[A-Za-z]'),
    "passport_number": re.compile(r'[A-Z]{3}\d{6}'),
    "dob": re.compile(r'\d{2}[/\-\.]\d{2}[/\-\.]\d{4}'),
    "expiration_date": re.compile(r'\d{2}[/\-\.]\d{2}[/\-\.]\d{4}'),
}

CONTENT_TO_FIELD = {
    "dni_number": "dni_number",
    "nie_number": "nie_number",
    "passport_number": "passport_number",
    "license_number": "license_number",
    "health_number": "health_number",
    "card_number": "card_number",
    "support_number": "support_number",
    "dob": "dob",
    "address": "address",
    "email": None,
    "phone": None,
}


def _preprocess_for_ocr(img: Image.Image) -> Image.Image:
    if img.mode != 'L':
        img = img.convert('L')
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)
    enhancer = ImageEnhance.Sharpness(img)
    img = enhancer.enhance(2.0)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def detect_fields_by_content(image: Image.Image) -> dict:
    processed = _preprocess_for_ocr(image)
    w, h = image.size

    ocr_data = pytesseract.image_to_data(
        processed, lang='spa+eng',
        config='--psm 4 --oem 3',
        output_type=pytesseract.Output.DICT
    )

    words = []
    n = len(ocr_data['text'])
    for i in range(n):
        conf = int(ocr_data['conf'][i])
        text = ocr_data['text'][i].strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x": ocr_data['left'][i],
            "y": ocr_data['top'][i],
            "w": ocr_data['width'][i],
            "h": ocr_data['height'][i],
            "conf": max(conf, 0),
            "block": ocr_data.get('block_num', [0]*n)[i],
        })

    result = {}
    found_labels = set()

    for field_name, label_patterns in FIELD_LABELS.items():
        label_indices = []
        for idx, wd in enumerate(words):
            for pat_str in label_patterns:
                if re.search(pat_str, wd["text"], re.IGNORECASE):
                    label_indices.append(idx)
                    break

        if not label_indices:
            continue

        value_candidates = []
        for li in label_indices:
            label = words[li]
            for j, wd in enumerate(words):
                if j == li:
                    continue
                dy = wd["y"] - label["y"]
                dx = wd["x"] - (label["x"] + label["w"])
                if abs(dy) < 35 and dx >= -15:
                    value_candidates.append((dx, dy, j, wd))

        value_candidates.sort(key=lambda c: (abs(c[1]), abs(c[0])))

        picked = []
        for dx, dy, cj, cw in value_candidates[:4]:
            if field_name in ("dni_number", "nie_number", "passport_number",
                              "license_number", "health_number", "card_number",
                              "support_number"):
                if not re.search(r'\d', cw["text"]):
                    continue
            picked.append(cw)

        if picked:
            xs = [cw["x"] for cw in picked]
            ys = [cw["y"] for cw in picked]
            x2s = [cw["x"] + cw["w"] for cw in picked]
            y2s = [cw["y"] + cw["h"] for cw in picked]
            result[field_name] = {
                "x1": min(xs) / w, "y1": min(ys) / h,
                "x2": max(x2s) / w, "y2": max(y2s) / h,
                "text": " ".join(cw["text"] for cw in picked),
                "confidence": max(cw["conf"] for cw in picked),
            }
            found_labels.add(field_name)

    for field_name, pattern in VALUE_PATTERNS.items():
        if field_name in found_labels:
            continue
        for wd in words:
            m = pattern.search(wd["text"])
            if m and wd["conf"] >= 30:
                result[field_name] = {
                    "x1": wd["x"] / w, "y1": wd["y"] / h,
                    "x2": (wd["x"] + wd["w"]) / w, "y2": (wd["y"] + wd["h"]) / h,
                    "text": wd["text"],
                    "confidence": wd["conf"],
                }
                break

    return result


def detect_excessive_field_boxes(image: Image.Image, doc_type: DocumentType) -> tuple:
    w, h = image.size
    content = detect_fields_by_content(image)

    excessive_keys = set(doc_type.excessive_fields().keys())

    boxes = []
    found_keys = set()
    for content_type, content_data in content.items():
        field_key = CONTENT_TO_FIELD.get(content_type)
        if field_key is None:
            continue
        if field_key in excessive_keys and field_key not in found_keys:
            bx1 = int(content_data["x1"] * w)
            by1 = int(content_data["y1"] * h)
            bx2 = int(content_data["x2"] * w)
            by2 = int(content_data["y2"] * h)
            margin = max(int(min(w, h) * 0.015), 3)
            bx1 = max(0, bx1 - margin)
            by1 = max(0, by1 - margin)
            bx2 = min(w, bx2 + margin)
            by2 = min(h, by2 + margin)
            boxes.append((bx1, by1, bx2, by2))
            found_keys.add(field_key)

    for key in excessive_keys:
        if key not in found_keys:
            if key in ("signature", "photo"):
                doc_boxes = get_field_boxes_for_type(doc_type.code)
                if key in doc_boxes:
                    fx1, fy1, fx2, fy2 = doc_boxes[key]
                    if key == "signature":
                        fx1 = 0.5
                        fx2 = 0.95
                    boxes.append((int(w * fx1), int(h * fy1), int(w * fx2), int(h * fy2)))

    return boxes, list(found_keys)


# ---- Detection (document type) ----

def detect_document_type(image_path: str) -> Tuple[Optional[DocumentType], float, str]:
    img = Image.open(image_path)
    ocr_text = _run_ocr(img)

    best_match = None
    best_score = 0.0
    evidence = []

    for code, doc_type in DOCUMENT_TYPES.items():
        all_hits = []
        key_hits = []
        for keyword in doc_type.templates:
            if keyword.lower() in ocr_text.lower():
                all_hits.append(keyword)
        for term in doc_type.key_terms:
            if term.lower() in ocr_text.lower():
                key_hits.append(term)

        if all_hits or key_hits:
            n_templates = max(len(doc_type.templates), 1)
            n_keys = max(len(doc_type.key_terms), 1)

            term_score = len(all_hits) / (n_templates * 0.12)
            key_bonus = len(key_hits) / max(n_keys * 0.25, 1)
            score = min(term_score * 0.35 + key_bonus * 0.65, 1.0)

            if score > best_score:
                best_score = score
                best_match = doc_type
                evidence = all_hits + [f"\u2605{k}" for k in key_hits]

    w, h = img.size
    if h > 0:
        ratio = w / h
        for code, doc_type in DOCUMENT_TYPES.items():
            rmin, rmax = doc_type.aspect_ratio_range
            if rmin <= ratio <= rmax:
                if best_match is None or best_score < 0.3:
                    best_match = doc_type
                    best_score = max(best_score, 0.3)
                    evidence.append(f"aspect_ratio({ratio:.2f})")

    if best_match is None:
        return None, 0.0, "No se detecto un tipo de documento conocido. OCR encontrado:\n" + ocr_text[:300]

    return best_match, best_score, _build_evidence(best_match, best_score, ocr_text)


def _run_ocr(img: Image.Image) -> str:
    try:
        text = pytesseract.image_to_string(img, lang='spa+eng', config='--psm 6')
        return text.strip()
    except Exception as e:
        return f"[OCR error: {e}]"


def _build_evidence(doc_type: DocumentType, score: float, ocr_text: str) -> str:
    lines = [
        f"Tipo detectado: {doc_type.name_es}",
        f"Confianza: {score*100:.0f}%",
        f"Campos totales: {len(doc_type.fields)}",
        f"Campos necesarios (RGPD min): {len(doc_type.necessary_fields())}",
        f"Campos a redactar: {len(doc_type.excessive_fields())}",
        "",
        "OCR extraído:",
        ocr_text[:500],
    ]
    return "\n".join(lines)


# ---- Preview (field box coordinates) ----

def get_field_preview_boxes(image_path: str, doc_type: DocumentType,
                             fields_to_highlight: list) -> dict:
    img = Image.open(image_path)
    w, h = img.size
    doc_boxes = get_field_boxes_for_type(doc_type.code)
    result = {}
    for field_key in fields_to_highlight:
        if field_key in doc_boxes:
            fx1, fy1, fx2, fy2 = doc_boxes[field_key]
        elif field_key in FIELD_BOXES:
            fx1, fy1, fx2, fy2 = FIELD_BOXES[field_key]
        else:
            continue
        result[field_key] = {
            "x1": int(w * fx1), "y1": int(h * fy1),
            "x2": int(w * fx2), "y2": int(h * fy2),
            "w": w, "h": h,
        }
    return result


# ---- Anonymization ----

REDACTION_COLOR = (0, 0, 0, 255)
REDACTION_COLOR_WATERMARK = (0, 0, 0, 200)
WATERMARK_TEXT = "DATOS EXCESIVOS (RGPD)"


def redact_field_boxes(image: Image.Image, boxes: list, mode: str = "blur") -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 18)
        except (IOError, OSError):
            font = ImageFont.load_default()

    for (x1, y1, x2, y2) in boxes:
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(image.width, x2), min(image.height, y2)
        if x2 <= x1 or y2 <= y1:
            continue
        if mode == "blur":
            region = image.crop((x1, y1, x2, y2))
            region = region.filter(ImageFilter.GaussianBlur(radius=18))
            image.paste(region, (x1, y1))
        elif mode == "redact":
            draw.rectangle([x1, y1, x2, y2], fill=REDACTION_COLOR)
        elif mode == "watermark":
            draw.rectangle([x1, y1, x2, y2], fill=REDACTION_COLOR_WATERMARK)
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            _, _, tw, th = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
            draw.text((cx - tw // 2, cy - th // 2), WATERMARK_TEXT,
                      fill=(255, 255, 255, 220), font=font)

    if mode != "blur":
        image = Image.alpha_composite(image, overlay)
    return image.convert("RGB")


def apply_minimization(image_path: str, doc_type: DocumentType,
                       fields_to_redact: list, mode: str = "watermark",
                       override_boxes: list = None) -> Image.Image:
    img = Image.open(image_path)
    if override_boxes is not None:
        boxes = override_boxes
    else:
        ocr_text = _run_ocr(img)
        boxes = _find_field_boxes(img, ocr_text, doc_type, fields_to_redact)
    return redact_field_boxes(img, boxes, mode=mode)


def _find_field_boxes(img: Image.Image, ocr_text: str,
                      doc_type: DocumentType, fields_to_redact: list) -> list:
    w, h = img.size
    boxes = []
    doc_boxes = get_field_boxes_for_type(doc_type.code)

    for field_key in fields_to_redact:
        if field_key in doc_boxes:
            fx1, fy1, fx2, fy2 = doc_boxes[field_key]
            boxes.append((int(w * fx1), int(h * fy1), int(w * fx2), int(h * fy2)))
        elif field_key in FIELD_BOXES:
            fx1, fy1, fx2, fy2 = FIELD_BOXES[field_key]
            boxes.append((int(w * fx1), int(h * fy1), int(w * fx2), int(h * fy2)))

    if not boxes:
        boxes.append((int(w * 0.4), int(h * 0.3), int(w * 0.9), int(h * 0.9)))

    return boxes
