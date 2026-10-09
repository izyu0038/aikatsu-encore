"""Read-only diagnostic for official Aikatsu Encore card-list POST form."""
import json
import re
import urllib.parse
import urllib.request
import http.cookiejar
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = 'https://dcd.aikatsu.com/encore/cardlist/'
CARD = re.compile(r'\b(?:E\d+-\d{2,3}|EP-\d{2,3})_(?:PR|ER|R|N)\b', re.I)

class FormReader(HTMLParser):
    def __init__(self):
        super().__init__(); self.inputs=[]; self.options=[]; self._option=None
    def handle_starttag(self, tag, attrs):
        d=dict(attrs)
        if tag=='input': self.inputs.append({k:d.get(k,'') for k in ('name','type','value')})
        if tag=='option': self._option={'value':d.get('value',''),'label':''}
    def handle_data(self, data):
        if self._option is not None: self._option['label']+=data
    def handle_endtag(self,tag):
        if tag=='option' and self._option is not None:
            self.options.append(self._option); self._option=None

def run():
    jar=http.cookiejar.CookieJar()
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers={'User-Agent':'Mozilla/5.0 (compatible; AikatsuCardDiagnostic/2.0)','Accept':'text/html,application/xhtml+xml','Referer':BASE}
    def request(label, url, data=None):
        entry={'label':label,'method':'POST' if data is not None else 'GET','submitted_fields':data,'requested_url':url}
        try:
            encoded=urllib.parse.urlencode(data).encode() if data is not None else None
            req=urllib.request.Request(url,data=encoded,headers=headers)
            with opener.open(req,timeout=35) as response:
                body=response.read(2_000_000).decode('utf-8','replace')
                entry['status']=response.status; entry['final_url']=response.url
            ids=sorted({x.upper() for x in CARD.findall(body)})
            form=FormReader();form.feed(body)
            entry.update(html_length=len(body),card_count=len(ids),promo_count=sum(x.startswith('EP-') for x in ids),
                         promo_ids=[x for x in ids if x.startswith('EP-')],card_id_samples=ids[:8],
                         input_fields=form.inputs[:20],options=form.options[:60],
                         promotion_contexts=[body[max(0,m.start()-130):m.end()+130] for m in list(re.finditer('プロモーション',body))[:5]])
        except Exception as exc:
            entry['error']=f'{type(exc).__name__}: {exc}'
        print(f"{label}: status={entry.get('status')} cards={entry.get('card_count')} promo={entry.get('promo_count')} url={entry.get('final_url')} error={entry.get('error')}")
        return entry
    results=[]
    results.append(request('initial_GET',BASE))
    url=BASE+'?search=true'
    for label,series in [('post_series_629002','629002'),('post_series_629001','629001'),('post_series_empty','')]:
        fields={'free':'','series':series,'type':'','rarity':'','category':'','brand':'','display':'1','sort':'1'}
        results.append(request(label,url,fields))
    # A minimal POST tests whether other form fields cause the server to default.
    results.append(request('post_minimal_629002',url,{'series':'629002','display':'1','sort':'1'}))
    report={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'purpose':'Read-only POST request diagnosis; no site data modified','results':results}
    out=Path('diagnostics/official_card_post_diagnostic.json');out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved report:',out)

if __name__=='__main__':run()
