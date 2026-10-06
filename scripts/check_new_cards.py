from __future__ import annotations
import json, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path

URLS = {
    "第1弾": "https://dcd.aikatsu.com/encore/cardlist/?display=1&search=true&series=629001&sort=1",
    "プロモーション": "https://dcd.aikatsu.com/encore/cardlist/?display=1&search=true&series=629002&sort=1",
}
ROOT = Path(__file__).resolve().parents[1]
KNOWN = ROOT / "data" / "known_cards.json"
REPORT = ROOT / "data" / "new_card_candidates.json"

# Official card images use IDs such as E1-01_PR / EP-002_PR in filenames/alt text.
CARD_RE = re.compile(r'\b(?:E\d+-\d{2,3}|EP-\d{3})_(?:PR|R|N|ER)\b', re.I)

def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (AikatsuEncoreCardChecker/1.0)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def main():
    known_data = json.loads(KNOWN.read_text(encoding="utf-8"))
    known = set(known_data.get("cards", []))
    found_by_source = {}
    all_found = set()
    errors = {}
    for label, url in URLS.items():
        try:
            html = fetch(url)
            ids = sorted(set(m.upper() for m in CARD_RE.findall(html)))
            found_by_source[label] = ids
            all_found.update(ids)
        except Exception as e:
            errors[label] = f"{type(e).__name__}: {e}"
    new = sorted(all_found - known)
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "known_count": len(known),
        "official_found_count": len(all_found),
        "new_count": len(new),
        "new_cards": new,
        "found_by_source": found_by_source,
        "errors": errors,
        "note": "候補検出のみ。キャラクター名・AP等は自動確定しません。"
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Nonzero only if all sources failed; new cards are not an error.
    if not all_found and errors:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
