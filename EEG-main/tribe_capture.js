window.addEventListener('DOMContentLoaded',()=>{
 requestAnimationFrame(async()=>{try{const s=await request('status');if(!s.readiness.ready){el('tribestart').disabled=true;say(s.readiness.reason)}}catch(e){say(e.message)}});
 let active=false,session=null,origin=0,timer=null,recorders=new Set(),poller=null;
 const el=id=>document.getElementById(id),say=t=>el('tribestatus').textContent=t;
 async function request(path,options={}){const response=await fetch('/tribe/'+path,{...options,headers:{Authorization:'Bearer '+token,...options.headers}});if(!response.ok)throw Error(await response.text());return response.json()}
 async function stop(){active=false;clearInterval(timer);clearInterval(poller);for(const r of recorders){r.onstop=null;if(r.state!=='inactive')r.stop()}recorders.clear();el('tribestart').disabled=false;el('tribestop').disabled=true;try{await request('stop',{method:'POST'});say('Stopped. Temporary session files cleared.')}catch(e){say(e.message)}}
 function capture(){
  if(!active)return;if(!stream||!stream.active){stop();return}
  const mime=['video/mp4','video/webm;codecs=vp8,opus','video/webm'].find(m=>MediaRecorder.isTypeSupported(m));
  if(!mime){say('This browser cannot record a supported media format.');stop();return}
  const started=performance.now(),start=(started-origin)/1000,chunks=[];let bytes=0;
  const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:1800000});recorders.add(recorder);
  recorder.ondataavailable=e=>{bytes+=e.data.size;if(bytes>32*1024*1024){stop();say('Window size limit reached.')}else if(e.data.size)chunks.push(e.data)};
  recorder.onerror=()=>{stop();say('Browser recording failed. Restart analysis.')};
  recorder.onstop=async()=>{recorders.delete(recorder);if(!active)return;const id=session;try{await request('window',{method:'POST',headers:{'Content-Type':mime,'X-Session':id,'X-Window-Start':String(start),'X-Window-Duration':String((performance.now()-started)/1000)},body:new Blob(chunks,{type:mime})})}catch(e){if(active)say(e.message)}};
  recorder.start(1000);setTimeout(()=>{if(recorder.state!=='inactive')recorder.stop()},60000);
 }
 el('tribestart').onclick=async()=>{try{if(!stream?.active)throw Error('Connect the phone video/audio first.');if(!window.MediaRecorder)throw Error('MediaRecorder unavailable.');const state=await request('start',{method:'POST'});session=state.session;origin=performance.now();active=true;el('tribestart').disabled=true;el('tribestop').disabled=false;capture();timer=setInterval(capture,30000);poller=setInterval(async()=>{try{const s=await request('status');if(!active)return;say(`Recording overlapping windows · ${s.active?'Processing':'Buffering'} · ${s.pending?'newest window queued':'no pending window'} · ${s.skipped} skipped`);el('triberesults').textContent=s.results.map(r=>`${r.start_seconds.toFixed(1)}–${(r.start_seconds+r.duration_seconds).toFixed(1)} s: ${r.status} · ${r.error||'Real model output received; timeline mapping not yet validated.'}`).join('\n')}catch(e){say(e.message)}},2000)}catch(e){say(e.message)}};
 el('tribestop').onclick=stop;
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&active){stop();say('Analysis stopped because the receiver went into the background.')}});
 window.addEventListener('pagehide',()=>{active=false;for(const r of recorders)if(r.state!=='inactive')r.stop()});
});
