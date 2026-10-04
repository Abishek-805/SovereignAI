import hashlib
import math
from pathlib import Path

import pymupdf

from backend.contracts import Chunk
from rag.ingest import extract
from rag.pdf_visuals import enrich_pdf_chunks, overall_star_rating


def rating_pdf(filled=5, label='Overall Rating'):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((150, 50), label, fontsize=14)
    page.insert_text((150, 140), 'Excellent Very Good Good', fontsize=11)
    for index in range(5):
        center_x, center_y = 130 + index * 23, 83
        points = []
        for corner in range(10):
            angle = -math.pi / 2 + corner * math.pi / 5
            radius = 10 if corner % 2 == 0 else 4.4
            points.append(pymupdf.Point(center_x + radius * math.cos(angle),
                                        center_y + radius * math.sin(angle)))
        shape = page.new_shape()
        shape.draw_polyline(points + [points[0]])
        shape.finish(fill=(0, .5, 0) if index < filled else (.75, .75, .75), color=None)
        shape.commit()
    result = document.tobytes()
    document.close()
    return result


def test_overall_vector_stars_are_extractable_and_usable_by_existing_index(tmp_path):
    data = rating_pdf()
    digest = hashlib.sha256(data).hexdigest()
    source_dir = tmp_path / 'sources'
    source_dir.mkdir()
    path = source_dir / f'{digest}.pdf'
    path.write_bytes(data)
    assert '5 out of 5 filled stars (Excellent)' in overall_star_rating(data, 1)
    assert '5 out of 5 filled stars (Excellent)' in extract(path).pages[0].text
    chunk = Chunk('c1', 'd1', digest, 'assessment.pdf', 'Overall Rating Excellent Very Good Good',
                  1, None, None)
    augmented = enrich_pdf_chunks([chunk], source_dir)[0]
    assert '5 out of 5 filled stars (Excellent)' in augmented.text
    assert chunk.text == 'Overall Rating Excellent Very Good Good'


def test_rating_extraction_requires_label_and_complete_star_scale():
    assert overall_star_rating(rating_pdf(filled=4), 1).startswith('Overall Rating: 4 out of 5 filled stars (Very Good)')
    assert overall_star_rating(rating_pdf(label='Decorative stars'), 1) is None
    assert overall_star_rating(rating_pdf(), 2) is None


def test_visual_enrichment_rejects_modified_snapshot(tmp_path):
    data = rating_pdf()
    digest = hashlib.sha256(data).hexdigest()
    path = Path(tmp_path) / f'{digest}.pdf'
    path.write_bytes(data + b'changed')
    chunk = Chunk('c1', 'd1', digest, 'assessment.pdf', 'Overall Rating', 1, None, None)
    assert enrich_pdf_chunks([chunk], tmp_path)[0].text == 'Overall Rating'
