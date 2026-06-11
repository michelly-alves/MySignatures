from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.models.accumulator import AccumulatorElement, AccumulatorState, Witness
from app.models.digital_signature import DigitalSignature
from app.models.document import Document
from app.models.signer import Signer
from app.services.accumulator_service import state_fingerprint

_BRT = ZoneInfo("America/Sao_Paulo")


def _to_brt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BRT)


def create_signed_pdf_seal(
    document: Document,
    signer: Signer,
    signature: DigitalSignature,
    state: AccumulatorState,
    element: AccumulatorElement,
    witness: Witness,
    previous_state: AccumulatorState | None = None,
) -> str:
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

    output_dir = Path("uploads/signed")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"signed-{signature.validation_code}-{source_path.name}"

    overlay_path = output_dir / f"seal-{signature.validation_code}.pdf"

    try:
        reader = PdfReader(str(source_path))
        last_page_box = reader.pages[-1].mediabox
        page_width  = float(last_page_box.width)
        page_height = float(last_page_box.height)

        c = canvas.Canvas(str(overlay_path), pagesize=(page_width, page_height))

        seal_height = 64 * mm
        margin_x = 15 * mm
        content_width = page_width - 2 * margin_x

        c.setFillColor(colors.HexColor("#F3FAF4"))
        c.rect(0, 0, page_width, seal_height, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#2E7D32"))
        c.setLineWidth(1)
        c.line(0, seal_height, page_width, seal_height)

        c.setFillColor(colors.HexColor("#1B5E20"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin_x, 56 * mm, "DOCUMENTO ASSINADO ELETRONICAMENTE")

        signed_at_utc = signature.signed_at or datetime.now(tz=timezone.utc)
        signed_at_text = _to_brt(signed_at_utc).strftime("%d/%m/%Y %H:%M:%S") + " (BRT)"

        if witness.is_valid is True:
            valid_label = "verificada"
        elif witness.is_valid is False:
            valid_label = "INVÁLIDA — consulte o portal de validação"
        else:
            valid_label = "não verificada — consulte o portal de validação"

        c.setFillColor(colors.HexColor("#263238"))
        c.setFont("Helvetica", 9)
        c.drawString(margin_x, 48 * mm, f"Assinado por: {signer.full_name}")
        c.drawString(margin_x, 43 * mm, f"Data/hora: {signed_at_text}")
        c.drawString(margin_x, 38 * mm, f"Código de validação: {signature.validation_code}")
        c.drawString(margin_x, 33 * mm, f"Prova de pertencimento ao acumulador RSA: {valid_label}")

        c.setFont("Helvetica", 8)
        c.drawString(margin_x, 27 * mm, "Hash SHA-256 do documento original:")
        c.setFont("Courier", 7)
        c.drawString(margin_x, 23 * mm, document.hash_sha256)

        if previous_state is not None:
            previous_label = (
                f"anterior #{previous_state.state_id}: "
                f"{state_fingerprint(previous_state.state_value_hex)}"
            )
        else:
            previous_label = "anterior: estado inicial do acumulador"

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#263238"))
        c.drawString(
            margin_x, 17 * mm,
            "Vínculo de cadeia do acumulador (SHA-256 dos estados — confira no registro público):",
        )
        c.setFont("Courier", 7)
        c.drawString(
            margin_x, 13 * mm,
            f"estado   #{state.state_id}: {state_fingerprint(state.state_value_hex)}",
        )
        c.drawString(margin_x, 9 * mm, previous_label)

        c.setFont("Helvetica-Oblique", 7)
        c.setFillColor(colors.HexColor("#2E7D32"))
        c.drawString(margin_x, 4 * mm, f"Verifique em: {signature.validation_url or ''}")

        del content_width
        c.save()

        overlay_reader = PdfReader(str(overlay_path))
        overlay_page   = overlay_reader.pages[0]
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
