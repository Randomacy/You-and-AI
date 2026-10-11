'use strict';
const moods={
 happy:{line:'Something good is growing.',description:'Petals whirl quickly and the whole bloom lifts with energy.'},
 sad:{line:'We don’t have to rush this.',description:'Petals loosen and fall while the center stays present and open.'},
 sleepy:{line:'Let’s let the day soften.',description:'Petals drift in a slow orbit as Bloom stretches into a yawn.'},
 focused:{line:'I’ve got the thread. Keep going.',description:'Petals lock into rhythm, glasses appear, and the expression sharpens.'}
};
const buttons=[...document.querySelectorAll('[data-mood]')];
function selectMood(mood){
 if(!Object.hasOwn(moods,mood))return;
 document.body.dataset.mood=mood;
 document.getElementById('mood-label').textContent=mood.toUpperCase();
 document.getElementById('message').textContent=moods[mood].line;
 document.getElementById('stage-caption').textContent=moods[mood].description;
 document.querySelector('.bloom').setAttribute('aria-label',`Bloom, a pink eight-petal flower in a ${mood} pose`);
 for(const button of buttons){const active=button.dataset.mood===mood;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));}
}
for(const button of buttons)button.addEventListener('click',()=>selectMood(button.dataset.mood));
document.addEventListener('keydown',event=>{
 if(event.altKey||event.ctrlKey||event.metaKey||event.repeat||/INPUT|TEXTAREA|SELECT/.test(event.target.tagName))return;
 const mood=['happy','sad','sleepy','focused'][Number(event.key)-1];
 if(mood){event.preventDefault();selectMood(mood);buttons.find(button=>button.dataset.mood===mood).focus();}
});
