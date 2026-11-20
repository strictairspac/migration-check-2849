import secrets,redis
from fastapi import HTTPException
from sqlalchemy import func
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.run import Run,TargetRow
from src.models.drill import DrillPackage,DrillAlias,DrillRow,DrillVersion,DrillJob
from src.utils.serialization import record
from src.services.migration import digest
from src.services.audit import log
queue=redis.Redis.from_url(REDIS_URL)
ACTIVE=('queued','running')
def _enqueue(job_id):
 try:queue.rpush('drill-appends',job_id)
 except redis.RedisError:
  with Session() as s:j=s.get(DrillJob,job_id);j.status='failed';j.error='队列不可用，请稍后使用续跑';s.commit()
  raise HTTPException(503,'队列不可用，任务已保存，请稍后使用续跑')
def _issued_run_ids(s,package_id,version):
 return {r[0] for r in s.query(DrillRow.run_id).filter_by(package_id=package_id).filter(DrillRow.introduced_version<=version).distinct()}
def _validate_runs(s,run_ids,issued):
 seen=set();todo=[]
 for rid in run_ids:
  if rid in seen or rid in issued:continue
  seen.add(rid)
  r=s.get(Run,rid)
  if not r:raise HTTPException(404,f'未找到对账运行#{rid}')
  if r.status!='completed':raise HTTPException(409,f'运行#{rid}尚未完成，仅已完成的运行可收入脱敏副本')
  todo.append(rid)
 if not todo:raise HTTPException(409,'所选运行均已收录，无新增行可追加')
 return todo
def _alias_for(s,package_id,sample_code):
 a=s.query(DrillAlias).filter_by(package_id=package_id,sample_code=sample_code).first()
 if a:return a.alias
 token=s.get(DrillPackage,package_id).alias_token
 seq=(s.query(func.max(DrillAlias.seq)).filter_by(package_id=package_id).scalar() or 0)+1
 alias=f'D-{token}-{seq:04d}'
 s.add(DrillAlias(package_id=package_id,sample_code=sample_code,alias=alias,seq=seq))
 s.flush()
 return alias
def list_items():
 with Session() as s:
  out=[]
  for p in s.query(DrillPackage).order_by(DrillPackage.id.desc()).limit(100).all():
   d=record(p)
   d['row_count']=s.query(DrillRow).filter_by(package_id=p.id).filter(DrillRow.introduced_version<=p.version).count()
   d['run_ids']=sorted(_issued_run_ids(s,p.id,p.version))
   job=s.query(DrillJob).filter_by(package_id=p.id).order_by(DrillJob.id.desc()).first()
   d['job']=record(job) if job else None
   out.append(d)
  return out
def detail(item_id):
 with Session() as s:
  p=s.get(DrillPackage,item_id)
  if not p:raise HTTPException(404,'未找到演练包')
  d=record(p)
  d['versions']=[record(v) for v in s.query(DrillVersion).filter_by(package_id=p.id).order_by(DrillVersion.version)]
  d['jobs']=[record(j) for j in s.query(DrillJob).filter_by(package_id=p.id).order_by(DrillJob.id.desc()).limit(20)]
  d['aliases']=[{'sample_code':a.sample_code,'alias':a.alias} for a in s.query(DrillAlias).filter_by(package_id=p.id).order_by(DrillAlias.seq)]
  d['run_ids']=sorted(_issued_run_ids(s,p.id,p.version))
  return d
def _new_job(s,package,run_ids):
 job=DrillJob(package_id=package.id,run_ids=run_ids,processed=[],target_version=package.version+1,status='queued')
 s.add(job);s.flush();return job
def create(data):
 with Session() as s:
  p=DrillPackage(name=data.name,recipient_group=data.recipient_group,alias_token=secrets.token_hex(3).upper(),status='open',version=0)
  s.add(p);s.flush()
  job=_new_job(s,p,_validate_runs(s,data.run_ids,set())) if data.run_ids else None
  s.commit();result=record(p);jid=job.id if job else None
 if jid:_enqueue(jid)
 return result
def append(item_id,data):
 with Session() as s:
  p=s.query(DrillPackage).filter_by(id=item_id).with_for_update().first()
  if not p:raise HTTPException(404,'未找到演练包')
  if p.status!='open':raise HTTPException(409,'演练包已撤回，请使用重开的新包')
  if s.query(DrillJob).filter_by(package_id=p.id).filter(DrillJob.status.in_(ACTIVE)).first():raise HTTPException(409,'已有进行中的追加任务，待完成或续跑结束后再试')
  job=_new_job(s,p,_validate_runs(s,data.run_ids,_issued_run_ids(s,p.id,p.version)))
  s.commit();result=record(job);jid=job.id
 _enqueue(jid)
 return result
def withdraw(item_id):
 with Session() as s:
  p=s.query(DrillPackage).filter_by(id=item_id).with_for_update().first()
  if not p:raise HTTPException(404,'未找到演练包')
  if p.status!='open':raise HTTPException(409,'演练包已撤回')
  p.status='withdrawn';s.commit();return record(p)
def reopen(item_id,data):
 with Session() as s:
  old=s.get(DrillPackage,item_id)
  if not old:raise HTTPException(404,'未找到演练包')
  if old.status!='withdrawn':raise HTTPException(409,'仅已撤回的演练包可重开')
  run_ids=sorted(_issued_run_ids(s,old.id,old.version))
  name=data.name or f'{old.name[:100]}·重开{secrets.token_hex(2).upper()}'
  p=DrillPackage(name=name,recipient_group=old.recipient_group,alias_token=secrets.token_hex(3).upper(),status='open',version=0)
  s.add(p);s.flush()
  job=_new_job(s,p,run_ids) if run_ids else None
  s.commit();pid=p.id;jid=job.id if job else None
 if jid:_enqueue(jid)
 return detail(pid)
def resume(job_id):
 with Session() as s:
  j=s.query(DrillJob).filter_by(id=job_id).with_for_update().first()
  if not j:raise HTTPException(404,'未找到追加任务')
  if j.status not in ('running','failed'):raise HTTPException(409,'仅中断或失败的任务需要续跑')
  j.status='queued';j.error=None;s.commit();result=record(j)
 _enqueue(job_id)
 return result
def download(item_id):
 with Session() as s:
  p=s.get(DrillPackage,item_id)
  if not p:raise HTTPException(404,'未找到演练包')
  if p.status!='open':raise HTTPException(410,'演练包已撤回，旧版脱敏副本不可再获取')
  if p.version<1:raise HTTPException(409,'尚无已完成的版本可下载')
  v=s.query(DrillVersion).filter_by(package_id=p.id,version=p.version).first()
  rows=[r.payload for r in s.query(DrillRow).filter_by(package_id=p.id).filter(DrillRow.introduced_version<=p.version).order_by(DrillRow.id)]
  if digest(rows)!=v.checksum:raise HTTPException(409,'副本数据与版本摘要不一致，请复核后再下载')
  return {'kind':'sanitized-drill-copy','format':1,'package':p.name,'recipient_group':p.recipient_group,'package_version':p.version,'issued_at':record(v)['created_at'],'source_run_count':len(_issued_run_ids(s,p.id,p.version)),'row_count':len(rows),'checksum':digest(rows),'rows':rows}
def process_append(job_id):
 with Session() as s:
  j=s.query(DrillJob).filter_by(id=job_id).with_for_update().first()
  if not j or j.status!='queued':return
  j.status='running';s.commit()
  package_id=j.package_id;run_ids=list(j.run_ids);target=j.target_version
 try:
  for run_id in run_ids:
   with Session() as s:
    p=s.get(DrillPackage,package_id)
    if p.status!='open':
     j=s.get(DrillJob,job_id);j.status='aborted';j.error='演练包已撤回，追加中止';s.commit()
     log('worker','drilljob.aborted',str(job_id));return
    j=s.get(DrillJob,job_id)
    if run_id in (j.processed or []):continue
    rows=s.query(TargetRow).filter_by(run_id=run_id).order_by(TargetRow.ordinal).all()
    s.query(DrillRow).filter_by(package_id=package_id,run_id=run_id).delete()
    for t in rows:
     alias=_alias_for(s,package_id,t.payload['sample_code'])
     s.add(DrillRow(package_id=package_id,run_id=run_id,ordinal=t.ordinal,introduced_version=target,payload={**t.payload,'sample_code':alias}))
    j.processed=(j.processed or [])+[run_id]
    s.commit()
  with Session() as s:
   p=s.query(DrillPackage).filter_by(id=package_id).with_for_update().first()
   j=s.get(DrillJob,job_id)
   if p.status!='open':
    j.status='aborted';j.error='演练包已撤回，追加中止';s.commit()
    log('worker','drilljob.aborted',str(job_id));return
   rows=[r.payload for r in s.query(DrillRow).filter_by(package_id=package_id).filter(DrillRow.introduced_version<=target).order_by(DrillRow.id)]
   if not s.query(DrillVersion).filter_by(package_id=package_id,version=target).first():
    s.add(DrillVersion(package_id=package_id,version=target,row_count=len(rows),checksum=digest(rows),added_run_ids=run_ids))
   if p.version<target:p.version=target
   j.status='completed';s.commit()
  log('worker','drilljob.completed',str(job_id))
 except Exception as exc:
  with Session() as s:j=s.get(DrillJob,job_id);j.status='failed';j.error=str(exc)[:1000];s.commit()
  log('worker','drilljob.failed',f'{job_id}: {str(exc)[:200]}')
  raise
