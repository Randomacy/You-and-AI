const $=id=>document.getElementById(id);
const suppliedToken=location.hash.slice(1);
let token=suppliedToken;
try{if(suppliedToken)sessionStorage.setItem('phoneReceiverToken',suppliedToken);else token=sessionStorage.getItem('phoneReceiverToken')||''}catch{}
history.replaceState(null,'',location.pathname);
let ws,pc,stream,pending=[];const status=text=>$('status').textContent=text;const send=data=>{if(ws?.readyState===1)ws.send(JSON.stringify(data))};
function peer(){pc=new RTCPeerConnection({iceServers:[]});pc.onicecandidate=e=>{if(e.candidate)send({type:'ice',candidate:e.candidate})};pc.onconnectionstatechange=()=>{status('Media: '+pc.connectionState);if(['failed','disconnected'].includes(pc.connectionState))status('Connection interrupted. Stop and create a new pairing QR. Check Wi-Fi isolation/firewall.')};return pc}
async function signal(data){if(data.type==='ice'){if(pc?.remoteDescription)await pc.addIceCandidate(data.candidate);else pending.push(data.candidate)}}
async function flush(){for(const c of pending)await pc.addIceCandidate(c);pending=[]}
function cleanup(){stream?.getTracks().forEach(t=>t.stop());stream=null;pc?.close();pc=null;if(ws){ws.onclose=null;ws.onmessage=null;ws.close()}ws=null;pending=[];$('video').srcObject=null}
window.addEventListener('pagehide',cleanup);

let audioCtx,analyser,qrUrl;
async function api(path){if(!token)throw Error('Missing receiver link. In Signal Room click Pair iPhone, then copy the Open receiver separately link into Safari. Do not copy the address bar.');const r=await fetch(path,{method:path==='/qr'?'GET':'POST',headers:{Authorization:'Bearer '+token}});if(r.status===403)throw Error('Receiver link expired or invalid. Return to Signal Room, click Pair iPhone, and copy the fresh Open receiver separately link into Safari.');if(!r.ok)throw Error('Pairing request failed: '+r.status);return r}
$('pair').onclick=async()=>{try{cleanup();const d=await(await api('/pair')).json();$('link').href=d.url;$('link').hidden=false;const blob=await(await api('/qr')).blob();if(qrUrl)URL.revokeObjectURL(qrUrl);qrUrl=URL.createObjectURL(blob);$('qr').src=qrUrl;$('qr').hidden=false;peer();pc.ontrack=e=>{stream=e.streams[0];$('video').srcObject=stream;if(audioCtx)attachMeter();$('video').play().catch(()=>status('Press Play on the video to begin.'))};ws=new WebSocket(location.origin.replace('https:','wss:')+'/ws');ws.onopen=()=>send({role:'receiver',token});ws.onmessage=async e=>{try{const d=JSON.parse(e.data);if(d.type==='offer'){await pc.setRemoteDescription(d.sdp);await flush();await pc.setLocalDescription(await pc.createAnswer());send({type:'answer',sdp:pc.localDescription});$('qr').hidden=true;$('link').hidden=true}else if(d.type==='disconnected'){cleanup();status('Phone disconnected. Create a new pairing QR.')}else await signal(d)}catch(err){status(err.message)}};ws.onclose=()=>{cleanup();status('Pairing closed. Create a new QR to reconnect.')};status('Scan with iPhone. Link expires in five minutes and can be used once.');}catch(e){status(e.message)}};
let source;
function attachMeter(){source?.disconnect();if(stream&&audioCtx){source=audioCtx.createMediaStreamSource(stream);analyser=audioCtx.createAnalyser();analyser.fftSize=2048;source.connect(analyser)}}
$('audio').onclick=async()=>{audioCtx??=new AudioContext();await audioCtx.resume();attachMeter();$('audio').textContent='Audio meter enabled'};
$('sound').onclick=()=>{$('video').muted=!$('video').muted;$('sound').textContent=$('video').muted?'Unmute playback':'Mute playback'};
$('stop').onclick=async()=>{cleanup();source?.disconnect();analyser=null;$('level').value=-60;$('qr').hidden=true;$('link').hidden=true;try{await api('/unpair');status('Unpaired. Phone capture stopped.')}catch(e){status(e.message)}};
setInterval(()=>{
 const tracks=stream?.getAudioTracks()||[];
 if(analyser&&stream&&audioCtx?.state==='running'&&tracks.some(t=>t.readyState==='live'&&!t.muted)){
  const samples=new Float32Array(analyser.fftSize);analyser.getFloatTimeDomainData(samples);
  const rms=Math.sqrt(samples.reduce((sum,v)=>sum+v*v,0)/samples.length);
  const peak=samples.reduce((max,v)=>Math.max(max,Math.abs(v)),0);
  const db=20*Math.log10(Math.max(rms,1e-8));
  $('level').value=Math.max(-60,Math.min(0,db));
  $('levelvalue').textContent=(rms<1e-7?'Silence':`${db.toFixed(1)} dBFS RMS`)+(peak>=.99?' · peak near clipping':'');
 }else{
  $('level').value=-60;
  $('levelvalue').textContent=!stream?'No audio stream':!analyser?'Click Enable audio meter':audioCtx?.state!=='running'?'Click Enable audio meter to resume':'Audio track muted or unavailable';
 }
},100);

setInterval(async()=>{if(!pc||pc.connectionState!=='connected')return;const stats=await pc.getStats();for(const v of stats.values()){if(v.type==='inbound-rtp'&&v.kind==='video')$('stats').textContent=`Video: ${v.frameWidth??'—'} × ${v.frameHeight??'—'} · ${v.framesPerSecond??'—'} fps · ${v.packetsLost??0} packets lost. EEG alignment is approximate.`}},2000);

if(!token){$('pair').disabled=true;status('Missing receiver credential. Open the full receiver link from Signal Room’s Open receiver separately link, not the address bar.')}


// One-shot local offline capture. Never stops the source stream's tracks.
(() => {
 const button=$('cliprecord'),cancel=$('clipcancel'),download=$('clipdownload');
 if(!button)return;
 let recorder=null,deadline=null,ticker=null,url=null,discard=false,captureId=null,captureStart=null;
 async function captureApi(action, options={}){
  const response=await fetch('/capture/'+action,{method:'POST',...options,headers:{Authorization:'Bearer '+token,...options.headers}});
  if(!response.ok)throw Error(await response.text());
  return response;
 }
 async function stopEEG(){
  if(!captureId)return;
  await captureApi('stop',{headers:{'Content-Type':'application/json'},body:JSON.stringify({id:captureId})});
 }
 const report=text=>$('clipstatus').textContent=text;
 function clearTimers(){clearTimeout(deadline);clearInterval(ticker)}
 function abort(reason){
  if(!recorder)return;
  discard=true;clearTimers();
  if(recorder.state!=='inactive')recorder.stop();
  report(reason);
 }
 cancel.onclick=()=>abort('Recording cancelled. No clip saved.');
 button.onclick=async()=>{
  try{
   if(!stream?.active)throw Error('Connect your iPhone audio and video first.');
   if(!window.MediaRecorder)throw Error('This browser does not support recording.');
   if(!stream.getVideoTracks().some(t=>t.readyState==='live')||!stream.getAudioTracks().some(t=>t.readyState==='live'))throw Error('Both video and microphone tracks are required.');
   const mime=['video/mp4','video/webm;codecs=vp8,opus','video/webm'].find(m=>MediaRecorder.isTypeSupported(m));
   if(!mime)throw Error('No supported recording format available.');
   if(url){URL.revokeObjectURL(url);url=null}
   download.hidden=true;discard=false;
   const chunks=[];let bytes=0;
   button.disabled=true;report('Starting EEG recording…');
   const requestAt=Date.now();
   const eeg=await (await captureApi('start',{headers:{'Content-Type':'application/json'},body:'{}'})).json();
   captureId=eeg.id;captureStart={server_eeg_start_unix:eeg.started_at_unix,request_browser_unix_ms:requestAt,response_browser_unix_ms:Date.now(),media_start_browser_unix_ms:Date.now()};
   const began=performance.now();
   recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:1800000});
   recorder.ondataavailable=e=>{
    bytes+=e.data.size;
    if(bytes>32*1024*1024){abort('Clip exceeded 32 MiB; recording discarded.');return}
    if(e.data.size)chunks.push(e.data);
   };
   recorder.onerror=()=>abort('Recording failed. Reconnect and try again.');
   recorder.onstop=async()=>{
    clearTimers();cancel.disabled=true;recorder=null;
    const duration=(performance.now()-began)/1000;
    try{
     await stopEEG();
     if(discard)return;
     if(duration<14||duration>17||!bytes){report('Recording interrupted or delayed. EEG saved, but no complete media package. Keep this tab visible and retry.');return}
     report('Saving audio/video and EEG on this Mac…');
     const blob=new Blob(chunks,{type:mime});
     const saved=await (await captureApi('media',{headers:{'Content-Type':mime,'X-Capture-Id':captureId,'X-Capture-Timing':JSON.stringify({...captureStart,media_duration_seconds:duration})},body:blob})).json();
     const response=await captureApi('download',{method:'GET',headers:{'X-Capture-Id':captureId}});
     url=URL.createObjectURL(await response.blob());download.href=url;download.download='brain-gremlin-'+captureId+'.zip';
     download.textContent='Download EEG + audio/video ZIP';download.hidden=false;
     report(`Saved ${duration.toFixed(1)} s of media and ${saved.sample_count} EEG samples in ${saved.folder}. ${saved.sample_count?'Download the ZIP to share.':'WARNING: no EEG samples were received; reconnect and retry.'}`);
    }catch(e){report('Capture could not be packaged: '+e.message)}
    finally{button.disabled=false;captureId=null}
   };
   recorder.start(1000);button.disabled=true;cancel.disabled=false;
   report('Recording: 15 seconds remaining…');
   ticker=setInterval(()=>report(`Recording: ${Math.max(0,Math.ceil(15-(performance.now()-began)/1000))} seconds remaining…`),250);
   deadline=setTimeout(()=>{if(recorder?.state==='recording')recorder.stop()},15000);
  }catch(e){clearTimers();try{await stopEEG()}catch{}captureId=null;button.disabled=false;cancel.disabled=true;recorder=null;report(e.message)}
 };
 document.addEventListener('visibilitychange',()=>{if(document.hidden)abort('Recording cancelled because the tab was hidden. Keep it visible and retry.');});
 window.addEventListener('pagehide',()=>{abort('Recording cancelled.');if(url)URL.revokeObjectURL(url)});
})();
