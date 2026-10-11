'use strict';
// Canvas counterpart of the Bloom design for the existing Signal Room habitat.
function drawBloomCanvas(c,w,h,mood,seconds,energy=0){
 const plum='#2d2250',yellow='#ffe558';
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const t=reduced?0:seconds;
 const size=Math.min(w*.65,h*.92,380),cx=w/2,cy=h*.53+(mood==='sad'?size*.025:0);
 const ellipse=(x,y,rx,ry,fill,stroke=null,line=2)=>{c.beginPath();c.ellipse(x,y,rx,ry,0,0,Math.PI*2);if(fill){c.fillStyle=fill;c.fill()}if(stroke){c.strokeStyle=stroke;c.lineWidth=line;c.stroke()}};
 for(let i=0;i<8;i++){
  let angle=i*Math.PI/4;
  if(mood==='happy')angle+=t*Math.PI*2/2.2;
  else if(mood==='sleepy')angle+=t*Math.PI*2/22;
  else if(mood==='focused')angle+=Math.floor(t*2.5)*Math.PI/20;
  else angle+=Math.sin(t*.5)*.03;
  let dx=0,dy=0,opacity=1;
  if(mood==='sad'&&!reduced){const fall=(t-i*1.7+160)%16;if(fall<2.5){const p=fall/2.5;dx=(i%2?-1:1)*p*size*.4;dy=p*size*.55;opacity=fall>1.9?(2.5-fall)/.6:1}}
  c.save();c.globalAlpha=opacity;c.translate(cx+dx,cy+dy);c.rotate(angle);
  const grad=c.createLinearGradient(0,-size*.44,0,size*.1);
  grad.addColorStop(0,'#ff9bbc');grad.addColorStop(.55,'#ee83b6');grad.addColorStop(1,'#bd8bde');
  ellipse(0,-size*(.18+energy*.015),size*.135,size*.26,grad,plum,2);
  c.restore();
 }
 let faceY=cy;
 if(mood==='happy'&&!reduced)faceY+=Math.sin(t*5.7)*size*.012;
 const r=size*.187;
 const halo=size*.38*(mood==='focused'&&!reduced?1+.025*Math.sin(t*3):1);
 const glow=c.createRadialGradient(cx,faceY,r*.5,cx,faceY,halo);
 glow.addColorStop(0,'#ffe55888');glow.addColorStop(.48,'#ffe55855');glow.addColorStop(1,'#ffe55800');
 ellipse(cx,faceY,halo,halo,glow);
 ellipse(cx,faceY,r,r,yellow,plum,2);
 const eyeY=faceY-r*.1,eyeDx=r*.25;
 for(const sign of [-1,1]){
  const ex=cx+sign*eyeDx;
  if(mood==='sleepy')ellipse(ex,eyeY,r*.024,r*.011,plum);
  else ellipse(ex,eyeY,r*.04,r*.105,plum);
 }
 let mouthW=r*(mood==='focused'||mood==='sad'?.19:.27);
 let mouthH=r*(mood==='focused'||mood==='sad'?.085:.13);
 if(mood==='sleepy'){mouthW=r*.13;mouthH=r*(.16+(reduced?0:.035*(1+Math.sin(t*2))))}
 ellipse(cx,faceY+r*.32,mouthW,mouthH,plum);
 if(mood==='focused'){
  const gr=r*.26;
  for(const sign of [-1,1])ellipse(cx+sign*eyeDx,eyeY,gr,gr,null,plum,3);
  c.strokeStyle=plum;c.lineWidth=3;c.beginPath();
  c.moveTo(cx-eyeDx+gr,eyeY);c.lineTo(cx+eyeDx-gr,eyeY);
  c.moveTo(cx-eyeDx-gr,eyeY);c.lineTo(cx-r*.88,eyeY);
  c.moveTo(cx+eyeDx+gr,eyeY);c.lineTo(cx+r*.88,eyeY);
  c.moveTo(cx-eyeDx-gr*.65,eyeY-gr*1.35);c.lineTo(cx-eyeDx+gr*.65,eyeY-gr*1.15);
  c.moveTo(cx+eyeDx-gr*.65,eyeY-gr*1.15);c.lineTo(cx+eyeDx+gr*.65,eyeY-gr*1.35);c.stroke();
 }
 if(mood==='happy'){
  c.strokeStyle=plum;c.lineWidth=4;c.lineCap='round';c.beginPath();
  for(const degrees of [-145,-90,-35]){const a=degrees*Math.PI/180,d=size*.42;c.moveTo(cx+Math.cos(a)*d,cy+Math.sin(a)*d);c.lineTo(cx+Math.cos(a)*(d+size*.07),cy+Math.sin(a)*(d+size*.07))}
  c.stroke();
 }
}
