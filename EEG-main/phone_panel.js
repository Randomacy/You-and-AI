document.getElementById('phoneopen').onclick=async()=>{const note=document.getElementById('phonenote');try{const d=await(await fetch('/api/phone')).json();if(!d.url){note.textContent='Start phone_server.py first. See IPHONE_SETUP.md.';return}const u=new URL(d.url);if(u.protocol!=='https:')throw Error('Invalid receiver URL');const a=document.getElementById('phonelink');a.href=u.href;a.hidden=false;document.getElementById('phoneframe').src=u.href;document.getElementById('phoneframe').hidden=false;note.textContent='If the panel cannot load, open the receiver link to check certificate trust. Use Safari if the in-app browser blocks media.'}catch(e){note.textContent=e.message}};
document.getElementById('phonecopy').onclick=async()=>{
 const note=document.getElementById('phonenote');
 try{
  const response=await fetch('/api/phone',{cache:'no-store'});if(!response.ok)throw Error('Unable to read pairing service configuration.');
  const data=await response.json();if(!data.url)throw Error('Start phone_server.py first.');
  const url=new URL(data.url);if(url.protocol!=='https:'||url.hash.length<20)throw Error('Receiver configuration is missing its credential. Restart phone_server.py.');
  try{await navigator.clipboard.writeText(url.href);note.textContent='Full private receiver link copied. Paste into Mac Safari. Do not share this link.'}
  catch{const input=document.getElementById('phonecopyfallback');input.value=url.href;input.hidden=false;input.focus();input.select();note.textContent='Press Command+C to copy the selected full link, then paste into Mac Safari. Do not share this link.'}
 }catch(error){note.textContent=error.message}
};
