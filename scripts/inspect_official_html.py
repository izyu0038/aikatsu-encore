"""Read-only diagnostic for official Aikatsu Encore card metadata.

Writes a JSON report to diagnostic_output only; never modifies card data.
"""
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

URL = 'https://dcd.aikatsu.com/encore/cardlist/?search=true'
FIELDS = {'free': '', 'series': '629001', 'type': '', 'rarity': '',
          'category': '', 'brand': '', 'display': '1', 'sort': '1'}
# 第1弾の実在するカードIDをHTMLから選ぶ（番号を推測しない）
TARGET_LIMIT = 5
LABELS = ('カード名', 'キャラクター', 'タイプ', 'ブランド', 'カテゴリ',
          'アピールポイント', '入手方法', 'レアリティ')
OUT = Path('diagnostic_output')


class CardModalParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.modals = {}
        self.active = None
        self.modal_depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.active is None and tag == 'div':
            match = re.fullmatch(r'cardModal-(E[1P]-[0-9]+_[A-Z]+)', a.get('id', ''))
            if match:
                self.active = match.group(1)
                self.modal_depth = 0
                self.modals[self.active] = {'text_parts': [], 'images': [], 'elements': []}
        if self.active is not None:
            self.stack.append(tag)
            if tag == 'div':
                self.modal_depth += 1
            if tag == 'img':
                self.modals[self.active]['images'].append({
                    'alt': a.get('alt', ''), 'src': a.get('src', ''),
                })
            if tag in ('h2', 'h3', 'h4', 'dt', 'dd', 'p', 'span'):
                self.modals[self.active]['elements'].append({
                    'tag': tag, 'class': a.get('class', ''), 'text': ''
                })

    def handle_data(self, data):
        if self.active is None:
            return
        value = ' '.join(data.split())
        if value:
            self.modals[self.active]['text_parts'].append(value)
            if self.modals[self.active]['elements']:
                self.modals[self.active]['elements'][-1]['text'] += value + ' '

    def handle_endtag(self, tag):
        if self.active is None:
            return
        if tag == 'div':
            self.modal_depth -= 1
        if self.stack:
            self.stack.pop()
        if self.modal_depth == 0:
            self.active = None


def main():
    request = urllib.request.Request(
        URL, data=urllib.parse.urlencode(FIELDS).encode('utf-8'),
        headers={'User-Agent': 'Mozilla/5.0',
                 'Content-Type': 'application/x-www-form-urlencoded',
                 'Accept': 'text/html'},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        html = response.read().decode('utf-8', 'replace')
        status = response.status
    parser = CardModalParser()
    parser.feed(html)
    targets = {}
    first_series_ids = sorted(card_id for card_id in parser.modals if card_id.startswith('E1-'))
    for card_id in first_series_ids[:TARGET_LIMIT]:
        modal = parser.modals.get(card_id)
        if modal is None:
            targets[card_id] = {'found': False}
            continue
        text = ' / '.join(modal['text_parts'])
        targets[card_id] = {
            'found': True,
            'visible_text': text[:12000],
            'labels_found_in_modal': [label for label in LABELS if label in text],
            'images': modal['images'],
            'text_elements': [e for e in modal['elements'] if e['text'].strip()][:80],
        }
    report = {
        'purpose': 'Identify metadata fields actually present as text in each official card modal',
        'http_status': status,
        'html_length': len(html),
        'total_modals': len(parser.modals),
        'first_series_modal_count': len(first_series_ids),
        'sampled_ids': first_series_ids[:TARGET_LIMIT],
        'series': '629001',
        'targets': targets,
        'caution': 'Text shown only on front/back card images cannot be extracted reliably from HTML. Do not infer missing values.',
    }
    # Keep every URL tied to its actual card modal; do not guess front/back roles.
    image_manifest = {
        'purpose': 'Review image URL candidates for five verified first-series card IDs',
        'source_page': URL,
        'series': FIELDS['series'],
        'cards': [],
        'caution': 'Image order is not proof of front/back. Verify visually before assigning metadata.',
    }
    for card_id in first_series_ids[:TARGET_LIMIT]:
        images = []
        for item in parser.modals[card_id]['images']:
            raw_src = item.get('src', '').strip()
            if not raw_src:
                continue
            absolute_url = urllib.parse.urljoin(URL, raw_src)
            images.append({
                'alt': item.get('alt', ''),
                'source_url': raw_src,
                'absolute_url': absolute_url,
                'role': 'unverified',
            })
        image_manifest['cards'].append({
            'card_id': card_id,
            'images': images,
            'image_count': len(images),
        })
    OUT.mkdir(exist_ok=True)
    manifest_path = OUT / 'first_series_image_manifest.json'
    manifest_path.write_text(
        json.dumps(image_manifest, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    path = OUT / 'html_structure_report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('HTTP:', status, 'Modals:', len(parser.modals), 'First-series:', len(first_series_ids))
    for card_id, info in targets.items():
        print(card_id, 'found:', info['found'], 'labels:', info.get('labels_found_in_modal', []))
    print('Report:', path)
    print('Image manifest:', manifest_path)


if __name__ == '__main__':
    main()
