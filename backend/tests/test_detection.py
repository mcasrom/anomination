import os
import sys
import json
import tempfile
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rgpd_rules import DOCUMENT_TYPES, map_ai_key, AI_KEY_MAP, analyze_necessity
from document_analyzer import detect_document_type, FIELD_BOXES, redact_field_boxes, apply_minimization

TEST_DIR = os.path.dirname(__file__)


def create_dni_test_image(path, text_lines=None):
    img = Image.new("RGB", (800, 500), (245, 235, 220))
    draw = ImageDraw.Draw(img)
    if text_lines:
        y = 30
        for line in text_lines:
            draw.text((30, y), line, fill=(0, 0, 0))
            y += 30
    img.save(path)
    return path


class TestRGPDRules:
    def test_document_types_exist(self):
        assert len(DOCUMENT_TYPES) == 8
        for code in ("dni", "nie", "passport", "driving_license", "residence_card", "health_card", "padron", "generic_passport"):
            assert code in DOCUMENT_TYPES

    def test_dni_fields(self):
        dni = DOCUMENT_TYPES["dni"]
        assert dni.name_es == "DNI / Documento Nacional de Identidad"
        assert dni.fields["full_name"].strictly_necessary is True
        assert dni.fields["dni_number"].strictly_necessary is False
        assert len(dni.necessary_fields()) == 4
        assert len(dni.excessive_fields()) == 8

    def test_analyze_necessity(self):
        dni = DOCUMENT_TYPES["dni"]
        result = analyze_necessity(dni)
        assert result["total_fields"] == 12
        assert result["necessary_fields"] == 4
        assert result["excessive_fields"] == 8


class TestAIKeyMapping:
    def test_map_ai_key(self):
        assert map_ai_key("surnames") == "full_name"
        assert map_ai_key("first_name") == "full_name"
        assert map_ai_key("sex") == "gender"
        assert map_ai_key("birth_date") == "dob"
        assert map_ai_key("expiry_date") == "expiration_date"
        assert map_ai_key("dni_number") == "dni_number"
        assert map_ai_key("nacionalidad") == "nationality"
        assert map_ai_key("fecha_emision") == "issue_date"

    def test_unknown_key_returns_none(self):
        assert map_ai_key("nonexistent_field") is None

    def test_all_document_fields_have_fallback_boxes(self):
        for doc_code, doc_type in DOCUMENT_TYPES.items():
            for field_key in doc_type.fields:
                if field_key in ("photo", "document_type"):
                    continue
                assert field_key in FIELD_BOXES, f"{doc_code}.{field_key} missing from FIELD_BOXES"


class TestDocumentDetection:
    def test_detect_dni_by_ocr(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            create_dni_test_image(path, [
                "DOCUMENTO NACIONAL DE IDENTIDAD",
                "DNI",
                "27438264T",
                "CASTILLO ROMERO",
                "MIGUEL",
            ])
            doc_type, confidence, evidence = detect_document_type(path)
            assert doc_type is not None, f"Detection failed: {evidence}"
            assert doc_type.code == "dni", f"Expected dni, got {doc_type.code}"
        finally:
            os.unlink(path)

    def test_detect_passport_by_ocr(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            create_dni_test_image(path, [
                "PASAPORTE",
                "UNION EUROPEA",
                "P<ESP",
                "GARCIA LOPEZ",
                "MARIA",
            ])
            doc_type, confidence, evidence = detect_document_type(path)
            assert doc_type is not None, f"Detection failed: {evidence}"
            assert doc_type.code == "passport", f"Expected passport, got {doc_type.code}"
        finally:
            os.unlink(path)

    def test_detect_driving_license_by_ocr(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            create_dni_test_image(path, [
                "PERMISO DE CONDUCIR",
                "DGT",
                "CONDUCTOR",
                "B1",
            ])
            doc_type, confidence, evidence = detect_document_type(path)
            assert doc_type is not None, f"Detection failed: {evidence}"
            assert doc_type.code == "driving_license", f"Expected driving_license, got {doc_type.code}"
        finally:
            os.unlink(path)

    def test_detect_unknown_returns_none(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            create_dni_test_image(path, ["Lorem ipsum dolor sit amet"])
            doc_type, confidence, evidence = detect_document_type(path)
            assert doc_type is None
        finally:
            os.unlink(path)


class TestFieldBoxes:
    def test_all_boxes_within_bounds(self):
        for name, (x1, y1, x2, y2) in FIELD_BOXES.items():
            assert 0 <= x1 < x2 <= 1.0, f"{name}: x coords invalid ({x1}, {x2})"
            assert 0 <= y1 < y2 <= 1.0, f"{name}: y coords invalid ({y1}, {y2})"

    def test_boxes_reasonable_size(self):
        for name, (x1, y1, x2, y2) in FIELD_BOXES.items():
            width = x2 - x1
            height = y2 - y1
            assert width > 0.02, f"{name}: too narrow ({width})"
            assert height > 0.02, f"{name}: too short ({height})"
            assert width < 0.95, f"{name}: too wide ({width})"
            assert height < 0.95, f"{name}: too tall ({height})"


class TestRedaction:
    def test_watermark_mode_does_not_crash(self):
        img = Image.new("RGB", (400, 300), (255, 255, 255))
        boxes = [(50, 50, 150, 100)]
        result = redact_field_boxes(img, boxes, mode="watermark")
        assert result.size == (400, 300)
        r, g, b = result.getpixel((100, 75))
        assert r > 100 or g < 200, "Expected some red tint from watermark"

    def test_blur_mode_does_not_crash(self):
        img = Image.new("RGB", (400, 300), (255, 255, 255))
        boxes = [(50, 50, 150, 100)]
        result = redact_field_boxes(img, boxes, mode="blur")
        assert result.size == (400, 300)

    def test_redact_mode_fills_red(self):
        img = Image.new("RGB", (400, 300), (255, 255, 255))
        boxes = [(50, 50, 150, 100)]
        result = redact_field_boxes(img, boxes, mode="redact")
        r, g, b = result.getpixel((100, 75))
        assert r > 150 and g < 100, f"Expected red fill, got RGB({r},{g},{b})"

    def test_apply_minimization_with_override_boxes(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            img = Image.new("RGB", (400, 300), (255, 255, 255))
            img.save(path)
            dni = DOCUMENT_TYPES["dni"]
            boxes = [(50, 50, 150, 100)]
            result = apply_minimization(path, dni, ["dni_number"], mode="redact", override_boxes=boxes)
            assert result.size == (400, 300)
        finally:
            os.unlink(path)

    def test_multiple_boxes(self):
        img = Image.new("RGB", (500, 500), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((100, 100), "Sensitive data here", fill=(0, 0, 0))
        draw.text((100, 200), "More sensitive", fill=(0, 0, 0))
        boxes = [(80, 80, 350, 130), (80, 190, 350, 230)]
        result = redact_field_boxes(img, boxes, mode="redact")
        r1, g1, b1 = result.getpixel((100, 105))
        r2, g2, b2 = result.getpixel((100, 210))
        assert r1 > 150 and g1 < 100
        assert r2 > 150 and g2 < 100
        r3, g3, b3 = result.getpixel((400, 105))
        assert r3 > 200, "Outside box should not be red (expected white background)"

    def test_boxes_clipped_to_image(self):
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        boxes = [(-50, -50, 300, 300)]
        result = redact_field_boxes(img, boxes, mode="redact")
        assert result.size == (200, 200)
