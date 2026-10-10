"""Read-only download of all registered official Aikatsu Encore card images.

Reads data/official_cards.json; does not change the card database.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data' / 'official_cards.json'
OUT = ROOT / 'diagnostic_output' / 'card_image_samples'
ALLOWED_HOST = 'dcd.aikatsu.com'
MAX_BYTES = 5_000_000


def download(url: str, destination: Path) -> dict:
    result = {'url': url, 'file': destination.name, 'downloaded': False}
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != ALLOWED_HOST:
        result['error'] = 'URL is not on the expected official HTTPS host'
        return result
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; EncoreImageInspection/1.0)',
            'Referer': 'https://dcd.aikatsu.com/encore/cardlist/',
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            result['http_status'] = response.status
            result['content_type'] = response.headers.get('Content-Type', '')
            content = response.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise ValueError('Image exceeds 5 MB')
        if not (content.startswith(b'RIFF') and content[8:12] == b'WEBP'):
            raise ValueError('Response is not a WebP image')
        destination.write_bytes(content)
        result.update(bytes=len(content), downloaded=True)
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    return result


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f'Card list not found: {SOURCE}')
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    cards = data['cards'] if isinstance(data, dict) else data
    if not isinstance(cards, list):
        raise ValueError('Expected a list of cards')
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for index, card in enumerate(cards, 1):
        card_id = str(card.get('id', ''))
        safe_id = ''.join(c if c.isalnum() or c in '_-' else '_' for c in card_id)
        if not safe_id:
            continue
        for side, key, suffix in [('front', 'front', ''), ('back', 'back', '_b')]:
            url = card.get(key, '')
            if not url:
                item = {'downloaded': False, 'error': f'Missing {key} URL'}
            else:
                item = download(url, OUT / f'{safe_id}{suffix}.webp')
                time.sleep(0.1)
            item.update(card_id=card_id, side=side)
            results.append(item)
        print(f'[{index}/{len(cards)}] {card_id}: ' + ', '.join(
            f'{x["side"]}={"OK" if x["downloaded"] else "FAILED"}'
            for x in results[-2:]
        ), flush=True)
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only visual inspection of every registered official card image',
        'source': 'data/official_cards.json',
        'card_count': len(cards),
        'image_count': len(results),
        'downloaded_count': sum(x['downloaded'] for x in results),
        'failed_count': sum(not x['downloaded'] for x in results),
        'images': results,
        'notes': [
            'No OCR or character identification has been performed.',
            'Images are evidence for manual review, not verified metadata.',
            'No files under data/ are modified.',
        ],
    }
    (OUT / 'image_sample_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print('Saved diagnostic_output/card_image_samples/image_sample_report.json')
    print(f'Images downloaded: {report["downloaded_count"]}/{report["image_count"]}')


if __name__ == '__main__':
    main()
