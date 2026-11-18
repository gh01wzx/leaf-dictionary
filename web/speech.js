'use strict';
// Windows offline audio: one active player, bounded cache, shared voice discovery.
let speechAccent='en-US', speechInfo=null, speechRequest=0, speechController=null, speechPlayer=null, speechURL=null, speechButton=null;
const speechCache=new Map();
try { speechAccent=localStorage.getItem('leaf-speech-accent') || 'en-US'; } catch {}
function pronunciationControls(word, compact=false) {
  return `<span class="speech${compact?' compact':''}"><button type="button" class="speech-button" data-speak="${escapeHTML(word)}" aria-label="朗读 ${escapeHTML(word)}" title="朗读（P）">${icon('speaker')}</button><button type="button" class="speech-button speech-slow" data-speak="${escapeHTML(word)}" data-slow="true" aria-label="慢速朗读 ${escapeHTML(word)}" title="慢速朗读">慢</button></span>`;
}
function stopSpeech() {
  speechRequest++;
  speechController?.abort(); speechController=null;
  if (speechPlayer) { speechPlayer.pause(); speechPlayer.src=''; speechPlayer=null; }
  if (speechURL) { URL.revokeObjectURL(speechURL); speechURL=null; }
  if (speechButton) { speechButton.classList.remove('speaking'); speechButton.removeAttribute('aria-busy'); speechButton=null; }
}
let speechInfoPending;
async function loadSpeechInfo() {
  speechInfoPending ||= api('speech').finally(() => { speechInfoPending=null; });
  const info=await speechInfoPending; speechInfo=info;
  const select=$('#speech-accent'), status=$('#speech-status');
  if (!info.accents.some(accent=>accent.id===speechAccent)) speechAccent=info.default || 'en-US';
  select.innerHTML=info.accents.map(accent=>`<option value="${escapeHTML(accent.id)}">${escapeHTML(accent.label)}</option>`).join('');
  select.value=speechAccent; select.disabled=!info.available;
  status.textContent=info.message;
  return info;
}
async function speakWord(word,slow,button) {
  const isSame=speechButton===button;
  stopSpeech();
  if (isSame) return;
  const request=speechRequest;
  speechButton=button; button.classList.add('speaking'); button.setAttribute('aria-busy','true');
  try {
    const info=speechInfo || await loadSpeechInfo();
    if (request!==speechRequest) return;
    if (!info.available) throw new Error(info.message);
    const key=JSON.stringify([word,speechAccent,slow]);
    let blob=speechCache.get(key);
    if (!blob) {
      speechController=new AbortController();
      const response=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json','X-Leaf-Token':token},body:JSON.stringify({word,accent:speechAccent,slow}),signal:speechController.signal});
      if (!response.ok) { const data=await response.json(); throw new Error(data.error || '读音暂时无法播放。'); }
      blob=await response.blob();
      speechCache.set(key,blob);
      if (speechCache.size>64) speechCache.delete(speechCache.keys().next().value);
    }
    if (request!==speechRequest) return;
    speechURL=URL.createObjectURL(blob); speechPlayer=new Audio(speechURL);
    speechPlayer.onended=()=>{if (request===speechRequest) stopSpeech();};
    speechPlayer.onerror=()=>{if (request===speechRequest) { stopSpeech(); toast('读音未能播放，请检查声音输出后重试。',true); }};
    await speechPlayer.play();
    if (request===speechRequest) button.removeAttribute('aria-busy');
  } catch (error) {
    if (request===speechRequest) { stopSpeech(); if (error.name!=='AbortError') toast(error.message || '读音暂时无法播放。',true); }
  }
}
