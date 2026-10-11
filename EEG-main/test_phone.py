import unittest,time
from aiohttp.test_utils import TestClient,TestServer
from phone_server import Pairing,create_app
class PhoneTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.state=Pairing();self.client=TestClient(TestServer(create_app('https://test.local',self.state)))
  await self.client.start_server();self.headers={'Host':'test.local','Origin':'https://test.local','Authorization':'Bearer '+self.state.owner}
 async def asyncTearDown(self):await self.client.close()
 async def test_pair_relay_expiry_and_reuse(self):
  r=await self.client.post('/pair',headers=self.headers);self.assertEqual(r.status,200)
  receiver=await self.client.ws_connect('/ws',headers=self.headers)
  await receiver.send_json({'role':'receiver','token':self.state.owner});self.assertEqual((await receiver.receive_json())['type'],'authenticated')
  phone=await self.client.ws_connect('/ws',headers=self.headers)
  await phone.send_json({'role':'phone','token':self.state.phone});await phone.receive_json();self.assertEqual((await phone.receive_json())['type'],'ready')
  await phone.send_json({'type':'offer','sdp':{'type':'offer','sdp':'test'}});self.assertEqual((await receiver.receive_json())['type'],'offer')
  await phone.close();self.assertEqual((await receiver.receive_json())['type'],'disconnected')
  reuse=await self.client.ws_connect('/ws',headers=self.headers);await reuse.send_json({'role':'phone','token':self.state.phone});self.assertEqual((await reuse.receive()).type,8)
  await receiver.close()
  await self.client.post('/pair',headers=self.headers);self.state.expires=time.monotonic()-1
  expired=await self.client.ws_connect('/ws',headers=self.headers);await expired.send_json({'role':'phone','token':self.state.phone});self.assertEqual((await expired.receive()).type,8)
 async def test_access_controls(self):
  self.assertEqual((await self.client.post('/pair',headers={'Host':'test.local','Origin':'https://test.local'})).status,403)
  bad=dict(self.headers,Origin='https://evil.example');self.assertEqual((await self.client.post('/pair',headers=bad)).status,403)
  self.assertEqual((await self.client.get('/.phone/ca-key.pem',headers=self.headers)).status,404)

 async def test_tribe_owner_auth_and_unready_gate(self):
  from unittest.mock import patch
  for method,path in [('get','/tribe/status'),('post','/tribe/start'),('post','/tribe/stop'),('post','/tribe/window')]:
   response=await getattr(self.client,method)(path,headers={'Host':'test.local','Origin':'https://test.local'})
   self.assertEqual(response.status,403)
  with patch('phone_server.TribeJobs.readiness',return_value={'ready':False,'reason':'benchmark pending'}):
   response=await self.client.post('/tribe/start',headers=self.headers)
   self.assertEqual(response.status,409)
   self.assertEqual(await response.text(),'benchmark pending')

 async def test_capture_package(self):
  import tempfile,json,io,zipfile
  from pathlib import Path
  from unittest.mock import patch
  sid='a'*24
  with tempfile.TemporaryDirectory() as root:
   folder=Path(root)/'recordings'/('capture-'+sid);folder.mkdir(parents=True)
   (folder/'manifest.json').write_text(json.dumps({'sample_count':125}))
   (folder/'eeg.npz').write_bytes(b'test fixture')
   with patch('phone_server.ROOT',Path(root)):
    bad=await self.client.post('/capture/media',headers={'Host':'test.local','Origin':'https://test.local'},data=b'media')
    self.assertEqual(bad.status,403)
    headers=dict(self.headers,**{'Content-Type':'video/mp4','X-Capture-Id':sid,'X-Capture-Timing':'{}'})
    response=await self.client.post('/capture/media',headers=headers,data=b'media fixture')
    self.assertEqual(response.status,200)
    response=await self.client.get('/capture/download',headers=headers)
    self.assertEqual(response.status,200)
    with zipfile.ZipFile(io.BytesIO(await response.read())) as archive:
     self.assertEqual(set(archive.namelist()),{'clip.mp4','eeg.npz','manifest.json','README.txt'})
