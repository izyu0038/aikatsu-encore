"""Read-only improved OCR comparison for every registered Aikatsu Encore card.

Runs after inspect_card_images.py. Saves candidates only under diagnostic_output.
Never modifies data/official_cards.json or production card metadata.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / 'diagnostic_output' / 'card_image_samples'
OUT = ROOT / 'diagnostic_output' / 'card_ocr_refined'


def recognize(image: Image.Image, psm: int) -> str:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'crop.png'
        image.save(source)
        completed = subprocess.run(
            ['tesseract', str(source), 'stdout', '-l', 'jpn+eng', '--psm', str(psm)],
            capture_output=True, text=True, timeout=45, check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.strip()[:300])
        return completed.stdout.strip()


def variants(image: Image.Image):
    gray = ImageOps.autocontrast(ImageOps.grayscale(image.convert('RGB')))
    scale = 3
    resized = gray.resize((gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS)
    yield 'gray', resized
    sharp = ImageEnhance.Contrast(resized).enhance(2.0).filter(
        ImageFilter.UnsharpMask(radius=1.4, percent=170)
    )
    yield 'high_contrast', sharp
    yield 'threshold', sharp.point(lambda p: 255 if p >= 155 else 0)


def main():
    if not IMAGES.exists():
        raise FileNotFoundError('Image directory missing: run inspect_card_images.py first')
    files = sorted(IMAGES.glob('*.webp'))
    if not files:
        raise FileNotFoundError('No .webp card images were found')
    OUT.mkdir(parents=True, exist_ok=True)
    cards = {}
    errors = []
    for index, path in enumerate(files, 1):
        back = path.stem.endswith('_b')
        card_id = path.stem[:-2] if back else path.stem
        side = 'back' if back else 'front'
        card = cards.setdefault(card_id, {'card_id': card_id, 'front': {}, 'back': {}})
        try:
            with Image.open(path) as original:
                w, h = original.size
                # Front: dress-name region. Back: left column of outfit item names.
                # Crop geometry is intentionally broad; no OCR text is auto-approved.
                regions = (
                    {'bottom_name': (0, int(h * .73), w, int(h * .96))}
                    if not back else
                    {'left_item_names': (int(w * .07), int(h * .22), int(w * .52), int(h * .74))}
                )
                readings = {}
                for region, bounds in regions.items():
                    crop = original.crop(bounds)
                    candidates = []
                    for variant_name, processed in variants(crop):
                        for psm in (6, 11):
                            try:
                                candidate = recognize(processed, psm)
                                candidates.append({'variant': variant_name, 'psm': psm, 'text': candidate})
                            except Exception as exc:
                                candidates.append({'variant': variant_name, 'psm': psm, 'error': str(exc)})
                    readings[region] = {'crop_xyxy': list(bounds), 'candidates': candidates}
                card[side] = {'image': path.name, 'regions': readings, 'status': 'unverified'}
        except Exception as exc:
            card[side] = {'image': path.name, 'status': 'error', 'error': str(exc)}
            errors.append({'image': path.name, 'error': str(exc)})
        print(f'[{index}/{len(files)}] {path.name}', flush=True)
    report = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only comparison of Japanese OCR candidates for all cards',
        'image_count': len(files), 'card_count': len(cards),
        'error_count': len(errors), 'errors': errors,
        'cards': [cards[key] for key in sorted(cards)],
        'warning': 'Raw OCR only. A matching candidate is not verified metadata. Do not auto-assign card or character names.',
    }
    output = OUT / 'card_ocr_refined_candidates.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved:', output)
    print('Production data unchanged.')


if __name__ == '__main__':
    main()
