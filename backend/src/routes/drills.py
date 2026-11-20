import json
from fastapi import APIRouter,Depends
from fastapi.responses import Response
from src.middlewares.auth import current,writer
from src.schemas.business import DrillPackageInput,DrillAppendInput,DrillReopenInput
from src.services import drills
from src.services.audit import log
router=APIRouter()
@router.get('/drill-packages')
def listing(u=Depends(current)):return drills.list_items()
@router.post('/drill-packages')
def create(data:DrillPackageInput,u=Depends(writer)):
 r=drills.create(data);log(u.email,'drill.create',r['name']);return r
@router.get('/drill-packages/{item_id}')
def detail(item_id:int,u=Depends(current)):return drills.detail(item_id)
@router.post('/drill-packages/{item_id}/appends')
def append(item_id:int,data:DrillAppendInput,u=Depends(writer)):
 r=drills.append(item_id,data);log(u.email,'drill.append',f'package={item_id} runs={r["run_ids"]}');return r
@router.post('/drill-packages/{item_id}/withdraw')
def withdraw(item_id:int,u=Depends(writer)):
 r=drills.withdraw(item_id);log(u.email,'drill.withdraw',str(item_id));return r
@router.post('/drill-packages/{item_id}/reopen')
def reopen(item_id:int,data:DrillReopenInput,u=Depends(writer)):
 r=drills.reopen(item_id,data);log(u.email,'drill.reopen',f'{item_id}->{r["id"]}');return r
@router.get('/drill-packages/{item_id}/download')
def download(item_id:int,u=Depends(current)):
 d=drills.download(item_id)
 return Response(json.dumps(d,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="drill-{item_id}-v{d["package_version"]}.json"'})
@router.post('/drill-jobs/{job_id}/resume')
def resume(job_id:int,u=Depends(writer)):
 r=drills.resume(job_id);log(u.email,'drill.resume',str(job_id));return r
