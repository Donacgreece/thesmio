#!/usr/bin/env python3
"""Fetch verified parliamentary law metadata. Retain last-good on failure.
Only official Parliament open-data source is used in this initial integration.
"""
import json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'public'/'data'/'catalog.json'
API = 'https://www.hellenicparliament.gr/api.ashx'
MAX_PAGES = int(os.environ.get('THESMIO_MAX_PAGES', '40'))
PAGE_SIZE = 50

def get(query):
    url = API + '?' + urlencode(query)
    req = Request(url, headers={'User-Agent':'ThesmioOpenData/0.1 (+https://github.com/Donacgreece/thesmio)','Accept':'application/json'})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=25) as r:
                raw = r.read(8_000_000)
                return json.loads(raw.decode('utf-8-sig'))
        except Exception as exc:
            if attempt == 2: raise RuntimeError(f'{url}: {exc}') from exc
            time.sleep(2 * (attempt+1))

def unwrap(body):
    """Accommodate common legacy ASP.NET JSON response envelopes."""
    if isinstance(body, str):
        try: return unwrap(json.loads(body))
        except (ValueError, TypeError): return []
    if isinstance(body, list):return body
    if isinstance(body, dict):
        for key in ('results','Results','items','Items','data','Data','laws','Laws','List','list','rows','Rows','result','Result','d'):
            if key in body:
                v=unwrap(body[key]);
                if isinstance(v,list):return v
        for v in body.values():
            if isinstance(v,list):return v
    return []

def pick(obj,*keys):
    if not isinstance(obj,dict): return ''
    lower={str(k).lower():v for k,v in obj.items()}
    for key in keys:
        v=obj.get(key,lower.get(key.lower()))
        if isinstance(v, (str,int,float)) and str(v).strip():return str(v).strip()
    return ''

def normalized_date(v):
    if not v:return ''
    if re.match(r'^\d{4}-\d\d-\d\d',v):return v[:10]
    m=re.match(r'^(\d\d?)/(\d\d?)/(\d{4})',v)
    if m:return f'{int(m[3]):04d}-{int(m[2]):02d}-{int(m[1]):02d}'
    m=re.search(r'Date\((\d+)\)',v)
    if m:
        try:return datetime.fromtimestamp(int(m[1])/1000,timezone.utc).date().isoformat()
        except (ValueError,OSError):pass
    return ''

def safe_url(value):
    if not value:return ''
    if value.startswith('/') :value='https://www.hellenicparliament.gr'+value
    try:
        p=urlparse(value)
        return value if p.scheme in ('https','http') and p.hostname else ''
    except ValueError:return ''

def transform(row):
    title=pick(row,'title','lawtitle','law_title','title_el','lawname','description','name')
    if not title:return None
    num=pick(row,'lawnum','law_num','lawnr','lawNumber','number')
    voted=normalized_date(pick(row,'datevoted','date_voted','voteddate','dateVoted'))
    inserted=normalized_date(pick(row,'dateinserted','date_inserted','dateInserted'))
    year=pick(row,'year','lawyear') or ((voted or inserted)[:4])
    ident=pick(row,'id','lawid','law_id','guid') or f'{num}-{year}-{title[:35]}'
    return dict(id=ident,title=title,lawnum=num,year=year,datevoted=voted,dateinserted=inserted,
        ministry=pick(row,'ministryname','ministry_name','ministry','ministryTitle'),
        category=pick(row,'categoryname','category','type','lawtype'),
        url=safe_url(pick(row,'url','link','lawurl','weburl')),
        pdf=safe_url(pick(row,'pdf','pdfurl','fileurl','file','documenturl')),
        description='',source='https://www.hellenicparliament.gr/opendata/')

def main():
    old={}
    if OUT.exists():
        try:old=json.loads(OUT.read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
    try:
        rows=[]
        for page in range(1, MAX_PAGES+1):
            body=get({'q':'laws','pageNo':page,'pageSize':PAGE_SIZE})
            batch=unwrap(body)
            if not batch:
                if page==1:raise RuntimeError('Unexpected or empty response on first page. Inspect upstream JSON schema.')
                break
            rows.extend(batch)
            print(f'Page {page}: {len(batch)} records')
            if len(batch)<PAGE_SIZE:break
            time.sleep(.35)
        laws={}
        for row in rows:
            value=transform(row)
            if value:laws[value['id']]=value
        if not laws:raise RuntimeError('No valid laws parsed: inspect API payload fields')
        items=sorted(laws.values(),key=lambda x:(x['datevoted'],x['year'],x['lawnum']),reverse=True)
        result={'updatedAt':datetime.now(timezone.utc).isoformat(),'source':'https://www.hellenicparliament.gr/opendata/','status':'ok','laws':items,'ministries':[],'categories':[],'error':None}
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Success: {len(items)} verified law records')
    except Exception as e:
        print('Source sync failed:',str(e),file=sys.stderr)
        # Keep previous valid dataset. No fabricated fallback results.
        if old.get('laws'):
            old['status']='stale';old['error']='Latest source refresh failed; showing last successful snapshot.'
            OUT.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
        else:
            old.update({'updatedAt':None,'source':'https://www.hellenicparliament.gr/opendata/','status':'error','laws':[],'ministries':[],'categories':[],'error':'First source sync failed. See GitHub Actions logs.'})
            OUT.write_text(json.dumps(old,ensure_ascii=False,indent=2),encoding='utf-8')
        # Nonzero exit is visible in Actions, but publishing is allowed to proceed separately.
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
