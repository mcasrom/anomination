import re
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import pytesseract
from typing import Optional, Tuple, List

from rgpd_rules import DOCUMENT_TYPES, DocumentType


FIELD_BOXES = {
    # DNI / NIE / Residence card format (credit-card size, landscape)
    # Layout: photo left ~28%, text fields to the right
    "dni_number": (0.32, 0.15, 0.75, 0.25),
    "nie_number": (0.32, 0.15, 0.75, 0.25),
    "card_number": (0.32, 0.15, 0.75, 0.25),
    "full_name": (0.32, 0.27, 0.78, 0.38),
    "photo": (0.02, 0.02, 0.28, 0.55),
    "expiration_date": (0.55, 0.62, 0.78, 0.70),
    "issue_date": (0.32, 0.62, 0.53, 0.70),
    "dob": (0.32, 0.40, 0.55, 0.48),
    "gender": (0.57, 0.40, 0.65, 0.48),
    "nationality": (0.67, 0.40, 0.78, 0.48),
    "address": (0.05, 0.72, 0.75, 0.88),
    "previous_address": (0.05, 0.82, 0.75, 0.95),
    "father_name": (0.32, 0.50, 0.55, 0.58),
    "mother_name": (0.57, 0.50, 0.78, 0.58),
    "signature": (0.55, 0.88, 0.95, 0.98),
    "support_number": (0.32, 0.05, 0.75, 0.13),

    # Passport format
    "passport_number": (0.05, 0.15, 0.55, 0.28),
    "pob": (0.05, 0.55, 0.55, 0.65),
    "height": (0.55, 0.55, 0.85, 0.65),
    "eye_color": (0.55, 0.65, 0.85, 0.72),

    # Driving license
    "license_number": (0.42, 0.15, 0.78, 0.28),
    "issuing_authority": (0.05, 0.75, 0.55, 0.85),
    "authority": (0.05, 0.75, 0.55, 0.85),
    "categories": (0.05, 0.50, 0.55, 0.60),

    # Health card
    "health_number": (0.40, 0.22, 0.85, 0.35),
}


# ---- Detection ----

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
                evidence = all_hits + [f"★{k}" for k in key_hits]

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
    result = {}
    for field_key in fields_to_highlight:
        if field_key in FIELD_BOXES:
            fx1, fy1, fx2, fy2 = FIELD_BOXES[field_key]
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

    for field_key in fields_to_redact:
        if field_key in FIELD_BOXES:
            fx1, fy1, fx2, fy2 = FIELD_BOXES[field_key]
            boxes.append((int(w * fx1), int(h * fy1), int(w * fx2), int(h * fy2)))

    if not boxes:
        boxes.append((int(w * 0.4), int(h * 0.3), int(w * 0.9), int(h * 0.9)))

    return boxes