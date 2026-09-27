"""Extract narrowly verifiable visual facts omitted by PDF text layers."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path


def overall_star_rating(pdf_bytes: bytes, page_number: int) -> str | None:
    """Read a five-star rating only when five vector stars sit under its label."""
    try:
        import pymupdf

        with pymupdf.open(stream=pdf_bytes, filetype='pdf') as document:
            if not 1 <= page_number <= len(document):
                return None
            page = document[page_number - 1]
            labels = page.search_for('Overall Rating')
            if not labels:
                return None
            drawings = page.get_drawings()
            for label in labels:
                stars = []
                for drawing in drawings:
                    box = drawing['rect']
                    fill = drawing.get('fill')
                    if (drawing.get('type') != 'f' or fill is None
                            or len(drawing['items']) != 10
                            or not all(item[0] == 'l' for item in drawing['items'])
                            or not 5 <= box.width <= 50 or not 5 <= box.height <= 50
                            or box.x0 < label.x0 - 40 or box.x1 > label.x1 + 40
                            or box.y0 < label.y1 + 4 or box.y1 > label.y1 + 55):
                        continue
                    red, green, blue = fill
                    filled = green > .25 and green > red * 1.2 and green > blue * 1.2
                    empty = .5 <= red <= .95 and abs(red - green) < .08 and abs(red - blue) < .08
                    if filled or empty:
                        stars.append((box.x0, box.y0, filled))
                stars.sort()
                if (len(stars) != 5 or max(y for _, y, _ in stars) - min(y for _, y, _ in stars) > 4
                        or any(right[0] - left[0] < 5 for left, right in zip(stars, stars[1:]))):
                    continue
                count = sum(filled for _, _, filled in stars)
                if not count:
                    continue
                legend = {5: 'Excellent', 4: 'Very Good', 3: 'Good'}.get(count)
                text = page.get_text()
                label_text = f' ({legend})' if legend and legend in text else ''
                return f'Overall Rating: {count} out of 5 filled stars{label_text}.'
    except (ImportError, RuntimeError, ValueError, OSError, KeyError, TypeError):
        return None
    return None


def enrich_pdf_chunks(chunks, source_dir: Path):
    """Add verified visual rating evidence to existing indexed PDF passages."""
    notes = {}
    enriched = []
    for chunk in chunks:
        if chunk.page is None or not chunk.display_name.lower().endswith('.pdf'):
            enriched.append(chunk)
            continue
        key = (chunk.version_hash, chunk.page)
        if key not in notes:
            path = source_dir / f'{chunk.version_hash}.pdf'
            try:
                data = path.read_bytes() if path.is_file() and not path.is_symlink() else b''
                notes[key] = overall_star_rating(data, chunk.page) if sha256(data).hexdigest() == chunk.version_hash else None
            except OSError:
                notes[key] = None
        note = notes[key]
        enriched.append(replace(chunk, text=f'{chunk.text}\n[Visual PDF evidence: {note}]')
                        if note and note not in chunk.text else chunk)
    return enriched
