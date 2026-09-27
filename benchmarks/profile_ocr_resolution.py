"""Compare warm local OCR quality and time at two PDF render resolutions."""
import json
from pathlib import Path
from time import perf_counter

from backend.service import Workbench
from rag.ocr import render_pdf_page, ocr_image, extract_text_from_observations, _engine


def main():
    workbench=Workbench()
    document=next(item for item in workbench.documents() if item['display_name']=='sih-scanned-inspection.pdf')
    data=(workbench.settings.data_dir/'sources'/(document['active_hash']+'.pdf')).read_bytes()
    _engine()
    results=[]
    for dpi in (100,150):
        started=perf_counter()
        image=render_pdf_page(data,1,dpi=dpi)
        observations=ocr_image(image)
        text=extract_text_from_observations(observations)
        results.append({'dpi':dpi,'seconds':round(perf_counter()-started,3),
                        'pixels':list(image.size),'text':text,
                        'measurement_found':'P-101 vibration measured 8.2 mm/s' in text})
    target=Path(__file__).with_name('ocr-resolution-20260925.json')
    target.write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(results,indent=2))


if __name__=='__main__':
    main()
