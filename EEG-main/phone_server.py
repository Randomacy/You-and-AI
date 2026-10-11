"""Local TLS signalling and opt-in TRIBE media uploads; no EEG access."""
import argparse, asyncio, io, json, secrets, ssl, time
import urllib.request, urllib.error, re, zipfile
from pathlib import Path
from aiohttp import web, WSMsgType
import qrcode
from tribe_jobs import TribeJobs
ROOT=Path(__file__).resolve().parent

class Pairing:
    def __init__(self):
        self.owner=secrets.token_urlsafe(32)
        self.phone=None; self.expires=0; self.used=False; self.peers={}
    async def reset(self):
        for peer in list(self.peers.values()):
            await peer.close()
        self.peers.clear(); self.phone=secrets.token_urlsafe(32)
        self.expires=time.monotonic()+300; self.used=False

def create_app(origin, state=None):
    state=state or Pairing()
    @web.middleware
    async def security(request, handler):
        if request.host!=origin.split('://')[1]: raise web.HTTPForbidden()
        if request.method!='GET' and request.headers.get('Origin')!=origin: raise web.HTTPForbidden()
        response=await handler(request)
        response.headers.update({'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors http://127.0.0.1:8765 http://localhost:8765"})
        return response
    app=web.Application(middlewares=[security],client_max_size=32*1024*1024)
    jobs=TribeJobs(ROOT)
    def owner(req):
        if not secrets.compare_digest(req.headers.get('Authorization',''), 'Bearer '+state.owner): raise web.HTTPForbidden()
    async def static(req):
        files={'/':'phone.html','/receiver':'phone_receiver.html','/phone.js':'phone.js','/receiver.js':'phone_receiver.js'}
        return web.FileResponse(ROOT/files[req.path])
    async def pair(req):
        owner(req);await state.reset()
        link=origin+'/#'+state.phone
        return web.json_response({'url':link,'expires_seconds':300})
    async def unpair(req):
        owner(req);await state.reset();state.phone=None
        return web.json_response({'ok':True})
    async def qr(req):
        owner(req)
        if not state.phone:raise web.HTTPConflict()
        output=io.BytesIO();qrcode.make(origin+'/#'+state.phone).save(output,format='PNG')
        return web.Response(body=output.getvalue(),content_type='image/png')
    async def tribe(req):
        owner(req)
        if req.path.endswith('/start'):
            if not jobs.readiness()['ready']:raise web.HTTPConflict(text=jobs.readiness()['reason'])
            return web.json_response(await jobs.start())
        if req.path.endswith('/stop'):return web.json_response(await jobs.stop())
        if req.path.endswith('/status'):return web.json_response(jobs.status())
        mime=req.headers.get('Content-Type','').split(';')[0]
        if mime not in ('video/mp4','video/webm'):raise web.HTTPUnsupportedMediaType()
        try:
            import math
            start=float(req.headers.get('X-Window-Start','nan'));duration=float(req.headers.get('X-Window-Duration','nan'))
            if not math.isfinite(start) or not math.isfinite(duration):raise ValueError('Invalid timestamps')
            result=await jobs.submit(req.headers.get('X-Session',''),await req.read(),'.mp4' if mime=='video/mp4' else '.webm',start,duration)
            return web.json_response(result)
        except ValueError as error:raise web.HTTPBadRequest(text=str(error))
    async def capture(req):
        owner(req)
        action=req.match_info['action']
        if action in ('start','stop'):
            body=await req.json()
            def proxy():
                request=urllib.request.Request('http://127.0.0.1:8765/api/record/'+action,
                    data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
                try:
                    with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
                except urllib.error.HTTPError as error:
                    raise ValueError(json.loads(error.read()).get('error','EEG recording failed'))
            try:return web.json_response(await asyncio.to_thread(proxy))
            except (ValueError,OSError) as error:raise web.HTTPBadRequest(text=str(error))
        sid=req.headers.get('X-Capture-Id','')
        if not re.fullmatch(r'[0-9a-f]{24}',sid):raise web.HTTPBadRequest(text='Invalid capture ID')
        folder=ROOT/'recordings'/('capture-'+sid)
        if not (folder/'manifest.json').exists():raise web.HTTPNotFound()
        if action=='media':
            mime=req.headers.get('Content-Type','').split(';')[0]
            if mime not in ('video/mp4','video/webm'):raise web.HTTPUnsupportedMediaType()
            if (folder/'session.zip').exists():raise web.HTTPConflict(text='Already packaged')
            try:
                timing=json.loads(req.headers.get('X-Capture-Timing','{}'))
                if not isinstance(timing,dict):raise ValueError()
            except (ValueError,TypeError):raise web.HTTPBadRequest(text='Invalid timing metadata')
            media=await req.read()
            if not media:raise web.HTTPBadRequest(text='Empty media')
            name='clip.mp4' if mime=='video/mp4' else 'clip.webm'
            (folder/name).write_bytes(media)
            manifest=json.loads((folder/'manifest.json').read_text())
            manifest['media']={'file':name,'target_duration_seconds':15,'browser_timing':timing}
            (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
            (folder/'README.txt').write_text('Offline multimodal capture. See manifest.json for channels, rate and timing limitations. EEG is raw microvolts, shape channels x samples, saved in eeg.npz. Load with numpy.load(..., allow_pickle=False). Pass clip.mp4 or clip.webm to tribe_worker.py. TRIBE uses media, not EEG. Do not treat timing as sample-synchronized or model outputs as measured brain activity.\n')
            with zipfile.ZipFile(folder/'session.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
                for item in (name,'eeg.npz','manifest.json','README.txt'):archive.write(folder/item,item)
            return web.json_response({'id':sid,'sample_count':manifest['sample_count'],'folder':str(folder)})
        if action=='download':return web.FileResponse(folder/'session.zip',headers={'Content-Disposition':'attachment; filename="brain-gremlin-'+sid+'.zip"'})
        raise web.HTTPNotFound()
    app.router.add_post('/capture/{action:start|stop|media}',capture)
    app.router.add_get('/capture/{action:download}',capture)
    async def shutdown(app):await jobs.stop()
    app.on_cleanup.append(shutdown)
    async def capture_script(req):return web.FileResponse(ROOT/'tribe_capture.js')
    async def socket(req):
        if req.headers.get('Origin')!=origin:raise web.HTTPForbidden()
        ws=web.WebSocketResponse(heartbeat=15,max_msg_size=65536)
        await ws.prepare(req);role=None
        try:
            msg=await asyncio.wait_for(ws.receive_json(),10)
            role=msg.get('role');token=msg.get('token','')
            if not isinstance(token,str):raise ValueError('Invalid token')
            if role=='receiver':valid=secrets.compare_digest(token,state.owner)
            elif role=='phone':valid=state.phone is not None and secrets.compare_digest(token,state.phone) and time.monotonic()<state.expires and not state.used
            else:valid=False
            if not valid or role in state.peers:raise ValueError('Pairing invalid, expired, or already used')
            if role=='phone':state.used=True
            state.peers[role]=ws
            await ws.send_json({'type':'authenticated'})
            if len(state.peers)==2:
                await state.peers['phone'].send_json({'type':'ready'})
            async for message in ws:
                if message.type!=WSMsgType.TEXT:break
                data=json.loads(message.data)
                if data.get('type') not in ('offer','answer','ice'):raise ValueError('Unsupported message')
                if data['type']=='offer' and role!='phone':raise ValueError('Invalid offer')
                if data['type']=='answer' and role!='receiver':raise ValueError('Invalid answer')
                target=state.peers.get('receiver' if role=='phone' else 'phone')
                if target is not None:await target.send_json(data)
        except (ValueError,TypeError,AttributeError,asyncio.TimeoutError):
            await ws.close(code=1008,message=b'Invalid or expired pairing')
        finally:
            if state.peers.get(role) is ws:
                state.peers.pop(role,None)
                await jobs.stop()
                target=state.peers.get('receiver' if role=='phone' else 'phone')
                if target is not None:await target.send_json({'type':'disconnected'})
        return ws
    for path in ('/','/receiver','/phone.js','/receiver.js'):app.router.add_get(path,static)
    app.router.add_post('/pair',pair);app.router.add_post('/unpair',unpair);app.router.add_get('/qr',qr);app.router.add_get('/ws',socket)
    for action in ('start','stop','window'):app.router.add_post('/tribe/'+action,tribe)
    app.router.add_get('/tribe/status',tribe)
    app.router.add_get('/tribe_capture.js',capture_script)
    return app

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',required=True);parser.add_argument('--port',type=int,default=8767);args=parser.parse_args()
    state=Pairing();origin=f'https://{args.host}:{args.port}'
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.minimum_version=ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(ROOT/'.phone/server.pem',ROOT/'.phone/server-key.pem')
    config=ROOT/'.phone/receiver.json';config.write_text(json.dumps({'url':origin+'/receiver#'+state.owner}));config.chmod(0o600)
    print('Phone receiver ready. Open Pair iPhone in Signal Room.',flush=True)
    try:web.run_app(create_app(origin,state),host=args.host,port=args.port,ssl_context=tls,access_log=None)
    finally:config.unlink(missing_ok=True)
if __name__=='__main__':main()
