# 质检演练脱敏副本 · 端到端验证（本地SQLite + fakeredis，不触碰仓库源码环境）
# 运行：python3 test-artifacts/gb-4109/test_drills.py
import os,sys,json,tempfile,re,contextlib
TMP=tempfile.mkdtemp(prefix='drill-test-')
os.environ['DATABASE_URL']='sqlite:///'+TMP+'/test.db'
os.environ['REDIS_URL']='redis://localhost:6379/0'
os.environ['JWT_SECRET']='drill-test-secret'
os.environ['SEED_DEMO']='false'
sys.path.insert(0,'/workspace/backend')
import fakeredis
from fastapi.testclient import TestClient
fake=fakeredis.FakeRedis()
import src.services.runs as runs_svc
import src.services.drills as drills_svc
runs_svc.queue=fake
drills_svc.queue=fake
import src.worker as worker
from src.main import app
from scripts.seed_demo import seed
from src.config.database import Session
from src.models.drill import DrillJob,DrillAlias,DrillRow
seed()
client=TestClient(app)
PASS=[];FAIL=[]
def check(name,cond,extra=''):
 (PASS if cond else FAIL).append(name)
 print(('PASS ' if cond else 'FAIL ')+name+((' :: '+str(extra)) if extra and not cond else ''))
def login(email):
 r=client.post('/auth/login',json={'email':email,'password':'Migrate2026!'})
 assert r.status_code==200,r.text
 return {'Authorization':'Bearer '+r.json()['token']}
OP=login('operator@migration.local');AD=login('admin@migration.local');VW=login('viewer@migration.local')
def drain():
 n=0
 while True:
  item=fake.lpop('migration-runs')
  if item is None:break
  worker.handle_run(int(item));n+=1
 while True:
  item=fake.lpop('drill-appends')
  if item is None:break
  try:drills_svc.process_append(int(item))
  except Exception:pass
  n+=1
 return n
def make_run(name,mapping_id):
 r=client.post('/runs',json={'name':name,'mapping_id':mapping_id},headers=OP)
 assert r.status_code==200,r.text
 return r.json()['id']
def get_run(rid):
 r=client.get(f'/runs/{rid}',headers=OP);assert r.status_code==200;return r.json()
def new_batch_run(tag,rows):
 r=client.post('/batches',json={'name':'批次'+tag,'source_file':tag+'.json','description':'t','rows':rows},headers=OP)
 assert r.status_code==200,r.text
 bid=r.json()['id']
 rules=[{'source':a,'target':b,'type':c,'required':True} for a,b,c in [('委托号','sample_code','text'),('检测项','test_name','text'),('结果','result_value','decimal'),('单位','unit','text'),('时间','measured_at','datetime')]]
 r=client.post('/mappings',json={'name':'映射'+tag,'batch_id':bid,'rules':rules,'chunk_size':4,'note':'t'},headers=OP)
 assert r.status_code==200,r.text
 rid=make_run('运行'+tag,r.json()['id']);drain()
 assert get_run(rid)['status']=='completed'
 return rid
def download(pid,hdr=OP,expect=200):
 r=client.get(f'/drill-packages/{pid}/download',headers=hdr)
 assert r.status_code==expect,f'{pid} expect {expect} got {r.status_code}: {r.text}'
 return r.json() if r.status_code==200 else r
def pkg(pid):
 r=client.get(f'/drill-packages/{pid}',headers=OP);assert r.status_code==200;return r.json()
def deep_strings(v):
 if isinstance(v,str):yield v
 elif isinstance(v,dict):
  for x in v.values():yield from deep_strings(x)
 elif isinstance(v,list):
  for x in v:yield from deep_strings(x)
ALIAS=re.compile(r'^D-[0-9A-F]{6}-\d{4}$')

# ---- 准备三个已完成运行：A(12行 JS-20261117-001..012) B(2行 与A共享001/002) C(2行 新委托号)
maps={m['name']:m['id'] for m in client.get('/mappings',headers=OP).json()}
runA=make_run('运行A-日班',maps['检验结果标准映射'])
runB=make_run('运行B-异常样本',maps['异常隔离复核映射'])
drain()
assert get_run(runA)['status']=='completed' and get_run(runA)['result']['accepted_count']==12
assert get_run(runB)['status']=='completed' and get_run(runB)['result']['accepted_count']==2
rowsC=[{'委托号':f'JS-20261118-{i:03d}','检测项':'屈服强度','结果':str(300+i),'单位':'MPa','时间':'2026-11-18T09:00:00+08:00'} for i in (1,2)]
runC=new_batch_run('C-次日',rowsC)
check('准备：三个已完成运行（A=12行 B=2行共享委托号 C=2行新委托号）',True)

# ---- 1. 建包+首批追加；2. 下载脱敏副本
r=client.post('/drill-packages',json={'name':'qc-drill-华东','recipient_group':'华东复核组','run_ids':[runA]},headers=OP)
check('创建演练包并入队首批追加',r.status_code==200,r.text)
P1=r.json()['id'];drain()
p1=pkg(P1)
check('首批追加完成发版 v1',p1['version']==1 and p1['jobs'][0]['status']=='completed',p1['jobs'])
d1=download(P1)
check('下载包格式与行数',d1['kind']=='sanitized-drill-copy' and d1['row_count']==12 and len(d1['rows'])==12)
check('下载行全部使用代号',all(ALIAS.match(x['sample_code']) for x in d1['rows']))
check('下载包不含原委托号',not any('JS-' in s for s in deep_strings(d1)))
check('下载包不含代号对照表',set(d1.keys())=={'kind','format','package','recipient_group','package_version','issued_at','source_run_count','row_count','checksum','rows'} and all(set(x)=={'sample_code','test_name','result_value','unit','measured_at'} for x in d1['rows']))
alias_v1={a['sample_code']:a['alias'] for a in p1['aliases']}
check('v1代号数量=委托数且互不相同（不串号）',len(alias_v1)==12 and len(set(alias_v1.values()))==12)

# ---- 3. 追加运行B：旧代号不变、同委托跨运行同代号、已发结果不变
r=client.post(f'/drill-packages/{P1}/appends',json={'run_ids':[runB]},headers=OP)
check('提交追加任务',r.status_code==200,r.text)
job2=r.json()['id'];drain()
p1=pkg(P1);d2=download(P1)
check('追加后发版 v2 共14行',p1['version']==2 and d2['row_count']==14)
alias_v2={a['sample_code']:a['alias'] for a in p1['aliases']}
check('追加不改旧代号',all(alias_v2.get(k)==v for k,v in alias_v1.items()))
check('同一委托跨运行同一代号',len([x for x in d2['rows'] if x['sample_code']==alias_v1['JS-20261117-001']])==2)
check('v2行集含v1已发结果（逐行不变）',all(x in d2['rows'] for x in d1['rows']))

# ---- 4. 重试同一批不重复收行（任务级重放 + API级重提）
with Session() as s:
 j=s.get(DrillJob,job2);j.status='queued';s.commit()
fake.rpush('drill-appends',job2);drain()
check('重放同一追加任务不重复收行',pkg(P1)['version']==2 and download(P1)['row_count']==14)
r=client.post(f'/drill-packages/{P1}/appends',json={'run_ids':[runA,runB]},headers=OP)
check('重复提交已收录运行被拒绝',r.status_code==409,r.status_code)

# ---- 5. 追加中断能续跑；6. 完成前还能取上一版
r=client.post(f'/drill-packages/{P1}/appends',json={'run_ids':[runC]},headers=OP)
job3=r.json()['id']
real_session=drills_svc.Session
class CrashSession:
 n=0
 def __call__(self):
  CrashSession.n+=1
  if CrashSession.n==3:raise ConnectionError('模拟进程崩溃')
  return real_session()
drills_svc.Session=CrashSession()
fake.rpush('drill-appends',job3)
item=fake.lpop('drill-appends')
try:drills_svc.process_append(int(item))
except ConnectionError:pass
drills_svc.Session=real_session
with Session() as s:j=s.get(DrillJob,job3);check('中断后任务标记失败可续跑（行已写入、版本未推进）',j.status=='failed' and runC in (j.processed or []),(j.status,j.processed))
d_mid=download(P1)
check('追加中断期间仍取上一版 v2',d_mid['package_version']==2 and d_mid['row_count']==14 and d_mid['checksum']==d2['checksum'])
r=client.post(f'/drill-jobs/{job3}/resume',headers=OP)
check('续跑接口受理',r.status_code==200,r.text)
drain()
p1=pkg(P1);d3=download(P1)
check('续跑完成发版 v3 共16行',p1['version']==3 and d3['row_count']==16)
from collections import Counter
cnt=Counter(x['sample_code'] for x in d3['rows'])
a1={a['sample_code']:a['alias'] for a in pkg(P1)['aliases']}
check('续跑不重复收行（跨运行同委托恰2行、新委托恰1行）',cnt[a1['JS-20261117-001']]==2 and cnt[a1['JS-20261117-002']]==2 and cnt[a1['JS-20261118-001']]==1 and cnt[a1['JS-20261118-002']]==1,dict(cnt))
with Session() as s:check('库内每运行每序号唯一',s.query(DrillRow).filter_by(package_id=P1).count()==16 and len({(r.run_id,r.ordinal) for r in s.query(DrillRow).filter_by(package_id=P1)})==16)
check('续跑后旧代号仍不变',all({a['sample_code']:a['alias'] for a in pkg(P1)['aliases']}.get(k)==v for k,v in alias_v2.items()))

# ---- 7. 第二接收组：代号各自独立
r=client.post('/drill-packages',json={'name':'qc-drill-华北','recipient_group':'华北复核组','run_ids':[runA,runB]},headers=OP)
P2=r.json()['id'];drain()
d_hd=download(P2);p2=pkg(P2)
alias_hd={a['sample_code']:a['alias'] for a in p2['aliases']}
check('不同接收组代号各自独立',alias_hd['JS-20261117-001']!=alias_v1['JS-20261117-001'] and d_hd['row_count']==14)

# ---- 8. 撤回与追加并发：撤回即取不到，进行中的追加安全中止
r=client.post('/drill-packages',json={'name':'qc-drill-华南','recipient_group':'华南复核组','run_ids':[runA]},headers=OP)
P3=r.json()['id'];drain()
check('撤回前可下载',download(P3)['row_count']==12)
r=client.post(f'/drill-packages/{P3}/appends',json={'run_ids':[runB]},headers=OP)
jobP3=r.json()['id']
r=client.post(f'/drill-packages/{P3}/withdraw',headers=OP)
check('追加在队时撤回成功（可并发）',r.status_code==200 and r.json()['status']=='withdrawn',r.text)
r=client.get(f'/drill-packages/{P3}/download',headers=OP)
check('撤回后旧单取不到(410)',r.status_code==410,r.status_code)
drain()
with Session() as s:j=s.get(DrillJob,jobP3)
check('进行中的追加安全中止',j.status=='aborted',j.status)
check('撤回后版本不再推进',pkg(P3)['version']==1)
r=client.post(f'/drill-packages/{P3}/appends',json={'run_ids':[runC]},headers=OP)
check('已撤回包拒绝再追加',r.status_code==409)

# ---- 9. 同一组重开换代号
r=client.post(f'/drill-packages/{P3}/reopen',json={'name':'qc-drill-华南-重开'},headers=OP)
check('撤回后可重开',r.status_code==200,r.text)
P4=r.json()['id']
check('重开携带原接收组与原运行集',r.json()['recipient_group']=='华南复核组' and r.json()['version']==0)
drain()
d4=download(P4);p4=pkg(P4)
alias_p3={a['sample_code']:a['alias'] for a in pkg(P3)['aliases']}
alias_p4={a['sample_code']:a['alias'] for a in p4['aliases']}
check('重开换代号（同委托新代号）',all(alias_p4[k]!=v for k,v in alias_p3.items()) and len(alias_p4)==len(alias_p3))
check('重开新包可正常下载',d4['row_count']==12)
r=client.get(f'/drill-packages/{P3}/download',headers=OP)
check('旧包重开后仍取不到',r.status_code==410)

# ---- 10. 备份恢复照常 + 11. 权限
bak=client.get(f'/runs/{runA}/backup',headers=VW)
check('viewer照常下载运行备份',bak.status_code==200)
r=client.post(f'/runs/{runA}/restore',json={'backup':bak.json()},headers=AD)
check('管理员回传备份恢复照常',r.status_code==200 and r.json()['verified'] is True,r.text)
check('恢复后演练包下载不受影响',download(P1)['row_count']==16)
r=client.post('/drill-packages',json={'name':'qc-drill-x','recipient_group':'x组','run_ids':[runA]},headers=VW)
check('viewer不可创建演练包',r.status_code==403)
r=client.get(f'/drill-packages/{P1}/download',headers=VW)
check('viewer可下载脱敏副本',r.status_code==200)
r=client.post(f'/drill-packages/{P1}/withdraw',headers=VW)
check('viewer不可撤回',r.status_code==403)

# ---- 12. 未完成的运行不可收入
r=client.post('/runs',json={'name':'运行D-待处理','mapping_id':maps['检验结果标准映射']},headers=OP)
runD=r.json()['id']
r=client.post(f'/drill-packages/{P1}/appends',json={'run_ids':[runD]},headers=OP)
check('未完成运行不可收入副本',r.status_code==409,r.status_code)
fake.lpop('migration-runs')

print()
print(f'通过 {len(PASS)} 项，失败 {len(FAIL)} 项')
if FAIL:
 print('失败项：');[print(' -',x) for x in FAIL]
 sys.exit(1)
print('全部验证通过')
