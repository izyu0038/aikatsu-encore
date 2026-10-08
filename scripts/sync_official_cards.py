"""Conservative official Encore card sync: publish only verified, explicit card metadata."""
from __future__ import annotations
import json, re, urllib.request, html
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SOURCES = {'第1弾':'629001', 'プロモーションカード':'629002'}
ID = re.compile(r'(?:E\d+-\d{2,3}|EP-\d{3})_(?:PR|ER|R|N)', re.I)
IMAGE = re.compile(r'https?://dcd\.aikatsu\.com/encore/images/cardlist/card/([^"\'\s<>?]+)\.webp',re.I)
RARITY = {'PR':'プレミアムレア','ER':'アンコールレア','R':'レア','N':'ノーマル'}

class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.images=[]
    def handle_starttag(self, tag, attrs):
        if tag not in ('img','a'): return
        d=dict(attrs)
        for key in ('src','data-src','data-original','href'):
            value=html.unescape(d.get(key,'')).replace('\\/','/')
            match=IMAGE.search(value)
            if match:
                self.images.append((match.group(1),d.get('alt','').strip(),value))

def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
    with urllib.request.urlopen(request,timeout=40) as response:
        return response.read().decode('utf-8','replace')

def extract(markup, series):
    parser=Parser(); parser.feed(markup)
    result={}; ids=set()
    for basename, alt, url in parser.images:
        match=ID.fullmatch(basename)
        if not match: continue
        card_id=match.group().upper(); ids.add(card_id)
        # No guessed names: require explicit, human-readable alt text beyond ID.
        name=re.sub(re.escape(card_id), '',alt,flags=re.I).strip(' -_　:：')
        if not name or name.lower() in ('card','カード','image','画像'): continue
        if len(name)>90 or '<' in name: continue
        rarity_code=card_id.rsplit('_',1)[-1]
        result[card_id]={'id':card_id,'name':name,'rarityCode':rarity_code,
                         'rarity':RARITY[rarity_code], 'cardType':series,
                         'front':f'https://dcd.aikatsu.com/encore/images/cardlist/card/{card_id}.webp',
                         'back':f'https://dcd.aikatsu.com/encore/images/cardlist/card/{card_id}_b.webp',
                         'character':'確認中','type':'確認中','brand':'確認中','category':'確認中',
                         'appealPoints':None}
    # Detect IDs in page even if metadata isn't sufficient to publish.
    ids.update(x.upper() for x in ID.findall(html.unescape(markup).replace('\\/','/')))
    return result,ids

def main():
    DATA.mkdir(exist_ok=True)
    target=DATA/'official_cards.json'
    old=json.loads(target.read_text('utf-8')) if target.exists() else {'cards':[]}
    existing={x['id']:x for x in old.get('cards',[]) if isinstance(x,dict) and x.get('id')}
    known_path=DATA/'known_cards.json'
    known_data=json.loads(known_path.read_text('utf-8')) if known_path.exists() else {'cards':[]}
    known={str(x.get('id') if isinstance(x,dict) else x).upper() for x in (known_data.get('cards',[]) if isinstance(known_data,dict) else known_data)}
    found=set(); errors={}; by_source={}; added=[]
    for label,code in SOURCES.items():
        url=f'https://dcd.aikatsu.com/encore/cardlist/?display=1&search=true&series={code}&sort=1'
        try:
            parsed,ids=extract(fetch(url),label)
            by_source[label]={'detected':len(ids),'publishable':len(parsed)}
            found.update(ids)
            for card_id,card in parsed.items():
                if card_id not in existing and card_id not in known:
                    existing[card_id]=card; added.append(card_id)
        except Exception as exc:
            errors[label]=f'{type(exc).__name__}: {exc}'
    checked=datetime.now(timezone.utc).isoformat()
    # Preserve all previously published entries on failed or partial scrapes.
    payload={'source':'https://dcd.aikatsu.com/encore/cardlist/','checkedAt':checked,
             'cards':sorted(existing.values(),key=lambda c:c['id'])}
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n','utf-8')
    candidates={'checked_at_utc':checked,'official_found_count':len(found),'new_count':len(found-known),
                'new_cards':sorted(found-known),'added_to_official_cards':sorted(added),
                'found_by_source':by_source,'errors':errors,
                'warnings':(['公式の28枚に達していません。ページ構造を要確認'] if by_source.get('プロモーションカード',{}).get('detected',0)<28 else []),
                'note':'名前が画像altに明記されたカードのみ自動登録。未確認の属性は確認中。'}
    (DATA/'new_card_candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(candidates,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
