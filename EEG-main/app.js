'use strict';
const channelMap=['Fp1','Fp2','Fz','Cz','T7','T8','Pz','Oz'];
const plants=[['🌿','Fern'],['🌵','Cactus'],['🌱','Sprout'],['🪴','Monstera'],['🌷','Tulip'],['🌻','Sunny']];
const actionList=[['←','Left'],['→','Right'],['↑','Up'],['↓','Down'],['✦','Click']];
let action=1,target=0,adopted=new Set(),energy=0,paused=matchMedia('(prefers-reduced-motion: reduce)').matches,t=0,last=0,burst=0;
const $=id=>document.getElementById(id);
let eeg=null, live=false, pollAt=0;
let emotionFace="unsure", bloomMood="happy";

$('channels').innerHTML=channelMap.map((name,i)=>`<span class="channel">${i+1} / ${name}</span>`).join('');
function render(){
 $('cards').innerHTML=plants.map(([emoji,name],i)=>`<button class="card ${i===target?'active':''}" data-target="${i}" aria-label="Highlight ${name}" aria-pressed="${i===target}"><span class="plant">${emoji}</span><strong>${name}</strong><small>${adopted.has(i)?'Adopted ♥':'A leafy little friend'}</small></button>`).join('');
 $('actions').innerHTML=actionList.map(([icon,name],i)=>`<button class="action ${i===action?'selected':''}" data-action="${i}" aria-label="Select ${name}" aria-pressed="${i===action}" title="${name}">${icon}<span style="display:block;font-size:9px;margin-top:4px">${name}</span></button>`).join('');
 $('count').textContent=`${adopted.size} plant${adopted.size===1?'':'s'} adopted`;
}
function selectBloomMood(mood){
 if(!['happy','sad','sleepy','focused'].includes(mood))return;
 bloomMood=mood;
 document.querySelectorAll('[data-bloom]').forEach(button=>{
  const active=button.dataset.bloom===mood;
  button.setAttribute('aria-pressed',String(active));
  button.classList.toggle('selected',active);
 });
 $('bloomlabel').textContent='BLOOM / '+mood.toUpperCase()+' · MANUAL PREVIEW';
}
$('bloompreviews').onclick=e=>{const button=e.target.closest('[data-bloom]');if(button)selectBloomMood(button.dataset.bloom)};
selectBloomMood(bloomMood);
function feedback(message,speech){$('log').textContent=message;$('bubble').textContent=speech;$('state').textContent='● Intention received';burst=1;}
function next(){action=(action+1)%5;render();feedback(`SIMULATED LEFT → selected ${actionList[action][1]}`,'“Okay… what shall we do next?”');}
function execute(){if(action===0)target=Math.floor(target/3)*3+(target+2)%3;if(action===1)target=Math.floor(target/3)*3+(target+1)%3;if(action===2||action===3)target=(target+3)%6;if(action===4){const already=adopted.has(target);adopted.add(target);$('result').textContent=already?`${plants[target][1]} is already at home with you.`:`${plants[target][1]} adopted! Your garden is growing.`;feedback(`SIMULATED RIGHT → Click → ${plants[target][1]}`,already?'“We’re already friends!”':'“Boop. You’re coming home with me!”');}else{feedback(`SIMULATED RIGHT → ${actionList[action][1]} → ${plants[target][1]}`,'“Ooh. This one?”');$('result').textContent=`${plants[target][1]} is highlighted. Select Click to adopt it.`;}render();}
$('next').onclick=next;$('execute').onclick=execute;
$('actions').onclick=e=>{const el=e.target.closest('[data-action]');if(el){action=Number(el.dataset.action);render();}};
$('cards').onclick=e=>{const el=e.target.closest('[data-target]');if(el){target=Number(el.dataset.target);$('result').textContent=`${plants[target][1]} is highlighted. Select Click to adopt it.`;render();}};
document.addEventListener('keydown',e=>{if(e.repeat||e.altKey||e.ctrlKey||e.metaKey||/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;if(e.key.toLowerCase()==='a'){e.preventDefault();next();}if(e.key.toLowerCase()==='d'){e.preventDefault();execute();}});
$('energy').oninput=e=>{energy=Number(e.target.value)/100;$('energyvalue').textContent=`${e.target.value}%`;};
function pauseLabel(){$('pause').textContent=paused?'Resume animation':'Pause animation';$('pause').setAttribute('aria-pressed',String(paused));}
$('pause').onclick=()=>{paused=!paused;pauseLabel();};
$('reset').onclick=()=>{adopted.clear();target=0;action=1;burst=0;$('result').textContent='Fern is highlighted. Select Click to adopt it.';$('log').textContent='Garden reset. Waiting for a simulated intention…';$('bubble').textContent='Something good is growing.';$('state').textContent=live?'● Feeling your signals':'● Waiting for EEG';render();};
function setup(id){const canvas=$(id),ctx=canvas.getContext('2d');const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);if(canvas.width!==Math.round(rect.width*dpr)||canvas.height!==Math.round(rect.height*dpr)){canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);}ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,rect.width,rect.height);return [ctx,rect.width,rect.height];}
function draw(){
 const [c,w,h]=setup('creature');
 drawBloomCanvas(c,w,h,bloomMood,t,live?energy:0);
 const [s,sw,sh]=setup('traces');
 for(let j=0;j<8;j++){
  s.beginPath();
  const values=live?eeg?.traces?.[j]:null;
  for(let x=0;x<sw;x+=2){const value=values?.[Math.min(values.length-1,Math.floor(x/sw*values.length))]||0;let y=(j+.5)*sh/8+value*(sh/8)*.23;if(x===0)s.moveTo(x,y);else s.lineTo(x,y)}
  s.strokeStyle=!live?'#425449':j===3||j===4?'#d6f68b':'#6c947a';s.lineWidth=1;s.stroke();
 }
}

function frame(now){const dt=Math.min((now-last)/1000,.05);last=now;if(!paused){t+=dt;burst=Math.max(0,burst-dt*.5);if(live&&!burst)$('state').textContent='● Feeling your signals';}draw();requestAnimationFrame(frame);}render();pauseLabel();requestAnimationFrame(frame);

function disconnected(message){updateDiagnostics(null);emotionFace='unsure';updateEmotion(null);live=false;energy=0;eeg=null;$('sourcebadge').textContent='EEG OFFLINE';$('connection').textContent=message;$('state').textContent='● Waiting for EEG';$('tracelabel').textContent='No live samples';$('energyvalue').textContent='—';$('energy').value=0;}
async function pollEEG(){
 try{const response=await fetch('/api/eeg',{cache:'no-store'});if(!response.ok)throw Error('Start server.py to enable the headset bridge.');const data=await response.json();pollAt=performance.now();eeg=data;live=data.status==='streaming'&&data.age_seconds<2;updateEmotion(data);updateDiagnostics(data);
 const selector=$('serialport'),chosen=selector.value,ports=data.ports||[];if(JSON.stringify(ports)!==selector.dataset.ports){selector.replaceChildren(...ports.map(port=>{const option=document.createElement('option');option.value=port;option.textContent=port;return option;}));selector.dataset.ports=JSON.stringify(ports);if(ports.includes(chosen))selector.value=chosen;}
 $('connect').disabled=!ports.length||['connecting','warming','streaming','stale','disconnecting'].includes(data.status);$('disconnect').disabled=['disconnected','error'].includes(data.status);
 $('connection').textContent=data.message;$('sourcebadge').textContent=live?(data.synthetic?'SYNTHETIC SDK TEST':'LIVE EEG · LOCAL ONLY'):data.status.toUpperCase();
 if(live){energy=energy*.7+data.energy*.3;$('energy').value=Math.round(energy*100);$('energyvalue').textContent=Math.round(energy*100)+'%';$('tracelabel').textContent=`${data.sample_rate} Hz nominal · ${data.measured_rate} samples/s received`;$('quality').textContent=data.warnings.length?'Signal check: '+data.warnings.join(' · '):'Receiving all eight channels. Display scale is automatic; this is not a contact-quality guarantee.';$('channels').replaceChildren(...channelMap.map((name,i)=>{const span=document.createElement('span');span.className='channel';span.textContent=`${i+1} / ${name} · ${data.rms_uv[i]} µV RMS`;return span;}));}
 else{energy=0;$('energy').value=0;$('energyvalue').textContent='—';$('state').textContent='● Waiting for EEG';$('tracelabel').textContent='No live samples';$('quality').textContent='EEG stays on this computer. Recording requires an explicit action. Manual controls remain available.';}
 }catch(error){disconnected(error.message);}finally{setTimeout(pollEEG,200);}
}
async function boardAction(path,body){$('connect').disabled=true;try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.error||'Connection is already active');}catch(error){$('connection').textContent=error.message;}}
$('connect').onclick=()=>boardAction('/api/connect',{port:$('serialport').value});$('disconnect').onclick=()=>boardAction('/api/disconnect',{});
setInterval(()=>{if(live&&performance.now()-pollAt>2500)disconnected('Stream unavailable. Check the local server.');},500);
pollEEG();

function updateEmotion(data){
 const emotion=live?data?.emotion:null;emotionFace=emotion?.face||'unsure';
 $('emotionlabel').textContent=emotionFace==='unsure'?'Unsure':'Estimated · '+emotionFace;
 $('emotionreason').textContent=emotion?.reason||'Waiting for a fresh EEG stream.';
 const metrics=data?.model_evaluation;
 $('validation').textContent=metrics?.valence?`Held-out-person balanced accuracy: pleasantness ${Math.round(metrics.valence.balanced_accuracy*100)}% · activation ${Math.round(metrics.arousal.balanced_accuracy*100)}%. Chance baseline: 50%.`:'Model evaluation unavailable.';
}
function updateDiagnostics(data){
 const rows=data?.status==='streaming'?data.diagnostics:null;
 $('packetquality').textContent=rows?`Packet-counter discontinuities this connection: ${data.packet_discontinuities}. Live readings update once per second.`:'Waiting for a live stream with diagnostics. Restart server.py after updating.';
 $('diagnostics').replaceChildren(...(rows||[]).map(row=>{const tr=document.createElement('tr');for(const value of [row.name,`${row.raw_min_uv} to ${row.raw_max_uv}`,`${row.clipping_percent}%`,`${row.line_noise_percent}%`,row.notes.join(' · ')]){const td=document.createElement('td');td.textContent=value;tr.appendChild(td);}return tr;}));
}
