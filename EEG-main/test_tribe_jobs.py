import asyncio,tempfile,unittest
from pathlib import Path
from tribe_jobs import TribeJobs
class JobsTests(unittest.IsolatedAsyncioTestCase):
 async def test_bounded_queue_and_stop(self):
  with tempfile.TemporaryDirectory() as root:
   jobs=TribeJobs(root);await jobs.start();session=jobs.session
   jobs.task=asyncio.create_task(asyncio.sleep(100))
   await jobs.submit(session,b'first','.mp4',0,60);first=jobs.pending['path']
   await jobs.submit(session,b'second','.mp4',30,60)
   self.assertFalse(first.exists());self.assertEqual(jobs.skipped,1)
   await jobs.stop();self.assertFalse((jobs.folder/session).exists())
   with self.assertRaises(ValueError):await jobs.submit(session,b'x','.mp4',60,60)
 async def test_missing_runtime_reports_error(self):
  with tempfile.TemporaryDirectory() as root:
   jobs=TribeJobs(root);await jobs.start();await jobs.submit(jobs.session,b'video','.mp4',0,60)
   await jobs.task;self.assertEqual(jobs.results[0]['status'],'error');await jobs.stop()

 async def test_invalid_window_is_rejected(self):
  with tempfile.TemporaryDirectory() as root:
   jobs=TribeJobs(root);await jobs.start()
   for extension,start,duration in [('.mp4',float('nan'),60),('.mp4',0,float('inf')),('/bad',0,60)]:
    with self.assertRaises(ValueError):await jobs.submit(jobs.session,b'video',extension,start,duration)
   self.assertEqual(jobs.bytes,0)
   await jobs.stop()
