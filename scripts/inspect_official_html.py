"""Read-only official Aikatsu Encore card-list structure diagnostic.

Run from GitHub Actions or locally. Never writes to data/ and never edits cards.
Outputs diagnostic_output/html_structure_report.json and
        diagnostic_output/first_series_image_manifest.json.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE = 'https://dcd.aikatsu.com/encore/cardlist/'
URL = BASE + '?search=true'
FIELDS = {'free': '', 'series': '629001', 'type': '', 'rarity': '',
          'category': '', 'brand': '', 'display': '1', 'sort': '1'}
CARD_ID = re.compile(r'(?:E[1-9]\d*-\d{2,3}|EP-\d{3})_(?:PR|ER|R|N)', re.I)
LABELS = ('カード名', 'キャラクター', 'タイプ', 'ブランド', 'カテゴリ',
          'アピールポイント', '入手方法', 'レアリティ')
TARGET_LIMIT = 5
OUT = Path(__file__).resolve().parents[1] / 'diagnostic_output'
VOID_TAGS = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.modals = {}
        self.active_id = None
        self.modal_div_depth = 0
        self.element_stack = []
        self.forms = []
        self.selects = []
        self._select = None
        self._option = None
        self.scripts = []
        self.inputs = []
        self.buttons = []
        self.labels = []
        self._label = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input':
            self.inputs.append({k: a.get(k, '') for k in ('name','id','type','value','checked','class')})
        if tag == 'button':
            self.buttons.append({k: a.get(k, '') for k in ('name','id','type','value','class')})
        if tag == 'label':
            self._label = {'for': a.get('for', ''), 'class': a.get('class', ''), 'text': ''}
        if tag == 'form':
            self.forms.append({k: a.get(k, '') for k in ('action', 'method', 'id')})
        if tag == 'script' and a.get('src'):
            self.scripts.append(urllib.parse.urljoin(BASE, a['src']))
        if tag == 'select':
            self._select = {'name': a.get('name', ''), 'id': a.get('id', ''), 'options': []}
        if tag == 'option' and self._select is not None:
            self._option = {'value': a.get('value', ''), 'label': ''}

        if self.active_id is None and tag == 'div':
            modal = re.fullmatch(r'cardModal-(' + CARD_ID.pattern + r')', a.get('id', ''), re.I)
            if modal:
                self.active_id = modal.group(1).upper()
                self.modal_div_depth = 0
                self.element_stack = []
                self.modals[self.active_id] = {'text_parts': [], 'images': [], 'text_elements': []}

        if self.active_id is None:
            return
        if tag == 'div':
            self.modal_div_depth += 1
        if tag == 'img':
            self.modals[self.active_id]['images'].append({
                'alt': a.get('alt', ''),
                'src': a.get('src', '') or a.get('data-src', ''),
            })
        # Capture each text element's OWN text, not text from unrelated siblings.
        if tag in ('h2','h3','h4','dt','dd','p','span','li','strong'):
            element = {'tag': tag, 'class': a.get('class', ''), 'text': ''}
            self.modals[self.active_id]['text_elements'].append(element)
            self.element_stack.append(element)
        elif tag not in VOID_TAGS:
            self.element_stack.append(None)

    def handle_data(self, data):
        if self._label is not None:
            self._label['text'] += data
        if self._option is not None:
            self._option['label'] += data
        if self.active_id is None:
            return
        value = ' '.join(data.split())
        if not value:
            return
        self.modals[self.active_id]['text_parts'].append(value)
        for element in self.element_stack:
            if element is not None:
                element['text'] += value + ' '

    def handle_endtag(self, tag):
        if tag == 'label' and self._label is not None:
            self._label['text'] = ' '.join(self._label['text'].split())[:300]
            self.labels.append(self._label)
            self._label = None
        if tag == 'option' and self._option is not None:
            self._option['label'] = ' '.join(self._option['label'].split())
            self._select['options'].append(self._option)
            self._option = None
        if tag == 'select' and self._select is not None:
            self.selects.append(self._select)
            self._select = None
        if self.active_id is None:
            return
        if tag == 'div':
            self.modal_div_depth -= 1
        if tag not in VOID_TAGS and self.element_stack:
            self.element_stack.pop()
        if self.modal_div_depth <= 0:
            self.active_id = None
            self.element_stack = []




class DropdownParser(HTMLParser):
    """Collect HTML search choices and nearby context without executing scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.choices = []
        self.fields = []
        self.current_select = None
        self.current_option = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        parent = self.stack[-1] if self.stack else None
        node = {'tag': tag, 'attrs': a, 'text': [], 'parent': parent}
        if 'data-value' in a:
            self.choices.append(node)
        if tag == 'select':
            self.current_select = {'name': a.get('name', ''), 'id': a.get('id', ''), 'options': []}
            self.fields.append(self.current_select)
        if tag == 'option' and self.current_select is not None:
            self.current_option = {'value': a.get('value', ''), 'label_parts': []}
            self.current_select['options'].append(self.current_option)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_data(self, data):
        cleaned = ' '.join(data.split())
        if not cleaned:
            return
        for node in self.stack:
            node['text'].append(cleaned)
        if self.current_option is not None:
            self.current_option['label_parts'].append(cleaned)

    def handle_endtag(self, tag):
        if tag == 'option':
            self.current_option = None
        if tag == 'select':
            self.current_select = None
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i]['tag'] == tag:
                del self.stack[i:]
                break

    def as_report(self):
        output = []
        for node in self.choices:
            a = node['attrs']
            ancestors = []
            parent = node['parent']
            while parent is not None and len(ancestors) < 5:
                pa = parent['attrs']
                ancestors.append({'tag': parent['tag'], 'id': pa.get('id', ''),
                                  'class': pa.get('class', ''), 'name': pa.get('name', ''),
                                  'data-name': pa.get('data-name', '')})
                parent = parent['parent']
            output.append({'tag': node['tag'], 'label': ' '.join(node['text'])[:200],
                           'data_value': a.get('data-value', ''),
                           'id': a.get('id', ''), 'class': a.get('class', ''),
                           'name': a.get('name', ''), 'ancestors': ancestors})
        selects = [{'name': field['name'], 'id': field['id'],
                    'options': [{'value': o['value'], 'label': ' '.join(o['label_parts'])}
                                for o in field['options']]}
                   for field in self.fields]
        return {'purpose': 'Read-only extraction of HTML data-value choices and select options',
                'data_value_choices': output, 'select_options': selects,
                'counts': {'data_value_choices': len(output), 'selects': len(selects)},
                'caution': 'Values are HTML observations only; search behavior remains unverified.'}


def inspect_scripts(script_urls):
    """Read-only inspection of same-site JavaScript; never execute remote code."""
    results = []
    seen = set()
    for url in script_urls:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != 'dcd.aikatsu.com':
            continue
        if url in seen or len(seen) >= 20:
            continue
        seen.add(url)
        item = {'url': url}
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': BASE})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read(1_000_001)
                item['http_status'] = resp.status
            if len(content) > 1_000_000:
                item['warning'] = 'File exceeds 1 MB; skipped analysis'
            else:
                source = content.decode('utf-8', 'replace')
                item['length'] = len(source)
                # Short, contextual excerpts; never claim that a keyword proves a working filter.
                pattern = re.compile(r'(?i)series|category|brand|rarity|cardlist|search|\btype\b|\bajax\b|fetch\s*\(|\.json')
                matches = list(pattern.finditer(source))
                item['keyword_match_count'] = len(matches)
                item['excerpts'] = [
                    {'keyword': m.group(), 'context': source[max(0, m.start()-140):min(len(source), m.end()+200)]}
                    for m in matches[:35]
                ]
        except Exception as exc:
            item['error'] = f'{type(exc).__name__}: {exc}'
        results.append(item)
    return results

def main():
    body = urllib.parse.urlencode(FIELDS).encode('utf-8')
    request = urllib.request.Request(URL, data=body, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; EncoreReadOnlyDiagnostic/1.0)',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'text/html',
        'Referer': BASE,
    })
    with urllib.request.urlopen(request, timeout=40) as response:
        markup = response.read(3_000_000).decode('utf-8', 'replace')
        status = response.status
        final_url = response.url

    parser = StructureParser()
    parser.feed(markup)
    dropdown_parser = DropdownParser()
    dropdown_parser.feed(markup)
    dropdown_report = dropdown_parser.as_report()
    first_ids = sorted(x for x in parser.modals if x.startswith('E1-'))
    sampled_ids = first_ids[:TARGET_LIMIT]
    targets = {}
    manifest = []
    for card_id in sampled_ids:
        modal = parser.modals[card_id]
        text = ' / '.join(modal['text_parts'])
        images = [{
            'alt': img['alt'], 'source_url': img['src'],
            'absolute_url': urllib.parse.urljoin(BASE, img['src']) if img['src'] else '',
            'role': 'unverified',
        } for img in modal['images']]
        targets[card_id] = {
            'visible_text': text[:12000],
            'labels_found_in_modal': [x for x in LABELS if x in text],
            'images': images,
            'text_elements': [dict(e, text=e['text'].strip()) for e in modal['text_elements'] if e['text'].strip()][:80],
        }
        manifest.append({'card_id': card_id, 'images': images, 'image_count': len(images)})

    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only inspection of card modal text and search form options',
        'http_status': status, 'final_url': final_url, 'html_length': len(markup),
        'total_modals': len(parser.modals), 'first_series_modal_count': len(first_ids),
        'sampled_ids': sampled_ids, 'submitted_fields': FIELDS,
        'forms': parser.forms[:20], 'selects': parser.selects[:30],
        'inputs': parser.inputs[:300], 'buttons': parser.buttons[:100],
        'labels': parser.labels[:300],
        'search_field_html_excerpts': [markup[max(0,m.start()-400):min(len(markup),m.end()+700)] for m in list(re.finditer(r'(?i)(?:name|id)=[\"\'](?:series|type|rarity|category|brand)[\"\']', markup))[:35]],
        'script_urls': parser.scripts[:40], 'targets': targets,
        'caution': ('Labels/options and HTTP 200 do not prove that a search filter works. '
                    'Image-only text cannot be inferred from HTML. Do not auto-assign metadata from this report.'),
    }
    js_report = {
        'checked_at_utc': report['checked_at_utc'],
        'purpose': 'Read-only inspection of same-host JavaScript references and search-related excerpts',
        'scripts': inspect_scripts(parser.scripts),
        'caution': 'Keyword matches do not prove filters work. No card metadata is assigned.',
    }
    image_manifest = {
        'purpose': 'Official image candidates; front/back role not yet verified',
        'source_page': URL, 'cards': manifest,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'html_structure_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'first_series_image_manifest.json').write_text(json.dumps(image_manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'javascript_search_report.json').write_text(json.dumps(js_report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'search_dropdown_options.json').write_text(json.dumps(dropdown_report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved: diagnostic_output/search_dropdown_options.json; choices:', dropdown_report['counts']['data_value_choices'])
    print('JS inspected:', len(js_report['scripts']))
    print('Saved: diagnostic_output/javascript_search_report.json')
    print('HTTP:', status, 'Modal count:', len(parser.modals), 'First series:', len(first_ids))
    print('Selects:', [(s['name'], len(s['options'])) for s in parser.selects])
    print('Inputs:', len(parser.inputs), 'Labels:', len(parser.labels))
    for card_id in sampled_ids:
        print(card_id, 'labels:', targets[card_id]['labels_found_in_modal'])
    print('Saved: diagnostic_output/html_structure_report.json')
    print('Saved: diagnostic_output/first_series_image_manifest.json')
    print('READ ONLY: no card data was changed.')


def verify_search_filters():
    """Compare returned card IDs for a few official filter values (read-only)."""
    cases = [
        ('baseline', None, None),
        ('type_cute', 'type', 'キュート'),
        ('type_cool', 'type', 'クール'),
        ('category_tops', 'category', 'トップス'),
        ('category_shoes', 'category', 'シューズ'),
        ('brand_angely_sugar', 'brand', 'エンジェリーシュガー'),
        ('rarity_pr', 'rarity', 'PR'),
        ('invalid_type_control', 'type', '__NONEXISTENT_FILTER_VALUE_98765__'),
    ]
    results = []
    baseline_ids = None
    for case_name, field, value in cases:
        fields = dict(FIELDS)
        if field:
            fields[field] = value
        request = urllib.request.Request(
            URL,
            data=urllib.parse.urlencode(fields).encode('utf-8'),
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; EncoreReadOnlyDiagnostic/1.0)',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'text/html',
                'Referer': BASE,
            },
        )
        item = {'case': case_name, 'field': field, 'value': value}
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                markup = response.read(3_000_000).decode('utf-8', 'replace')
                item['http_status'] = response.status
                item['final_url'] = response.url
            parser = StructureParser()
            parser.feed(markup)
            ids = sorted(card_id for card_id in parser.modals if card_id.startswith('E1-'))
            item['card_count'] = len(ids)
            item['card_ids'] = ids
            item['html_length'] = len(markup)
            if case_name == 'baseline':
                baseline_ids = set(ids)
            elif baseline_ids is not None:
                item['is_subset_of_baseline'] = set(ids).issubset(baseline_ids)
                item['identical_to_baseline'] = set(ids) == baseline_ids
                item['outside_baseline'] = sorted(set(ids) - baseline_ids)
        except Exception as exc:
            item['error'] = f'{type(exc).__name__}: {exc}'
        results.append(item)
        print('Filter check:', case_name, 'cards:', item.get('card_count'), 'error:', item.get('error'))

    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'Read-only verification of POST search filters against baseline first-series card IDs',
        'submitted_series': FIELDS['series'],
        'results': results,
        'interpretation_note': (
            'Different subsets suggest filtering, but do not prove every card attribute. '
            'If a filter returns the baseline or zero cards, check server handling and control results. '
            'No card data is modified.'
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / 'search_filter_verification.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved:', destination)


if __name__ == '__main__':
    main()
    verify_search_filters()
