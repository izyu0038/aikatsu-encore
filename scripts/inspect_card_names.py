"""Read-only investigation of official Aikatsu Encore card names and character mentions.

Run with Python 3.10+. Writes only diagnostic_output/card_name_research.json.
No third-party dependencies. No card metadata is modified.
"""
from __future__ import annotations
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = 'https://dcd.aikatsu.com'
ROOT = BASE + '/encore/'
NEWS = ROOT + 'news/'
OUT = Path(__file__).resolve().parents[1] / 'diagnostic_output' / 'card_name_research.json'
CARD = re.compile(r'\b(?:E\d+-\d{2,3}|EP-\d{3})[ _-]*(?:PR|ER|R|N)\b', re.I)
CHARACTERS = ['星宮いちご','霧矢あおい','紫吹蘭','有栖川おとめ','藤堂ユリカ','北大路さくら','一ノ瀬かえで','神崎美月','大空あかり','氷上スミレ','新条ひなき','紅林珠璃','天羽まどか','黒沢凛','大地のの','白樺リサ','橋本環奈']

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]; self.images=[]; self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style'): self.skip+=1
        if tag=='a' and a.get('href'): self.links.append(a['href'])
        if tag=='img': self.images.append({'alt':a.get('alt',''),'src':a.get('src','') or a.get('data-src','')})
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip:
            value=' '.join(data.split())
            if value:self.parts.append(value)

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; EncoreReadOnlyResearch/1.0)'})
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read(2_000_000).decode('utf-8','replace'),r.status

def canonical_id(raw):
    return re.sub(r'[ _-]+(?=(?:PR|ER|R|N)$)','_',raw.upper().replace(' ',''))

def main():
    index,status=fetch(NEWS)
    p=Page();p.feed(index)
    urls=[]
    for href in p.links:
        url=urllib.parse.urljoin(NEWS,href)
        parsed=urllib.parse.urlparse(url)
        if parsed.hostname=='dcd.aikatsu.com' and re.fullmatch(r'/encore/news/\d+\.php',parsed.path) and url not in urls:
            urls.append(url)
    urls=urls[:35]
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'news_index_status':status,
            'news_pages_found':len(urls),'news_pages':[],'candidate_mentions':[],
            'warning':'Mentions are candidate evidence only. Proximity does not establish a reliable card-name or character mapping. No data was modified.'}
    for i,url in enumerate(urls):
        item={'url':url}
        try:
            html,status=fetch(url)
            page=Page();page.feed(html)
            text=' '.join(page.parts)
            item['status']=status
            item['character_mentions']=[name for name in CHARACTERS if name in text]
            matches=list(CARD.finditer(text))
            item['card_id_mentions']=sorted(set(canonical_id(m.group()) for m in matches))
            item['card_contexts']=[{'card_id':canonical_id(m.group()),'nearby_text':text[max(0,m.start()-70):m.end()+110]} for m in matches[:30]]
            item['image_alt_candidates']=[{'alt':im['alt'][:180],'src':urllib.parse.urljoin(url,im['src'])} for im in page.images if CARD.search(im['alt'])][:30]
            report['candidate_mentions'].extend({'source':url,**entry} for entry in item['card_contexts'])
        except Exception as exc:
            item['error']=f'{type(exc).__name__}: {exc}'
        report['news_pages'].append(item)
        if i<len(urls)-1:time.sleep(0.25)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('News pages inspected:',len(report['news_pages']))
    print('Candidate card mentions:',len(report['candidate_mentions']))
    print('Saved:',OUT)
    print('READ ONLY: no card data was modified.')

if __name__=='__main__':main()
