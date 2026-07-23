# -*- coding: utf-8 -*-
import os
import uuid
import json
import io
from flask import Flask, request, jsonify, render_template, send_file, url_for
from PIL import Image

from document_analyzer import detect_document_type, apply_minimization, get_field_preview_boxes
from rgpd_rules import DOCUMENT_TYPES, analyze_necessity
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

    ai_result = None
    if ai_available():
        try:
            with open(analyze_path, 'rb') as f:
                img_bytes = f.read()
            ai_result = detect_document_with_ai(img_bytes)
        except Exception:
            pass

    doc_type, confidence, evidence = detect_document_type(analyze_path)

    if doc_type is None and ai_result and ai_result.get("document_type"):
        from rgpd_rules import DOCUMENT_TYPES as DT
        ai_doc_type = ai_result.get("document_type")
        if ai_doc_type in DT:
            doc_type = DT[ai_doc_type]
            confidence = ai_result.get("confidence", 0.5)
            evidence = f"IA ({ai_result.get('document_name', ai_doc_type)}): {ai_result.get('summary', '')}"
        else:
            return jsonify({
                "success": False,
                "error": "No se pudo detectar el tipo de documento.",
                "ocr_evidence": evidence,
                "ai_suggestion": ai_result,
            })

    if doc_type is None:
        return jsonify({
            "success": False,
            "error": "No se pudo detectar el tipo de documento.",
            "ocr_evidence": evidence,
            "ai_suggestion": ai_result,
        })

    analysis = analyze_necessity(doc_type)
    necessary_keys = [k for k, v in doc_type.fields.items() if v.strictly_necessary]
    excessive_keys = [k for k, v in doc_type.fields.items() if not v.strictly_necessary]

    preview_boxes = get_field_preview_boxes(analyze_path, doc_type, excessive_keys)
    img = Image.open(analyze_path)

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
        "image_width": img.size[0],
        "image_height": img.size[1],
        "is_pdf": is_pdf_file,
        "page_count": page_count,
        "ai_used": ai_result is not None,
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

    boxes = get_field_preview_boxes(analyze_path, doc_type, fields_to_show)
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

    if is_pdf_file and PYMUPDF_AVAILABLE:
        doc_type = DOCUMENT_TYPES.get(doc_type_code)
        if doc_type is None:
            return jsonify({"error": "Tipo de documento no reconocido"}), 400
        if mode not in ('blur', 'redact', 'watermark'):
            mode = 'watermark'

        page_boxes = {0: []}
        analyze_path = filepath + "_page0.png" if os.path.exists(filepath + "_page0.png") else filepath
        from document_analyzer import FIELD_BOXES
        img = Image.open(analyze_path)
        w, h = img.size
        for field_key in fields_to_redact:
            if field_key in FIELD_BOXES:
                fx1, fy1, fx2, fy2 = FIELD_BOXES[field_key]
                page_boxes[0].append((int(w * fx1), int(h * fy1), int(w * fx2), int(h * fy2)))

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

    analyze_path = filepath
    if is_pdf_file:
        page0 = filepath + "_page0.png"
        if os.path.exists(page0):
            analyze_path = page0

    result_img = apply_minimization(analyze_path, doc_type, fields_to_redact, mode=mode)
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