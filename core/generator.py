"""Generación de constancias en PDF.

Sobre una plantilla (imagen PNG/JPG o PDF) se escribe el nombre del participante
en la posición indicada. Las posiciones se guardan como proporciones (0 a 1) de la
página, así funcionan igual con cualquier tamaño de plantilla.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from pathlib import Path

import pymupdf as fitz  # PyMuPDF: solo se usa para la vista previa
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BUILTIN_FONTS = {
    "Helvetica Negrita": "Helvetica-Bold",
    "Helvetica": "Helvetica",
    "Times Negrita": "Times-Bold",
    "Times": "Times-Roman",
    "Times Cursiva": "Times-Italic",
    "Courier": "Courier",
}

ROLES = ["Asistentes", "Ponentes", "Comité Organizador", "Comité de Logística"]

DEFAULT_STYLE = {
    "font": "Times Negrita",
    "size": 32,
    "color": "#1F2A44",
    "align": "center",  # left | center | right
    "x": 0.5,           # proporción del ancho (para center = punto central)
    "y": 0.50,          # proporción desde ARRIBA
    "max_w": 0.70,      # ancho máximo del texto (proporción); reduce la fuente si no cabe
    "case": "Tipo título",  # Tipo título | MAYÚSCULAS | Tal cual
}

_PARTICLES = {"de", "del", "la", "las", "los", "y", "e", "van", "von", "da", "do", "dos"}


# ----------------------------------------------------------------- utilidades
def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn"
    )


def slugify(s: str) -> str:
    s = strip_accents(s).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s or "sin_nombre"


def normalize_role(value: str) -> str | None:
    """Convierte 'asistente', 'Comite organizador', 'LOGISTICA'... al rol oficial."""
    v = strip_accents(str(value)).lower().strip()
    if not v or v == "nan":
        return None
    if v.startswith("asist"):
        return "Asistentes"
    if v.startswith("ponen") or v.startswith("confer") or v.startswith("speaker"):
        return "Ponentes"
    if "logist" in v:
        return "Comité de Logística"
    if "organiz" in v:
        return "Comité Organizador"
    return None


def format_name(name: str, case: str) -> str:
    name = re.sub(r"\s+", " ", str(name)).strip()
    if case == "MAYÚSCULAS":
        return name.upper()
    if case == "Tipo título":
        words = name.lower().split(" ")
        out = []
        for i, w in enumerate(words):
            out.append(w if (w in _PARTICLES and i > 0) else w[:1].upper() + w[1:])
        return " ".join(out)
    return name


_registered: set[str] = set()


def resolve_font(font_label: str, fonts_dir: Path | None) -> str:
    """Devuelve el nombre de fuente de ReportLab (registra TTF personalizadas)."""
    if font_label in BUILTIN_FONTS:
        return BUILTIN_FONTS[font_label]
    if fonts_dir:
        ttf = Path(fonts_dir) / f"{font_label}.ttf"
        if ttf.exists():
            key = f"{font_label}:{ttf.stat().st_mtime_ns}"
            if key not in _registered:
                pdfmetrics.registerFont(TTFont(font_label, str(ttf)))
                _registered.add(key)
            return font_label
    return BUILTIN_FONTS["Helvetica Negrita"]


# ------------------------------------------------------------------ generación
def make_certificate(template_path: str | Path, text: str, style: dict,
                     fonts_dir: Path | None = None) -> bytes:
    """Genera un PDF de una página con `text` sobre la plantilla."""
    st = {**DEFAULT_STYLE, **style}
    template_path = Path(template_path)
    is_pdf = template_path.suffix.lower() == ".pdf"

    if is_pdf:
        reader = PdfReader(str(template_path))
        base_page = reader.pages[0]
        pw = float(base_page.mediabox.width)
        ph = float(base_page.mediabox.height)
    else:
        with Image.open(template_path) as im:
            iw, ih = im.size
        pw = 842.0 if iw >= ih else 595.0  # A4 horizontal o vertical
        ph = pw * ih / iw

    font = resolve_font(st["font"], fonts_dir)
    shown = format_name(text, st["case"])
    size = float(st["size"])
    max_width_pts = float(st["max_w"]) * pw
    while size > 8 and pdfmetrics.stringWidth(shown, font, size) > max_width_pts:
        size -= 1

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    if not is_pdf:
        c.drawImage(ImageReader(str(template_path)), 0, 0, width=pw, height=ph, mask="auto")
    c.setFillColor(HexColor(st["color"]))
    c.setFont(font, size)
    x = float(st["x"]) * pw
    y = ph - float(st["y"]) * ph
    if st["align"] == "left":
        c.drawString(x, y, shown)
    elif st["align"] == "right":
        c.drawRightString(x, y, shown)
    else:
        c.drawCentredString(x, y, shown)
    c.save()

    if not is_pdf:
        return buf.getvalue()

    overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
    base = PdfReader(str(template_path)).pages[0]
    base.merge_page(overlay)
    writer = PdfWriter()
    writer.add_page(base)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def merge_pdfs(pdfs: list[bytes]) -> bytes:
    writer = PdfWriter()
    for data in pdfs:
        for page in PdfReader(io.BytesIO(data)).pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def zip_pdfs(files: dict[str, bytes]) -> bytes:
    """files: {nombre_archivo.pdf: bytes}"""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def render_preview(pdf_bytes: bytes, zoom: float = 1.3) -> bytes:
    """PNG de la primera página (para mostrar en pantalla)."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")
