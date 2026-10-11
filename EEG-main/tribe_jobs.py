"""Bounded local inference queue: one running job, one newest pending window."""
import asyncio,json,secrets,shutil,time,os,signal,math
from pathlib import Path
class TribeJobs:
 def __init__(self,root):
  self.root=Path(root);self.folder=self.root/'.tribe/sessions';self.session=None;self.pending=None;self.task=None;self.process=None;self.results=[];self.skipped=0;self.active=None;self.enabled=False;self.bytes=0
 def readiness(self):
  path=self.root/'.tribe/readiness.json'
  return json.loads(path.read_text()) if path.exists() else {'ready':False,'reason':'TRIBE inference has not been validated'}
 def status(self):
  return {'readiness':self.readiness(),'enabled':self.enabled,'session':self.session,'active':self.active,'pending':self.pending['id'] if self.pending else None,'skipped':self.skipped,'results':self.results[-8:],'runtime_available':(self.root/'.tribe/venv/bin/python').exists()}
 async def start(self):
  await self.stop();self.session=secrets.token_hex(12);self.enabled=True;self.results=[];self.skipped=0;self.bytes=0;self.folder.mkdir(parents=True,exist_ok=True)
  return self.status()
 async def stop(self):
  self.enabled=False
  await self.terminate_worker()
  if self.task:
   self.task.cancel()
   try:await self.task
   except asyncio.CancelledError:pass
  self.task=None;self.pending=None;self.process=None;self.active=None
  if self.session:shutil.rmtree(self.folder/self.session,ignore_errors=True)
  return self.status()
 async def terminate_worker(self):
  process=self.process
  if process is None:return
  try:os.killpg(process.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  try:await asyncio.wait_for(process.wait(),5)
  except asyncio.TimeoutError:pass
  # The parent can exit before its speech subprocess; terminate the entire group.
  try:os.killpg(process.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  await process.wait()
 async def submit(self,session,body,extension,start,duration):
  if not self.enabled or session!=self.session:raise ValueError('Analysis session expired')
  if extension not in ('.mp4','.webm') or not body or not math.isfinite(start) or not math.isfinite(duration) or len(body)>32*1024*1024 or not 1<=duration<=75 or start<0:raise ValueError('Window exceeds limits')
  if self.bytes+len(body)>512*1024*1024:raise ValueError('Session upload limit reached; stop and start a new session')
  self.bytes+=len(body);job_id=secrets.token_hex(8);directory=self.folder/self.session/job_id;directory.mkdir(parents=True)
  path=directory/('video'+extension);path.write_bytes(body)
  job={'id':job_id,'path':path,'start':start,'duration':duration,'session':session}
  if self.pending:shutil.rmtree(self.pending['path'].parent,ignore_errors=True);self.skipped+=1
  self.pending=job
  if self.task is None or self.task.done():self.task=asyncio.create_task(self.run())
  return self.status()
 async def run(self):
  while self.pending and self.enabled:
   job=self.pending;self.pending=None;self.active=job['id'];output=job['path'].parent/'prediction.json';began=time.monotonic()
   result={'id':job['id'],'start_seconds':job['start'],'duration_seconds':job['duration']}
   try:
    runtime=self.root/'.tribe/venv/bin/python'
    if not runtime.exists():raise RuntimeError('TRIBE environment is not installed')
    with (job['path'].parent/'worker.log').open('wb') as log:
     self.process=await asyncio.create_subprocess_exec(str(runtime),str(self.root/'tribe_worker.py'),str(job['path']),str(output),stdout=log,stderr=log,start_new_session=True)
     await asyncio.wait_for(self.process.wait(),900)
    if self.process.returncode:raise RuntimeError('TRIBE inference failed; inspect the local worker log before retrying.')
    result.update(status='ready',prediction=json.loads(output.read_text()))
   except asyncio.TimeoutError:
    await self.terminate_worker();result.update(status='error',error='Inference exceeded 15-minute limit')
   except Exception as error:result.update(status='error',error=str(error))
   finally:
    # Upstream extraction creates WAV and transcript sidecars beside the input.
    for suffix in (job['path'].suffix,'.wav','.tsv'):
     job['path'].with_suffix(suffix).unlink(missing_ok=True)
    self.active=None;self.process=None
   result['processing_seconds']=round(time.monotonic()-began,2)
   if self.enabled and job['session']==self.session:self.results.append(result);self.results=self.results[-8:]
