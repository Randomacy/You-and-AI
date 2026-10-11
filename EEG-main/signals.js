
const $=id=>document.getElementById(id),names=['Fp1','Fp2','Fz','Cz','T7','T8','Pz','Oz'];let paused=false,latest=null;
const cards=names.map((name,i)=>{const el=document.createElement('section');el.className='card';el.innerHTML=`<div class="label"><strong>${i+1} / ${name}</strong><span class="rms">— µV RMS</span></div><canvas aria-label="${name} filtered signal"></canvas><div class="meta quality">Waiting for samples</div>`;$('grid').append(el);return el});
function draw(){cards.forEach((el,i)=>{
 const c=el.querySelector('canvas'),r=c.getBoundingClientRect(),d=devicePixelRatio||1;
 c.width=r.width*d;c.height=r.height*d;const ctx=c.getContext('2d');ctx.scale(d,d);
 const left=76,right=r.width-14,top=24,bottom=r.height-32,w=right-left,h=bottom-top;
 const live=latest?.status==='streaming',scale=latest?.trace_scale_uv?.[i],times=latest?.trace_times_seconds;
 const calibrated=live&&Number.isFinite(scale)&&Array.isArray(times)&&times.length>1;
 ctx.font='11px system-ui';ctx.fillStyle='#b9c9c4';ctx.textAlign='left';ctx.fillText('µV · median-centred',left,13);
 const fmt=n=>n.toLocaleString(undefined,{maximumFractionDigits:1});
 [2,1,0,-1,-2].forEach(v=>{const y=top+(2-v)*h/4;ctx.strokeStyle=v===0?'#58746b':'#294143';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.textAlign='right';ctx.fillStyle='#b9c9c4';ctx.fillText(calibrated?fmt(v*scale):'—',left-8,y+4)});
 const duration=calibrated?-times[0]:3;
 [0,.333333,.666667,1].forEach(f=>{const x=left+f*w;ctx.strokeStyle='#294143';ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.stroke();ctx.textAlign=f===0?'left':f===1?'right':'center';ctx.fillStyle='#b9c9c4';ctx.fillText(f===1?'0 s (latest)':(-duration*(1-f)).toFixed(1)+' s',x,bottom+20)});
 if(!calibrated){ctx.textAlign='center';ctx.fillText(live?'Restart server to load amplitude scales':'Waiting for live samples',left+w/2,top+h/2-12);return}
 const values=latest.traces?.[i]||[];ctx.save();ctx.beginPath();ctx.rect(left,top,w,h);ctx.clip();ctx.strokeStyle='#bce69e';ctx.lineWidth=1.5;ctx.beginPath();values.forEach((v,j)=>{const x=left+(times[j]+duration)/duration*w,y=top+(2-v)*h/4;j?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke();ctx.restore();
})}
async function action(path,body){try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());await poll()}catch(e){$('status').textContent='Connection request failed: '+e.message}}
$('connect').onclick=()=>action('/api/connect',{port:$('port').value});$('disconnect').onclick=()=>action('/api/disconnect',{});$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'Resume view':'Pause view';if(!paused)poll()};
async function poll(){try{const r=await fetch('/api/eeg',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);const d=await r.json();const selected=$('port').value;const ports=d.ports||[];if(JSON.stringify(ports)!==JSON.stringify([...$('port').options].map(x=>x.value))){$('port').replaceChildren(...ports.map(p=>new Option(p,p)));if(ports.includes(selected))$('port').value=selected}
$('connect').disabled=!ports.length||['streaming','connecting','warming','disconnecting'].includes(d.status);$('disconnect').disabled=d.status==='disconnected';$('status').textContent=(paused?'VIEW PAUSED · ':'')+(d.synthetic?'SYNTHETIC · ':'')+d.message+(d.status==='streaming'?` · ${d.measured_rate} samples/s · ${d.packet_discontinuities??'—'} packet gaps`:'');
if(paused&&d.status==='streaming')return;latest=d;updateFocus(d);cards.forEach((el,i)=>{const live=d.status==='streaming',q=d.diagnostics?.[i];el.querySelector('.rms').textContent=live?`${d.rms_uv?.[i]??'—'} µV RMS`:'— µV RMS';const label=el.querySelector('.quality');label.textContent=live&&q?`Raw 50 Hz power: ${q.line_noise_percent}% · Clipping: ${q.clipping_percent}% · ${q.notes.join(' · ')}${Number.isFinite(q.line_power_uv2)?` · Raw 49–51 Hz: ${q.line_power_uv2.toLocaleString()} µV² · Raw other 1–60 Hz: ${q.other_power_uv2.toLocaleString()} µV² · After filtering 49–51 Hz: ${q.filtered_line_power_uv2?.toLocaleString()??'—'} µV² (${q.filtered_line_noise_percent??'—'}%)`:' · Restart server for absolute power readings'}`:'No fresh measurements';label.className='meta quality'+(live&&((d.rms_uv?.[i]||0)>150||(q?.line_noise_percent||0)>50)?' warning':'')});draw();}catch(e){latest=null;updateFocus(null);$('status').textContent='Bridge unavailable. Start server.py in the EEG folder.';cards.forEach(el=>{el.querySelector('.rms').textContent='— µV RMS';el.querySelector('.quality').textContent='No fresh measurements'});draw()}}
window.addEventListener('resize',draw);poll();setInterval(poll,500);

// Fixed hues and a shared adjustable amplitude ceiling keep the mapping explicit.
const hues=[350,24,48,145,180,213,264,310];
const art=$('art'),artctx=art.getContext('2d');let artTime=0,lastFrame=0,lastPaint=-1;
let paintMarks=[];
const brushHeads=Array(8).fill(null);
const brushAngles=names.map((_,i)=>i*Math.PI/4);
const priorLevels=Array(8).fill(0);
const HOLD_SECONDS=5,FADE_SECONDS=2;
function paintOpacity(age){return age<=HOLD_SECONDS?1:Math.max(0,1-(age-HOLD_SECONDS)/FADE_SECONDS)}
const brightness=Array(8).fill(0);
const legend=names.map((name,i)=>{const el=document.createElement('div');el.innerHTML=`<span class="swatch" style="background:hsl(${hues[i]} 80% 60%)"></span>${i+1} / ${name}<small>Waiting</small>`;$('legend').append(el);return el});
$('ceiling').oninput=()=>{$('ceilingvalue').textContent=Number($('ceiling').value).toLocaleString()};
function paintArt(now){
 const dt=Math.min((now-lastFrame)/1000,.1);lastFrame=now;
 const live=latest?.status==='streaming';if(!paused)artTime+=dt;
 const deposit=live&&!paused&&artTime-lastPaint>=1/30;if(deposit)lastPaint=artTime;
 if(!live)brushHeads.fill(null);
 const box=art.getBoundingClientRect(),ratio=Math.min(devicePixelRatio||1,2),w=box.width,h=box.height;
 if(art.width!==Math.round(w*ratio)||art.height!==Math.round(h*ratio)){art.width=Math.round(w*ratio);art.height=Math.round(h*ratio)}
 artctx.setTransform(ratio,0,0,ratio,0,0);artctx.fillStyle='#090d17';artctx.fillRect(0,0,w,h);
 const cap=Number($('ceiling').value);
 for(let i=0;i<8;i++){
  const rms=latest?.rms_uv?.[i],valid=live&&Number.isFinite(rms);
  const target=valid?Math.min(Math.max(rms,0)/cap,1):0;
  if(!paused||!live)brightness[i]+=(target-brightness[i])*(1-Math.exp(-dt*3));
  const level=brightness[i],light=7+level*65;
  if(deposit&&valid){
   // This is an artistic mapping of amplitude changes, not decoded intention.
   const previous=brushHeads[i]||{x:.5+.28*Math.cos(i*Math.PI/4),y:.5+.28*Math.sin(i*Math.PI/4)};
   const change=level-priorLevels[i];priorLevels[i]=level;
   brushAngles[i]+=.008+Math.max(-.06,Math.min(.06,change*1.8));
   // Gently steer inward near the boundary, avoiding hard bounces.
   const toward=Math.atan2(.5-previous.y,.5-previous.x);
   const edge=Math.max(Math.abs(previous.x-.5),Math.abs(previous.y-.5));
   if(edge>.34){const delta=Math.atan2(Math.sin(toward-brushAngles[i]),Math.cos(toward-brushAngles[i]));brushAngles[i]+=delta*.05}
   const speed=.0012+.0018*level;
   const point={x:Math.max(.04,Math.min(.96,previous.x+Math.cos(brushAngles[i])*speed)),y:Math.max(.04,Math.min(.96,previous.y+Math.sin(brushAngles[i])*speed))};
   const prev=previous;
   const mark={from:prev,to:point,born:artTime,hue:hues[i],light,width:.008+.032*level,seed:Math.random()*100};
   paintMarks.push(mark);
   if(recording){renderMark(recordContext,mark,recordCanvas.width,recordCanvas.height,1);recordCount++}
   brushHeads[i]=point;
  }
  legend[i].querySelector('small').textContent=valid?`${Math.round(rms).toLocaleString()} µV RMS · ${Math.round(target*100)}% light${rms>=cap?' (ceiling)':''}`:'No fresh signal';
 }
 paintMarks=paintMarks.filter(mark=>artTime-mark.born<HOLD_SECONDS+FADE_SECONDS);
 if($('paintview').value==='complete'&&recordCanvas){artctx.drawImage(recordCanvas,0,0,w,h)}
 else {for(const mark of paintMarks)renderMark(artctx,mark,w,h,paintOpacity(artTime-mark.born));}
 if($('paintview').value==='complete'&&!recordCanvas){artctx.fillStyle='#b9c9c4';artctx.font='16px system-ui';artctx.textAlign='center';artctx.fillText('Start a recording to build your complete painting',w/2,h/2)}
 updateRecording(live);
 $('artnote').textContent=(paused&&live?'Paused · ':live?(latest.synthetic?'Synthetic test signal · ':'Live headset · '):'No fresh signal · ')+`Brightness = filtered RMS ÷ ${cap.toLocaleString()} µV, capped at 100%. Each stroke holds for 5 seconds, then fades over 2 seconds. Brightness and width follow amplitude; changes gently steer the brushes. This artistic mapping includes signal noise and does not decode thoughts.`;
 requestAnimationFrame(paintArt);
}
requestAnimationFrame(paintArt);
document.querySelector('details').addEventListener('toggle',draw);

// A fixed-resolution raster accumulates strokes once; memory does not grow with duration.
let recording=false,recordCanvas=null,recordContext=null,recordCount=0,recordStarted=0,downloadUrl=null,saving=false;
function renderMark(ctx,mark,w,h,opacity){
 const size=mark.width*Math.min(w,h),x1=mark.from.x*w,y1=mark.from.y*h,x2=mark.to.x*w,y2=mark.to.y*h;
 ctx.lineCap='round';
 for(let bristle=0;bristle<7;bristle++){
  const offset=(bristle-3)*size/7,jitter=Math.sin(mark.seed+bristle*3)*size*.08;
  ctx.globalAlpha=opacity*(.22+.18*(.5+.5*Math.sin(mark.seed+bristle)));ctx.strokeStyle=`hsl(${mark.hue} 75% ${mark.light+(bristle%2)*3}%)`;
  ctx.lineWidth=size/(5+(bristle%3));ctx.beginPath();ctx.moveTo(x1+offset,y1+jitter);ctx.lineTo(x2+offset,y2+jitter);ctx.stroke();
 }
 ctx.globalAlpha=1;
}
function updateRecording(live){
 $('ceiling').disabled=recording||saving;
 $('recordstart').disabled=recording||saving||!live||paused;
 $('recordstop').disabled=!recording;
 if(recording){const seconds=Math.floor((performance.now()-recordStarted)/1000);$('recordstatus').textContent=`Recording · ${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')} · ${recordCount.toLocaleString()} strokes · ${paused?'view paused; no strokes added':!live?'signal unavailable; waiting':'accumulating the complete painting'}`}
}
$('recordstart').onclick=()=>{
 if(recording||saving||paused||latest?.status!=='streaming')return;
 recordCanvas=document.createElement('canvas');const rect=art.getBoundingClientRect();recordCanvas.width=2400;recordCanvas.height=Math.max(1,Math.round(2400*rect.height/rect.width));
 recordContext=recordCanvas.getContext('2d');recordContext.fillStyle='#090d17';recordContext.fillRect(0,0,recordCanvas.width,recordCanvas.height);
 recordCount=0;recordStarted=performance.now();recording=true;brushHeads.fill(null);updateRecording(true);
};
$('recordstop').onclick=()=>{
 if(!recording)return;recording=false;saving=true;updateRecording(latest?.status==='streaming');$('recordstatus').textContent='Preparing your PNG…';
 const filename='brainflow-painting-'+new Date().toISOString().replace(/[:.]/g,'-')+'.png';
 recordCanvas.toBlob(blob=>{
  saving=false;
  if(!blob){$('recordstatus').textContent='PNG export failed. Please try a new recording.';return}
  if(downloadUrl)URL.revokeObjectURL(downloadUrl);downloadUrl=URL.createObjectURL(blob);
  const link=$('recorddownload');link.href=downloadUrl;link.download=filename;link.hidden=false;link.click();
  $('recordstatus').textContent=`Picture ready · ${recordCount.toLocaleString()} strokes · ${recordCanvas.width} × ${recordCanvas.height} pixels. If downloading did not start, use the download link.`;
 },'image/png');
};
window.addEventListener('beforeunload',event=>{if(recording||saving){event.preventDefault();event.returnValue=''}});

function updateFocus(data){
 const f=data?.status==='streaming'?data.focus:null,valid=f?.status==='experimental'&&Number.isFinite(f.ratio)&&Number.isFinite(f.balance);
 $('focusstate').textContent=valid?'Live spectral engagement pattern':'Focus unclear';
 $('focusreason').textContent=f?.reason||(data?.status==='streaming'?'Restart server.py to enable the focus panel.':'Waiting for fresh EEG.');
 $('focusratio').textContent=valid?`Engagement ratio: ${f.ratio.toFixed(3)} · uncalibrated`:'Engagement ratio: —';
 $('focusorb').textContent=valid?'EEG proxy':'Unclear';
 $('focusorb').style.background=valid?`hsl(170 55% ${18+Math.max(0,Math.min(1,f.balance))*55}%)`:'#35404d';
}
