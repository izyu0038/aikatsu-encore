"""Read-only official-news evidence collector for Aikatsu Encore cards.

Outputs possible evidence, NOT verified card-character mappings.
Does not change data/official_cards.json.
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE = 'https://dcd.aikatsu.com/encore/'
OUT = Path('diagnostic_output/official_character_research')
CARD_RE = re.compile(r'\b(?:E\d{1,2}-\d{2,3}|EP-\d{3})[ _-]?(?:PR|ER|R|N)\b', re.I)
# Candidate character/person names; appearances alone do not establish a card relationship.
NAMES = ['星宮いちご', '霧矢あおい', '紫吹蘭', '有栖川おとめ', '藤堂ユリカ', '北大路さくら',
         '一ノ瀬かえで', '神崎美月', '大空あかり', '氷上スミレ', '新条ひなき', '紅林珠璃',
         '黒沢凛', '天羽まどか', '服部ユウ', '栗栖ここね', '堂島ニーナ', '橋本環奈']
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; CardResearch/1.0)'}

def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return BeautifulSoup(response.text, 'html.parser')

def normalize_id(s):
    return re.sub(r'[ _-]+(?=(?:PR|ER|R|N)$)', '_', s.upper())

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path('data/official_cards.json').read_text(encoding='utf-8'))
    ids = {c['id'] for c in data['cards']}
    report = {'note': 'Mentions are evidence candidates only; never automatically assign character from proximity.',
              'total_cards': len(ids), 'pages': [], 'cards': {cid: [] for cid in sorted(ids)}, 'errors': []}
    index = fetch(urljoin(BASE, 'news/'))
    links = sorted({urljoin(BASE, a['href']) for a in index.select('a[href]')
                    if re.search(r'/encore/news/\d+\.php(?:\?.*)?$', urljoin(BASE, a['href']))})
    for url in links:
        try:
            soup = fetch(url)
            for tag in soup(['script', 'style', 'nav', 'footer']): tag.decompose()
            content = soup.get_text(' ', strip=True)
            found = sorted({normalize_id(x) for x in CARD_RE.findall(content)})
            names = [n for n in NAMES if n in content]
            report['pages'].append({'url': url, 'card_ids': found, 'character_mentions': names})
            for cid in found:
                if cid not in ids: continue
                snippets = []
                for match in CARD_RE.finditer(content):
                    if normalize_id(match.group()) == cid:
                        snippets.append(content[max(0, match.start()-100):match.end()+180])
                report['cards'][cid].append({'url': url, 'character_mentions_on_page': names,
                                              'snippets': snippets[:6],
                                              'status': 'unverified_candidate'})
            time.sleep(0.15)
        except Exception as exc:
            report['errors'].append({'url': url, 'error': str(exc)})
    (OUT / 'official_character_evidence.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'total_cards': len(ids), 'news_pages_checked': len(report['pages']),
               'cards_with_news_mentions': sum(bool(v) for v in report['cards'].values()),
               'errors': len(report['errors']), 'character_assignments_made': 0}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
