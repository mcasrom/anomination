# -*- coding: utf-8 -*-
import os
import uuid
import json
import io
from flask import Flask, request, jsonify, render_template, send_file, url_for
from PIL import Image

from document_analyzer import detect_document_type, apply_minimization, get_field_preview_boxes, get_field_boxes_for_type, FIELD_BOXES as FLAT_FIELD_BOXES
from rgpd_rules import DOCUMENT_TYPES, DocumentField, analyze_necessity, map_ai_key, AI_COMPOSITE_KEYS
from ai_detector import detect_document_with_ai, suggest_redactions_with_ai, ai_available
from pdf_processor import (
    pdf_to_images, images_to_pdf, redact_pdf_page, redact_pdf_all_pages,
    get_pdf_page_count, get_pdf_page_size, PYMUPDF_AVAILABLE, PDF2IMAGE_AVAILABLE
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['JSON_AS_ASCII'] = False
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'tif', 'webp'}
ALLOWED_EXTENSIONS_PDF = ALLOWED_EXTENSIONS | {'pdf'}


def allowed_file(filename, pdf_ok=False):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if pdf_ok:
        return ext in ALLOWED_EXTENSIONS_PDF
    return ext in ALLOWED_EXTENSIONS


def is_pdf(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'


def ocr_image_to_text(filepath: str) -> str:
    try:
        from document_analyzer import _run_ocr
        img = Image.open(filepath)
        return _run_ocr(img)
    except Exception as e:
        return f"[Error OCR: {e}]"


@app.route('/')
def index():
    doc_types_json = json.dumps({k: {"name": v.name_es, "fields": {
        fk: {"label": fv.label_es, "necessary": fv.strictly_necessary, "sensitivity": fv.sensitivity,
             "reason": fv.reason_if_excessive}
        for fk, fv in v.fields.items()
    }} for k, v in DOCUMENT_TYPES.items()})
    return render_template('index.html', doc_types=doc_types_json,
                           ai_available=ai_available())


@app.route('/api/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400
    if not allowed_file(file.filename, pdf_ok=True):
        return jsonify({"error": f"Formato no soportado. Permitidos: {', '.join(ALLOWED_EXTENSIONS_PDF)}"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    is_pdf_file = is_pdf(filename)

    if is_pdf_file:
        try:
            images = pdf_to_images(filepath, dpi=200)
            if not images:
                return jsonify({"success": False, "error": "No se pudieron leer las páginas del PDF."})
            first_page_img_path = filepath + "_page0.png"
            images[0].save(first_page_img_path)
            analyze_path = first_page_img_path
            page_count = len(images)
        except Exception as e:
            return jsonify({"success": False, "error": f"Error al procesar PDF: {str(e)}"})
    else:
        analyze_path = filepath
        page_count = 1

    ai_fields_data = None
    doc_type = None

    if ai_available():
        try:
            with open(analyze_path, 'rb') as f:
                img_bytes = f.read()
            from document_analyzer import _run_ocr
            ocr_text = _run_ocr(Image.open(analyze_path))
            ai_result = detect_document_with_ai(img_bytes, ocr_text=ocr_text)
            if ai_result and ai_result.get("document_type"):
                from rgpd_rules import DOCUMENT_TYPES as DT
                ai_doc_code = ai_result["document_type"]
                if ai_doc_code in DT:
                    doc_type = DT[ai_doc_code]
                    confidence = ai_result.get("confidence", 0.5)
                    evidence = "IA: " + ai_result.get("summary", "")
                    ai_fields_data = ai_result.get("fields", [])
                else:
                    doc_type = None
        except Exception:
            ai_result = None

    if doc_type is None:
        doc_type, confidence, evidence = detect_document_type(analyze_path)
        if doc_type is None:
            return jsonify({
                "success": False,
                "error": "No se pudo detectar el tipo de documento.",
                "ocr_evidence": evidence,
                "ai_suggestion": ai_result if ai_available() else None,
            })

    analysis = analyze_necessity(doc_type)
    necessary_keys = [k for k, v in doc_type.fields.items() if v.strictly_necessary]
    excessive_keys = [k for k, v in doc_type.fields.items() if not v.strictly_necessary]

    img = Image.open(analyze_path)
    img_w, img_h = img.size

    preview_boxes = {}

    if ai_fields_data:
        mapped_fields = []
        composite_buckets = {}
        for f in ai_fields_data:
            ai_key = f.get("key", "")
            sys_key = map_ai_key(ai_key)
            if sys_key is None or "box" not in f:
                continue
            entry = {"sys_key": sys_key, "ai_key": ai_key, "box": f["box"]}
            if ai_key in AI_COMPOSITE_KEYS:
                composite_buckets.setdefault(sys_key, []).append(entry)
            else:
                mapped_fields.append(entry)

        for sys_key, parts in composite_buckets.items():
            if len(parts) == 1:
                mapped_fields.append(parts[0])
            else:
                boxes = [p["box"] for p in parts]
                xs = [b[f"{c}"] for b in boxes for c in ("x1", "x2")]
                ys = [b[f"{c}"] for b in boxes for c in ("y1", "y2")]
                merged = {"x1": min(xs), "y1": min(ys), "x2": max(xs), "y2": max(ys)}
                mapped_fields.append({"sys_key": sys_key, "ai_key": "+".join(p["ai_key"] for p in parts), "box": merged})

        def norm_coord(val, dim):
            if val > 1.5:
                return val / dim if dim else 0.0
            return val

        exact_key_hits = {e["ai_key"] for e in mapped_fields if e["ai_key"] == e["sys_key"]}

        preview_boxes_ai = {}
        for entry in mapped_fields:
            sys_key = entry["sys_key"]
            if sys_key in preview_boxes_ai:
                if entry["ai_key"] != sys_key and sys_key in exact_key_hits:
                    continue
            b = entry["box"]
            rx1 = norm_coord(b["x1"], img_w)
            ry1 = norm_coord(b["y1"], img_h)
            rx2 = norm_coord(b["x2"], img_w)
            ry2 = norm_coord(b["y2"], img_h)
            bx1 = int(rx1 * img_w)
            by1 = int(ry1 * img_h)
            bx2 = int(rx2 * img_w)
            by2 = int(ry2 * img_h)
            entry["box"] = {"x1": rx1, "y1": ry1, "x2": rx2, "y2": ry2}
            preview_boxes_ai[sys_key] = {
                "x1": bx1, "y1": by1, "x2": bx2, "y2": by2, "w": img_w, "h": img_h,
            }
        for key, box in preview_boxes_ai.items():
            if key in excessive_keys:
                preview_boxes[key] = box

        is_absolute = False
        with open(analyze_path + "_ai_fields.json", 'w') as f:
            used_keys = set()
            deduped = []
            for e in mapped_fields:
                sk = e["sys_key"]
                if sk in used_keys:
                    continue
                if e["ai_key"] != sk:
                    exact = [x for x in mapped_fields if x["sys_key"] == sk and x["ai_key"] == sk]
                    if exact:
                        continue
                used_keys.add(sk)
                deduped.append(e)
            serializable = [{
                "key": e["sys_key"],
                "ai_key": e["ai_key"],
                "box": {
                    "x1": e["box"]["x1"] / (img_w if is_absolute else 1),
                    "y1": e["box"]["y1"] / (img_h if is_absolute else 1),
                    "x2": e["box"]["x2"] / (img_w if is_absolute else 1),
                    "y2": e["box"]["y2"] / (img_h if is_absolute else 1),
                } if is_absolute else e["box"],
            } for e in deduped]
            json.dump(serializable, f)

    doc_field_boxes = get_field_boxes_for_type(doc_type.code) if doc_type else {}
    for key in excessive_keys:
        if key not in preview_boxes:
            if key in doc_field_boxes:
                fx1, fy1, fx2, fy2 = doc_field_boxes[key]
            elif key in FLAT_FIELD_BOXES:
                fx1, fy1, fx2, fy2 = FLAT_FIELD_BOXES[key]
            else:
                continue
            preview_boxes[key] = {
                "x1": int(img_w * fx1), "y1": int(img_h * fy1),
                "x2": int(img_w * fx2), "y2": int(img_h * fy2),
                "w": img_w, "h": img_h,
            }

    result = {
        "success": True,
        "session_id": filename,
        "document_type": doc_type.code,
        "document_name": doc_type.name_es,
        "confidence": confidence,
        "evidence": evidence,
        "analysis": analysis,
        "necessary_fields": necessary_keys,
        "excessive_fields": excessive_keys,
        "preview_boxes": preview_boxes,
        "image_width": img_w,
        "image_height": img_h,
        "is_pdf": is_pdf_file,
        "page_count": page_count,
        "ai_used": ai_fields_data is not None,
    }

    if is_pdf_file:
        result["first_page_url"] = url_for('get_result', filename=os.path.basename(analyze_path))

    return jsonify(result)


@app.route('/api/preview', methods=['POST'])
def preview_boxes():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON inválido"}), 400

    session_id = data.get('session_id')
    doc_type_code = data.get('document_type')
    fields_to_show = data.get('fields_to_show', [])

    if not session_id or not doc_type_code:
        return jsonify({"error": "Faltan parámetros"}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    if not os.path.exists(filepath):
        return jsonify({"error": "Sesión no encontrada."}), 404

    analyze_path = filepath
    if is_pdf(session_id):
        page0_path = filepath + "_page0.png"
        if os.path.exists(page0_path):
            analyze_path = page0_path

    doc_type = DOCUMENT_TYPES.get(doc_type_code)
    if not doc_type:
        return jsonify({"error": "Tipo de documento no reconocido"}), 400

    from PIL import Image
    img_w, img_h = Image.open(analyze_path).size
    doc_field_boxes = get_field_boxes_for_type(doc_type_code)

    boxes = {}
    ai_fields_path = analyze_path + "_ai_fields.json"
    has_ai_fields = False
    if os.path.exists(ai_fields_path):
        with open(ai_fields_path) as f:
            ai_fields = json.load(f)
        for field in ai_fields:
            key = field.get("key", "")
            if key in fields_to_show and "box" in field:
                b = field["box"]
                boxes[key] = {
                    "x1": int(b["x1"] * img_w),
                    "y1": int(b["y1"] * img_h),
                    "x2": int(b["x2"] * img_w),
                    "y2": int(b["y2"] * img_h),
                    "w": img_w,
                    "h": img_h,
                }
                has_ai_fields = True
    if not has_ai_fields:
        for key in fields_to_show:
            if key not in boxes:
                if key in doc_field_boxes:
                    fx1, fy1, fx2, fy2 = doc_field_boxes[key]
                elif key in FLAT_FIELD_BOXES:
                    fx1, fy1, fx2, fy2 = FLAT_FIELD_BOXES[key]
                else:
                    continue
                boxes[key] = {
                    "x1": int(img_w * fx1), "y1": int(img_h * fy1),
                    "x2": int(img_w * fx2), "y2": int(img_h * fy2),
                    "w": img_w, "h": img_h,
                }

    return jsonify({
        "success": True,
        "boxes": boxes,
        "image_width": img_w,
        "image_height": img_h,
    })


@app.route('/api/redact', methods=['POST'])
def redact():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON inválido"}), 400

    session_id = data.get('session_id')
    fields_to_redact = data.get('fields_to_redact', [])
    doc_type_code = data.get('document_type')
    mode = data.get('mode', 'watermark')

    if not session_id or not doc_type_code:
        return jsonify({"error": "Faltan parámetros requeridos"}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    if not os.path.exists(filepath):
        return jsonify({"error": "Sesión no encontrada. Vuelva a subir el documento."}), 404

    is_pdf_file = is_pdf(session_id)

    analyze_path = filepath
    if is_pdf_file:
        p0 = filepath + "_page0.png"
        if os.path.exists(p0):
            analyze_path = p0

    from document_analyzer import FIELD_BOXES as FLAT_FB
    doc_field_boxes = get_field_boxes_for_type(doc_type_code) if doc_type_code else {}
    img = Image.open(analyze_path)
    w, h = img.size

    def get_field_boxes(fields):
        boxes_list = []
        ai_fields_path = analyze_path + "_ai_fields.json"
        ai_lookup = {}
        if os.path.exists(ai_fields_path):
            with open(ai_fields_path) as f:
                for af in json.load(f):
                    if "box" in af:
                        ai_lookup[af["key"]] = af["box"]

        for fk in fields:
            if fk in ai_lookup:
                b = ai_lookup[fk]
                boxes_list.append((int(b["x1"] * w), int(b["y1"] * h),
                                    int(b["x2"] * w), int(b["y2"] * h)))
            elif fk in doc_field_boxes:
                fx1, fy1, fx2, fy2 = doc_field_boxes[fk]
                boxes_list.append((int(w * fx1), int(h * fy1), int(w * fx2), int(h * fy2)))
            elif fk in FLAT_FB:
                fx1, fy1, fx2, fy2 = FLAT_FB[fk]
                boxes_list.append((int(w * fx1), int(h * fy1), int(w * fx2), int(h * fy2)))
        if not boxes_list:
            boxes_list.append((int(w * 0.4), int(h * 0.3), int(w * 0.9), int(h * 0.9)))
        return boxes_list

    if is_pdf_file and PYMUPDF_AVAILABLE:
        doc_type = DOCUMENT_TYPES.get(doc_type_code)
        if doc_type is None:
            return jsonify({"error": "Tipo de documento no reconocido"}), 400
        if mode not in ('blur', 'redact', 'watermark'):
            mode = 'watermark'
        page_boxes = {0: get_field_boxes(fields_to_redact)}
        result_path = filepath + "_redacted.pdf"
        redact_pdf_all_pages(filepath, page_boxes, mode=mode, output_path=result_path)
        return jsonify({
            "success": True,
            "result_url": url_for('get_result', filename=os.path.basename(result_path)),
            "redacted_fields": fields_to_redact,
            "preserved_fields": [k for k in doc_type.fields if k not in fields_to_redact],
        })

    doc_type = DOCUMENT_TYPES.get(doc_type_code)
    if doc_type is None:
        return jsonify({"error": "Tipo de documento no reconocido"}), 400
    if mode not in ('blur', 'redact', 'watermark'):
        mode = 'watermark'

    redact_boxes = get_field_boxes(fields_to_redact)
    result_img = apply_minimization(analyze_path, doc_type, fields_to_redact, mode=mode, override_boxes=redact_boxes)
    result_path = filepath + "_redacted.png"
    result_img.save(result_path)

    mime = 'application/pdf' if is_pdf_file else 'image/png'

    return jsonify({
        "success": True,
        "result_url": url_for('get_result', filename=os.path.basename(result_path)),
        "redacted_fields": fields_to_redact,
        "preserved_fields": [k for k in doc_type.fields if k not in fields_to_redact],
        "mime_type": mime,
    })


@app.route('/api/auto-redact', methods=['POST'])
def auto_redact():
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400
    if not allowed_file(file.filename, pdf_ok=True):
        return jsonify({"error": f"Formato no soportado. Permitidos: {', '.join(ALLOWED_EXTENSIONS_PDF)}"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    session_id = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    file.save(filepath)

    analyze_path = filepath
    if is_pdf(session_id):
        try:
            images = pdf_to_images(filepath, dpi=200)
            if not images:
                return jsonify({"success": False, "error": "No se pudieron leer las páginas del PDF."})
            analyze_path = filepath + "_page0.png"
            images[0].save(analyze_path)
        except Exception as e:
            return jsonify({"success": False, "error": f"Error al procesar PDF: {str(e)}"})

    img = Image.open(analyze_path)
    w, h = img.size

    doc_type = None
    confidence = 0
    evidence = ""
    doc_name = "Documento"
    detected_fields = []
    redact_boxes = []

    with open(analyze_path, 'rb') as f:
        img_bytes = f.read()

    ocr_text = ocr_image_to_text(analyze_path)

    ai_result = None
    if ai_available():
        try:
            ai_result = detect_document_with_ai(img_bytes, ocr_text=ocr_text)
        except Exception:
            pass

    ai_doc_code = None
    if ai_result and ai_result.get("document_type"):
        ai_doc_code = ai_result["document_type"]
        if ai_doc_code in DOCUMENT_TYPES:
            doc_type = DOCUMENT_TYPES[ai_doc_code]
            confidence = ai_result.get("confidence", 0.5)
            doc_name = ai_result.get("document_name", doc_type.name_es)
            evidence = "IA: " + ai_result.get("summary", "")

    if doc_type is None:
        detected, conf, ev = detect_document_type(analyze_path)
        if detected:
            doc_type = detected
            confidence = conf
            evidence = ev
            doc_name = doc_type.name_es

    doc_field_boxes = get_field_boxes_for_type(doc_type.code) if doc_type else {}

    if doc_type:
        excessive = list(doc_type.excessive_fields().keys())
        for key in excessive:
            if key in doc_field_boxes:
                fx1, fy1, fx2, fy2 = doc_field_boxes[key]
            elif key in FLAT_FIELD_BOXES:
                fx1, fy1, fx2, fy2 = FLAT_FIELD_BOXES[key]
            else:
                continue
            bx1, by1 = int(w * fx1), int(h * fy1)
            bx2, by2 = int(w * fx2), int(h * fy2)
            redact_boxes.append((bx1, by1, bx2, by2))
            detected_fields.append({
                "key": key,
                "label": doc_type.fields.get(key, DocumentField(key, key, key, False, "medium")).label_es,
                "sensitive": True
            })

    if not redact_boxes:
        result_path = filepath + "_redacted.png"
        img.save(result_path)
        return jsonify({
            "success": True,
            "result_url": url_for('get_result', filename=os.path.basename(result_path)),
            "document_name": doc_name,
            "redacted_fields": [],
            "detected_fields": [],
            "download_name": "anonimizado.png",
            "warning": "No se detectaron campos que redactar. Usa el modo manual para seleccionar áreas.",
        })

    result_img = apply_minimization(analyze_path, None, [], mode='redact', override_boxes=redact_boxes)
    result_path = filepath + "_redacted.png"
    result_img.save(result_path)

    return jsonify({
        "success": True,
        "result_url": url_for('get_result', filename=os.path.basename(result_path)),
        "document_name": doc_name,
        "document_type": doc_type.code if doc_type else None,
        "confidence": confidence,
        "evidence": evidence,
        "redacted_fields": [f["label"] or f["key"] for f in detected_fields],
        "detected_fields": detected_fields,
        "download_name": "anonimizado.png",
        "template_boxes": [
            {"key": f["key"], "label": f["label"],
             "x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3]}
            for f, b in zip(detected_fields, redact_boxes)
        ] if detected_fields else [],
    })


@app.route('/api/result/<filename>')
def get_result(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Archivo no encontrado"}), 404
    mime = 'application/pdf' if filename.lower().endswith('.pdf') else 'image/png'
    return send_file(filepath, mimetype=mime)


@app.route('/api/analyze-general', methods=['POST'])
def analyze_general():
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400
    if not allowed_file(file.filename, pdf_ok=True):
        return jsonify({"error": f"Formato no soportado. Permitidos: {', '.join(ALLOWED_EXTENSIONS_PDF)}"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    is_pdf_file = is_pdf(filename)
    if is_pdf_file:
        try:
            images = pdf_to_images(filepath, dpi=200)
            if not images:
                return jsonify({"success": False, "error": "No se pudieron leer las páginas del PDF."})
            analyze_path = filepath + "_page0.png"
            images[0].save(analyze_path)
            page_count = len(images)
        except Exception as e:
            return jsonify({"success": False, "error": f"Error al procesar PDF: {str(e)}"})
    else:
        analyze_path = filepath
        page_count = 1

    ocr_text = ocr_image_to_text(analyze_path)

    ai_suggestions = None
    if ai_available():
        try:
            with open(analyze_path, 'rb') as f:
                img_bytes = f.read()
            ai_suggestions = suggest_redactions_with_ai(img_bytes)
        except Exception:
            pass

    from document_analyzer import _run_ocr, FIELD_BOXES
    img = Image.open(analyze_path)
    w, h = img.size

    return jsonify({
        "success": True,
        "session_id": filename,
        "is_pdf": is_pdf_file,
        "page_count": page_count,
        "image_width": w,
        "image_height": h,
        "ocr_text": ocr_text[:2000],
        "ai_suggestions": ai_suggestions,
        "ai_available": ai_available(),
        "fields": [
            {"key": "full_document", "label": "Documento completo", "sensitive": False},
        ],
    })


@app.route('/api/redact-general', methods=['POST'])
def redact_general():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON inválido"}), 400

    session_id = data.get('session_id')
    regions = data.get('regions', [])
    mode = data.get('mode', 'watermark')

    if not session_id:
        return jsonify({"error": "Faltan parámetros requeridos"}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session_id)
    if not os.path.exists(filepath):
        return jsonify({"error": "Sesión no encontrada."}), 404

    if mode not in ('blur', 'redact', 'watermark'):
        mode = 'watermark'

    is_pdf_file = is_pdf(session_id)

    if is_pdf_file and PYMUPDF_AVAILABLE:
        page_boxes = {}
        for r in regions:
            pn = r.get('page', 0)
            if pn not in page_boxes:
                page_boxes[pn] = []
            page_boxes[pn].append((r['x1'], r['y1'], r['x2'], r['y2']))

        result_path = filepath + "_redacted.pdf"
        redact_pdf_all_pages(filepath, page_boxes, mode=mode, output_path=result_path)

        return jsonify({
            "success": True,
            "result_url": url_for('get_result', filename=os.path.basename(result_path)),
            "regions_redacted": len(regions),
        })

    analyze_path = filepath
    if is_pdf_file:
        p0 = filepath + "_page0.png"
        if os.path.exists(p0):
            analyze_path = p0

    from document_analyzer import redact_field_boxes
    img = Image.open(analyze_path)
    boxes = [(r['x1'], r['y1'], r['x2'], r['y2']) for r in regions]
    result_img = redact_field_boxes(img, boxes, mode=mode)
    result_path = filepath + "_redacted.png"
    result_img.save(result_path)

    return jsonify({
        "success": True,
        "result_url": url_for('get_result', filename=os.path.basename(result_path)),
        "regions_redacted": len(regions),
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)