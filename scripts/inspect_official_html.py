"""Read-only diagnostic: inspect card-specific HTML near official promo images.

Does not write to the website's data/ directory or alter existing card data.
"""
import json
import re
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

OUT = Path('diagnostic_output')
OUT.mkdir(exist_ok=True)
URL = 'https://dcd.aikatsu.com/encore/cardlist/?search=true'
FIELDS = {'free': '', 'series': '629901', 'type': '', 'rarity': '',
          'category': '', 'brand': '', 'display': '1', 'sort': '1'}
TARGETS = ['EP-029_R', 'EP-035_R', 'EP-038_N']


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = ' '.join(data.split())
        if value:
            self.parts.append(value)


def surrounding_html(markup, card_id):
    # This is diagnostic context, not proof that nearby text belongs to a card.
    hits = list(re.finditer(re.escape(card_id), markup, flags=re.I))
    samples = []
    for match in hits[:4]:
        left = max(0, match.start() - 2500)
        right = min(len(markup), match.end() + 3500)
        snippet = markup[left:right]
        parser = TextExtractor()
        parser.feed(snippet)
        text = ' / '.join(parser.parts)
        samples.append({
            'position': match.start(),
            'html_excerpt': snippet,
            'nearby_visible_text': text[:2500],
            'contains_acquisition_label': '入手方法' in snippet,
        })
    return {'occurrences': len(hits), 'samples': samples}


def main():
    request = urllib.request.Request(
        URL,
        data=urllib.parse.urlencode(FIELDS).encode('utf-8'),
        headers={'User-Agent': 'Mozilla/5.0',
                 'Content-Type': 'application/x-www-form-urlencoded',
                 'Accept': 'text/html'},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        body = response.read().decode('utf-8', 'replace')
        final_url = response.url
        status = response.status

    report = {
        'purpose': 'Inspect whether card ID and acquisition method can be reliably associated',
        'request': {'url': URL, 'method': 'POST', 'fields': FIELDS},
        'response_url': final_url,
        'http_status': status,
        'html_length': len(body),
        'targets': {card_id: surrounding_html(body, card_id) for card_id in TARGETS},
        'caution': 'Nearby text is NOT verified as belonging to a card. Review HTML structure before implementing extraction. No metadata is inferred from images.',
    }
    destination = OUT / 'html_structure_report.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Diagnostic complete. HTTP:', status)
    for card_id, details in report['targets'].items():
        print(card_id, 'occurrences:', details['occurrences'])
    print('Report saved:', destination)


if __name__ == '__main__':
    main()
