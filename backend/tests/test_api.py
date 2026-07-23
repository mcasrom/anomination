import os
import sys
import json
import tempfile
import io
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = tempfile.mkdtemp()
    with app.test_client() as c:
        yield c


def _make_test_image(size=(800, 500), text_lines=None):
    img = Image.new("RGB", size, (245, 235, 220))
    if text_lines:
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        y = 30
        for line in text_lines:
            draw.text((30, y), line, fill=(0, 0, 0))
            y += 30
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class TestAnalyzeEndpoint:
    def test_analyze_no_file_returns_400(self, client):
        resp = client.post("/api/analyze")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data

    def test_analyze_empty_filename_returns_400(self, client):
        resp = client.post("/api/analyze", data={"file": (io.BytesIO(b""), "")})
        assert resp.status_code == 400

    def test_analyze_dni_image_returns_analysis(self, client):
        img = _make_test_image(text_lines=[
            "DOCUMENTO NACIONAL DE IDENTIDAD",
            "DNI",
            "27438264T",
        ])
        resp = client.post("/api/analyze", data={
            "file": (img, "test_dni.png")
        }, content_type="multipart/form-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["document_type"] == "dni"
        assert "session_id" in data
        assert "preview_boxes" in data
        assert "excessive_fields" in data
        assert data["excessive_fields"] is not None
        assert len(data["excessive_fields"]) > 0

    def test_analyze_unknown_document_returns_error(self, client):
        img = _make_test_image(text_lines=["This is not a known document"])
        resp = client.post("/api/analyze", data={
            "file": (img, "unknown.png")
        }, content_type="multipart/form-data")
        data = resp.get_json()
        assert data.get("success") is False or data.get("success") is None

    def test_analyze_unsupported_format_returns_400(self, client):
        resp = client.post("/api/analyze", data={
            "file": (io.BytesIO(b"fake"), "test.txt")
        }, content_type="multipart/form-data")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "error" in data


class TestPreviewEndpoint:
    def test_preview_no_data_returns_400(self, client):
        resp = client.post("/api/preview", content_type="application/json", data="{}")
        assert resp.status_code == 400

    def test_preview_nonexistent_session_returns_404(self, client):
        resp = client.post("/api/preview",
            content_type="application/json",
            data=json.dumps({"session_id": "nonexistent.png", "document_type": "dni", "fields_to_show": ["dni_number"]}))
        assert resp.status_code == 404


class TestRedactEndpoint:
    def test_redact_no_data_returns_400(self, client):
        resp = client.post("/api/redact", content_type="application/json", data="{}")
        assert resp.status_code == 400

    def test_redact_nonexistent_session_returns_404(self, client):
        resp = client.post("/api/redact",
            content_type="application/json",
            data=json.dumps({
                "session_id": "nonexistent.png",
                "document_type": "dni",
                "fields_to_redact": ["dni_number"],
                "mode": "watermark",
            }))
        assert resp.status_code == 404

    def test_redact_full_flow(self, client):
        img = _make_test_image(text_lines=[
            "DOCUMENTO NACIONAL DE IDENTIDAD",
            "DNI",
            "27438264T",
        ])
        analyze_resp = client.post("/api/analyze", data={
            "file": (img, "test_dni.png")
        }, content_type="multipart/form-data")
        assert analyze_resp.status_code == 200
        analyze_data = analyze_resp.get_json()
        session_id = analyze_data["session_id"]

        redact_resp = client.post("/api/redact",
            content_type="application/json",
            data=json.dumps({
                "session_id": session_id,
                "document_type": "dni",
                "fields_to_redact": ["dni_number", "address"],
                "mode": "watermark",
            }))
        assert redact_resp.status_code == 200
        redact_data = redact_resp.get_json()
        assert redact_data["success"] is True
        assert "result_url" in redact_data
        assert "dni_number" in redact_data["redacted_fields"]

    def test_redact_invalid_mode_defaults_to_watermark(self, client):
        img = _make_test_image(text_lines=["DOCUMENTO NACIONAL DE IDENTIDAD"])
        analyze_resp = client.post("/api/analyze", data={
            "file": (img, "test_dni.png")
        }, content_type="multipart/form-data")
        assert analyze_resp.status_code == 200
        session_id = analyze_resp.get_json()["session_id"]

        redact_resp = client.post("/api/redact",
            content_type="application/json",
            data=json.dumps({
                "session_id": session_id,
                "document_type": "dni",
                "fields_to_redact": ["dni_number"],
                "mode": "invalid_mode",
            }))
        assert redact_resp.status_code == 200


class TestResultEndpoint:
    def test_result_nonexistent_returns_404(self, client):
        resp = client.get("/api/result/nonexistent.png")
        assert resp.status_code == 404

    def test_result_after_redact_returns_image(self, client):
        img = _make_test_image(text_lines=["DOCUMENTO NACIONAL DE IDENTIDAD"])
        analyze_resp = client.post("/api/analyze", data={
            "file": (img, "test_dni.png")
        }, content_type="multipart/form-data")
        session_id = analyze_resp.get_json()["session_id"]

        redact_resp = client.post("/api/redact",
            content_type="application/json",
            data=json.dumps({
                "session_id": session_id,
                "document_type": "dni",
                "fields_to_redact": ["dni_number"],
                "mode": "watermark",
            }))
        result_url = redact_resp.get_json()["result_url"]
        result_resp = client.get(result_url)
        assert result_resp.status_code == 200
        assert result_resp.mimetype == "image/png"


class TestGeneralEndpoints:
    def test_analyze_general_returns_ocr_text(self, client):
        img = _make_test_image(text_lines=["Hello World"])
        resp = client.post("/api/analyze-general", data={
            "file": (img, "test.png")
        }, content_type="multipart/form-data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "ocr_text" in data

    def test_redact_general_works(self, client):
        img = _make_test_image(text_lines=["Test"])
        analyze_resp = client.post("/api/analyze-general", data={
            "file": (img, "test.png")
        }, content_type="multipart/form-data")
        session_id = analyze_resp.get_json()["session_id"]

        resp = client.post("/api/redact-general",
            content_type="application/json",
            data=json.dumps({
                "session_id": session_id,
                "regions": [{"x1": 10, "y1": 10, "x2": 100, "y2": 100}],
                "mode": "redact",
            }))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "result_url" in data


class TestIndexEndpoint:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Anonymation" in resp.data or b"RGPD" in resp.data
