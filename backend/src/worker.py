import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.run import Run,TargetRow
from src.services.migration import migrate,make_backup,key_digest,Cancelled
from src.services import drills
from src.services.audit import log
q=redis.Redis.from_url(REDIS_URL)
def progress(run_id,info):
 Path('/tmp/worker-heartbeat').touch()
 with Session() as s:
  r=s.get(Run,run_id)
  if r.cancel_requested or r.status=='cancelled':raise Cancelled()
  r.progress=info;s.commit()
def handle_run(run_id):
 with Session() as s:
  r=s.query(Run).filter_by(id=run_id).with_for_update().first()
  if not r or r.status!='queued':return
  r.status='running';snapshot=r.snapshot;s.commit()
 try:
  result=migrate(snapshot['batch']['rows'],snapshot['mapping']['rules'],snapshot['mapping']['chunk_size'],lambda info:progress(run_id,info))
  result['backup']=make_backup(result,run_id,snapshot['batch']['name'])
  with Session() as s:
   r=s.query(Run).filter_by(id=run_id).with_for_update().first()
   if r.cancel_requested:raise Cancelled()
   for i,row in enumerate(result['accepted_rows']):s.add(TargetRow(run_id=run_id,ordinal=i,key_digest=key_digest(row),payload=row))
   r.result=result;r.status='completed';s.commit()
  log('worker','run.completed',str(run_id))
 except Cancelled:
  with Session() as s:r=s.get(Run,run_id);r.status='cancelled';r.error='用户取消，未提交目标行';s.commit()
  log('worker','run.cancelled',str(run_id))
 except Exception as exc:
  logging.exception('migration failed')
  with Session() as s:r=s.get(Run,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
def handle_append(job_id):
 try:drills.process_append(job_id)
 except Exception:logging.exception('drill append failed')
def loop():
 while True:
  Path('/tmp/worker-heartbeat').touch()
  try:
   item=q.blpop(['migration-runs','drill-appends'],timeout=2)
   if not item:continue
   kind=item[0].decode() if isinstance(item[0],bytes) else item[0]
   if kind=='migration-runs':handle_run(int(item[1]))
   else:handle_append(int(item[1]))
  except Exception:logging.exception('worker loop');time.sleep(2)
if __name__=='__main__':loop()
