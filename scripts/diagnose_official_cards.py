"""Read-only diagnostics of official Aikatsu Encore card listing responses."""
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from html.parser import HTMLParser

BASE = 'https://dcd.aikatsu.com/encore/cardlist/'
OUT = Path(__file__).resolve().parents[1] / 'diagnostics'
URLS = {
    'base': BASE,
    'search': BASE + '?search=true',
    'first_series': BASE + '?display=1&search=true&series=629001&sort=1',
    'promo': BASE + '?display=1&search=true&series=629002&sort=1',
}
CARD = re.compile(r'(?:E\d+-\d{2,3}|EP-\d{3})_(?:PR|ER|R|N)\b', re.I)

class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.scripts = []
        self.selects = []
        self.inputs = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self.forms.append({'method': a.get('method'), 'action': a.get('action'), 'id': a.get('id')})
        elif tag == 'script' and a.get('src'):
            self.scripts.append(urljoin(BASE, a['src']))
        elif tag == 'select':
            self.selects.append({'name': a.get('name'), 'id': a.get('id')})
        elif tag == 'input':
            self.inputs.append({'name': a.get('name'), 'type': a.get('type'), 'value': a.get('value')})

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; EncoreDiagnostic/1.0)', 'Accept': 'text/html,application/xhtml+xml'})
    with urllib.request.urlopen(req, timeout=35) as resp:
        raw = resp.read(3_000_000)
        return raw.decode('utf-8', 'replace'), resp.geturl(), resp.status

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'pages': {}, 'scripts': []}
    script_urls = []
    for key, url in URLS.items():
        try:
            body, final_url, status = get(url)
            parser = Tags()
            parser.feed(body)
            ids = sorted({m.group().upper() for m in CARD.finditer(body)})
            report['pages'][key] = {
                'requested_url': url, 'final_url': final_url, 'http_status': status,
                'html_characters': len(body), 'card_id_count': len(ids), 'card_ids': ids,
                'promo_id_count': sum(x.startswith('EP-') for x in ids),
                'forms': parser.forms[:15], 'selects': parser.selects[:30],
                'inputs': parser.inputs[:40], 'script_urls': parser.scripts[:40],
                'mentions_series_629002': '629002' in body,
                'mentions_promotion': 'プロモーション' in body,
            }
            script_urls.extend(parser.scripts)
        except Exception as exc:
            report['pages'][key] = {'requested_url': url, 'error': f'{type(exc).__name__}: {exc}'}
    # Inspect a small number of same-host JS files for card API / series hints; no raw page contents saved.
    seen = set()
    for url in script_urls:
        if url in seen or len(seen) >= 12:
            break
        if not url.startswith('https://dcd.aikatsu.com/encore/'):
            continue
        seen.add(url)
        try:
            body, final_url, status = get(url)
            hints = sorted(set(re.findall(r'.{0,65}(?:cardlist|629002|series|ajax|\.json|fetch\().{0,65}', body, re.I)))[:25]
            report['scripts'].append({'url': url, 'status': status, 'length': len(body), 'hints': hints})
        except Exception as exc:
            report['scripts'].append({'url': url, 'error': f'{type(exc).__name__}: {exc}'})
    output = OUT / 'official_card_diagnostic.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Diagnostic saved:', output)
    for key, data in report['pages'].items():
        print(key, 'status=', data.get('http_status'), 'count=', data.get('card_id_count'), 'promo=', data.get('promo_id_count'), 'error=', data.get('error'))
    print('Scripts inspected:', len(report['scripts']))

if __name__ == '__main__':
    main()
