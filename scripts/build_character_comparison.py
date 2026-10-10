"""Read-only visual comparison sheets for card characters and official reference portraits."""
import csv
import io
import json
import re
import time
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT = Path('diagnostic_output/character_comparison')
OUT.mkdir(parents=True, exist_ok=True)
CSV = Path('data/idol_character_reference_candidates.csv')
CARD_DIR = Path('diagnostic_output/card_image_samples')
FONT_CANDIDATES = ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
font_path = next((x for x in FONT_CANDIDATES if Path(x).exists()), None)
font = ImageFont.truetype(font_path, 16) if font_path else ImageFont.load_default()


def sheet(items, name, columns=6, width=180, height=245):
    for start in range(0, len(items), 48):
        batch = items[start:start+48]
        rows = (len(batch)+columns-1)//columns
        canvas = Image.new('RGB', (columns*width, rows*height), 'white')
        draw = ImageDraw.Draw(canvas)
        for i, (label, im) in enumerate(batch):
            x = (i%columns)*width; y=(i//columns)*height
            thumb = ImageOps.contain(im.convert('RGB'), (width-12, height-42))
            canvas.paste(thumb, (x+(width-thumb.width)//2, y+4))
            draw.text((x+5,y+height-34), label[:22], fill='black', font=font)
        canvas.save(OUT/f'{name}_{start//48+1:02d}.jpg', quality=90)


def main():
    if not CSV.exists():
        raise FileNotFoundError(f'Missing {CSV}; upload the reference CSV to data/ first')
    with CSV.open(encoding='utf-8-sig', newline='') as f:
        refs = list(csv.DictReader(f))
    results=[]; reference_images=[]
    for n, row in enumerate(refs,1):
        url=row['image_url']; name=row['character_candidate']
        entry={'index':n,'character_candidate':name,'image_url':url,'status':'error'}
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; character-reference-diagnostic/1.0)'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content=resp.read(6_000_000)
            im=Image.open(io.BytesIO(content)); im.load()
            reference_images.append((f'{n:03d} {name}',im))
            entry['status']='ok'
        except Exception as e:
            entry['error']=str(e)[:250]
        results.append(entry)
        time.sleep(0.1)
    sheet(reference_images,'official_references')
    cards=[]
    for p in sorted(CARD_DIR.glob('*.webp')):
        if p.stem.endswith('_b'): continue
        try:
            with Image.open(p) as im: cards.append((p.stem, im.copy()))
        except Exception: pass
    sheet(cards,'card_fronts')
    summary={'reference_candidates':len(refs),'reference_downloaded':len(reference_images), 'card_fronts_found':len(cards),'note':'Visual review only. No automated character assignment; no production files changed.','references':results}
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='references'},ensure_ascii=False))

if __name__=='__main__': main()
