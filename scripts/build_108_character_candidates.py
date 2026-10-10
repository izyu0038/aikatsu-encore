"""Read-only, heuristic character candidate review for Aikatsu Encore cards.
No model is trained; color/shape resemblance is NOT identification.
"""
import base64, csv, html, io, json, re, urllib.request
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

ROOT=Path('diagnostic_output/character_108_review'); ROOT.mkdir(parents=True,exist_ok=True)
CARD_FILE=Path('data/108_character_verification.csv')
REF_FILE=Path('data/idol_character_reference_candidates.csv')
CACHE=Path('diagnostic_output/character_108_cache'); CACHE.mkdir(parents=True,exist_ok=True)

def read_csv(p):
    if not p.exists(): raise FileNotFoundError(f'Missing {p} (check filename and folder)')
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def get_image(url):
    if not url.startswith('https://'): raise ValueError('HTTPS URL required')
    from hashlib import sha256
    target=CACHE/(sha256(url.encode()).hexdigest()+'.img')
    if not target.exists():
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 Aikatsu character review'})
        with urllib.request.urlopen(req,timeout=25) as r:
            data=r.read(7_000_001)
        if len(data)>7_000_000:raise ValueError('image too large')
        target.write_bytes(data)
    im=Image.open(target); im.load(); return im.convert('RGB')

def descriptor(im):
    # Low-level visual resemblance only: RGB histograms + coarse spatial colors.
    # Crops emphasize the upper-middle part of a card, which may still contain clothing/UI.
    w,h=im.size
    crop=im.crop((int(w*.14),int(h*.05),int(w*.86),int(h*.77)))
    arr=np.asarray(ImageOps.fit(crop,(64,64)),dtype=np.float32)/255.
    bins=[]
    for c in range(3):
        hist,_=np.histogram(arr[:,:,c],bins=16,range=(0,1))
        bins.extend((hist/hist.sum()).tolist())
    # coarse grid preserves rough composition
    grid=np.asarray(ImageOps.fit(crop,(8,8)),dtype=np.float32).reshape(-1)/255.
    vec=np.concatenate([np.asarray(bins,dtype=np.float32)*2,grid*.3])
    return vec/(np.linalg.norm(vec)+1e-9)

def thumb(im,maxsize=(140,190)):
    im=im.copy(); im.thumbnail(maxsize)
    out=io.BytesIO(); im.save(out,format='JPEG',quality=65)
    return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode('ascii')

def main():
    cards=read_csv(CARD_FILE); refs=read_csv(REF_FILE)
    if len(cards)!=108:print(f'WARNING: expected 108 cards, CSV contains {len(cards)}')
    print(f'Cards: {len(cards)}; reference rows: {len(refs)}',flush=True)
    ref_items=[]; ref_errors=[]
    for i,row in enumerate(refs,1):
        name=row.get('character_candidate','').strip(); url=row.get('image_url','').strip()
        if not name or not url:continue
        try:
            im=get_image(url)
            ref_items.append((name,url,descriptor(im),thumb(im,(100,135))))
        except Exception as e:ref_errors.append({'row':i,'name':name,'error':str(e)[:180]})
    if not ref_items:raise RuntimeError('No reference images downloaded; cannot compare')
    unique_names=sorted(set(x[0] for x in ref_items))
    records=[]; errors=[]
    for i,row in enumerate(cards,1):
        cid=row.get('card_id','').strip(); url=row.get('card_image','').strip()
        if not cid or not url:
            errors.append({'row':i,'card_id':cid,'error':'missing card_id or card_image'});continue
        try:
            im=get_image(url); v=descriptor(im)
            # Collapse multiple images per name to best match; no confidence/probability.
            scores={}
            for name,refurl,refvec,refthumb in ref_items:
                score=float(np.dot(v,refvec))
                if name not in scores or score>scores[name][0]:scores[name]=(score,refurl,refthumb)
            ranked=sorted(scores.items(),key=lambda x:x[1][0],reverse=True)[:3]
            records.append({'card_id':cid,'card_name':row.get('card_name',''),
                'card_image':url,'card_thumb':thumb(im),'candidates':[
                {'name':name,'similarity':round(data[0],4),'reference_url':data[1], 'reference_thumb':data[2]}
                for name,data in ranked]})
        except Exception as e:errors.append({'row':i,'card_id':cid,'error':str(e)[:180]})
        if i%20==0:print(f'Processed {i}/{len(cards)}',flush=True)
    outcsv=ROOT/'character_candidates_108.csv'
    with outcsv.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['card_id','card_name','candidate_1','candidate_2','candidate_3','verification_status','confirmed_character','card_image'])
        for r in records:
            names=[x['name'] for x in r['candidates']]
            writer.writerow([r['card_id'],r['card_name'],*(names+['']*3)[:3],'要目視確認','',r['card_image']])
    # Self-contained HTML; selection only happens in the user's browser, never changes repository data.
    payload=json.dumps(records,ensure_ascii=False).replace('<','\\u003c')
    names_json=json.dumps(unique_names,ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>108枚 キャラクター候補確認</title>
<style>body{font-family:system-ui,sans-serif;background:#fff8fb;color:#35293a;max-width:1150px;margin:auto;padding:15px}h1{font-size:1.5rem}.note{background:#fff0d5;padding:14px;border-radius:10px}article{display:flex;gap:15px;background:white;margin:14px 0;padding:14px;border:1px solid #e8dce7;border-radius:12px;flex-wrap:wrap}.cardimg{width:145px;object-fit:contain;align-self:flex-start}.content{flex:1;min-width:230px}.choices{display:flex;gap:8px;flex-wrap:wrap}.choice{width:130px;border:1px solid #ddd;border-radius:8px;padding:6px;font-size:12px}.choice img{max-width:100px;height:100px;object-fit:contain;display:block;margin:auto}select,button{font-size:16px;padding:8px;margin-top:8px}button{background:#c74181;color:white;border:0;border-radius:8px;cursor:pointer}.sub{color:#67566c;font-size:13px}a{color:#a02c68}#count{font-weight:bold}</style>
<h1>108枚 キャラクター候補の目視確認</h1><p class="note"><strong>重要：</strong>候補は色・画像構図の似方だけで並べたもので、AIによる人物認識や正解判定ではありません。上位候補が正しいとは限りません。各カードを目で確認し、確実な場合だけキャラクター名を選択してください。不明な場合は「未確認」のままにしてください。サイトのデータは一切変更されません。</p>
<p>確認済み：<span id="count">0</span> / <span id="total"></span>　<button id="save">確認結果CSVを保存</button></p><div id="cards"></div>
<script>
const records=__RECORDS__; const names=__NAMES__;const selections={};const container=document.getElementById('cards');document.getElementById('total').textContent=records.length;
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
for(const r of records){const a=document.createElement('article');const options=['<option value="">未確認</option>',...names.map(n=>'<option value="'+esc(n)+'">'+esc(n)+'</option>')].join('');a.innerHTML='<img class="cardimg" src="'+r.card_thumb+'"><div class="content"><strong>'+esc(r.card_id)+'</strong> '+esc(r.card_name)+'<p class="sub">画像の色・構図が似ている参考画像（正解保証なし）</p><div class="choices">'+r.candidates.map((c,i)=>'<div class="choice"><div>候補'+(i+1)+': '+esc(c.name)+'</div><img src="'+c.reference_thumb+'"><a href="'+esc(c.reference_url)+'" target="_blank" rel="noopener">公式画像</a></div>').join('')+'</div><label>目視確認した名前：<select>'+options+'</select></label><p class="sub">候補以外の名前も選択可能。判定不能なら未確認のままにしてください。</p></div>';const select=a.querySelector('select');select.addEventListener('change',()=>{selections[r.card_id]=select.value;document.getElementById('count').textContent=Object.values(selections).filter(Boolean).length});container.appendChild(a)}
function csvCell(s){return '"'+String(s??'').replace(/"/g,'""')+'"'}
document.getElementById('save').onclick=()=>{const lines=[['card_id','card_name','confirmed_character','verification_status','card_image'],...records.map(r=>[r.card_id,r.card_name,selections[r.card_id]||'',selections[r.card_id]?'目視確認済み':'未確認',r.card_image])];const blob=new Blob(['\\uFEFF'+lines.map(row=>row.map(csvCell).join(',')).join('\\r\\n')],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='character_108_reviewed.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
</script></html>'''
    page=page.replace('__RECORDS__',payload).replace('__NAMES__',names_json)
    (ROOT/'review_108_cards.html').write_text(page,encoding='utf-8')
    summary={'input_cards':len(cards),'processed_cards':len(records),'reference_rows':len(refs),'reference_images_downloaded':len(ref_items),'distinct_reference_names':len(unique_names),'card_errors':errors,'reference_errors':ref_errors,'warning':'Heuristic visual candidates only; all require human verification; no production data modified.'}
    (ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if not isinstance(v,list)},ensure_ascii=False))
if __name__=='__main__':main()
