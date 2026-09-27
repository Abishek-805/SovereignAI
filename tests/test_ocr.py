import pytest
from PIL import Image
import io
import pytesseract
from rag.ocr import is_ocr_available, ocr_image, extract_text_from_observations
from rag.ingest import extract
import pymupdf
from PIL import ImageDraw, ImageFont

def test_ocr_availability():
    # If missing, should return false without exception
    available = is_ocr_available()
    assert isinstance(available, bool)

def test_ocr_image_missing_engine(monkeypatch):
    monkeypatch.setattr("rag.ocr.is_ocr_available", lambda: False)
    img = Image.new('RGB', (100, 100))
    obs = ocr_image(img)
    assert obs == []
    
    text = extract_text_from_observations(obs)
    assert text == ""

def test_extract_text():
    from rag.ocr import OcrObservation
    obs = [
        OcrObservation(text="Pump", confidence=95.0, box=(0,0,10,10)),
        OcrObservation(text="P-101", confidence=90.0, box=(15,0,20,10))
    ]
    assert extract_text_from_observations(obs) == "Pump P-101"


def test_scanned_page_is_searchable_with_physical_page_and_method(tmp_path):
    image = Image.new('RGB', (1200, 300), 'white')
    ImageDraw.Draw(image).text((30,60),'P-101 vibration 8.2 mm/s',
                               font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',58),fill='black')
    from io import BytesIO
    buffer=BytesIO(); image.save(buffer,format='PNG')
    doc=pymupdf.open(); doc.new_page().insert_text((80,80),'Text layer page one')
    doc.new_page(width=600,height=200).insert_image(pymupdf.Rect(0,0,600,150),stream=buffer.getvalue())
    source=tmp_path/'mixed.pdf'; source.write_bytes(doc.tobytes()); doc.close()
    result=extract(source)
    assert len(result.pages)==2
    assert result.pages[1].page==2
    assert result.pages[1].method=='ocr'
    assert 'P-101 vibration 8.2 mm/s' in result.pages[1].text
    assert result.pages[1].confidence is not None
