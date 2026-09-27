import io
import logging
from dataclasses import dataclass
from typing import Optional

from PIL import Image
import pytesseract
import numpy as np
from pathlib import Path
from threading import Lock
from functools import lru_cache
try:
    from rapidocr import RapidOCR
    import rapidocr
except ImportError:
    RapidOCR = None
try:
    import pymupdf
except ImportError:
    pymupdf = None

logger = logging.getLogger(__name__)
_lock = Lock()


def _packaged_rapidocr():
    if RapidOCR is None:
        return False
    directory=Path(rapidocr.__file__).parent/'models'
    return all((directory/name).is_file() for name in (
        'PP-OCRv6_det_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx','PP-OCRv6_rec_small.onnx'))


@lru_cache(maxsize=1)
def _engine():
    return RapidOCR()

@dataclass
class OcrObservation:
    text: str
    confidence: float
    box: Optional[tuple[int, int, int, int]] = None
    engine: str = "tesseract"

def is_ocr_available() -> bool:
    if _packaged_rapidocr():
        return True
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

def render_pdf_page(pdf_bytes: bytes, page_num: int, dpi: int = 150) -> Image.Image:
    if pymupdf is None:
        raise RuntimeError("pymupdf not installed, cannot render PDF")
    
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if page_num < 1 or page_num > len(doc):
        raise ValueError(f"Page {page_num} out of bounds")
        
    page = doc[page_num - 1] # 0-indexed in pymupdf
    if page.rect.width*dpi/72 > 3500 or page.rect.height*dpi/72 > 3500:
        doc.close()
        raise ValueError('Page raster exceeds 3500 pixels per side at configured DPI')
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    doc.close()
    return img

def ocr_image(img: Image.Image) -> list[OcrObservation]:
    if not is_ocr_available():
        logger.warning("OCR engine (Tesseract) is not installed on this system. Cannot read image text.")
        return []
    
    if _packaged_rapidocr():
        with _lock:
            result=_engine()(np.asarray(img.convert('RGB')))
        observations=[]
        for text,score,points in zip(result.txts or (),result.scores or (),result.boxes if result.boxes is not None else ()):
            left=int(min(point[0] for point in points)); top=int(min(point[1] for point in points))
            right=int(max(point[0] for point in points)); bottom=int(max(point[1] for point in points))
            observations.append(OcrObservation(text=text,confidence=float(score)*100,box=(left,top,right,bottom),engine='rapidocr-onnx'))
        return observations
    # Use image_to_data for bounding boxes and confidence
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    
    observations = []
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if not text:
            continue
            
        conf = float(data['conf'][i])
        if conf < 0: 
            continue # Tesseract uses -1 for layout blocks
            
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        
        observations.append(OcrObservation(
            text=text,
            confidence=conf,
            box=(x, y, w, h)
        ))
        
    return observations

def extract_text_from_observations(observations: list[OcrObservation]) -> str:
    """Flatten observations to text for indexing."""
    return " ".join(obs.text for obs in observations)
