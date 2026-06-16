from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.models.accumulator import AccumulatorState
from app.models.document import Document
from app.services.accumulator_service import state_fingerprint

_BRT = ZoneInfo("America/Sao_Paulo")


def _to_brt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BRT)


def create_signed_pdf_seal(
    document: Document,
    entries: list[dict],
    state: AccumulatorState,
    previous_state: AccumulatorState | None = None,
) -> str:
    """
    Carimba a última página do PDF com o selo consolidado de assinatura.

    ``entries`` é a lista de TODOS os signatários que assinaram o documento
    (modelo paralelo), cada um com ``full_name``, ``signed_at``,
    ``validation_code`` e ``validation_url``. O selo lista cada signatário,
    o hash do documento original, o elo atual da cadeia do acumulador e um
    link clicável para a tela de validação.
    """
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "Dependências para carimbo do PDF ausentes. Instale: pypdf reportlab tzdata"
        ) from exc

    source_path = Path(document.file_path)
    if not source_path.exists():
        raise RuntimeError("Arquivo original do documento não encontrado para carimbo")

    # Referência (assinatura mais recente) para nomear arquivos e o link.
    last_code = entries[-1]["validation_code"] if entries else "doc"
    verify_url = (entries[-1].get("validation_url") if entries else "") or ""

    output_dir = Path("uploads/signed")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"signed-{last_code}-{source_path.name}"
    overlay_path = output_dir / f"seal-{last_code}.pdf"

    try:
        reader = PdfReader(str(source_path))
        last_page_box = reader.pages[-1].mediabox
        page_width = float(last_page_box.width)
        page_height = float(last_page_box.height)

        # Altura dinâmica: cresce com o número de signatários, sem ultrapassar
        # 60% da página.
        seal_height = min((50 + 5 * len(entries)) * mm, page_height * 0.6)
        margin_x = 15 * mm

        c = canvas.Canvas(str(overlay_path), pagesize=(page_width, page_height))
        c.setFillColor(colors.HexColor("#F3FAF4"))
        c.rect(0, 0, page_width, seal_height, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#2E7D32"))
        c.setLineWidth(1)
        c.line(0, seal_height, page_width, seal_height)

        # Cursor vertical (desenha de cima para baixo).
        y = seal_height - 8 * mm
        c.setFillColor(colors.HexColor("#1B5E20"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin_x, y, "DOCUMENTO ASSINADO ELETRONICAMENTE")

        y -= 6 * mm
        c.setFillColor(colors.HexColor("#263238"))
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin_x, y, f"Signatário(s): {len(entries)}")

        c.setFont("Helvetica", 8)
        for entry in entries:
            y -= 5 * mm
            signed_at = entry.get("signed_at") or datetime.now(tz=timezone.utc)
            signed_at_text = _to_brt(signed_at).strftime("%d/%m/%Y %H:%M")
            name = entry.get("full_name") or "—"
            code = entry.get("validation_code") or "—"
            c.drawString(
                margin_x, y,
                f"•  {name}  —  {signed_at_text} (BRT)  —  código {code}",
            )

        y -= 7 * mm
        c.setFont("Helvetica", 8)
        c.drawString(margin_x, y, "Hash SHA-256 do documento original:")
        y -= 4 * mm
        c.setFont("Courier", 7)
        c.drawString(margin_x, y, document.hash_sha256)

        if previous_state is not None:
            previous_label = (
                f"anterior #{previous_state.state_id}: "
                f"{state_fingerprint(previous_state.state_value_hex)}"
            )
        else:
            previous_label = "anterior: estado inicial do acumulador"

        y -= 6 * mm
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#263238"))
        c.drawString(
            margin_x, y,
            "Vínculo de cadeia do acumulador (SHA-256 dos estados — confira no registro público):",
        )
        y -= 4 * mm
        c.setFont("Courier", 7)
        c.drawString(
            margin_x, y,
            f"estado   #{state.state_id}: {state_fingerprint(state.state_value_hex)}",
        )
        y -= 4 * mm
        c.drawString(margin_x, y, previous_label)

        # Link clicável para a tela de validação (assinatura mais recente).
        y -= 5 * mm
        label = "Verifique em: "
        c.setFont("Helvetica-Oblique", 7)
        c.setFillColor(colors.HexColor("#263238"))
        c.drawString(margin_x, y, label)
        if verify_url:
            label_width = c.stringWidth(label, "Helvetica-Oblique", 7)
            url_x = margin_x + label_width
            url_width = c.stringWidth(verify_url, "Helvetica-Oblique", 7)
            c.setFillColor(colors.HexColor("#1565C0"))
            c.drawString(url_x, y, verify_url)
            c.setStrokeColor(colors.HexColor("#1565C0"))
            c.setLineWidth(0.4)
            c.line(url_x, y - 1, url_x + url_width, y - 1)
            c.linkURL(
                verify_url,
                (url_x, y - 1.5, url_x + url_width, y + 7),
                relative=0,
                thickness=0,
            )

        c.save()

        overlay_reader = PdfReader(str(overlay_path))
        overlay_page = overlay_reader.pages[0]
        writer = PdfWriter()

        for index, page in enumerate(reader.pages):
            if index == len(reader.pages) - 1:
                page.merge_page(overlay_page)
            writer.add_page(page)

        with output_path.open("wb") as output_file:
            writer.write(output_file)

    finally:
        overlay_path.unlink(missing_ok=True)

    return str(output_path)
