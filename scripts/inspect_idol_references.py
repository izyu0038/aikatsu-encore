"""Read-only audit of official Aikatsu idol reference pages.
No image downloads, no edits to card data, and no character assignments.
"""
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

URLS = [
    'https://www.aikatsu.net/02/character/index.html',
    'https://www.aikatsu.net/portal/idol/',
    'https://www.tv-tokyo.co.jp/anime/aikatsuonparade/charalist/',
    'https://dcd.aikatsu.com/encore/idol/',
]
OUT = Path('diagnostic_output/idol_references')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; AikatsuCardResearch/1.0)'}

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'purpose': 'Reference discovery only; no character identification is asserted', 'pages': []}
    for url in URLS:
        page = {'requested_url': url, 'images': [], 'links': []}
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            page['http_status'] = r.status_code
            page['final_url'] = r.url
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            soup = BeautifulSoup(r.text, 'html.parser')
            page['title'] = soup.title.get_text(' ', strip=True) if soup.title else ''
            for img in soup.select('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-original') or ''
                if src:
                    page['images'].append({'alt': img.get('alt', '').strip(), 'src': urljoin(r.url, src),
                                           'parent_text': img.parent.get_text(' ', strip=True)[:100] if img.parent else ''})
            for a in soup.select('a[href]'):
                href = urljoin(r.url, a['href'])
                if urlparse(href).netloc == urlparse(r.url).netloc:
                    label = a.get_text(' ', strip=True) or (a.find('img').get('alt', '') if a.find('img') else '')
                    page['links'].append({'label': label[:100], 'url': href})
            page['images'] = page['images'][:500]
            page['links'] = page['links'][:500]
        except Exception as exc:
            page['error'] = str(exc)
        report['pages'].append(page)
    dest = OUT / 'idol_reference_report.json'
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{'url': p['requested_url'], 'status': p.get('http_status'),
                       'images': len(p['images']), 'links': len(p['links']), 'error': p.get('error')}
                      for p in report['pages']], ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
