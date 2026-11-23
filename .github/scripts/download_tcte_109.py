import base64,hashlib,json,os,re,time,datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
BASE='https://web1.tcte.edu.tw/EXAM/109_4y/'
ROOT=Path('output'); (ROOT/'pdf').mkdir(parents=True,exist_ok=True)
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; ExamArchive/1.0)','Referer':BASE,'Accept':'application/pdf,*/*'}
index=requests.get(BASE,headers=HEADERS,timeout=45)
index.raise_for_status()
(ROOT/'index.html').write_bytes(index.content)
soup=BeautifulSoup(index.content,'html.parser')
items=[];by_filename={}
for a in soup.select('input[onclick]'):
 s=a.get('onclick','')
 m=re.search(r"location.href=['\"]([^'\"]+)['\"]",s)
 if not m:continue
 url=urljoin(BASE,m.group(1)); b=re.search(r'obj=([^&]+)',url)
 if not b:continue
 try:name=base64.b64decode(b.group(1)).decode()
 except Exception:continue
 if not (name.startswith('109-4y-') and name.endswith('.pdf')):continue
 if '-Grade-' in name:continue
 if not re.fullmatch(r'[a-zA-Z0-9_.-]+',name):continue
 if name in by_filename:continue
 by_filename[name]={'filename':name,'url':url,'source_button':a.get('value'),'category':'standard_answer' if '-standard' in name else 'question'}
items=list(by_filename.values())
(ROOT/'source_index.json').write_text(json.dumps({'official_source':BASE,'expected_count':len(items),'items':items},ensure_ascii=False,indent=2),encoding='utf-8')
print('EXPECTED',len(items),flush=True)
def get(item):
 err=[]
 for attempt in range(4):
  try:
   rs=requests.get(item['url'],headers=HEADERS,timeout=(15,75),allow_redirects=True)
   rs.raise_for_status()
   b=rs.content
   if not b.startswith(b'%PDF-'):raise ValueError('invalid PDF magic '+repr(b[:80]))
   if b'%%EOF' not in b[-8192:]:raise ValueError('PDF EOF missing')
   dest=ROOT/'pdf'/item['filename'];dest.write_bytes(b)
   d={k:item[k] for k in ['filename','url','source_button','category']};d.update(status='downloaded',size=len(b),sha256=hashlib.sha256(b).hexdigest(),final_url=rs.url)
   return d
  except Exception as e:
   err.append(str(e)[:250]);time.sleep(1.0*(attempt+1))
 return {**item,'status':'failed','errors':err}
results=[]
with ThreadPoolExecutor(max_workers=6) as pool:
 fs={pool.submit(get,x):x for x in items}
 for fu in as_completed(fs):
  r=fu.result();results.append(r)
  print('SUCCESS' if r['status']=='downloaded' else 'FAILED',r['filename'],r.get('size',r.get('errors')),flush=True)
results.sort(key=lambda r:r['filename'])
summary={'exam':'109 四技二專統一入學測驗','source':BASE,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'expected':len(items),'success':sum(x['status']=='downloaded' for x in results),'failed':sum(x['status']!='downloaded' for x in results),'question_count':sum(x['status']=='downloaded' and x['category']=='question' for x in results),'answer_count':sum(x['status']=='downloaded' and x['category']=='standard_answer' for x in results),'bytes':sum(x.get('size',0) for x in results),'files':results}
(ROOT/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('SUMMARY',summary['expected'],summary['success'],summary['failed'],summary['bytes'])