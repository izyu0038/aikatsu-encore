"""Read-only Japanese OCR research for all registered Aikatsu Encore card images.

Runs image downloader first; writes candidate text only to diagnostic_output.
Does not assign card names or character names to the production database.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / 'diagnostic_output' / 'card_image_samples'
OUT = ROOT / 'diagnostic_output' / 'card_ocr_research'


def ocr(image: Image.Image, mode: int) -> str:
    """Use Japanese Tesseract; return raw unverified OCR text."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        file = Path(td) / 'input.png'
        image.save(file)
        result = subprocess.run(
            ['tesseract', str(file), 'stdout', '-l', 'jpn+eng', '--psm', str(mode)],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[:400])
        return result.stdout.strip()


def preprocess(image: Image.Image) -> Image.Image:
    image = image.convert('RGB')
    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.7)
    image = image.filter(ImageFilter.UnsharpMask(radius=1.4, percent=150))
    return image.resize((image.width * 3, image.height * 3), Image.Resampling.LANCZOS)


def main() -> None:
    if not IMAGES.exists():
        raise FileNotFoundError('Images missing. Run scripts/inspect_card_images.py first.')
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(IMAGES.glob('*.webp'))
    records = {}
    for i, path in enumerate(files, 1):
        is_back = path.stem.endswith('_b')
        card_id = path.stem[:-2] if is_back else path.stem
        side = 'back' if is_back else 'front'
        entry = records.setdefault(card_id, {'card_id': card_id, 'front': {}, 'back': {}})
        try:
            with Image.open(path) as im:
                w, h = im.size
                # Front dress name often appears at the bottom; back has a left-hand item list.
                crops = (
                    [('bottom', (0, int(h * .76), w, h)),
                     ('full', (0, 0, w, h))]
                    if not is_back else
                    [('left_items', (0, int(h * .23), int(w * .63), int(h * .77))),
                     ('upper', (0, int(h * .1), w, int(h * .42)))]
                )
                results = {}
                for label, bounds in crops:
                    part = preprocess(im.crop(bounds))
                    results[label] = {'text': ocr(part, 6), 'crop_xyxy': list(bounds)}
                entry[side] = {'image': path.name, 'ocr': results, 'status': 'unverified'}
        except Exception as exc:
            entry[side] = {'image': path.name, 'error': str(exc), 'status': 'error'}
        print(f'[{i}/{len(files)}] {path.name}', flush=True)
    result = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Raw OCR candidates for manual review; not verified metadata',
        'image_count': len(files),
        'card_count': len(records),
        'cards': list(records.values()),
        'warning': 'OCR can misread stylized Japanese text. Do not assign names or characters automatically.',
    }
    (OUT / 'card_ocr_candidates.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(f'Saved OCR candidates for {len(records)} cards; original card data unchanged.')


if __name__ == '__main__':
    main()
