const cropState={sourceUrl:'',targetCharacterId:null,scale:1,x:0,y:0,dragging:false,startX:0,startY:0,baseScale:1};

const state={
  mode:'assistant',characters:[],activeCharacter:null,activeConversationId:null,
  assistantConversationId:null,personas:[],activePersonaId:null,streaming:false,editingCharId:null
};

const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};

async function api(path,opts={}){
  const r=await fetch(path,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});
  if(!r.ok){let msg=await r.text().catch(()=>r.statusText);throw new Error(`${r.status}: ${msg}`);}
  return r.status===204?null:r.json();
}

function showMode(mode){
  state.mode=mode;
  $$('.mode-btn').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
  $('#assistant-panel')?.classList.toggle('hidden',mode!=='assistant');
  $('#character-panel')?.classList.toggle('hidden',mode!=='characters');
  $('#assistant-view')?.classList.toggle('hidden',mode!=='assistant');
  $('#character-view')?.classList.toggle('hidden',mode!=='characters');
  $('#image-view')?.classList.toggle('hidden',mode!=='images');
}

function setStatus(text){
  const s=$('#image-status'); if(s)s.textContent=text||'';
}

/* ========================= PERSONAS ========================= */

function syncPersonaSelectors(){
  const selectors=[$('#persona-select'),$('#character-persona-select')].filter(Boolean);
  selectors.forEach(sel=>{
    const current=String(state.activePersonaId||'');
    sel.innerHTML='';
    if(!state.personas.length){
      const o=document.createElement('option');o.value='';o.textContent='No persona yet';sel.appendChild(o);
      return;
    }
    state.personas.forEach(p=>{
      const o=document.createElement('option');o.value=p.id;o.textContent=p.name;sel.appendChild(o);
    });
    sel.value=current && state.personas.some(p=>String(p.id)===current)?current:String(state.personas[0].id);
  });
  if(!state.activePersonaId && state.personas.length) state.activePersonaId=state.personas[0].id;
  if($('#persona-select'))$('#persona-select').value=state.activePersonaId||'';
  if($('#character-persona-select'))$('#character-persona-select').value=state.activePersonaId||'';
  const name=state.personas.find(p=>p.id==state.activePersonaId)?.name||'None';
  if($('#assistant-persona-top'))$('#assistant-persona-top').textContent=`Persona: ${name}`;
}

async function loadPersonas(){
  state.personas=await api('/api/personas');
  if(state.activePersonaId && !state.personas.some(p=>p.id==state.activePersonaId))state.activePersonaId=null;
  syncPersonaSelectors();
}

function clearPersonaForm(){
  ['p-edit-id','p-name','p-avatar','p-description','p-pronouns','p-age','p-appearance','p-personality','p-style','p-background','p-details'].forEach(id=>{if($('#'+id))$('#'+id).value='';});
  $('#persona-save').textContent='Save persona';
}

function fillPersonaForm(p){
  $('#p-edit-id').value=p?.id||'';
  $('#p-name').value=p?.name||'';
  $('#p-avatar').value=p?.avatar_path||'';
  $('#p-description').value=p?.description||'';
  $('#p-pronouns').value=p?.pronouns||'';
  $('#p-age').value=p?.age||'';
  $('#p-appearance').value=p?.appearance||'';
  $('#p-personality').value=p?.personality||'';
  $('#p-style').value=p?.speaking_style||'';
  $('#p-background').value=p?.background||'';
  $('#p-details').value=p?.details||'';
  $('#persona-save').textContent=p?'Save changes':'Save persona';
}

async function openPersonaModal(){
  await renderPersonas();
  $('#persona-modal').classList.remove('hidden');
}

async function renderPersonas(){
  const list=await api('/api/personas');
  state.personas=list;
  syncPersonaSelectors();
  const box=$('#persona-list');
  box.innerHTML='';
  if(!list.length){
    box.appendChild(el('div','empty-list','No personas yet. Create one below.'));
    clearPersonaForm();
    return;
  }
  list.forEach(p=>{
    const row=el('div','persona-row');
    const left=el('div','persona-row-main');
    const avatar=el('div','persona-avatar',(p.name?.[0]||'?').toUpperCase());
    if(p.avatar_path){avatar.style.backgroundImage=`url("${p.avatar_path}")`;avatar.textContent='';}
    const info=el('div','persona-row-info');
    info.append(el('strong',null,p.name));
    info.append(el('span','muted',p.description||'No description'));
    left.append(avatar,info);
    const actions=el('div','row-actions');
    const use=el('button','mini',p.id==state.activePersonaId?'✓':'Use');
    use.onclick=async()=>{state.activePersonaId=p.id;syncPersonaSelectors();await updateActiveConversationPersona();renderPersonas();};
    const edit=el('button','mini','Edit');
    edit.onclick=()=>fillPersonaForm(p);
    const del=el('button','mini danger','Delete');
    del.onclick=async()=>{
      if(!confirm(`Delete persona "${p.name}"?`))return;
      await api(`/api/personas/${p.id}`,{method:'DELETE'});
      if(state.activePersonaId==p.id)state.activePersonaId=null;
      await loadPersonas();
      renderPersonas();
    };
    actions.append(use,edit,del);
    row.append(left,actions);box.appendChild(row);
  });
}

async function savePersona(){
  const payload={
    name:$('#p-name').value.trim(),avatar_path:$('#p-avatar').value.trim(),description:$('#p-description').value.trim(),
    pronouns:$('#p-pronouns').value.trim(),age:$('#p-age').value.trim(),appearance:$('#p-appearance').value.trim(),
    personality:$('#p-personality').value.trim(),speaking_style:$('#p-style').value.trim(),background:$('#p-background').value.trim(),details:$('#p-details').value.trim()
  };
  if(!payload.name){alert('Persona name is required');return;}
  const id=$('#p-edit-id').value;
  try{
    const saved=id?await api(`/api/personas/${id}`,{method:'PUT',body:JSON.stringify(payload)}):await api('/api/personas',{method:'POST',body:JSON.stringify(payload)});
    state.activePersonaId=saved.id;
    await loadPersonas();
    fillPersonaForm(saved);
    await renderPersonas();
  }catch(e){alert(`Could not save persona: ${e.message}`);}
}

async function updateActiveConversationPersona(){
  if(!state.activeConversationId)return;
  try{await api(`/api/conversations/${state.activeConversationId}`,{method:'PUT',body:JSON.stringify({persona_id:state.activePersonaId||null})});}
  catch(e){console.warn('Could not update conversation persona:',e);}
}

/* ========================= ASSISTANT ========================= */

async function createAssistantConversation(){
  const conv=await api('/api/assistant/conversations',{method:'POST',body:JSON.stringify({persona_id:state.activePersonaId||null,title:'newAIr Assistant'})});
  state.assistantConversationId=conv.id;
  await loadAssistantConversations();
  renderAssistantMessages(await api(`/api/assistant/conversations/${conv.id}/messages`));
}

async function loadAssistantConversations(){
  const list=await api('/api/assistant/conversations');
  const box=$('#assistant-conversation-list');box.innerHTML='';
  list.forEach(c=>{
    const r=el('div','conversation-item',c.title||`Chat #${c.id}`);
    r.classList.toggle('active',c.id===state.assistantConversationId);
    r.onclick=async()=>{state.assistantConversationId=c.id;renderAssistantMessages(await api(`/api/assistant/conversations/${c.id}/messages`));loadAssistantConversations();};
    box.appendChild(r);
  });
  if(!state.assistantConversationId && list.length){state.assistantConversationId=list[0].id;renderAssistantMessages(await api(`/api/assistant/conversations/${list[0].id}/messages`));}
}

function renderAssistantMessages(ms){const box=$('#assistant-messages');box.innerHTML='';ms.forEach(m=>box.appendChild(renderMessageBubble(m)));box.scrollTop=box.scrollHeight;}

async function sendAssistant(){
  const input=$('#assistant-input'),text=input.value.trim();if(!text||state.streaming)return;
  if(!state.assistantConversationId)await createAssistantConversation();
  $('#assistant-messages').appendChild(renderMessageBubble({role:'user',content:text}));input.value='';autoGrow(input);
  await streamInto(`/api/assistant/conversations/${state.assistantConversationId}/chat`,{message:text},'#assistant-messages');
}

/* ========================= CHARACTERS ========================= */

async function loadCharacters(){
  state.characters=await api('/api/characters');
  const list=$('#character-list');list.innerHTML='';
  if(!state.characters.length){list.appendChild(el('div','empty-list','No characters yet. Click + to create one.'));return;}
  state.characters.forEach(c=>{
    const r=el('div','char-item');
    const av=el('div','char-avatar',(c.name?.[0]||'?').toUpperCase());
    if(c.avatar_path){av.style.backgroundImage=`url("${c.avatar_path}")`;av.textContent='';}
    const info=el('div','char-item-info');info.append(el('div','char-item-name',c.name));
    if(c.description)info.append(el('div','char-item-desc',c.description));
    if(c.tags)info.append(el('div','char-tags',c.tags));
    const edit=el('button','mini','Edit');edit.onclick=e=>{e.stopPropagation();openCharModal(c);};
    r.append(av,info,edit);r.onclick=()=>selectCharacter(c);list.appendChild(r);
  });
}

async function selectCharacter(c){
  state.activeCharacter=c;updateCharacterHeader();showMode('characters');
  try{
    const convs=await api(`/api/characters/${c.id}/conversations`);
    if(convs.length)await openCharacterConversation(convs[0].id);else await startCharacterConversation();
  }catch(e){alert(`Could not open character: ${e.message}`);}
}

function updateCharacterHeader(){
  const c=state.activeCharacter;if(!c)return;
  $('#chat-char-name').textContent=c.name;
  const av=$('#chat-char-avatar');
  if(av){av.textContent=c.avatar_path?'':(c.name?.[0]||'?').toUpperCase();av.style.backgroundImage=c.avatar_path?`url("${c.avatar_path}")`:'';}
}

async function startCharacterConversation(){
  if(!state.activeCharacter){alert('Select a character first');return;}
  const conv=await api(`/api/characters/${state.activeCharacter.id}/conversations`,{method:'POST',body:JSON.stringify({persona_id:state.activePersonaId||null})});
  await openCharacterConversation(conv.id);
}

async function openCharacterConversation(id){
  state.activeConversationId=id;
  const conv=await api(`/api/conversations/${id}`);
  state.activePersonaId=conv.persona_id||null;
  syncPersonaSelectors();
  $('#chat-conv-title').textContent=conv.title||`Chat #${id}`;
  renderMessages(await api(`/api/conversations/${id}/messages`));
}

function renderMessages(ms){const box=$('#messages');box.innerHTML='';ms.forEach(m=>box.appendChild(renderMessageBubble(m)));box.scrollTop=box.scrollHeight;}

/* ========================= CHARACTER EDITOR ========================= */

function setEditorTab(tab){
  $$('.editor-tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
  $$('.editor-section').forEach(s=>s.classList.toggle('hidden',s.id!==tab));
}

function parseInitialMessages(c){
  let a=[];
  try{a=JSON.parse(c?.initial_messages||'[]')}catch{}
  if(!Array.isArray(a))a=[];
  if(!a.length&&c?.greeting)a=[c.greeting];
  return a.slice(0,10);
}
function renderInitialMessages(items=[]){
  const box=$('#initial-messages-list'); if(!box)return; box.innerHTML='';
  const values=(items.length?items:['']).slice(0,10);
  values.forEach((value,i)=>{
    const row=el('div','initial-message-row');
    const head=el('div','initial-message-head'); head.append(el('span',null,`Message ${i+1}`));
    const remove=el('button','mini','Remove'); remove.type='button'; remove.onclick=()=>{row.remove(); renumberInitialMessages();}; head.appendChild(remove);
    const ta=document.createElement('textarea'); ta.rows=5; ta.className='initial-message-input'; ta.placeholder='{{char}} greets {{user}}…'; ta.value=value||'';
    row.append(head,ta); box.appendChild(row);
  });
  renumberInitialMessages();
}
function renumberInitialMessages(){
  $$('.initial-message-row').forEach((row,i)=>{const h=row.querySelector('.initial-message-head span');if(h)h.textContent=`Message ${i+1}`;});
}
function addInitialMessage(){
  const box=$('#initial-messages-list'); if(!box)return; const count=box.querySelectorAll('.initial-message-row').length; if(count>=10)return;
  const vals=[...box.querySelectorAll('.initial-message-input')].map(x=>x.value); vals.push(''); renderInitialMessages(vals); box.querySelector('.initial-message-row:last-child textarea')?.focus();
}
function openCharModal(c=null){
  state.editingCharId=c?.id||null;
  $('#char-modal-title').textContent=c?'Edit Character':'New Character';
  $('#f-name').value=c?.name||'';$('#f-avatar').value=c?.avatar_path||'';$('#f-description').value=c?.description||'';$('#f-tags').value=c?.tags||'';$('#f-creator-notes').value=c?.creator_notes||'';
  $('#f-personality').value=c?.personality||'';$('#f-scenario').value=c?.scenario||'';$('#f-example').value=c?.example_dialogue||'';$('#f-system').value=c?.system_prompt||'';
  $('#f-appearance').value=c?.appearance||'';$('#f-background').value=c?.background||'';$('#f-visual-style').value=c?.visual_style||'';$('#f-negative-prompt').value=c?.negative_prompt||'';$('#f-preferred-lora').value=c?.preferred_lora||'';$('#f-image-preset').value=c?.image_preset||'balanced';
  renderInitialMessages(parseInitialMessages(c));
  $('#char-delete-btn').classList.toggle('hidden',!c);setEditorTab('char-general');$('#char-modal').classList.remove('hidden');
}

async function saveCharacter(){
  const initial_messages=[...document.querySelectorAll('.initial-message-input')].map(x=>x.value.trim()).filter(Boolean).slice(0,10);
  const payload={name:$('#f-name').value.trim(),avatar_path:$('#f-avatar').value.trim(),description:$('#f-description').value.trim(),tags:$('#f-tags').value.trim(),creator_notes:$('#f-creator-notes').value.trim(),personality:$('#f-personality').value.trim(),appearance:$('#f-appearance').value.trim(),background:$('#f-background').value.trim(),visual_style:$('#f-visual-style').value.trim(),negative_prompt:$('#f-negative-prompt').value.trim(),preferred_lora:$('#f-preferred-lora').value.trim(),image_preset:$('#f-image-preset').value,scenario:$('#f-scenario').value.trim(),greeting:initial_messages[0]||'',initial_messages,example_dialogue:$('#f-example').value.trim(),system_prompt:$('#f-system').value.trim()};
  if(!payload.name){alert('Character name is required');return;}
  try{
    let saved;
    if(state.editingCharId)saved=await api(`/api/characters/${state.editingCharId}`,{method:'PUT',body:JSON.stringify(payload)});
    else saved=await api('/api/characters',{method:'POST',body:JSON.stringify(payload)});
    $('#char-modal').classList.add('hidden');await loadCharacters();
    if(state.activeCharacter&&state.editingCharId===state.activeCharacter.id){state.activeCharacter=saved;updateCharacterHeader();}
  }catch(e){alert(`Could not save character: ${e.message}`);}
}

async function generatePortraitFromEditor(){
  const id=state.editingCharId;
  if(!id){alert('Save the character first, then generate its portrait.');return;}
  $('#char-modal')?.classList.add('hidden');
  state.activeCharacter=state.characters.find(c=>c.id==id)||state.activeCharacter;
  await openImageStudio();
  if($('#image-character-select'))$('#image-character-select').value=String(id);
  await generateCharacterImage();
}

async function deleteCharacter(){
  if(!state.editingCharId)return;
  const c=state.characters.find(x=>x.id==state.editingCharId);
  if(!confirm(`Delete "${c?.name||'this character'}" and its conversations?`))return;
  try{await api(`/api/characters/${state.editingCharId}`,{method:'DELETE'});$('#char-modal').classList.add('hidden');state.activeCharacter=null;state.activeConversationId=null;await loadCharacters();showMode('characters');}
  catch(e){alert(`Could not delete character: ${e.message}`);}
}

/* ========================= CHAT ========================= */

function escapeMessageHtml(text){
  return String(text ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;').replace(/'/g,'&#39;');
}
function formatRoleplayText(text){
  const safe=escapeMessageHtml(text);
  // newAIr roleplay format: *action* is italic; ordinary text is spoken dialogue.
  return safe.replace(/\*([^*\n]+)\*/g,'<em class="roleplay-action">$1</em>');
}
function setMessageContent(node,text){node.innerHTML=formatRoleplayText(text);}

function renderMessageBubble(m){
  const b=el('div',`msg ${m.role}`);setMessageContent(b,m.content||'');b.dataset.id=m.id||'';
  if(m.id&&m.role!=='system'){
    const a=el('div','msg-actions');
    const ed=el('button',null,'Edit');ed.onclick=()=>editMessage(b,m);
    const del=el('button',null,'Delete');del.onclick=()=>deleteMessage(b,m.id);
    a.append(ed,del);
    if(m.role==='assistant'){const more=el('button','generate-more-btn','▶ Generate more');more.onclick=async()=>{if(state.streaming)return; await streamInto(`/api/conversations/${state.activeConversationId}/continue`,{max_tokens:getResponseMaxTokens()},'#messages');};a.append(more);}
    b.appendChild(a);
  }
  return b;
}

async function editMessage(b,m){const ta=el('textarea');ta.value=m.content;ta.rows=4;b.replaceChildren(ta);ta.focus();const save=async()=>{const v=ta.value.trim();if(v&&v!==m.content){await api(`/api/messages/${m.id}`,{method:'PUT',body:JSON.stringify({content:v})});m.content=v;}b.replaceWith(renderMessageBubble(m));};ta.addEventListener('blur',save,{once:true});ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ta.blur();}});}
async function deleteMessage(b,id){try{await api(`/api/messages/${id}`,{method:'DELETE'});b.remove();}catch(e){alert(e.message);}}
function setBusy(v){state.streaming=v;['#send-btn','#regen-btn','#continue-btn','#assistant-send'].forEach(s=>{if($(s))$(s).disabled=v;});}
function getResponseMaxTokens(){const mode=localStorage.getItem('newair_response_length')||'standard';const map={short:180,standard:350,long:650,very_long:1000};if(mode==='custom'){const n=Number(localStorage.getItem('newair_custom_response_tokens')||400);return Math.max(64,Math.min(2048,Math.round(n/16)*16));}return map[mode]||350;}
function openChatSettings(){const mode=localStorage.getItem('newair_response_length')||'standard';$('#response-length').value=mode;$('#custom-response-wrap').classList.toggle('hidden',mode!=='custom');$('#custom-response-tokens').value=localStorage.getItem('newair_custom_response_tokens')||400;$('#chat-settings-modal').classList.remove('hidden');}
function saveChatSettings(){const mode=$('#response-length').value;let n=Math.max(64,Math.min(2048,Number($('#custom-response-tokens').value)||400));localStorage.setItem('newair_response_length',mode);localStorage.setItem('newair_custom_response_tokens',String(n));$('#chat-settings-modal').classList.add('hidden');}
async function streamInto(path,body,selector){
  const box=$(selector),b=el('div','msg assistant streaming','');box.appendChild(b);box.scrollTop=box.scrollHeight;setBusy(true);
  try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});if(!r.ok||!r.body)throw new Error(`request failed: ${r.status} ${await r.text().catch(()=> '')}`);const reader=r.body.getReader(),dec=new TextDecoder();let buf='',full='';while(true){const {value,done}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;while((i=buf.indexOf('\n\n'))>=0){const raw=buf.slice(0,i);buf=buf.slice(i+2);const line=raw.replace(/^data:\s*/,'');if(!line)continue;let p;try{p=JSON.parse(line)}catch{continue}if(p.delta){full+=p.delta;setMessageContent(b,full);box.scrollTop=box.scrollHeight}else if(p.error){setMessageContent(b,`[error: ${p.error}]`);}}}b.classList.remove('streaming');}
  catch(e){setMessageContent(b,`[connection error: ${e.message}]`);b.classList.remove('streaming');}
  finally{setBusy(false);}
}
async function sendCharacter(){const input=$('#composer-input'),text=input.value.trim();if(!text||state.streaming||!state.activeConversationId)return;$('#messages').appendChild(renderMessageBubble({role:'user',content:text}));input.value='';autoGrow(input);await streamInto(`/api/conversations/${state.activeConversationId}/chat`,{message:text,max_tokens:getResponseMaxTokens()},'#messages');}
async function regenerate(){if(!state.activeConversationId||state.streaming)return;const last=$('#messages .msg.assistant:last-of-type');if(last)last.remove();await streamInto(`/api/conversations/${state.activeConversationId}/regenerate`,{max_tokens:getResponseMaxTokens()},'#messages');}
async function continueReply(){if(!state.activeConversationId||state.streaming)return;await streamInto(`/api/conversations/${state.activeConversationId}/continue`,{max_tokens:getResponseMaxTokens()},'#messages');}
function autoGrow(t){t.style.height='auto';t.style.height=Math.min(180,t.scrollHeight)+'px';}

/* ========================= LORE / MEMORY ========================= */
async function openLoreModal(){if(!state.activeCharacter)return;try{const es=await api(`/api/characters/${state.activeCharacter.id}/lorebook`),box=$('#lore-list');box.innerHTML='';es.forEach(e=>{const r=el('div','list-row',`${e.title} [${e.keywords.join(', ')}]`);const d=el('button',null,'Delete');d.onclick=async()=>{await api(`/api/characters/lorebook/${e.id}`,{method:'DELETE'});openLoreModal();};r.appendChild(d);box.appendChild(r);});$('#lore-modal').classList.remove('hidden');}catch(e){alert(e.message);}}
async function addLore(){const title=$('#lore-title').value.trim(),keywords=$('#lore-keywords').value.split(',').map(x=>x.trim()).filter(Boolean),content=$('#lore-content').value.trim();if(!title||!keywords.length||!content){alert('Fill title, keywords and content');return;}await api(`/api/characters/${state.activeCharacter.id}/lorebook`,{method:'POST',body:JSON.stringify({title,keywords,content})});$('#lore-title').value='';$('#lore-keywords').value='';$('#lore-content').value='';openLoreModal();}
async function openMemoryModal(){if(!state.activeCharacter)return;const fs=await api(`/api/characters/${state.activeCharacter.id}/memories`),box=$('#memory-list');box.innerHTML='';fs.forEach(f=>box.appendChild(el('div','list-row',f.fact)));$('#memory-modal').classList.remove('hidden');}
async function addMemory(){const fact=$('#memory-fact').value.trim();if(!fact)return;await api(`/api/characters/${state.activeCharacter.id}/memories`,{method:'POST',body:JSON.stringify({fact})});$('#memory-fact').value='';openMemoryModal();}

/* ========================= PROFILE IMAGE CROP ========================= */
function openCropModal(url, characterId=null){
  if(!url){alert('No image selected to crop.');return;}
  const modal=$('#crop-modal'),img=$('#crop-source');
  cropState.sourceUrl=url;cropState.targetCharacterId=characterId?Number(characterId):null;cropState.scale=1;cropState.x=0;cropState.y=0;cropState.dragging=false;
  img.onload=()=>{fitCropImage();renderCrop();};
  img.src=url+(url.includes('?')?'&':'?')+'crop='+Date.now();
  $('#crop-zoom').value='1';modal.classList.remove('hidden');
}
function fitCropImage(){
  const stage=$('#crop-stage'),img=$('#crop-source');if(!stage||!img.naturalWidth)return;
  const w=stage.clientWidth,h=stage.clientHeight;
  cropState.baseScale=Math.max(w/img.naturalWidth,h/img.naturalHeight);
  cropState.scale=1;cropState.x=0;cropState.y=0;
}
function renderCrop(){
  const img=$('#crop-source');if(!img)return;
  const stage=$('#crop-stage');const w=stage.clientWidth,h=stage.clientHeight;
  const scale=cropState.baseScale*cropState.scale;
  const iw=img.naturalWidth*scale,ih=img.naturalHeight*scale;
  const maxX=Math.max(0,(iw-w)/2),maxY=Math.max(0,(ih-h)/2);
  cropState.x=Math.max(-maxX,Math.min(maxX,cropState.x));cropState.y=Math.max(-maxY,Math.min(maxY,cropState.y));
  img.style.width=iw+'px';img.style.height=ih+'px';img.style.left=`calc(50% + ${cropState.x}px)`;img.style.top=`calc(50% + ${cropState.y}px)`;
}
function cropPointerDown(e){const img=$('#crop-source');if(!img||img.classList.contains('hidden'))return;cropState.dragging=true;cropState.startX=e.clientX-cropState.x;cropState.startY=e.clientY-cropState.y;img.setPointerCapture?.(e.pointerId);}
function cropPointerMove(e){if(!cropState.dragging)return;cropState.x=e.clientX-cropState.startX;cropState.y=e.clientY-cropState.startY;renderCrop();}
function cropPointerUp(){cropState.dragging=false;}
function resetCrop(){cropState.scale=1;cropState.x=0;cropState.y=0;$('#crop-zoom').value='1';renderCrop();}
async function applyCrop(){
  const src=$('#crop-source');const stage=$('#crop-stage');if(!src.naturalWidth)return;
  const size=512,canvas=document.createElement('canvas');canvas.width=size;canvas.height=size;const ctx=canvas.getContext('2d');
  const scale=cropState.baseScale*cropState.scale;const stageW=stage.clientWidth,stageH=stage.clientHeight;
  const left=(stageW-(src.naturalWidth*scale))/2+cropState.x;const top=(stageH-(src.naturalHeight*scale))/2+cropState.y;
  const ratio=size/stageW;
  ctx.fillStyle='#111';ctx.fillRect(0,0,size,size);
  ctx.drawImage(src,left*ratio,top*ratio,src.naturalWidth*scale*ratio,src.naturalHeight*scale*ratio);
  try{
    const saved=await api('/api/characters/avatar/crop',{method:'POST',body:JSON.stringify({data_url:canvas.toDataURL('image/png')})});
    if(cropState.targetCharacterId){
      const character=state.characters.find(c=>c.id===cropState.targetCharacterId);
      if(character){const updated=await api(`/api/characters/${character.id}`,{method:'PUT',body:JSON.stringify({avatar_path:saved.url})});state.activeCharacter=state.activeCharacter?.id===character.id?updated:state.activeCharacter;await loadCharacters();populateImageCharacterSelect();if(state.activeCharacter?.id===character.id)updateCharacterHeader();setStatus(`Avatar updated for ${character.name}.`);}
    } else if($('#f-avatar') && !$('#char-modal').classList.contains('hidden')) {
      $('#f-avatar').value=saved.url;
    }
    $('#crop-modal').classList.add('hidden');
  }catch(e){alert(`Could not save cropped image: ${e.message}`);}
}

/* ========================= MODELS / IMAGES ========================= */
async function openModelModal(){try{const info=await api('/api/models');$('#models-dir-path').textContent=info.models_dir||'';$('#model-loaded').textContent=info.llama_cpp_installed?`GPU layers: ${info.gpu_layers} · Context: ${info.context_tokens} · Loaded: ${info.loaded||'none'}`:`AI engine error: ${info.llama_cpp_error||'llama-cpp-python unavailable'}`;const box=$('#model-list');box.innerHTML='';(info.available||[]).forEach(f=>{const r=el('div','list-row',f);const b=el('button',null,'Load');b.onclick=async()=>{b.disabled=true;$('#model-loaded').textContent=`Loading ${f}…`;try{const result=await api('/api/models/load',{method:'POST',body:JSON.stringify({filename:f})});$('#model-loaded').textContent=result.message||`Loaded: ${result.loaded||f}`;}catch(e){$('#model-loaded').textContent=`Load failed: ${e.message}`;}finally{b.disabled=false;}};r.appendChild(b);box.appendChild(r);});if(!info.available?.length)box.appendChild(el('div','empty-list','No GGUF models found.'));$('#model-modal').classList.remove('hidden');}catch(e){alert(e.message);}}

/* ========================= IMAGE STUDIO PRO ========================= */
const imageState={quality:'balanced',aspect:'16:9',seedLocked:false,current:null,history:[],profiles:{},loras:[],studioTab:'character',sceneReady:false,img2imgSource:'',faceIdSource:'',img2imgPreset:'preserve',inpaintSource:'',inpaintImage:null,inpaintMask:null,inpaintDrawing:false,inpaintErase:false};
function bytesToGB(n){return n?`${(n/1073741824).toFixed(1)} GB`:"—";}
function setStudioTab(tab){
  imageState.studioTab=['normal','img2img','faceid','inpaint'].includes(tab)?tab:'character';
  $$('.studio-tab').forEach(b=>b.classList.toggle('active',b.dataset.studioTab===imageState.studioTab));
  $('#studio-character-panel')?.classList.toggle('hidden',imageState.studioTab!=='character');
  $('#studio-normal-panel')?.classList.toggle('hidden',imageState.studioTab!=='normal');
  $('#studio-img2img-panel')?.classList.toggle('hidden',imageState.studioTab!=='img2img');
  $('#studio-faceid-panel')?.classList.toggle('hidden',imageState.studioTab!=='faceid');
  $('#studio-inpaint-panel')?.classList.toggle('hidden',imageState.studioTab!=='inpaint');
  if(imageState.studioTab==='normal'){ $('#image-aspect').value='16:9'; populateAspect(); }
  else if(imageState.studioTab==='character' && !$('#image-prompt').value.trim()){ $('#image-aspect').value='3:4'; populateAspect(); }
  if(imageState.studioTab==='img2img') syncImg2ImgControls();
  if(imageState.studioTab==='inpaint') initInpaintCanvas();
}
function currentCharacter(){const id=Number($('#image-character-select')?.value||0);return state.characters.find(c=>c.id===id)||state.activeCharacter||null;}
function populateAspect(){const map={'1:1':[1,1],'4:3':[4,3],'3:4':[3,4],'16:9':[16,9],'9:16':[9,16],'21:9':[21,9]};const v=$('#image-aspect')?.value;if(!map[v])return;const [a,b]=map[v];let w=1024,h=Math.round(w*b/a);if(h<256){h=256;w=Math.round(h*a/b);}$('#image-width').value=Math.max(256,Math.round(w/8)*8);$('#image-height').value=Math.max(256,Math.round(h/8)*8);}
function applyQuality(q){imageState.quality=q;$$('.quality-btn').forEach(b=>b.classList.toggle('active',b.dataset.quality===q));const p=imageState.profile||{};const steps=q==='fast'?p.fast_steps||18:q==='high'?p.high_steps||36:p.balanced_steps||28;$('#image-steps').value=steps;$('#image-guidance').value=p.guidance||5.5;}
function renderSamplers(list){const s=$('#image-sampler');if(!s)return;s.innerHTML='';(list||[]).forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o);});s.value=imageState.profile?.sampler||list?.[0]||'DPM++ 2M Karras';}
function renderLoras(){const s=$('#image-lora-select');if(!s)return;s.innerHTML='';imageState.loras.forEach((n,i)=>{const o=document.createElement('option');o.value=n;o.textContent=n;s.appendChild(o);});}
function selectedLoras(){return [...($('#image-lora-select')?.selectedOptions||[])].map(o=>{const safe=o.value.replace(/[^a-zA-Z0-9_-]/g,'_');return {name:o.value,weight:Number($('#lora-weight-'+safe)?.value||.7)};});}
function renderLoraSliders(){const box=$('#lora-sliders');if(!box)return;box.innerHTML='';imageState.loras.forEach(n=>{const safe='lora-weight-'+n.replace(/[^a-zA-Z0-9_-]/g,'_');const row=el('div','lora-row');row.innerHTML=`<span title="${n}">${n}</span><input id="${safe}" type="range" min="0" max="1.5" value="0.7" step="0.05"><b>0.70</b>`;const r=row.querySelector('input'),b=row.querySelector('b');r.oninput=()=>b.textContent=Number(r.value).toFixed(2);box.appendChild(row);});}
function buildPromptFromFields(){const fields=[$('#prompt-subject')?.value,$('#prompt-environment')?.value,$('#prompt-lighting')?.value,$('#prompt-camera')?.value].map(x=>x?.trim()).filter(Boolean);if(fields.length)$('#image-prompt').value=fields.join(', ');updateTokenMeter();}
async function updateTokenMeter(){const text=$('#image-prompt')?.value||'';if(!text)return;try{const d=await api('/api/images/token-info',{method:'POST',body:JSON.stringify({text})});const pct=Math.min(100,Math.round(d.tokens/Math.max(1,d.limit)*100));$('#prompt-token-label').textContent=`Prompt tokens: ${d.tokens} / ${d.limit}${d.truncated?' · will be truncated':''}`;$('#prompt-token-bar').style.width=pct+'%';$('#prompt-token-bar').classList.toggle('warning',pct>85);}catch(e){}}
async function enhancePrompt(){const p=$('#image-prompt').value.trim();if(!p)return alert('Enter a prompt first.');const b=$('#enhance-prompt');b.disabled=true;setStatus('Dolphin is directing the prompt…');try{const d=await api('/api/images/enhance-prompt',{method:'POST',body:JSON.stringify({prompt:p})});$('#image-prompt').value=d.prompt;updateTokenMeter();setStatus('Prompt enhanced. If Dolphin was not already loaded, the image model may need to be reloaded.');}catch(e){setStatus(`Prompt enhancement failed: ${e.message}`);}finally{b.disabled=false;}}
async function buildCharacterPrompt(){const c=currentCharacter();if(!c)return alert('Select a character first.');const b=$('#build-character-prompt');if(b)b.disabled=true;setStatus('Dolphin is designing the character visually…');try{const d=await api(`/api/characters/${c.id}/image-prompt`,{method:'POST',body:JSON.stringify({ai:true})});$('#image-prompt').value=d.prompt||'';$('#image-negative').value=d.negative_prompt||'';selectPreferredLoras(d.loras);$('#image-aspect').value='3:4';populateAspect();applyQuality(d.preset||'balanced');updateTokenMeter();if($('#character-image-status'))$('#character-image-status').textContent=d.source==='llm'?'AI visual prompt created from the character definition.':'Used the local fallback prompt builder.';}catch(e){setStatus(`Character prompt failed: ${e.message}`);}finally{if(b)b.disabled=false;}}
function selectPreferredLoras(value){const wanted=String(value||'').split(',').map(x=>x.trim()).filter(Boolean);[...($('#image-lora-select')?.options||[])].forEach(o=>o.selected=wanted.includes(o.value));}
async function generateCharacterImage(){const c=currentCharacter();if(!c)return alert('Select a character first.');const b=$('#generate-character-image');if(b)b.disabled=true;setStatus(`Creating a visual prompt for ${c.name}…`);try{const d=await api(`/api/characters/${c.id}/image-prompt`,{method:'POST',body:JSON.stringify({ai:true})});$('#image-prompt').value=d.prompt||'';$('#image-negative').value=d.negative_prompt||'';selectPreferredLoras(d.loras);$('#image-aspect').value='3:4';populateAspect();applyQuality(d.preset||'balanced');updateTokenMeter();let status=await api('/api/images');if(!status.loaded){const model=$('#image-model-select')?.value;if(!model)throw new Error('No image model is available.');await loadImageModel();}setStatus(`Generating ${c.name}…`);const seed=Number($('#image-seed').value);const payload={prompt:d.prompt,negative_prompt:d.negative_prompt||'',width:Number($('#image-width').value),height:Number($('#image-height').value),steps:Number($('#image-steps').value),guidance:Number($('#image-guidance').value),seed,sampler:$('#image-sampler').value,quality:imageState.quality,batch:1,hires:$('#image-hires').checked,hires_scale:Number($('#hires-scale').value),hires_denoise:Number($('#hires-denoise').value),loras:selectedLoras(),character_id:c.id};const result=await api('/api/images/generate',{method:'POST',body:JSON.stringify(payload)});showGeneration(result.results?.[0]||result);if(!imageState.seedLocked&&seed<0)$('#image-seed').value=(result.results?.[0]||result).seed;setStatus(`${c.name} image generated.`);if($('#character-image-status'))$('#character-image-status').textContent='Image generated from the character definition. No extra prompt was required.';}catch(e){setStatus(`Character image failed: ${e.message}`);if($('#character-image-status'))$('#character-image-status').textContent=e.message;}finally{if(b)b.disabled=false;}}
function openSceneBuilder(){const c=currentCharacter();$('#scene-location').value='';$('#scene-time').value='';$('#scene-weather').value='';$('#scene-lighting').value='';$('#scene-action').value='';$('#scene-expression').value='';$('#scene-camera').value='';$('#scene-style').value='';if(c){$('#scene-style').value=c.visual_style||'';$('#scene-expression').value='';}$('#scene-modal').classList.remove('hidden');}
function buildScene(){const c=currentCharacter();if(!c)return alert('Select a character first.');const bits=[];if(c.appearance)bits.push(c.appearance);if(c.visual_style)bits.push(c.visual_style);[['Location','scene-location'],['Time','scene-time'],['Weather','scene-weather'],['Lighting','scene-lighting'],['Action','scene-action'],['Expression','scene-expression'],['Camera','scene-camera'],['Style','scene-style']].forEach(([label,id])=>{const v=$('#'+id)?.value.trim();if(v)bits.push(v);});$('#image-prompt').value=bits.join(', ');$('#image-aspect').value='16:9';populateAspect();imageState.sceneReady=true;$('#scene-modal').classList.add('hidden');updateTokenMeter();if($('#scene-image-status'))$('#scene-image-status').textContent='Scenario ready. Generate when you are happy with the setup.';}
function populateImageCharacterSelect(){
  const sel=$('#image-character-select');
  if(!sel)return;
  const current=sel.value;
  sel.innerHTML='';
  const placeholder=document.createElement('option');
  placeholder.value='';
  placeholder.textContent=state.characters.length?'Select a character…':'No characters found';
  sel.appendChild(placeholder);
  state.characters.filter(c=>Number(c.id)!==0).forEach(c=>{
    const o=document.createElement('option');
    o.value=String(c.id);
    o.textContent=c.name;
    sel.appendChild(o);
  });
  const preferred=state.activeCharacter?.id||current;
  if(preferred && state.characters.some(c=>String(c.id)===String(preferred))){
    sel.value=String(preferred);
  }
}
function syncCharacterToImage(c){if(!c)return;$('#image-character-select').value=String(c.id);}
function showGeneration(result){imageState.current=result;$('#generated-image').src=result.url+'?t='+Date.now();$('#generated-image').classList.remove('hidden');$('#image-placeholder').classList.add('hidden');$('#image-actions').classList.remove('hidden');const info=$('#generation-info');info.classList.remove('hidden');info.innerHTML=`<span>${result.model_family||''}</span><span>${result.width}×${result.height}</span><span>${result.steps||$('#image-steps').value} steps</span><span>${result.sampler||$('#image-sampler').value}</span><span>seed ${result.seed}</span><span>${result.generation_ms?((result.generation_ms/1000).toFixed(1)+'s'):''}</span>`;loadGallery();}
function setImg2ImgSource(dataUrl,label='Source image'){imageState.img2imgSource=dataUrl||'';const img=$('#img2img-source-thumb');if(dataUrl){img.src=dataUrl;img.classList.remove('hidden');$('#img2img-source-status').textContent=label;}else{img.removeAttribute('src');img.classList.add('hidden');$('#img2img-source-status').textContent='No source image selected.';}}
function syncImg2ImgControls(){const list=imageState.profile?.samplers||['DPM++ 2M Karras','DPM++ SDE Karras','Euler A','Euler','DDIM','UniPC'];const s=$('#img2img-sampler');if(!s)return;s.innerHTML='';list.forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o);});s.value=imageState.profile?.sampler||list[0];}
function setImg2ImgPreset(preset){const map={preserve:{strength:.28,steps:24,guidance:5.0,help:'Keeps the source composition, identity and details as stable as possible.'},balanced:{strength:.45,steps:26,guidance:5.0,help:'Changes the requested elements while preserving the main structure of the source.'},creative:{strength:.65,steps:30,guidance:5.5,help:'Allows stronger visual changes. Expect more regeneration of faces, clothing and background.'}};const v=map[preset]||map.preserve;imageState.img2imgPreset=preset;$$('.img2img-preset').forEach(b=>b.classList.toggle('active',b.dataset.img2imgPreset===preset));$('#img2img-strength').value=v.strength;$('#img2img-strength-value').textContent=v.strength.toFixed(2);$('#img2img-steps').value=v.steps;$('#img2img-guidance').value=v.guidance;$('#img2img-strength-help').textContent=v.help;}
function readFileAsDataUrl(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(new Error('Could not read the image.'));r.readAsDataURL(file);});}
async function handleImg2ImgFile(file){if(!file)return;if(!/^image\/(png|jpeg|webp)$/.test(file.type))return alert('Please choose a PNG, JPG or WebP image.');if(file.size>15*1024*1024)return alert('Please keep the source image under 15 MB.');try{setImg2ImgSource(await readFileAsDataUrl(file),`${file.name} · ${(file.size/1048576).toFixed(1)} MB`);}catch(e){setImg2ImgSource('');setStatus(e.message);}}
async function useCurrentForImg2Img(){const src=imageState.current?.url||$('#generated-image')?.getAttribute('src')?.split('?')[0];if(!src)return alert('Generate an image first, or upload one.');try{const r=await fetch(src);const b=await r.blob();setImg2ImgSource(await readFileAsDataUrl(b),'Current generated image');setStudioTab('img2img');}catch(e){setStatus(`Could not use current image: ${e.message}`);}}
function clearImg2Img(){imageState.img2imgSource='';setImg2ImgSource('');$('#img2img-prompt').value='';$('#img2img-negative').value='';}
async function optimizeImg2ImgPrompt(){const p=$('#img2img-prompt').value.trim();if(!p)return alert('Enter an edit instruction first.');const b=$('#img2img-optimize');b.disabled=true;setStatus('Dolphin is simplifying the edit instruction…');try{const d=await api('/api/images/enhance-prompt',{method:'POST',body:JSON.stringify({prompt:p,mode:'edit'})});$('#img2img-prompt').value=d.prompt||p;setStatus('Edit instruction optimized.');}catch(e){setStatus(`Prompt optimization failed: ${e.message}`);}finally{b.disabled=false;}}
function handleFaceIdFile(file){if(!file)return;readFileAsDataUrl(file).then(d=>{imageState.faceIdSource=d;const img=$('#faceid-source-thumb');img.src=d;img.classList.remove('hidden');$('#faceid-source-status').textContent=file.name;}).catch(e=>$('#faceid-status').textContent=e.message);}
async function refreshFaceIdStatus(){try{const [d,info]=await Promise.all([api('/api/images/faceid/status'),api('/api/images')]);const sel=$('#faceid-model');if(sel){const current=sel.value;sel.innerHTML='';(info.models||[]).forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;const low=m.toLowerCase();const family=(low.includes('realisticvision')||low.includes('v60b1')||low.includes('v51vae'))?'SD 1.5':(low.includes('pony')?'Pony/SDXL':'SDXL');const ready=family==='SD 1.5'?d.sd15_ready:d.sdxl_ready;o.disabled=!ready;o.textContent+=ready?'':'  (FaceID adapter needed)';sel.appendChild(o);});if(current&&[...sel.options].some(o=>o.value===current&&!o.disabled))sel.value=current;else{const first=[...sel.options].find(o=>!o.disabled);if(first)sel.value=first.value;}updateFaceIdModelHelp(d);}const missing=[];if(!d.image_encoder)missing.push('CLIP image encoder');if(!d.insightface_installed)missing.push('InsightFace');if(!d.sd15_ready)missing.push('SD1.5 FaceID adapter');if(!d.sdxl_ready)missing.push('SDXL FaceID adapter');$('#faceid-setup-status').textContent=(d.sd15_ready||d.sdxl_ready)?'FaceID Plus V2 is ready. Choose a compatible generation model above.':`Setup needed: ${missing.join(', ')}. See FACEID_SETUP.md.`;}catch(e){$('#faceid-setup-status').textContent='Could not check FaceID setup.';}}
function updateFaceIdModelHelp(d){const sel=$('#faceid-model');const o=sel?.selectedOptions?.[0];if(!o)return;$('#faceid-model-help').textContent=o.disabled?'This model needs the matching SDXL FaceID Plus V2 adapter files.':'FaceID will generate with the selected base model.';}
async function runFaceToScene(){if(!imageState.faceIdSource)return alert('Choose a face reference first.');const prompt=$('#faceid-prompt').value.trim();if(!prompt)return alert('Describe the scene you want.');const model=$('#faceid-model')?.value;if(!model)return alert('Choose a compatible generation model first.');const b=$('#faceid-generate');b.disabled=true;$('#faceid-status').textContent='Extracting identity and generating with '+model+'…';try{const d=await api('/api/images/face-to-scene',{method:'POST',body:JSON.stringify({prompt,negative_prompt:$('#faceid-negative').value.trim(),image_data:imageState.faceIdSource,identity_strength:Number($('#faceid-strength').value),steps:Number($('#faceid-steps').value),guidance:Number($('#faceid-guidance').value),seed:Number($('#faceid-seed').value),style:$('#faceid-style').value,width:Number($('#faceid-width').value),height:Number($('#faceid-height').value),model_name:model,parent_id:imageState.current?.id||null})});showGeneration(d);if(Number($('#faceid-seed').value)<0)$('#faceid-seed').value=d.seed;$('#faceid-status').textContent=`Generated ${d.width}×${d.height} with ${d.model} + FaceID Plus V2.`;}catch(e){$('#faceid-status').textContent=`Face → Full Scene failed: ${e.message}`;}finally{b.disabled=false;}}
async function runImg2ImgOutpaint(){
  if(!imageState.img2imgSource)return alert('Choose a source image first.');
  const prompt=$('#img2img-prompt').value.trim()||'full body, natural anatomy, complete legs and feet, matching the original person, lighting and camera';
  const b=$('#img2img-outpaint'); b.disabled=true; $('#img2img-status').textContent='Extending the canvas and generating the missing area…';
  try{const d=await api('/api/images/outpaint',{method:'POST',body:JSON.stringify({prompt,image_data:imageState.img2imgSource,direction:'down',pixels:512,steps:30,guidance:5.2,seed:Number($('#img2img-seed').value),sampler:$('#img2img-sampler').value,style:$('#img2img-style').value,parent_id:imageState.current?.id||null})});showGeneration(d);if(Number($('#img2img-seed').value)<0)$('#img2img-seed').value=d.seed;$('#img2img-status').textContent=`Extended to ${d.width}×${d.height}. Original pixels were preserved.`;}catch(e){$('#img2img-status').textContent=`Full-body extension failed: ${e.message}`;}finally{b.disabled=false;}}

async function runImg2Img(){if(!imageState.img2imgSource)return alert('Choose a source image first.');const prompt=$('#img2img-prompt').value.trim();if(!prompt)return alert('Describe what you want changed.');const b=$('#img2img-generate');b.disabled=true;setStatus('Applying a controlled image edit…');$('#img2img-status').textContent='Keeping the source stable while applying your instruction.';try{const d=await api('/api/images/img2img',{method:'POST',body:JSON.stringify({prompt,negative_prompt:$('#img2img-negative').value.trim(),image_data:imageState.img2imgSource,strength:Number($('#img2img-strength').value),steps:Number($('#img2img-steps').value),guidance:Number($('#img2img-guidance').value),seed:Number($('#img2img-seed').value),sampler:$('#img2img-sampler').value,loras:selectedLoras(),style:$('#img2img-style').value,edit_mode:$('#img2img-edit-mode').value})});showGeneration(d);if(Number($('#img2img-seed').value)<0)$('#img2img-seed').value=d.seed;setStatus('Image edit completed.');$('#img2img-status').textContent=`Created ${d.width}×${d.height} using ${d.model_family||'local diffusion'}.`;}catch(e){setStatus(`Image edit failed: ${e.message}`);$('#img2img-status').textContent=e.message;}finally{b.disabled=false;}}

function setInpaintSource(dataUrl,label='Source image'){
  imageState.inpaintSource=dataUrl||''; imageState.inpaintImage=null; imageState.inpaintMask=null;
  const canvas=$('#inpaint-canvas'); if(canvas){canvas.width=1;canvas.height=1;}
  const status=$('#inpaint-status'); if(status) status.textContent=dataUrl?label:'No source image selected.';
  if(dataUrl){const img=new Image();img.onload=()=>{imageState.inpaintImage=img;initInpaintCanvas();};img.src=dataUrl;}
}
function initInpaintCanvas(){
  const c=$('#inpaint-canvas'), img=imageState.inpaintImage; if(!c||!img)return;
  const maxW=900,maxH=600,scale=Math.min(1,maxW/img.naturalWidth,maxH/img.naturalHeight);c.width=Math.max(1,Math.round(img.naturalWidth*scale));c.height=Math.max(1,Math.round(img.naturalHeight*scale));
  const ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);
  imageState.inpaintMask=document.createElement('canvas');imageState.inpaintMask.width=c.width;imageState.inpaintMask.height=c.height;const m=imageState.inpaintMask.getContext('2d');m.fillStyle='black';m.fillRect(0,0,c.width,c.height);
}
function inpaintPoint(e){const c=$('#inpaint-canvas');if(!c||!imageState.inpaintMask)return;const r=c.getBoundingClientRect(),x=(e.clientX-r.left)*c.width/r.width,y=(e.clientY-r.top)*c.height/r.height;const m=imageState.inpaintMask.getContext('2d'),v=Number($('#inpaint-brush').value||48);m.fillStyle=imageState.inpaintErase?'black':'white';m.beginPath();m.arc(x,y,v/2,0,Math.PI*2);m.fill();drawInpaintCanvas();}
function drawInpaintCanvas(){const c=$('#inpaint-canvas'),img=imageState.inpaintImage,mask=imageState.inpaintMask;if(!c||!img||!mask)return;const ctx=c.getContext('2d');ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(img,0,0,c.width,c.height);ctx.globalAlpha=.38;ctx.fillStyle='#ff3355';const m=mask.getContext('2d').getImageData(0,0,mask.width,mask.height).data;const overlay=document.createElement('canvas');overlay.width=mask.width;overlay.height=mask.height;const o=overlay.getContext('2d'),od=o.createImageData(mask.width,mask.height);for(let i=0;i<m.length;i+=4){const a=m[i]*.62;od.data[i]=255;od.data[i+1]=40;od.data[i+2]=80;od.data[i+3]=a;}o.putImageData(od,0,0);ctx.drawImage(overlay,0,0);ctx.globalAlpha=1;}
function clearInpaintMask(){if(!imageState.inpaintMask)return;const m=imageState.inpaintMask.getContext('2d');m.fillStyle='black';m.fillRect(0,0,imageState.inpaintMask.width,imageState.inpaintMask.height);drawInpaintCanvas();}
function fillInpaintMask(){if(!imageState.inpaintMask)return;const m=imageState.inpaintMask.getContext('2d');m.fillStyle='white';m.fillRect(0,0,imageState.inpaintMask.width,imageState.inpaintMask.height);drawInpaintCanvas();}
function clearInpaint(){imageState.inpaintSource='';imageState.inpaintImage=null;imageState.inpaintMask=null;const c=$('#inpaint-canvas');if(c){c.width=1;c.height=1;}$('#inpaint-prompt').value='';$('#inpaint-negative').value='';$('#inpaint-status').textContent='No source image selected.';}
async function handleInpaintFile(file){if(!file)return;if(!/^image\/(png|jpeg|webp)$/.test(file.type))return alert('Please choose a PNG, JPG or WebP image.');if(file.size>15*1024*1024)return alert('Please keep the source image under 15 MB.');setInpaintSource(await readFileAsDataUrl(file),`${file.name} · ${(file.size/1048576).toFixed(1)} MB`);}
async function useCurrentForInpaint(){const src=imageState.current?.url||$('#generated-image')?.getAttribute('src')?.split('?')[0];if(!src)return alert('Generate an image first, or upload one.');try{const r=await fetch(src);const b=await r.blob();setInpaintSource(await readFileAsDataUrl(b),'Current generated image');setStudioTab('inpaint');}catch(e){setStatus(`Could not use current image: ${e.message}`);}}
async function optimizeInpaintPrompt(){const p=$('#inpaint-prompt').value.trim();if(!p)return alert('Enter an edit instruction first.');const b=$('#inpaint-optimize');b.disabled=true;try{const d=await api('/api/images/enhance-prompt',{method:'POST',body:JSON.stringify({prompt:p,mode:'edit'})});$('#inpaint-prompt').value=d.prompt||p;}catch(e){setStatus(`Prompt optimization failed: ${e.message}`);}finally{b.disabled=false;}}
async function refreshInpaintStatus(){try{const d=await api('/api/images/inpaint/status');$('#inpaint-model-status').textContent=d.available?`Ready: ${d.model}${d.loaded?' · loaded':''}`:'Model missing. Put sd-v1-5-inpainting.ckpt in image_models\\inpainting.';}catch(e){$('#inpaint-model-status').textContent=e.message;}}
function applyInpaintQuality(){const q=$('#inpaint-quality')?.value||'balanced';const presets={precise:{steps:34,guidance:5,padding:96,feather:3,expand:8},balanced:{steps:30,guidance:5.5,padding:96,feather:4,expand:8},creative:{steps:36,guidance:6,padding:128,feather:6,expand:12}};const p=presets[q]||presets.balanced;$('#inpaint-steps').value=p.steps;$('#inpaint-guidance').value=p.guidance;$('#inpaint-padding').value=p.padding;$('#inpaint-feather').value=p.feather;$('#inpaint-expand').value=p.expand;}
async function runInpaint(){if(!imageState.inpaintImage||!imageState.inpaintMask)return alert('Choose a source image first.');const prompt=$('#inpaint-prompt').value.trim();if(!prompt)return alert('Describe what should appear in the masked area.');const b=$('#inpaint-generate');b.disabled=true;$('#inpaint-status').textContent='Loading the dedicated inpainting model and rendering the masked region…';try{const maskData=imageState.inpaintMask.toDataURL('image/png');const d=await api('/api/images/inpaint',{method:'POST',body:JSON.stringify({prompt,negative_prompt:$('#inpaint-negative').value.trim(),image_data:imageState.inpaintSource,mask_data:maskData,steps:Number($('#inpaint-steps').value),guidance:Number($('#inpaint-guidance').value),padding:Number($('#inpaint-padding').value),feather:Number($('#inpaint-feather').value),mask_expand:Number($('#inpaint-expand').value),seed:Number($('#inpaint-seed').value),sampler:$('#inpaint-sampler').value,parent_id:imageState.current?.id||null})});showGeneration(d);if(Number($('#inpaint-seed').value)<0)$('#inpaint-seed').value=d.seed;$('#inpaint-status').textContent=`Inpaint complete · ${d.width}×${d.height} · ${d.model_family}`;}catch(e){$('#inpaint-status').textContent=`Inpaint failed: ${e.message}`;}finally{b.disabled=false;}}


async function generateImage(){
  const prompt=$('#image-prompt').value.trim();if(!prompt)return alert('Enter a prompt');
  const b=$('#generate-image');b.disabled=true;setStatus('Generating locally…');
  try{const seed=Number($('#image-seed').value), isCharacterTab=imageState.studioTab==='character', character=isCharacterTab?currentCharacter():null;
    const payload={prompt,negative_prompt:$('#image-negative').value.trim(),width:Number($('#image-width').value),height:Number($('#image-height').value),steps:Number($('#image-steps').value),guidance:Number($('#image-guidance').value),seed,sampler:$('#image-sampler').value,quality:imageState.quality,batch:Number($('#image-batch').value),hires:$('#image-hires').checked,hires_scale:Number($('#hires-scale').value),hires_denoise:Number($('#hires-denoise').value),loras:selectedLoras(),character_id:character?.id||null,style:$('#image-style')?.value||'photorealistic'};
    const d=await api('/api/images/generate',{method:'POST',body:JSON.stringify(payload)});showGeneration(d.results?.[0]||d);if(d.results?.length>1)setStatus(`Generated ${d.results.length} images. Latest result shown.`);else setStatus(isCharacterTab?'Scenario image generated.':'Image generated successfully.');if(!imageState.seedLocked&&seed<0)$('#image-seed').value=(d.results?.[0]||d).seed;if(isCharacterTab)imageState.sceneReady=false;
  }catch(e){setStatus(`Generation failed: ${e.message}`);}finally{b.disabled=false;}
}
async function generateSceneImage(){
  const c=currentCharacter();if(!c)return alert('Select a character first.');if(!$('#image-prompt').value.trim())return alert('Build the scenario first.');
  const b=$('#generate-scene-image');if(b)b.disabled=true;setStatus(`Generating ${c.name}'s scenario…`);
  try{const seed=Number($('#image-seed').value);const payload={prompt:$('#image-prompt').value.trim(),negative_prompt:$('#image-negative').value.trim(),width:Number($('#image-width').value),height:Number($('#image-height').value),steps:Number($('#image-steps').value),guidance:Number($('#image-guidance').value),seed,sampler:$('#image-sampler').value,quality:imageState.quality,batch:1,hires:$('#image-hires').checked,hires_scale:Number($('#hires-scale').value),hires_denoise:Number($('#hires-denoise').value),loras:selectedLoras(),character_id:c.id};const d=await api('/api/images/generate',{method:'POST',body:JSON.stringify(payload)});showGeneration(d.results?.[0]||d);if(!imageState.seedLocked&&seed<0)$('#image-seed').value=(d.results?.[0]||d).seed;setStatus(`${c.name} scenario generated.`);if($('#scene-image-status'))$('#scene-image-status').textContent='Scenario image generated.';imageState.sceneReady=false;}catch(e){setStatus(`Scenario generation failed: ${e.message}`);if($('#scene-image-status'))$('#scene-image-status').textContent=e.message;}finally{if(b)b.disabled=false;}
}
async function openImageStudio(){try{const info=await api('/api/images');const sel=$('#image-model-select');sel.innerHTML='';(info.models||[]).forEach(m=>{const o=document.createElement('option');o.value=m;o.textContent=m;sel.appendChild(o);});if(!info.models?.length){const o=document.createElement('option');o.value='';o.textContent='No local image model';sel.appendChild(o);}imageState.profile=info.profile||{};renderSamplers(info.samplers||[]);imageState.loras=info.loras||[];renderLoras();renderLoraSliders();if(!state.characters.length)await loadCharacters();populateImageCharacterSelect();const g=info.gpu||{};$('#gpu-chip').textContent=g.available?`GPU ${g.used_gb}/${g.total_gb} GB`:'GPU unavailable';$('#model-chip').textContent=info.loaded?`Model ${String(info.loaded).split(/[/\\]/).pop()}`:'Model: none';setStatus(info.backend_available?`Ready${info.loaded?' · '+String(info.loaded).split(/[/\\]/).pop():''}`:`Image backend unavailable. ${info.error||''}`);await loadGallery();await refreshFaceIdStatus();showMode('images');}catch(e){setStatus(`Image Studio error: ${e.message}`);showMode('images');}}
async function refreshImageStudio(){return openImageStudio();}
async function loadImageModel(){const n=$('#image-model-select').value;if(!n)return;try{setStatus('Loading model and freeing text-model VRAM…');const r=await api('/api/images/load',{method:'POST',body:JSON.stringify({name:n})});imageState.profile=r.profile||{};renderSamplers(imageState.profile.samplers);$('#image-width').value=imageState.profile.default_width||1024;$('#image-height').value=imageState.profile.default_height||576;applyQuality(imageState.quality);$('#model-chip').textContent='Model '+n;setStatus(`Loaded: ${n}`);await updateGpuChip();}catch(e){setStatus(`Load failed: ${e.message}`);}}
async function updateGpuChip(){try{const g=await api('/api/images/gpu');$('#gpu-chip').textContent=g.available?`GPU ${g.used_gb}/${g.total_gb} GB`:'GPU unavailable';}catch(e){}}
async function loadGallery(){try{const list=await api('/api/images/history?limit=30');imageState.history=list;const box=$('#image-gallery');box.innerHTML='';if(!list.length){box.appendChild(el('div','empty-list','No generations yet.'));return;}list.forEach(item=>{const card=el('div','gallery-item');const img=el('img');img.src=item.url;img.loading='lazy';img.title=item.prompt;const meta=el('div','gallery-meta',`${item.width}×${item.height} · seed ${item.seed}`);const star=el('button','gallery-star',item.favorite?'★':'☆');star.onclick=async e=>{e.stopPropagation();await api(`/api/images/history/${item.id}`,{method:'PUT',body:JSON.stringify({favorite:!item.favorite})});loadGallery();};card.append(img,meta,star);card.onclick=()=>loadGeneration(item);box.appendChild(card);});}catch(e){console.warn('Gallery:',e);}}
function loadGeneration(item){imageState.current=item;$('#generated-image').src=item.url+'?t='+Date.now();$('#generated-image').classList.remove('hidden');$('#image-placeholder').classList.add('hidden');$('#image-actions').classList.remove('hidden');$('#image-prompt').value=item.prompt||'';$('#image-negative').value=item.negative_prompt||'';$('#image-width').value=item.width;$('#image-height').value=item.height;$('#image-steps').value=item.steps;$('#image-guidance').value=item.guidance;$('#image-seed').value=item.seed;$('#image-sampler').value=item.sampler;$('#generation-info').classList.remove('hidden');$('#generation-info').innerHTML=`<span>${item.model_family}</span><span>${item.width}×${item.height}</span><span>${item.steps} steps</span><span>${item.sampler}</span><span>seed ${item.seed}</span>`;updateTokenMeter();}
async function favoriteCurrent(){if(!imageState.current?.id)return;await api(`/api/images/history/${imageState.current.id}`,{method:'PUT',body:JSON.stringify({favorite:true})});loadGallery();}
function remixCurrent(){if(!imageState.current)return;loadGeneration(imageState.current);setStatus('Remix loaded. Change anything and generate again.');}
function toggleHires(){ $('#hires-options')?.classList.toggle('hidden',!$('#image-hires').checked); }
function setImageAspect(){if($('#image-aspect').value!=='custom')populateAspect();}

/* Set the currently displayed generated image as the selected character's avatar. */
async function setCurrentImageAsAvatar(){
  const result=imageState.current;
  if(!result?.url){
    alert('Generate or select an image first.');
    return;
  }
  const character=currentCharacter();
  if(!character){
    alert('Select a character first.');
    return;
  }

  const btn=$('#set-avatar-image');
  if(btn) btn.disabled=true;
  try{
    const updated=await api(`/api/characters/${character.id}`,{
      method:'PUT',
      body:JSON.stringify({avatar_path:String(result.url).split('?')[0]})
    });
    state.activeCharacter=updated||{...character,avatar_path:result.url};
    await loadCharacters();
    populateImageCharacterSelect();
    if(state.activeCharacter?.id===character.id) updateCharacterHeader();
    setStatus(`Avatar updated for ${character.name}.`);
  }catch(e){
    console.error('Avatar update failed:',e);
    alert(`Could not set avatar: ${e.message}`);
  }finally{
    if(btn) btn.disabled=false;
  }
}

/* ========================= CHAT WRITING TOOLS ========================= */
function toggleChatAiMenu(show){
  const m=$('#chat-ai-menu'); if(!m)return; m.classList.toggle('hidden',show===undefined?!m.classList.contains('hidden'):!show);
}
async function runWritingTool(action){
  toggleChatAiMenu(false); if(!state.activeConversationId||state.streaming)return;
  const draft=$('#composer-input')?.value.trim()||'';
  let instruction='';
  if(action==='enhance'&&!draft){alert('Write something in the draft first.');return;}
  if(action==='write') instruction=window.prompt('What should newAIr write?','Write a natural response that fits the current conversation.')||'';
  if(action==='write'&&!instruction)return;
  const title={enhance:'Enhance my draft',write:'Write something for me',summarize:'Chat summary'}[action]||'Writing assistant';
  $('#ai-helper-title').textContent=title;$('#ai-helper-result').value='Working…';$('#ai-helper-insert').style.display=action==='summarize'?'none':'';$('#ai-helper-modal').classList.remove('hidden');
  try{
    const d=await api(`/api/conversations/${state.activeConversationId}/writing-assist`,{method:'POST',body:JSON.stringify({action,draft,instruction})});
    $('#ai-helper-result').value=d.text||'';
  }catch(e){$('#ai-helper-result').value=`[error] ${e.message}`;}
}

/* ========================= WIRING ========================= */
function wire(){
  $$('.mode-btn').forEach(b=>b.onclick=()=>b.dataset.mode==='images'?openImageStudio():showMode(b.dataset.mode));
  $('#new-char-btn')?.addEventListener('click',()=>openCharModal());
  $('#edit-char-btn')?.addEventListener('click',()=>state.activeCharacter&&openCharModal(state.activeCharacter));
  $('#char-cancel-btn')?.addEventListener('click',()=>$('#char-modal').classList.add('hidden'));
  $('#char-cancel-btn-bottom')?.addEventListener('click',()=>$('#char-modal').classList.add('hidden'));
  $('#char-save-btn')?.addEventListener('click',saveCharacter);
  $('#char-delete-btn')?.addEventListener('click',deleteCharacter);$('#editor-generate-portrait')?.addEventListener('click',generatePortraitFromEditor);
  $('#add-initial-message')?.addEventListener('click',addInitialMessage);
  $('#chat-ai-btn')?.addEventListener('click',e=>{e.stopPropagation();toggleChatAiMenu();});
  $$('#chat-ai-menu button').forEach(b=>b.addEventListener('click',()=>runWritingTool(b.dataset.aiAction)));
  document.addEventListener('click',e=>{if(!e.target.closest('.composer-ai-wrap'))toggleChatAiMenu(false);});
  $('#ai-helper-close')?.addEventListener('click',()=>$('#ai-helper-modal').classList.add('hidden'));
  $('#ai-helper-copy')?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('#ai-helper-result').value);$('#ai-helper-copy').textContent='Copied';setTimeout(()=>$('#ai-helper-copy').textContent='Copy',900);}catch{}});
  $('#ai-helper-insert')?.addEventListener('click',()=>{$('#composer-input').value=$('#ai-helper-result').value;autoGrow($('#composer-input'));$('#ai-helper-modal').classList.add('hidden');$('#composer-input').focus();});
  $$('.editor-tab').forEach(b=>b.addEventListener('click',()=>setEditorTab(b.dataset.tab)));
  $('#f-macro-help')?.addEventListener('change',e=>{const v=e.target.value;if(v){const ta=document.activeElement?.tagName==='TEXTAREA'?document.activeElement:$('#f-personality');const pos=ta.value.length;ta.value=ta.value.slice(0,pos)+v+ta.value.slice(pos);e.target.value='';ta.focus();}});

  $('#manage-personas-btn')?.addEventListener('click',openPersonaModal);
  $('#manage-character-personas-btn')?.addEventListener('click',openPersonaModal);
  $('#assistant-persona-top')?.addEventListener('click',openPersonaModal);
  $('#persona-close')?.addEventListener('click',()=>$('#persona-modal').classList.add('hidden'));
  $('#persona-new')?.addEventListener('click',()=>{clearPersonaForm();$('#p-name').focus();});
  $('#persona-save')?.addEventListener('click',savePersona);
  $('#persona-select')?.addEventListener('change',async e=>{state.activePersonaId=e.target.value?+e.target.value:null;syncPersonaSelectors();if(state.assistantConversationId){try{await api(`/api/assistant/conversations/${state.assistantConversationId}`,{method:'PUT',body:JSON.stringify({persona_id:state.activePersonaId||null})});}catch(e){console.warn(e);}}});
  $('#character-persona-select')?.addEventListener('change',async e=>{state.activePersonaId=e.target.value?+e.target.value:null;syncPersonaSelectors();await updateActiveConversationPersona();});

  $('#new-conv-btn')?.addEventListener('click',startCharacterConversation);
  $('#send-btn')?.addEventListener('click',sendCharacter);$('#regen-btn')?.addEventListener('click',regenerate);$('#continue-btn')?.addEventListener('click',continueReply);$('#chat-settings-btn')?.addEventListener('click',openChatSettings);$('#chat-settings-close')?.addEventListener('click',()=>$('#chat-settings-modal').classList.add('hidden'));$('#chat-settings-save')?.addEventListener('click',saveChatSettings);$('#response-length')?.addEventListener('change',e=>$('#custom-response-wrap').classList.toggle('hidden',e.target.value!=='custom'));
  $('#assistant-send')?.addEventListener('click',sendAssistant);$('#new-assistant-btn')?.addEventListener('click',createAssistantConversation);

  $('#lore-btn')?.addEventListener('click',openLoreModal);$('#lore-close')?.addEventListener('click',()=>$('#lore-modal').classList.add('hidden'));$('#lore-add')?.addEventListener('click',addLore);
  $('#memory-btn')?.addEventListener('click',openMemoryModal);$('#memory-close')?.addEventListener('click',()=>$('#memory-modal').classList.add('hidden'));$('#memory-add')?.addEventListener('click',addMemory);
  $('#model-manager-btn')?.addEventListener('click',openModelModal);
  $('#export-project-btn')?.addEventListener('click',()=>{window.location='/api/project/export';});$('#model-close')?.addEventListener('click',()=>$('#model-modal').classList.add('hidden'));
  $('#crop-avatar-btn')?.addEventListener('click',()=>openCropModal($('#f-avatar').value.trim(), state.editingCharId||null));
  $('#crop-generated-image')?.addEventListener('click',()=>{const src=$('#generated-image').getAttribute('src')?.split('?')[0];if(src)openCropModal(src,$('#image-character-select')?.value||state.activeCharacter?.id||null);});
  $('#crop-close')?.addEventListener('click',()=>$('#crop-modal').classList.add('hidden'));$('#crop-cancel')?.addEventListener('click',()=>$('#crop-modal').classList.add('hidden'));$('#crop-apply')?.addEventListener('click',applyCrop);$('#crop-reset')?.addEventListener('click',resetCrop);$('#crop-zoom')?.addEventListener('input',e=>{cropState.scale=Number(e.target.value);renderCrop();});
  $('#crop-stage')?.addEventListener('pointerdown',cropPointerDown);$('#crop-stage')?.addEventListener('pointermove',cropPointerMove);window.addEventListener('pointerup',cropPointerUp);

  $('#load-image-model')?.addEventListener('click',loadImageModel);$('#generate-character-image')?.addEventListener('click',generateCharacterImage);$('#generate-scene-image')?.addEventListener('click',generateSceneImage);document.addEventListener('click',e=>{
    const tab=e.target.closest?.('.studio-tab');
    if(tab){e.preventDefault();setStudioTab(tab.dataset.studioTab);}
  });
  $('#set-avatar-image')?.addEventListener('click',setCurrentImageAsAvatar);
  $('#refresh-image-models')?.addEventListener('click',refreshImageStudio);$('#build-prompt')?.addEventListener('click',buildPromptFromFields);$('#enhance-prompt')?.addEventListener('click',enhancePrompt);$('#build-character-prompt')?.addEventListener('click',buildCharacterPrompt);$('#scene-builder-btn')?.addEventListener('click',openSceneBuilder);$('#scene-close')?.addEventListener('click',()=>$('#scene-modal').classList.add('hidden'));$('#scene-build')?.addEventListener('click',buildScene);$('#refresh-gallery')?.addEventListener('click',loadGallery);$('#favorite-image')?.addEventListener('click',favoriteCurrent);$('#remix-image')?.addEventListener('click',remixCurrent);$('#random-seed')?.addEventListener('click',()=>$('#image-seed').value=Math.floor(Math.random()*2147483647));$('#lock-seed')?.addEventListener('click',e=>{imageState.seedLocked=!imageState.seedLocked;e.currentTarget.textContent=imageState.seedLocked?'🔒':'🔓';});$('#image-hires')?.addEventListener('change',toggleHires);$('#image-aspect')?.addEventListener('change',setImageAspect);$('#image-prompt')?.addEventListener('input',updateTokenMeter);$$('.quality-btn').forEach(b=>b.addEventListener('click',()=>applyQuality(b.dataset.quality)));$('#image-model-select')?.addEventListener('change',async()=>{const n=$('#image-model-select').value;try{const profiles=await api('/api/images/profiles');const key=n.toLowerCase().includes('realisticvision')||n.toLowerCase().includes('v60b1')||n.toLowerCase().includes('v51vae')?'sd15':n.toLowerCase().includes('pony')?'pony':'sdxl';imageState.profile=profiles[key]||imageState.profile;renderSamplers(imageState.profile.samplers||Object.keys(profiles));syncImg2ImgControls();$('#image-width').value=imageState.profile.default_width||1024;$('#image-height').value=imageState.profile.default_height||576;applyQuality(imageState.quality);}catch(e){console.warn('Profile:',e);}});$('#generate-image')?.addEventListener('click',generateImage);$('#regenerate-image')?.addEventListener('click',generateImage);$('#image-character-select')?.addEventListener('change',e=>{const c=state.characters.find(x=>x.id===Number(e.target.value));if(c)state.activeCharacter=c;});

  $('#faceid-file')?.addEventListener('change',e=>handleFaceIdFile(e.target.files?.[0]));$('#faceid-model')?.addEventListener('change',async()=>{try{const d=await api('/api/images/faceid/status');updateFaceIdModelHelp(d);}catch(e){}});$('#faceid-generate')?.addEventListener('click',runFaceToScene);$('#faceid-strength')?.addEventListener('input',e=>$('#faceid-strength-value').textContent=Number(e.target.value).toFixed(2));$('#faceid-random-seed')?.addEventListener('click',()=>$('#faceid-seed').value=Math.floor(Math.random()*2147483647));$('#faceid-drop')?.addEventListener('dragover',e=>{e.preventDefault();e.currentTarget.classList.add('dragging');});$('#faceid-drop')?.addEventListener('dragleave',e=>e.currentTarget.classList.remove('dragging'));$('#faceid-drop')?.addEventListener('drop',e=>{e.preventDefault();e.currentTarget.classList.remove('dragging');handleFaceIdFile(e.dataTransfer.files?.[0]);});$('#img2img-file')?.addEventListener('change',e=>handleImg2ImgFile(e.target.files?.[0]));$('#img2img-use-current')?.addEventListener('click',useCurrentForImg2Img);$('#img2img-outpaint')?.addEventListener('click',runImg2ImgOutpaint);$('#img2img-clear')?.addEventListener('click',clearImg2Img);$('#img2img-generate')?.addEventListener('click',runImg2Img);$('#img2img-optimize')?.addEventListener('click',optimizeImg2ImgPrompt);$('#img2img-copy-prompt')?.addEventListener('click',()=>{$('#img2img-prompt').value=$('#image-prompt').value.trim();});$('#img2img-random-seed')?.addEventListener('click',()=>$('#img2img-seed').value=Math.floor(Math.random()*2147483647));$('#img2img-strength')?.addEventListener('input',e=>{$('#img2img-strength-value').textContent=Number(e.target.value).toFixed(2);});$$('.img2img-preset').forEach(b=>b.addEventListener('click',()=>setImg2ImgPreset(b.dataset.img2imgPreset)));$('#img2img-edit-mode')?.addEventListener('change',e=>{const m={general:.40,background:.46,clothing:.38,relight:.28,restyle:.52,full_body:.62};const v=m[e.target.value]??.40;$('#img2img-strength').value=v;$('#img2img-strength-value').textContent=v.toFixed(2);});$('#img2img-drop')?.addEventListener('dragover',e=>{e.preventDefault();e.currentTarget.classList.add('dragging');});$('#img2img-drop')?.addEventListener('dragleave',e=>e.currentTarget.classList.remove('dragging'));$('#img2img-drop')?.addEventListener('drop',e=>{e.preventDefault();e.currentTarget.classList.remove('dragging');handleImg2ImgFile(e.dataTransfer.files?.[0]);});
  $('#inpaint-quality')?.addEventListener('change',applyInpaintQuality);$('#inpaint-file')?.addEventListener('change',e=>handleInpaintFile(e.target.files?.[0]));$('#inpaint-use-current')?.addEventListener('click',useCurrentForInpaint);$('#inpaint-clear')?.addEventListener('click',clearInpaint);$('#inpaint-generate')?.addEventListener('click',runInpaint);$('#inpaint-optimize')?.addEventListener('click',optimizeInpaintPrompt);$('#inpaint-copy-prompt')?.addEventListener('click',()=>$('#inpaint-prompt').value=$('#image-prompt').value.trim());$('#inpaint-random-seed')?.addEventListener('click',()=>$('#inpaint-seed').value=Math.floor(Math.random()*2147483647));$('#inpaint-clear-mask')?.addEventListener('click',clearInpaintMask);$('#inpaint-fill-mask')?.addEventListener('click',fillInpaintMask);$('#inpaint-erase')?.addEventListener('click',e=>{imageState.inpaintErase=!imageState.inpaintErase;e.currentTarget.textContent=imageState.inpaintErase?'Paint':'Erase'});$('#inpaint-brush')?.addEventListener('input',e=>$('#inpaint-brush-value').textContent=e.target.value);const ic=$('#inpaint-canvas');if(ic){ic.addEventListener('pointerdown',e=>{if(!imageState.inpaintMask)return;imageState.inpaintDrawing=true;ic.setPointerCapture?.(e.pointerId);inpaintPoint(e)});ic.addEventListener('pointermove',e=>{if(imageState.inpaintDrawing)inpaintPoint(e)});ic.addEventListener('pointerup',()=>imageState.inpaintDrawing=false);ic.addEventListener('pointercancel',()=>imageState.inpaintDrawing=false);}applyInpaintQuality();refreshInpaintStatus();
  setImg2ImgPreset('preserve');
  ['#assistant-input','#composer-input'].forEach(sel=>{const i=$(sel);if(!i)return;i.addEventListener('input',()=>autoGrow(i));i.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sel==='#assistant-input'?sendAssistant():sendCharacter();}});});
}

(async()=>{try{wire();await loadPersonas();await loadCharacters();await loadAssistantConversations();showMode('assistant');}catch(e){console.error('newAIr startup error:',e);}})();
