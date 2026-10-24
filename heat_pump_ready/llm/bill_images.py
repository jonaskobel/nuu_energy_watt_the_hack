"""Prepare bill photos and bounded PDF pages as in-memory vision attachments."""

import io

from ..contracts import Attachment
from .interfaces import RunnerError

MAX_BILL_PAGES = 6


def prepare_bill_images(attachments: tuple) -> tuple:
    """Return JPG/PNG images, rendering PDFs locally with at most six pages total.

    Args: validated bill attachments (photos or PDFs).
    Returns: image attachments with original file/page names; nothing is persisted.
    Raises: RunnerError for unreadable files, missing PDF support or excess pages.
    """
    images = []
    for attachment in attachments:
        if attachment.media_type == 'application/pdf':
            images.extend(render_bill_pdf(attachment, MAX_BILL_PAGES - len(images)))
        elif attachment.media_type in ('image/jpeg', 'image/png'):
            images.append(attachment)
        else:
            raise RunnerError('Rechnung bitte als JPG, PNG oder PDF hochladen.')
        if len(images) > MAX_BILL_PAGES:
            raise RunnerError('Bitte insgesamt höchstens sechs Rechnungsseiten hochladen.')
    return tuple(images)


def render_bill_pdf(attachment: Attachment, remaining_pages: int) -> tuple:
    """Render every PDF page to a bounded JPEG without retaining document handles."""
    try:
        import pypdfium2 as pdfium
    except ImportError as error:
        raise RunnerError(
            'Für Rechnungs-PDFs pypdfium2 installieren oder ein JPG/PNG-Foto verwenden.'
        ) from error
    try:
        with pdfium.PdfDocument(attachment.content) as document:
            if not 0 < len(document) <= remaining_pages:
                raise RunnerError('Bitte insgesamt höchstens sechs Rechnungsseiten hochladen.')
            images = []
            for index in range(len(document)):
                page = document[index]
                bitmap = None
                image = None
                try:
                    width, height = page.get_size()
                    if min(width, height) <= 0:
                        raise RunnerError('Rechnungs-PDF enthält eine ungültige Seite.')
                    scale = min(2.5, 2200 / max(width, height))
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil().convert('RGB')
                    content = io.BytesIO()
                    image.save(content, format='JPEG', quality=90)
                    images.append(Attachment(
                        f'{attachment.name} · Seite {index + 1}',
                        'image/jpeg', 'bill', content.getvalue(),
                    ))
                finally:
                    if image is not None:
                        image.close()
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
            return tuple(images)
    except RunnerError:
        raise
    except Exception as error:
        raise RunnerError('Rechnungs-PDF konnte nicht gelesen werden. Bitte ein lesbares Foto verwenden.') from error
