#!/usr/bin/env python3
"""THESMIO: public-source snapshot synchronizer. Never fabricates records.

Each source is isolated. A failed refresh retains its last-good data. Data
returned by Vouliwatch remains credited and subject to its own usage terms.
"""
import html
from html.parser import HTMLParser
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse, quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'public/data/catalog.json'
PARLIAMENT = 'https://www.hellenicparliament.gr/api.ashx'
TRANSPARENCY = 'https://diafaneia.hellenicparliament.gr/api.ashx'
VW = 'https://api.vouliwatch.gr/v1'
DIAVGEIA = 'https://diavgeia.gov.gr/opendata'
STAMP = datetime.now(timezone.utc).isoformat()
SOURCES = {
 'laws': ('Βουλή των Ελλήνων', 'https://www.hellenicparliament.gr/opendata/'),
 'documents': ('Διαφάνεια της Βουλής', 'https://diafaneia.hellenicparliament.gr/OpenData'),
 'members': ('Vouliwatch', 'https://api.vouliwatch.gr/v1'),
 'parties': ('Vouliwatch', 'https://api.vouliwatch.gr/v1'),
 'votes': ('Vouliwatch', 'https://api.vouliwatch.gr/v1'),
 'control': ('Vouliwatch', 'https://api.vouliwatch.gr/v1'),
 'diavgeia': ('Πρόγραμμα Διαύγεια', 'https://diavgeia.gov.gr/api/help'),
}
LIMITS = {'laws': 30, 'documents': 3, 'members': 1, 'parties': 2, 'votes': 5, 'control': 4, 'diavgeia': 5}


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
    def handle_data(self, data): self.parts.append(data)
    def handle_starttag(self, tag, attrs):
        if tag in ('p','br','li','div'): self.parts.append(' ')

def clean(value, cap=900):
    if value is None: return ''
    if isinstance(value,(list,dict)): return ''
    txt=str(value)
    parser=_HTMLText()
    try: parser.feed(txt); txt=' '.join(parser.parts)
    except Exception: txt=re.sub(r'<[^>]+>',' ',txt)
    txt=html.unescape(txt).replace('\u200b',' ')
    txt=re.sub(r'\s+',' ',txt).strip()
    return txt[:cap].rstrip()


def fetch(url, params=None):
    if params: url += ('&' if '?' in url else '?') + urlencode(params)
    req = Request(url, headers={'User-Agent': 'THESMIO-OpenData/0.2 (https://github.com/Donacgreece/thesmio)', 'Accept': 'application/json'})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=28) as r:
                return json.loads(r.read(12_000_000).decode('utf-8-sig'))
        except Exception as exc:
            if attempt == 2: raise RuntimeError(f'{url}: {type(exc).__name__}: {exc}') from exc
            time.sleep(2 * (attempt + 1))


def xml_law_rows(payload):
    """Best-effort parsing of the Parliament API's documented XML representation."""
    root=ET.fromstring(payload)
    items=[]
    for node in root.iter():
        children=list(node)
        if not children: continue
        row={child.tag.split('}')[-1]: (child.text or '').strip() for child in children if not list(child)}
        keys={k.lower() for k in row}
        if ('title' in keys or 'lawtitle' in keys or 'lawnum' in keys) and len(row)>=2:
            items.append(row)
    return items


def arr(body):
    """Find actual lists in nested envelopes, including ASP.NET JSON wrappers."""
    if isinstance(body,str):
        try:return arr(json.loads(body))
        except ValueError:return []
    if isinstance(body,list):
        if not body:return []
        if all(isinstance(x,dict) for x in body):return body
        for x in body:
            r=arr(x)
            if r:return r
        return []
    if isinstance(body,dict):
        priorities=('data','results','items','rows','laws','documents','members','political_parties','parties','votings','votes','d','response','records','decisions','list','result','value')
        for key in priorities:
            for k,v in body.items():
                if str(k).lower()==key:
                    result=arr(v)
                    if result:return result
        for v in body.values():
            if isinstance(v,(list,dict)):
                result=arr(v)
                if result:return result
    return []

def pick(obj, *keys):
    if not isinstance(obj, dict): return ''
    lowered = {str(k).lower().replace('_', ''): v for k, v in obj.items()}
    for key in keys:
        v = lowered.get(key.lower().replace('_', ''))
        if isinstance(v, dict):
            for sub in ('name', 'title', 'label', 'value', 'full_name'):
                if v.get(sub): v = v[sub]; break
        if isinstance(v, (str, int, float)) and str(v).strip(): return clean(v)
    return ''


def date(value):
    if not value: return ''
    if isinstance(value, (int, float)):
        try: return datetime.fromtimestamp(value / (1000 if value > 10_000_000_000 else 1), timezone.utc).date().isoformat()
        except (ValueError, OSError, OverflowError): return ''
    value = str(value)
    if re.match(r'^\d{4}-\d\d-\d\d', value): return value[:10]
    m = re.match(r'^(\d\d?)/(\d\d?)/(\d{4})', value)
    if m: return f'{int(m[3]):04d}-{int(m[2]):02d}-{int(m[1]):02d}'
    m = re.search(r'Date\((\d+)\)', value)
    if m:
        try: return datetime.fromtimestamp(int(m[1]) / 1000, timezone.utc).date().isoformat()
        except (ValueError, OSError, OverflowError): return ''
    return ''


def href(value, base='https://www.hellenicparliament.gr'):
    if not isinstance(value, str) or not value: return ''
    if value.startswith('/'): value = base + value
    p = urlparse(value)
    return value if p.scheme in ('http', 'https') and p.hostname else ''


def ident(row, *keys):
    found = pick(row, *keys)
    return found if found else hashlib.sha1(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]


def law(row):
    title = pick(row, 'title', 'lawtitle', 'law_title', 'title_el', 'lawname', 'description', 'name', 'shorttitle', 'subject', 'law', 'caption', 'lawdescription')
    if not title: return None
    voted = date(pick(row, 'datevoted', 'date_voted', 'voteddate', 'dateVoted'))
    inserted = date(pick(row, 'dateinserted', 'date_inserted', 'dateInserted'))
    number = pick(row, 'lawnum', 'law_num', 'lawnr', 'lawNumber', 'number', 'law_no')
    year = pick(row, 'year', 'lawyear') or (voted or inserted)[:4]
    return dict(id=ident(row,'id','lawid','law_id','guid','_id'), title=title, lawnum=number, year=year,
        datevoted=voted,dateinserted=inserted,ministry=pick(row,'ministryname','ministry','ministryTitle'),
        category=pick(row,'categoryname','category','type','lawtype'),
        url=href(pick(row,'url','link','lawurl','weburl','permalink')),
        pdf=href(pick(row,'pdf','pdfurl','fileurl','documenturl')),
        description='',source=SOURCES['laws'][1])


def generic(row, kind):
    if not isinstance(row, dict): return None
    labelsets = {
     'members': ('fullname','full_name','display_name','name','title'),
     'parties': ('name','title','short_name','abbreviation'),
     'votes': ('title','subject','name','description','label'),
     'control': ('title','subject','name','question','description'),
     'documents': ('title','subject','description','name','protocolnumber'),
    }
    title = pick(row, *labelsets[kind])
    if kind == 'members' and not title:
        title = ' '.join(filter(None,(pick(row,'first_name','firstname','firstName'),pick(row,'last_name','lastname','lastName'))))
    if not title: return None
    base = 'https://api.vouliwatch.gr' if kind not in ('documents',) else 'https://diafaneia.hellenicparliament.gr'
    return {
     'id': ident(row,'id','_id','uuid','slug','path','_path','ada'),
     'title': clean(title, 280),
     'subtitle': clean(pick(row,'party','political_party','parliament_group','district','electoral_district','description','type','ministry'), 220),
     'date': date(pick(row,'date','created_at','updated_at','voting_date','datevoted','date_published','dateposted','publish_date')),
     'url': href(pick(row,'url','link','permalink','weburl','document_url'),base),
     'source': SOURCES[kind][0],
     'detail': clean(pick(row,'result','status','type','category','position'), 100),
    }


def normalize_diavgeia(row):
    """Normalize only public search metadata; official ADA remains canonical ID."""
    if not isinstance(row, dict): return None
    ada = pick(row, 'ada')
    title = pick(row, 'subject')
    if not ada or not title: return None
    # Never construct paths from arbitrary input; ADA is from the upstream response.
    return {
      'id': ada, 'ada': ada, 'title': clean(title, 280),
      'subtitle': pick(row,'organizationLabel','organizationName','organizationId'),
      'date': date(row.get('issueDate') or row.get('submissionTimestamp')),
      'url': 'https://diavgeia.gov.gr/decision/view/' + ada,
      'source': 'Πρόγραμμα Διαύγεια',
      'detail': pick(row, 'decisionTypeLabel','decisionTypeId','status'),
    }


def collect_diavgeia():
    """Incremental, bounded snapshot. Respect upstream search downtime and rate limits.

    Search is currently reported limited to ADA during maintenance: errors are
    expected and preserved as source status, not interpreted as no new decisions.
    """
    today = datetime.now(timezone.utc).date()
    # Up to 72-hour overlap picks up delayed submissions without scraping.
    start = today - timedelta(days=3)
    output = {}
    for page in range(LIMITS['diavgeia']):
        body = fetch(DIAVGEIA + '/search', {
           'from_date':start.isoformat(),'to_date':today.isoformat(),
           'status':'published','sort':'recent','page':page,'size':100
        })
        if isinstance(body,dict) and body.get('error'):
            raise RuntimeError(f'Diavgeia search unavailable: {str(body["error"])[:140]}')
        rows=arr(body)
        if page==0 and not rows:
            raise RuntimeError(f'Diavgeia search empty or restricted; root={list(body)[:12] if isinstance(body,dict) else type(body).__name__}')
        for item in rows:
            normalized=normalize_diavgeia(item)
            if normalized: output[normalized['id']]=normalized
        print(f'diavgeia: page={page}, results={len(rows)}, valid={len(output)}')
        if len(rows)<100: break
        time.sleep(.8)
    if not output: raise RuntimeError('No valid ADA records from Diavgeia')
    return list(output.values())


def collect_pages(base, query, kind, max_pages, page_size):
    records = []
    for page in range(1,max_pages+1):
        args = dict(query)
        if kind in ('laws','documents'): args.update(pageNo=page,pageSize=page_size)
        else: args.update(page=page,per_page=page_size)
        body = fetch(base,args)
        batch = arr(body)
        if page == 1 and not batch:
            # Fail closed: upstream schema may have changed; do not silently wipe data.
            raise RuntimeError(f'Unexpected empty or unmapped response from {kind}. Root keys: {list(body)[:20] if isinstance(body,dict) else type(body).__name__}')
        if not batch: break
        records.extend(batch)
        print(f'{kind}: page {page}, {len(batch)} records')
        if page>1 and len(records)>=2*len(batch) and batch == records[-2*len(batch):-len(batch)]: break
        time.sleep(.35)
    return records


def collect_law_archive():
    """Independent MIT-licensed legislative-text index fallback.

    A GitHub tree provides filenames and raw document paths. We index only
    verified path metadata and optional text headers, never invent law titles.
    The repository contains source-derived text, not consolidated law.
    """
    tree_url = 'https://api.github.com/repos/kafidas/just-text/git/trees/main?recursive=1'
    headers = {'Accept': 'application/vnd.github+json',
               'User-Agent': 'THESMIO/0.5 (https://github.com/Donacgreece/thesmio)'}
    token = os.environ.get('GITHUB_TOKEN', '')
    if token: headers['Authorization'] = f'Bearer {token}'
    request = Request(tree_url, headers=headers)
    with urlopen(request, timeout=35) as r:
        obj = json.load(r)
    if obj.get('truncated'):
        print('LAW ARCHIVE: GitHub tree truncated',file=sys.stderr)
    paths = [item['path'] for item in obj.get('tree', [])
             if item.get('type') == 'blob' and item.get('path','').lower().endswith(('.txt','.md'))
             and re.match(r'^(20(?:2[1-6]))/',item['path'])]
    paths.sort(reverse=True)
    if not paths:
        raise RuntimeError('Alternative legal archive returned no document paths')
    result = {}
    # Controlled incremental coverage: existing records remain available; fetch a
    # bounded subset per synchronization to respect GitHub API / bandwidth limits.
    for path in paths[:180]:
        match = re.search(r'(?<!\d)([45]\d{3})(?!\d)',path)
        if not match: continue
        year_match=re.match(r'^(20\d{2})/',path)
        if not year_match: continue
        year=year_match.group(1)
        law_number=match.group(1)
        rel='https://github.com/kafidas/just-text/blob/main/' + '/'.join(quote(bit,safe='') for bit in path.split('/'))
        key=f'{law_number}/{year}'
        # Validated numeric year/number in the archive path, no AI title synthesis.
        result[key]={'id':'archive-'+key,'title':f'Νόμος {key}',
             'lawnum':law_number,'year':year,'datevoted':'','dateinserted':'',
             'ministry':'','category':'Κείμενο νόμου (αρχείο)', 'url':rel,'pdf':'',
             'description':'Κείμενο όπως μεταγράφηκε από ΦΕΚ, όχι κωδικοποιημένη νομοθεσία.',
             'source':'https://github.com/kafidas/just-text'}
    if not result: raise RuntimeError('Alternative archive has files but no parseable law numbers')
    print(f'law archive: {len(result)} metadata entries')
    return list(result.values())



def collect_gazette_index():
    """Fallback index of actual FEK-A issue files, NOT an index of numbered laws.

    Third-party versioned mirror: lighteternal/legalize-gr (MIT repository).
    A single FEK issue can contain multiple acts, so NEVER map the FEK issue
    number to a law number. Keep a deep link to the mirrored source document.
    """
    api='https://api.github.com/repos/lighteternal/legalize-gr/git/trees/main?recursive=1'
    headers={'Accept':'application/vnd.github+json',
             'User-Agent':'THESMIO/0.6 (+https://github.com/Donacgreece/thesmio)'}
    token=os.getenv('GITHUB_TOKEN','')
    if token:headers['Authorization']='Bearer '+token
    with urlopen(Request(api,headers=headers),timeout=50) as response:
        tree=json.load(response)
    if not isinstance(tree,dict) or not isinstance(tree.get('tree'),list):
        raise RuntimeError('Unexpected legalize-gr tree response')
    if tree.get('truncated'):
        raise RuntimeError('legalize-gr tree truncated; declining partial index')
    matches=[]
    for row in tree['tree']:
        if row.get('type')!='blob':continue
        path=row.get('path','')
        match=re.fullmatch(r'gr/FEK-A-(\d{1,5})-(20\d{2})\.md',path,re.IGNORECASE)
        if not match:continue
        issue,year=int(match.group(1)),int(match.group(2))
        if not 2000<=year<=datetime.now(timezone.utc).year or issue<1:continue
        matches.append((year,issue,path))
    if not matches:raise RuntimeError('No valid FEK A files in legalize-gr tree')
    matches.sort(reverse=True)
    # index the 2,500 newest gazette issues without requesting their complete text.
    result=[]
    for year,issue,path in matches[:2500]:
        link='https://github.com/lighteternal/legalize-gr/blob/main/'+path
        result.append({'id':f'fek-a-{year}-{issue}',
                       'title':f'ΦΕΚ Α΄ {issue}/{year}',
                       'lawnum':'','year':str(year),'datevoted':'','dateinserted':'',
                       'ministry':'','category':'ΦΕΚ Α΄ (αρχείο τρίτου)',
                       'url':link,'pdf':'',
                       'description':'Τεύχος ΦΕΚ Α΄ σε αρχείο Markdown. Δεν αποτελεί αριθμό νόμου ή κωδικοποιημένο κείμενο.',
                       'source':'https://github.com/lighteternal/legalize-gr'})
    print(f'gazette mirror: {len(result)} FEK issues indexed (not numbered laws)')
    return result


def backup_legislation():
    errors=[]
    for provider in (collect_law_archive,collect_gazette_index):
        try:
            result=provider()
            if result:return result
        except Exception as exc:
            errors.append(f'{getattr(provider, '__name__', 'collector')}: {exc}')
            print(f'legislation backup failed: {errors[-1]}',file=sys.stderr)
    raise RuntimeError('No legislative backup available: '+'; '.join(errors))

def run_source(kind):
    if kind == 'diavgeia':
        return collect_diavgeia()
    if kind == 'laws':
        try:
            raw = collect_pages(PARLIAMENT, {'q':'laws'}, kind, LIMITS[kind], 50)
        except Exception as primary:
            print(f'laws: JSON endpoint failed ({primary}); trying official XML format', file=sys.stderr)
            xmlurl = PARLIAMENT + '?' + urlencode({'q':'laws','pageNo':1,'pageSize':50,'format':'xml'})
            request = Request(xmlurl, headers={'User-Agent':'THESMIO-OpenData/0.4.1 (https://github.com/Donacgreece/thesmio)','Accept':'application/xml,text/xml'})
            try:
                with urlopen(request, timeout=35) as response:
                    raw = xml_law_rows(response.read(12_000_000).decode('utf-8-sig'))
                if not raw: raise RuntimeError('XML returned no recognized legislative rows')
                print(f'laws: XML fallback returned {len(raw)} rows')
            except Exception as secondary:
                print(f'Parliament JSON/XML unavailable ({secondary}); using attributed text archive fallback', file=sys.stderr)
                return backup_legislation()
        cleaned = [law(x) for x in raw]
    elif kind == 'documents':
        raw = collect_pages(TRANSPARENCY, {'q':'documents'},kind,LIMITS[kind],30)
        cleaned = [generic(x,kind) for x in raw]
    else:
        endpoints = {'members':'/parliament/gr/session/members','parties':'/political_parties','votes':'/votings','control':'/parliamentary-control/documents'}
        if kind == 'members':
            body = fetch(VW+endpoints[kind]); raw=arr(body)
            if not raw: raise RuntimeError('Member list returned empty/unrecognized response')
        else: raw = collect_pages(VW+endpoints[kind],{},kind,LIMITS[kind],20)
        cleaned = [generic(x,kind) for x in raw]
    out = {}
    for x in cleaned:
        if x: out[x['id']]=x
    if not out: raise RuntimeError(f'No valid {kind} records after normalization')
    vals = list(out.values())
    if kind == 'laws': vals.sort(key=lambda r: (r['datevoted'],r['year'],r['lawnum']),reverse=True)
    elif kind in ('votes','control','documents'): vals.sort(key=lambda r:r['date'],reverse=True)
    return vals


def main():
    try: old = json.loads(OUT.read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError): old={}
    catalog = {
      'updatedAt':old.get('updatedAt'), 'source':SOURCES['laws'][1],
      'status':'pending', 'error':None,
      'laws':old.get('laws',[]), 'ministries':old.get('ministries',[]), 'categories':old.get('categories',[]),
      'members':old.get('members',[]),'parties':old.get('parties',[]),'votes':old.get('votes',[]),
      'control':old.get('control',[]),'documents':old.get('documents',[]),
      'diavgeia':old.get('diavgeia',[]),
      'sources':dict(old.get('sources') or {}),
    }
    failures=[]; successes=0
    for kind in ('laws','members','parties','votes','control','documents','diavgeia'):
        src,link=SOURCES[kind]
        previous=catalog.get(kind,[])
        try:
            fresh=run_source(kind)
            # Do not silently shrink a populated dataset to a few records due to upstream changes.
            if kind != 'diavgeia' and previous and len(fresh) < max(3,len(previous)//5):
                raise RuntimeError(f'Unexpected dataset shrink: {len(previous)} -> {len(fresh)}')
            catalog[kind]=(sorted({r['id']:r for r in (previous + fresh)}.values(), key=lambda r:r.get('date',''), reverse=True)[:2500] if kind == 'diavgeia' else fresh)
            catalog['sources'][kind]={'name':('Kafidas / just-text' if kind=='laws' and fresh and fresh[0].get('id','').startswith('archive-') else ('Legalize GR (ευρετήριο ΦΕΚ)' if kind=='laws' and fresh and fresh[0].get('id','').startswith('fek-a-') else src)),
              'url':(fresh[0]['source'] if kind=='laws' and fresh and fresh[0].get('id','').startswith(('archive-','fek-a-')) else link),
              'status':('fallback' if kind=='laws' and fresh and fresh[0].get('id','').startswith(('archive-','fek-a-')) else 'ok'),
              'updatedAt':STAMP,'count':len(catalog[kind]),'coverage':('ΦΕΚ Α΄, όχι μεμονωμένοι νόμοι' if kind=='laws' and fresh and fresh[0].get('id','').startswith('fek-a-') else 'Κατάλογος διαθέσιμων εγγραφών')}
            successes+=1
        except Exception as e:
            failures.append(kind)
            catalog['sources'][kind]={'name':src,'url':link,'status':'stale' if previous else 'error',
              'updatedAt':(catalog['sources'].get(kind) or {}).get('updatedAt'), 'count':len(previous), 'error':str(e)[:700]}
            print(f'WARNING [{kind}] {type(e).__name__}: {e}',file=sys.stderr)
    # Use fresh metadata when available, else retain last-good.
    for name in ('ministries','categories'):
        try:
            raw=arr(fetch(PARLIAMENT,{'q':name}))
            if raw:catalog[name]=raw
        except Exception as e: print(f'WARNING [{name}]: {e}',file=sys.stderr)
    if successes: catalog['updatedAt']=STAMP
    catalog['status']='ok' if not failures else ('partial' if successes else 'stale')
    if not successes and not any(catalog[k] for k in SOURCES): catalog['status']='error'
    catalog['error']=f'Αποτυχία ενημέρωσης: {", ".join(failures)}' if failures else None
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'THESMIO: {successes}/7 sources synced; laws={len(catalog["laws"])} members={len(catalog["members"])} parties={len(catalog["parties"])} votes={len(catalog["votes"])} control={len(catalog["control"])} documents={len(catalog["documents"])} diavgeia={len(catalog["diavgeia"])}')
    # Explicit failed sources in GitHub Actions, but never destroy a good snapshot.
    return 0 if successes else 1

if __name__=='__main__': sys.exit(main())
