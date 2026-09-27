"""Small synthetic routed-vs-single-model smoke; not a held-out evaluation."""
import json
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

from rag.vision import ask_vision
from router.model_registry import ModelRegistry

ROOT = Path(__file__).resolve().parents[1]
TEXT_CASES = [
    {'question':'Inspection: Pump P-101 vibration measured 8.2 mm/s. What reading was measured? Answer concisely.',
     'expected':'8.2'},
    {'question':'SOP: investigate P-101 vibration above 7.1 mm/s. What is the investigation threshold? Answer concisely.',
     'expected':'7.1'},
    {'question':'Report: P-101 has no temperature reading. Is its temperature known? Answer concisely.',
     'expected':'not'},
]


def text_request(alias, question):
    started=time.perf_counter()
    response=httpx.post('http://127.0.0.1:8087/v1/chat/completions',json={
        'model':alias,'messages':[{'role':'user','content':question}],
        'temperature':0,'max_tokens':256},timeout=120,trust_env=False,follow_redirects=False)
    response.raise_for_status()
    payload=response.json()
    choice=payload['choices'][0]
    answer=choice['message']['content']
    return {'answer':answer,'seconds':time.perf_counter()-started,
            'finish_reason':choice.get('finish_reason'),'usage':payload.get('usage',{})}


def label_image():
    image=Image.new('RGB',(700,220),'white')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('arial.ttf',55)
    draw.text((35,25),'Pump P-101',font=font,fill='black')
    draw.text((35,105),'Vibration: 8.2 mm/s',font=font,fill='black')
    return image


def run():
    registry=ModelRegistry()
    registry.acquire_lease('text')
    routed_text=[]
    for case in TEXT_CASES:
        result=text_request('sovereign-text',case['question'])
        result['correct']=case['expected'].lower() in result['answer'].lower()
        routed_text.append(result)
    started=time.perf_counter()
    registry.acquire_lease('vision')
    switch_seconds=time.perf_counter()-started
    baseline_text=[]
    for case in TEXT_CASES:
        result=text_request('sovereign-vision',case['question'])
        result['correct']=case['expected'].lower() in result['answer'].lower()
        baseline_text.append(result)
    started=time.perf_counter()
    vision=ask_vision(label_image(),'What pump ID and vibration value are printed?')
    vision_result={'answer':vision['answer'],'seconds':time.perf_counter()-started,
                   'correct':'P-101' in vision['answer'] and '8.2' in vision['answer']}
    report={'scope':'synthetic smoke, not held-out',
            'text_cases':TEXT_CASES,'routed_text':routed_text,'single_vision_text':baseline_text,
            'vision_case':vision_result,'switch_text_to_vision_seconds':switch_seconds,
            'routed_total_seconds':sum(item['seconds'] for item in routed_text)+switch_seconds+vision_result['seconds'],
            'single_vision_total_seconds':sum(item['seconds'] for item in baseline_text)+vision_result['seconds']}
    destination=ROOT/'benchmarks'/'routing-smoke-result.json'
    destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
    registry.acquire_lease('text')
    return report


if __name__=='__main__':
    result=run()
    print(json.dumps({key:result[key] for key in ('switch_text_to_vision_seconds','routed_total_seconds','single_vision_total_seconds')},indent=2))
