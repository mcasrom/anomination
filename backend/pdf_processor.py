import os
import tempfile
from PIL import Image
import io

try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False


def pdf_to_images(pdf_path: str, dpi: int = 200) -> list:
    if not PDF2IMAGE_AVAILABLE:
        raise ImportError("pdf2image no está instalado")
    return convert_from_path(pdf_path, dpi=dpi)


def image_to_pdf(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format='PDF')
    return buf.getvalue()


def images_to_pdf(images: list, output_path: str):
    if not images:
        return
    first = images[0]
    if first.mode != 'RGB':
        first = first.convert('RGB')
    rest = []
    for img in images[1:]:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        rest.append(img)
    first.save(output_path, save_all=True, append_images=rest)


def redact_pdf_page(pdf_path: str, page_num: int, boxes: list, mode: str = "watermark",
                    output_path: str = None) -> str:
    if not PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF no está instalado")

    doc = fitz.open(pdf_path)
    if page_num < 0 or page_num >= len(doc):
        doc.close()
        raise ValueError(f"Número de página inválido: {page_num}")

    page = doc[page_num]
    page_rect = page.rect

    for (x1, y1, x2, y2) in boxes:
        rect = fitz.Rect(x1, y1, x2, y2)
        if mode == "redact":
            page.add_redact_annot(rect, fill=(0.78, 0.16, 0.16, 0.8))
            page.apply_redactions()
        elif mode == "watermark":
            page.add_redact_annot(rect, fill=(0.78, 0.16, 0.16, 0.6))
            page.apply_redactions()
            page.insert_textbox(
                rect,
                "DATOS EXCESIVOS (RGPD)",
                fontsize=8,
                color=(1, 1, 1),
                align=1,
                fill=None,
            )
        else:
            from PIL import ImageFilter
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            x1_px = int(x1 * pix.width / page_rect.width)
            y1_px = int(y1 * pix.height / page_rect.height)
            x2_px = int(x2 * pix.width / page_rect.width)
            y2_px = int(y2 * pix.height / page_rect.height)
            region = img.crop((x1_px, y1_px, x2_px, y2_px))
            region = region.filter(ImageFilter.GaussianBlur(radius=8))
            img.paste(region, (x1_px, y1_px))
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            page_images = convert_from_path(
                pdf_path, dpi=150, first_page=page_num + 1, last_page=page_num + 1
            )
            page_images[0] = img
            images_to_pdf(page_images, output_path if output_path else pdf_path)
            doc.close()
            return output_path if output_path else pdf_path

    if output_path:
        doc.save(output_path, garbage=4, deflate=True)
    else:
        doc.save(pdf_path, garbage=4, deflate=True)
    doc.close()
    return output_path if output_path else pdf_path


def redact_pdf_all_pages(pdf_path: str, page_boxes: dict, mode: str = "watermark",
                         output_path: str = None) -> str:
    if not output_path:
        base, ext = os.path.splitext(pdf_path)
        output_path = f"{base}_redacted{ext}"

    doc = fitz.open(pdf_path)
    for page_num, boxes in page_boxes.items():
        if not boxes:
            continue
        page = doc[page_num]
        page_rect = page.rect
        for (x1, y1, x2, y2) in boxes:
            rect = fitz.Rect(x1, y1, x2, y2)
            if mode == "redact":
                page.add_redact_annot(rect, fill=(0.78, 0.16, 0.16, 0.8))
                page.apply_redactions()
            elif mode == "watermark":
                page.add_redact_annot(rect, fill=(0.78, 0.16, 0.16, 0.6))
                page.apply_redactions()
                page.insert_textbox(
                    rect,
                    "DATOS EXCESIVOS (RGPD)",
                    fontsize=8,
                    color=(1, 1, 1),
                    align=1,
                )

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def get_pdf_page_count(pdf_path: str) -> int:
    if not PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF no está instalado")
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


def get_pdf_page_size(pdf_path: str, page_num: int = 0) -> tuple:
    if not PYMUPDF_AVAILABLE:
        raise ImportError("PyMuPDF no está instalado")
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    rect = page.rect
    doc.close()
    return (int(rect.width), int(rect.height))
