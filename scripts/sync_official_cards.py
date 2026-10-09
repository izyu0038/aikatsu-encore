"""Official Encore card sync: verified IDs/images; no invented card metadata.

Fail safely: never remove existing data, never treat a successful HTTP request as
proof that the site's search filters worked, and report coverage limitations.
"""
from __future__ import annotations
import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
BASE = 'https://dcd.aikatsu.com/encore/cardlist/'
IMAGE_BASE = 'https://dcd.aikatsu.com/encore/images/cardlist/card/'
ID_PATTERN = r'(?:E[1-9]\d*-\d{2,3}|EP-\d{3})_(?:PR|ER|R|N)'
FRONT_RE = re.compile(r'(?:^|/)(%s)\.webp(?:[?#].*)?$' % ID_PATTERN, re.I)
SERIES_RE = re.compile(r'(?:\?|&|&amp;)series=(\d{4,12})', re.I)
RARITY = {'PR':'プレミアムレア','ER':'アンコールレア','R':'レア','N':'ノーマル'}

class CardPage(HTMLParser):
    def __init__(self):
        super().__init__(); self.images = {}; self.series_options = set(); self._in_select = False
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ('option', 'button'):
            value = d.get('data-value', d.get('value', ''))
            if value.isdigit() and len(value) >= 4:
                self.series_options.add(value)
        if tag not in ('img','a','source'): return
        for attr in ('src','data-src','data-original','data-lazy-src','href','srcset'):
            raw = html.unescape(d.get(attr,'')).replace('\\/','/')
            for candidate in raw.split(','):
                url = candidate.strip().split(' ')[0]
                m = FRONT_RE.search(url)
                if m and ('/images/cardlist/card/' in url or url.startswith(m.group(1))):
                    card_id = m.group(1).upper()
                    self.images[card_id] = (url, d.get('alt','').strip())

def fetch(url, fields=None):
    """Send the same form-encoded POST as the official search form."""
    headers = {'User-Agent':'Mozilla/5.0', 'Accept':'text/html'}
    if fields is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    body = urllib.parse.urlencode(fields).encode('utf-8') if fields is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as response:
        return response.read().decode('utf-8','replace')


def search_fields(series=''):
    return {'free':'', 'series':series, 'type':'', 'rarity':'',
            'category':'', 'brand':'', 'display':'1', 'sort':'1'}

def series_of(card_id):
    if card_id.startswith('EP-'): return 'プロモーションカード'
    return '第' + card_id.split('-',1)[0][1:] + '弾'

def parse(markup):
    p = CardPage(); p.feed(markup)
    # Discover future series from actual card IDs and selectable official series values.
    series_ids = set(SERIES_RE.findall(markup)) | p.series_options
    return p.images, series_ids

def candidate(card_id, alt):
    # A card ID and image are sufficient for a clearly marked provisional entry.
    name = re.sub(re.escape(card_id), '', alt, flags=re.I).strip(' -_　:：')
    if not name or name.lower() in ('card','カード','image','画像') or len(name)>90 or '<' in name:
        name = f'名称確認中（{card_id}）'
    rarity_code = card_id.rsplit('_',1)[-1]
    return {'id':card_id,'name':name,'rarityCode':rarity_code,'rarity':RARITY[rarity_code],
            'cardType':series_of(card_id),'front':IMAGE_BASE+card_id+'.webp',
            'back':IMAGE_BASE+card_id+'_b.webp','character':'確認中','type':'確認中',
            'brand':'確認中','category':'確認中','appealPoints':None}

def main():
    DATA.mkdir(exist_ok=True)
    target = DATA/'official_cards.json'
    old = json.loads(target.read_text('utf-8')) if target.exists() else {'cards':[]}
    existing = {str(c['id']).upper():c for c in old.get('cards',[]) if isinstance(c,dict) and c.get('id')}
    known_file = DATA/'known_cards.json'
    known_data = json.loads(known_file.read_text('utf-8')) if known_file.exists() else {'cards':[]}
    known_list = known_data.get('cards',[]) if isinstance(known_data,dict) else known_data
    known = {str(c.get('id') if isinstance(c,dict) else c).upper() for c in known_list}
    # The official form submits POST to ?search=true. In the verified
    # 2026-10-09 diagnostic, a blank series returned 113 cards (85 + 28 promos).
    # Do not use the obsolete 629002 code; the official promo code is 629901.
    pages = {}; errors = {}; discovered_series = set(); warnings = []
    sources = [('全カード（POST）', ''), ('プロモーションカード（POST）', '629901'),
               ('第1弾（POST）', '629001')]
    for label, code in sources:
        try:
            imgs, options = parse(fetch(BASE+'?search=true', search_fields(code)))
            pages[label] = imgs
            discovered_series.update(options)
        except Exception as exc:
            errors[label] = f'{type(exc).__name__}: {exc}'
    # Discover additional official series codes from the site's dropdown,
    # including <button data-value="..."> rather than only <option> elements.
    # Future series may be included in the blank-series POST already.
    for code in sorted(discovered_series - {'629001','629901'}):
        if len(discovered_series) > 30:
            warnings.append('公式の弾数候補が多いため、追加の個別検索を省略しました。')
            break
        label = '公式弾数コード ' + code
        try:
            imgs, options = parse(fetch(BASE+'?search=true', search_fields(code)))
            pages[label] = imgs
        except Exception as exc:
            errors[label] = f'{type(exc).__name__}: {exc}'
    # Only images actually referenced in official cardlist pages count.
    all_images = {}
    for imgs in pages.values(): all_images.update(imgs)
    if not all_images:
        warnings.append('公式ページからカード画像を検出できませんでした。既存データを保持します。')
    if pages.get('第1弾（POST）') and pages.get('プロモーションカード（POST）'):
        a,b = set(pages['第1弾（POST）']),set(pages['プロモーションカード（POST）'])
        if a == b:
            warnings.append('第1弾とプロモーションのPOST応答が同一です。検索条件が無視された可能性があります。')
    found_by_series = {}
    for card_id in all_images:
        label = series_of(card_id)
        found_by_series.setdefault(label,[]).append(card_id)
    for label in found_by_series: found_by_series[label].sort()
    added = []
    for card_id,(_,alt) in sorted(all_images.items()):
        if card_id not in existing and card_id not in known:
            existing[card_id] = candidate(card_id,alt)
            added.append(card_id)
    if not pages:
        raise SystemExit('All official page fetches failed; existing data unchanged')
    checked = datetime.now(timezone.utc).isoformat()
    # Never delete existing entries or replace user-verified metadata.
    payload = {'source':BASE,'checkedAt':checked,'cards':sorted(existing.values(),key=lambda c:c['id'])}
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n','utf-8')
    promo_count = len(found_by_series.get('プロモーションカード',[]))
    if promo_count < 28:
        warnings.append(f'プロモーションは{promo_count}枚検出。公式表示28枚との差があります。ページの取得範囲を確認してください。')
    report = {'checked_at_utc':checked,'official_found_count':len(all_images),
              'new_count':len(set(all_images)-known),'new_cards':sorted(set(all_images)-known),
              'added_to_official_cards':added,'found_by_series':{k:len(v) for k,v in sorted(found_by_series.items())},
              'found_by_source':{k:len(v) for k,v in pages.items()},
              'discovered_series_codes':sorted(discovered_series),
              'errors':errors,'warnings':warnings,
              'note':'公式カード画像のIDから仮登録。未取得のカード名・属性は確認中。公式サイトの掲載範囲や将来の構造変更により検出漏れの可能性あり。'}
    (DATA/'new_card_candidates.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
