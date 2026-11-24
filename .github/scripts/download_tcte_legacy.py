import os,re,json,time,hashlib,datetime,io,zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin,urlparse,unquote
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
from bs4 import BeautifulSoup
YEAR=int(os.environ['EXAM_ROC_YEAR'])
BASE=f'https://web1.tcte.edu.tw/EXAM/{YEAR:03d}_4y/'
OUT=Path('output'); (OUT/'original').mkdir(parents=True,exist_ok=True)
sess=requests.Session()
HEAD={'User-Agent':'Mozilla/5.0 (compatible; ExamPaperArchive/1.0)','Referer':BASE}
resp=sess.get(BASE,headers=HEAD,timeout=(12,50));resp.raise_for_status()
(OUT/'index.html').write_bytes(resp.content)
soup=BeautifulSoup(resp.content,'html.parser')
items={}
allowed={'.pdf','.zip','.jpg','.jpeg','.png','.gif','.xls','.xlsx','.htm','.html'}
for a in soup.select('a[href]'):
    h=a.get('href','').strip()
    if not h or h.startswith('#'): continue
    url=urljoin(BASE,h)
    p=urlparse(url)
    if p.scheme not in ('http','https') or p.netloc!='web1.tcte.edu.tw':continue
    b=urlparse(BASE).path
    if not p.path.startswith(b):continue
    rel=unquote(p.path[len(b):]).lstrip('/')
    parts=PurePosixPath(rel).parts
    if not parts or '..' in parts:continue
    ext=PurePosixPath(rel).suffix.lower()
    if ext not in allowed:continue
    if re.search(r'(?i)(?:grade|grad[e]|組距)',rel):continue
    if ext=='.zip' and '-gif.zip' in rel.lower():continue
    if ext in {'.htm','.html'} and not re.search(r'(?i)(answer|solve)',rel):continue
    if rel.lower() in ('index.html','index.htm'):continue
    label=a.get_text(' ',strip=True)[:100]
    kind='answer' if re.search(r'(?i)(answer|solve|standard|final|解答|答案)',rel+' '+label) else 'question'
    if ext in ('.jpg','.jpeg','.png','.gif'):kind='question_image'
    items[rel]={'relative_path':rel,'source_url':url,'source_anchor':label,'file_type':ext,'category':kind}
(OUT/'source_index.json').write_text(json.dumps({'official_index':BASE,'candidates':len(items),'files':list(items.values())},ensure_ascii=False,indent=2),encoding='utf-8')
print('EXPECTED',len(items),'BY_EXTENSION',{x:sum(v['file_type']==x for v in items.values()) for x in allowed},flush=True)
def download(item):
    err=[]
    for attempt in range(3):
        try:
            r=sess.get(item['source_url'],headers=HEAD,timeout=(15,90))
            r.raise_for_status()
            data=r.content;ext=item['file_type']
            if ext=='.pdf' and not(data.startswith(b'%PDF-') and b'%%EOF' in data[-8192:]):raise ValueError('Invalid PDF structure '+repr(data[:30]))
            if ext=='.zip' and not zipfile.is_zipfile(io.BytesIO(data)):raise ValueError('Invalid ZIP')
            if ext in ('.jpg','.jpeg') and not data.startswith(b'\xff\xd8'):raise ValueError('Invalid JPEG')
            if ext=='.gif' and not data.startswith((b'GIF87a',b'GIF89a')):raise ValueError('Invalid GIF')
            if len(data)<100:raise ValueError('Unusually small file '+str(len(data)))
            dest=OUT/'original'/item['relative_path']
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            return {**item,'status':'downloaded','size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'final_url':r.url}
        except Exception as e:
            err.append(str(e)[:220]);time.sleep(attempt+1)
    return {**item,'status':'failed','errors':err}
rs=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    fs={pool.submit(download,item):item for item in items.values()}
    for f in as_completed(fs):
        d=f.result();rs.append(d)
        print('SUCCESS' if d['status']=='downloaded' else 'FAILED',d['relative_path'],d.get('size',d.get('errors')),flush=True)
rs.sort(key=lambda d:d['relative_path'])
summary={'exam':f'{YEAR} 四技二專統一入學測驗（舊版原始檔）','source':BASE,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'expected':len(rs),'success':sum(d['status']=='downloaded' for d in rs),'failed':sum(d['status']=='failed' for d in rs),'bytes':sum(d.get('size',0) for d in rs),'pdfs':sum(d['status']=='downloaded' and d['file_type']=='.pdf' for d in rs),'archives':sum(d['status']=='downloaded' and d['file_type']=='.zip' for d in rs),'images':sum(d['status']=='downloaded' and d['file_type'] in ('.jpg','.jpeg','.png','.gif') for d in rs),'files':rs}
(OUT/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('SUMMARY',summary['expected'],summary['success'],summary['failed'],summary['pdfs'],summary['archives'],summary['images'],summary['bytes'],flush=True)