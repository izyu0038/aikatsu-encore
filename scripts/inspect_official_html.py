"""Read-only diagnostic for the official Aikatsu Encore card search response."""
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

OUT = Path('diagnostic_output')
OUT.mkdir(exist_ok=True)
URL = 'https://dcd.aikatsu.com/encore/cardlist/?search=true'
FIELDS = {'free':'', 'series':'629901', 'type':'', 'rarity':'',
          'category':'', 'brand':'', 'display':'1', 'sort':'1'}
TARGET = 'EP-035_R'

class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.matches = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.stack.append((tag, attrs))
        if tag == 'img' and TARGET.lower() in str(attrs).lower():
            self.matches.append({'img_attributes': attrs,
                                 'parent_tags': self.stack[-5:-1]})
    def handle_startendtag(self, tag, attrs):
        if tag == 'img':
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

req = urllib.request.Request(URL, data=urllib.parse.urlencode(FIELDS).encode(),
    headers={'User-Agent':'Mozilla/5.0', 'Content-Type':'application/x-www-form-urlencoded',
             'Accept':'text/html'})
with urllib.request.urlopen(req, timeout=40) as response:
    body = response.read().decode('utf-8', 'replace')
    final_url = response.url

# Extract a bounded source excerpt around target card without uploading entire page.
positions = [m.start() for m in re.finditer(re.escape(TARGET), body, flags=re.I)]
parts = []
for pos in positions[:5]:
    parts.append(body[max(0,pos-1800):min(len(body),pos+2200)])
parser = Tags()
parser.feed(body)
report = {
    'request': {'url':URL, 'method':'POST', 'fields':FIELDS},
    'response_url':final_url, 'html_length':len(body),
    'target':TARGET, 'target_occurrences':len(positions),
    'image_tag_context':parser.matches[:5],
    'source_excerpts':parts,
    'hint':'Inspect nearby text, data-* attributes, links, and scripts. Image alt=表面 is not a card name.'
}
(OUT/'html_structure_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Diagnostic complete. Target occurrences:', len(positions))
print('Report saved: diagnostic_output/html_structure_report.json')
