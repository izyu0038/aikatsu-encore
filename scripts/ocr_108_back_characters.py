"""Read-only character-name OCR from 108 Aikatsu Encore card backs.
Outputs review files only; never edits data/official_cards.json.
"""
import csv, io, json, re, subprocess, tempfile, urllib.request, base64, html
from pathlib import Path
from difflib import SequenceMatcher
from PIL import Image, ImageEnhance, ImageOps, ImageFilter

SOURCE = Path('data/108_character_verification.csv')
REF = Path('data/idol_character_reference_candidates.csv')
OUT = Path('diagnostic_output/character_back_ocr_108')
OUT.mkdir(parents=True, exist_ok=True)


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def back_url(front):
    if not re.search(r'\.webp(?:\?.*)?$', front, re.I):
        raise ValueError('Unexpected front image URL')
    return re.sub(r'\.webp(?=\?|$)', '_b.webp', front, flags=re.I)


def fetch(url):
    if not url.startswith('https://dcd.aikatsu.com/encore/images/cardlist/card/'):
        raise ValueError('Unexpected card image host/path')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(8_000_001)
    if len(data) > 8_000_000:
        raise ValueError('Image too large')
    im = Image.open(io.BytesIO(data))
    im.load()
    return im.convert('RGB')


def zone_specs(cid):
    # Card layouts from supplied E1-04_PR (accessory), E1-31_ER, E1-54_R.
    # Include alternate zones: rarity alone does not reliably identify accessories.
    accessory = ('accessory', (.16, .83, .47, .97))
    encore = ('encore_rare', (.16, .00, .59, .105))
    standard = ('standard', (.60, .005, .96, .115))
    if cid.upper().endswith('_ER'):
        return [encore, standard, accessory]
    return [standard, accessory, encore]


def crop_fraction(im, rect):
    w, h = im.size
    return im.crop((int(rect[0]*w), int(rect[1]*h), int(rect[2]*w), int(rect[3]*h)))


def ocr(im, psm):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'crop.png'
        im.save(path)
        r = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'jpn+eng', '--psm', str(psm)],
                           capture_output=True, text=True, timeout=30)
        if r.returncode:
            raise RuntimeError(r.stderr.strip()[:180])
        return r.stdout.strip()


def process(im):
    gray = ImageOps.autocontrast(ImageOps.grayscale(im))
    gray = gray.resize((gray.width*3, gray.height*3), Image.Resampling.LANCZOS)
    sharp = ImageEnhance.Contrast(gray).enhance(1.7).filter(ImageFilter.UnsharpMask(radius=1, percent=150))
    return [gray, sharp]


def normalize(s):
    return re.sub(r'[\s\W_]+', '', s, flags=re.UNICODE)


def suggestions(readings, names):
    scores = {}
    for name in names:
        target = normalize(name)
        if len(target) < 2:
            continue
        best = 0.0
        for reading in readings:
            raw = normalize(reading['text'])
            if not raw:
                continue
            if target in raw:
                best = max(best, 1.0)
            else:
                for i in range(max(1, len(raw)-len(target)+1)):
                    fragment = raw[i:i+len(target)]
                    best = max(best, SequenceMatcher(None, target, fragment).ratio())
        if best >= .48:
            scores[name] = round(best, 3)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:5]


def thumb(im):
    im = im.copy()
    im.thumbnail((460, 160))
    buf = io.BytesIO()
    im.save(buf, format='JPEG', quality=76)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f'Missing {SOURCE}')
    cards = rows(SOURCE)
    if len(cards) != 108:
        raise ValueError(f'Expected 108 cards, found {len(cards)}. Stop to avoid incomplete run.')
    names = sorted({r.get('character_candidate', '').strip() for r in rows(REF) if r.get('character_candidate', '').strip()}) if REF.exists() else []
    # This is a candidate dictionary, not an exhaustive list of all possible characters.
    output, errors = [], []
    for index, card in enumerate(cards, 1):
        cid = card['card_id'].strip()
        try:
            url = back_url(card['card_image'].strip())
            im = fetch(url)
            readings, zones = [], []
            for label, rect in zone_specs(cid):
                cropped = crop_fraction(im, rect)
                zones.append({'zone': label, 'image': thumb(cropped)})
                for vi, variant in enumerate(process(cropped)):
                    for psm in (6, 7):
                        result = ocr(variant, psm)
                        readings.append({'zone': label, 'variant': vi, 'psm': psm, 'text': result})
            candidates = suggestions(readings, names)
            output.append({'card_id': cid, 'card_name': card.get('card_name', ''), 'back_url': url,
                           'zones': zones, 'readings': readings, 'suggestions': candidates})
        except Exception as exc:
            errors.append({'card_id': cid, 'error': str(exc)[:250]})
            output.append({'card_id': cid, 'card_name': card.get('card_name', ''), 'error': str(exc)[:250],
                           'zones': [], 'readings': [], 'suggestions': []})
        print(f'[{index}/{len(cards)}] {cid}', flush=True)

    with (OUT / 'character_back_ocr_108.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['card_id', 'card_name', 'suggested_name_1', 'suggested_name_2', 'suggested_name_3',
                         'best_similarity', 'ocr_text', 'confirmed_character', 'review_status', 'back_url'])
        for item in output:
            s = item['suggestions']
            writer.writerow([item['card_id'], item['card_name'], *([x[0] for x in s[:3]] + ['']*3)[:3],
                             s[0][1] if s else '', ' | '.join(f"{r['zone']}: {r['text']}" for r in item['readings']),
                             '', '未確認', item.get('back_url', '')])
    summary = {'target_cards': len(cards), 'processed': len(output)-len(errors), 'errors': errors,
               'reference_name_count': len(names), 'automatically_confirmed': 0,
               'note': 'All names are OCR suggestions only. No site data changed.'}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'raw_ocr.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    # Self-contained visual review: names shown with each crop, no script/network required.
    parts = ['<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>108枚 裏面キャラクター名確認</title><style>body{font-family:system-ui,sans-serif;max-width:1050px;margin:auto;padding:14px;background:#fff8fb;color:#333}article{background:white;border:1px solid #e6dce3;border-radius:12px;margin:12px 0;padding:12px}.zones{display:flex;flex-wrap:wrap;gap:12px}.zone{max-width:460px}.zone img{max-width:100%;display:block}pre{white-space:pre-wrap;word-break:break-all;background:#f7f4f7;padding:8px}h1{font-size:1.4rem}</style>',
             '<h1>108枚 カード裏面の名前を確認</h1><p>上部・アクセサリー左下・ER左上の3か所を全カードで調査しています。候補は未確認です。実際の画像と照合してください。既存サイトは変更していません。</p>']
    for item in output:
        parts.append('<article><h2>'+html.escape(item['card_id'])+'</h2><p>候補：'+html.escape(' / '.join(f'{n} ({score})' for n,score in item['suggestions']) or '候補なし')+'</p>')
        if item.get('error'):
            parts.append('<p>取得失敗：'+html.escape(item['error'])+'</p>')
        parts.append('<div class="zones">')
        for zone in item['zones']:
            parts.append('<div class="zone"><b>'+html.escape(zone['zone'])+'</b><img src="'+zone['image']+'"></div>')
        parts.append('</div><details><summary>OCRの読み取り結果</summary><pre>'+html.escape('\n'.join(f"{r['zone']}/{r['variant']}/{r['psm']}: {r['text']}" for r in item['readings']))+'</pre></details></article>')
    parts.append('</html>')
    (OUT / 'review_character_back_108.html').write_text('\n'.join(parts), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
