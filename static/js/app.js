const cropState={sourceUrl:'',targetCharacterId:null,scale:1,x:0,y:0,dragging:false,startX:0,startY:0,baseScale:1};
const inpaintState={image:null,drawing:false,lastX:0,lastY:0};

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

  if(!state.activePersonaId && state.personas.length)
    state.activePersonaId=state.personas[0].id;

  if($('#persona-select'))
    $('#persona-select').value=state.activePersonaId||'';

  if($('#character-persona-select'))
    $('#character-persona-select').value=state.activePersonaId||'';

  const name=state.personas.find(p=>p.id==state.activePersonaId)?.name||'None';

  if($('#assistant-persona-top'))
    $('#assistant-persona-top').textContent=`Persona: ${name}`;
}

async function loadPersonas(){
  state.personas=await api('/api/personas');

  if(
    state.activePersonaId &&
    !state.personas.some(p=>p.id==state.activePersonaId)
  ){
    state.activePersonaId=null;
  }

  syncPersonaSelectors();
}

function clearPersonaForm(){
  [
    'p-edit-id',
    'p-name',
    'p-avatar',
    'p-description',
    'p-pronouns',
    'p-age',
    'p-appearance',
    'p-personality',
    'p-style',
    'p-background',
    'p-details'
  ].forEach(id=>{
    if($('#'+id))$('#'+id).value='';
  });

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
    box.appendChild(
      el('div','empty-list','No personas yet. Create one below.')
    );

    clearPersonaForm();
    return;
  }

  list.forEach(p=>{
    const row=el('div','persona-row');
    const left=el('div','persona-row-main');

    const avatar=el(
      'div',
      'persona-avatar',
      (p.name?.[0]||'?').toUpperCase()
    );

    if(p.avatar_path){
      avatar.style.backgroundImage=`url("${p.avatar_path}")`;
      avatar.textContent='';
    }

    const info=el('div','persona-row-info');

    info.append(
      el('strong',null,p.name)
    );

    info.append(
      el('span','muted',p.description||'No description')
    );

    left.append(avatar,info);

    const actions=el('div','row-actions');

    const use=el(
      'button',
      'mini',
      p.id==state.activePersonaId?'✓':'Use'
    );

    use.onclick=async()=>{
      state.activePersonaId=p.id;
      syncPersonaSelectors();
      await updateActiveConversationPersona();
      renderPersonas();
    };

    const edit=el('button','mini','Edit');

    edit.onclick=()=>{
      fillPersonaForm(p);
    };

    const del=el('button','mini danger','Delete');

    del.onclick=async()=>{
      if(!confirm(`Delete persona "${p.name}"?`))
        return;

      await api(
        `/api/personas/${p.id}`,
        {method:'DELETE'}
      );

      if(state.activePersonaId==p.id)
        state.activePersonaId=null;

      await loadPersonas();
      renderPersonas();
    };

    actions.append(use,edit,del);
    row.append(left,actions);
    box.appendChild(row);
  });
}

async function savePersona(){
  const payload={
    name:$('#p-name').value.trim(),
    avatar_path:$('#p-avatar').value.trim(),
    description:$('#p-description').value.trim(),
    pronouns:$('#p-pronouns').value.trim(),
    age:$('#p-age').value.trim(),
    appearance:$('#p-appearance').value.trim(),
    personality:$('#p-personality').value.trim(),
    speaking_style:$('#p-style').value.trim(),
    background:$('#p-background').value.trim(),
    details:$('#p-details').value.trim()
  };

  if(!payload.name){
    alert('Persona name is required');
    return;
  }

  const id=$('#p-edit-id').value;

  try{
    const saved=id
      ?await api(
        `/api/personas/${id}`,
        {
          method:'PUT',
          body:JSON.stringify(payload)
        }
      )
      :await api(
        '/api/personas',
        {
          method:'POST',
          body:JSON.stringify(payload)
        }
      );

    state.activePersonaId=saved.id;

    await loadPersonas();
    fillPersonaForm(saved);
    await renderPersonas();

  }catch(e){
    alert(`Could not save persona: ${e.message}`);
  }
}

async function updateActiveConversationPersona(){
  if(!state.activeConversationId)
    return;

  try{
    await api(
      `/api/conversations/${state.activeConversationId}`,
      {
        method:'PUT',
        body:JSON.stringify({
          persona_id:state.activePersonaId||null
        })
      }
    );
  }catch(e){
    console.warn(
      'Could not update conversation persona:',
      e
    );
  }
}


/* ========================= ASSISTANT ========================= */

async function createAssistantConversation(){
  const conv=await api(
    '/api/assistant/conversations',
    {
      method:'POST',
      body:JSON.stringify({
        persona_id:state.activePersonaId||null,
        title:'newAIr Assistant'
      })
    }
  );

  state.assistantConversationId=conv.id;

  await loadAssistantConversations();

  renderAssistantMessages(
    await api(
      `/api/assistant/conversations/${conv.id}/messages`
    )
  );
}

async function loadAssistantConversations(){
  const list=await api('/api/assistant/conversations');

  const box=$('#assistant-conversation-list');
  box.innerHTML='';

  list.forEach(c=>{
    const r=el(
      'div',
      'conversation-item',
      c.title||`Chat #${c.id}`
    );

    r.classList.toggle(
      'active',
      c.id===state.assistantConversationId
    );

    r.onclick=async()=>{
      state.assistantConversationId=c.id;

      renderAssistantMessages(
        await api(
          `/api/assistant/conversations/${c.id}/messages`
        )
      );

      loadAssistantConversations();
    };

    box.appendChild(r);
  });

  if(
    !state.assistantConversationId &&
    list.length
  ){
    state.assistantConversationId=list[0].id;

    renderAssistantMessages(
      await api(
        `/api/assistant/conversations/${list[0].id}/messages`
      )
    );
  }
}

function renderAssistantMessages(ms){
  const box=$('#assistant-messages');

  box.innerHTML='';

  ms.forEach(m=>{
    box.appendChild(
      renderMessageBubble(m)
    );
  });

  box.scrollTop=box.scrollHeight;
}

async function sendAssistant(){
  const input=$('#assistant-input');
  const text=input.value.trim();

  if(!text||state.streaming)
    return;

  if(!state.assistantConversationId)
    await createAssistantConversation();

  $('#assistant-messages').appendChild(
    renderMessageBubble({
      role:'user',
      content:text
    })
  );

  input.value='';
  autoGrow(input);

  await streamInto(
    `/api/assistant/conversations/${state.assistantConversationId}/chat`,
    {message:text},
    '#assistant-messages'
  );
}


/* ========================= CHARACTERS ========================= */

async function loadCharacters(){
  state.characters=await api('/api/characters');

  const list=$('#character-list');

  list.innerHTML='';

  if(!state.characters.length){
    list.appendChild(
      el(
        'div',
        'empty-list',
        'No characters yet. Click + to create one.'
      )
    );

    return;
  }

  state.characters.forEach(c=>{
    const r=el('div','char-item');

    const av=el(
      'div',
      'char-avatar',
      (c.name?.[0]||'?').toUpperCase()
    );

    if(c.avatar_path){
      av.style.backgroundImage=`url("${c.avatar_path}")`;
      av.textContent='';
    }

    const info=el(
      'div',
      'char-item-info'
    );

    info.append(
      el(
        'div',
        'char-item-name',
        c.name
      )
    );

    if(c.description)
      info.append(
        el(
          'div',
          'char-item-desc',
          c.description
        )
      );

    if(c.tags)
      info.append(
        el(
          'div',
          'char-tags',
          c.tags
        )
      );

    const edit=el(
      'button',
      'mini',
      'Edit'
    );

    edit.onclick=e=>{
      e.stopPropagation();
      openCharModal(c);
    };

    r.append(av,info,edit);

    r.onclick=()=>{
      selectCharacter(c);
    };

    list.appendChild(r);
  });
}

async function selectCharacter(c){
  state.activeCharacter=c;

  updateCharacterHeader();
  showMode('characters');

  try{
    const convs=await api(
      `/api/characters/${c.id}/conversations`
    );

    if(convs.length)
      await openCharacterConversation(convs[0].id);
    else
      await startCharacterConversation();

  }catch(e){
    alert(
      `Could not open character: ${e.message}`
    );
  }
}

function updateCharacterHeader(){
  const c=state.activeCharacter;

  if(!c)
    return;

  $('#chat-char-name').textContent=c.name;

  const av=$('#chat-char-avatar');

  if(av){
    av.textContent=c.avatar_path
      ?''
      :(c.name?.[0]||'?').toUpperCase();

    av.style.backgroundImage=c.avatar_path
      ?`url("${c.avatar_path}")`
      :'';
  }
}

async function startCharacterConversation(){
  if(!state.activeCharacter){
    alert('Select a character first');
    return;
  }

  const conv=await api(
    `/api/characters/${state.activeCharacter.id}/conversations`,
    {
      method:'POST',
      body:JSON.stringify({
        persona_id:state.activePersonaId||null
      })
    }
  );

  await openCharacterConversation(conv.id);
}

async function openCharacterConversation(id){
  state.activeConversationId=id;

  const conv=await api(
    `/api/conversations/${id}`
  );

  state.activePersonaId=conv.persona_id||null;

  syncPersonaSelectors();

  $('#chat-conv-title').textContent=
    conv.title||`Chat #${id}`;

  renderMessages(
    await api(
      `/api/conversations/${id}/messages`
    )
  );
}

function renderMessages(ms){
  const box=$('#messages');

  box.innerHTML='';

  ms.forEach(m=>{
    box.appendChild(
      renderMessageBubble(m)
    );
  });

  box.scrollTop=box.scrollHeight;
}


/* ========================= CHARACTER EDITOR ========================= */

function setEditorTab(tab){
  $$('.editor-tab').forEach(b=>{
    b.classList.toggle(
      'active',
      b.dataset.tab===tab
    );
  });

  $$('.editor-section').forEach(s=>{
    s.classList.toggle(
      'hidden',
      s.id!==tab
    );
  });
}

function openCharModal(c=null){
  state.editingCharId=c?.id||null;

  $('#char-modal-title').textContent=
    c?'Edit Character':'New Character';

  $('#f-name').value=c?.name||'';
  $('#f-avatar').value=c?.avatar_path||'';
  $('#f-description').value=c?.description||'';
  $('#f-tags').value=c?.tags||'';
  $('#f-personality').value=c?.personality||'';
  $('#f-scenario').value=c?.scenario||'';
  $('#f-greeting').value=c?.greeting||'';
  $('#f-example').value=c?.example_dialogue||'';
  $('#f-system').value=c?.system_prompt||'';

  $('#char-delete-btn').classList.toggle(
    'hidden',
    !c
  );

  setEditorTab('char-general');

  $('#char-modal').classList.remove('hidden');
}

async function saveCharacter(){
  const payload={
    name:$('#f-name').value.trim(),
    avatar_path:$('#f-avatar').value.trim(),
    description:$('#f-description').value.trim(),
    tags:$('#f-tags').value.trim(),
    personality:$('#f-personality').value.trim(),
    scenario:$('#f-scenario').value.trim(),
    greeting:$('#f-greeting').value.trim(),
    example_dialogue:$('#f-example').value.trim(),
    system_prompt:$('#f-system').value.trim()
  };

  if(!payload.name){
    alert('Character name is required');
    return;
  }

  try{
    let saved;

    if(state.editingCharId){
      saved=await api(
        `/api/characters/${state.editingCharId}`,
        {
          method:'PUT',
          body:JSON.stringify(payload)
        }
      );
    }else{
      saved=await api(
        '/api/characters',
        {
          method:'POST',
          body:JSON.stringify(payload)
        }
      );
    }

    $('#char-modal').classList.add('hidden');

    await loadCharacters();

    if(
      state.activeCharacter &&
      state.editingCharId===state.activeCharacter.id
    ){
      state.activeCharacter=saved;
      updateCharacterHeader();
    }

  }catch(e){
    alert(
      `Could not save character: ${e.message}`
    );
  }
}

async function deleteCharacter(){
  if(!state.editingCharId)
    return;

  const c=state.characters.find(
    x=>x.id==state.editingCharId
  );

  if(
    !confirm(
      `Delete "${c?.name||'this character'}" and its conversations?`
    )
  )
    return;

  try{
    await api(
      `/api/characters/${state.editingCharId}`,
      {
        method:'DELETE'
      }
    );

    $('#char-modal').classList.add('hidden');

    state.activeCharacter=null;
    state.activeConversationId=null;

    await loadCharacters();

    showMode('characters');

  }catch(e){
    alert(
      `Could not delete character: ${e.message}`
    );
  }
}


/* ========================= CHAT ========================= */

function renderMessageBubble(m){
  const b=el(
    'div',
    `msg ${m.role}`,
    m.content
  );

  b.dataset.id=m.id||'';

  if(m.id&&m.role!=='system'){
    const a=el(
      'div',
      'msg-actions'
    );

    const ed=el(
      'button',
      null,
      'edit'
    );

    ed.onclick=()=>{
      editMessage(b,m);
    };

    const del=el(
      'button',
      null,
      'delete'
    );

    del.onclick=()=>{
      deleteMessage(b,m.id);
    };

    a.append(ed,del);
    b.append(a);
  }

  return b;
}

async function editMessage(b,m){
  const ta=el('textarea');

  ta.value=m.content;
  ta.rows=4;

  b.replaceChildren(ta);

  ta.focus();

  const save=async()=>{
    const v=ta.value.trim();

    if(v&&v!==m.content){
      await api(
        `/api/messages/${m.id}`,
        {
          method:'PUT',
          body:JSON.stringify({
            content:v
          })
        }
      );

      m.content=v;
    }

    b.replaceWith(
      renderMessageBubble(m)
    );
  };

  ta.addEventListener(
    'blur',
    save,
    {once:true}
  );

  ta.addEventListener(
    'keydown',
    e=>{
      if(
        e.key==='Enter' &&
        !e.shiftKey
      ){
        e.preventDefault();
        ta.blur();
      }
    }
  );
}

async function deleteMessage(b,id){
  try{
    await api(
      `/api/messages/${id}`,
      {
        method:'DELETE'
      }
    );

    b.remove();

  }catch(e){
    alert(e.message);
  }
}

function setBusy(v){
  state.streaming=v;

  [
    '#send-btn',
    '#regen-btn',
    '#continue-btn',
    '#assistant-send'
  ].forEach(s=>{
    if($(s))
      $(s).disabled=v;
  });
}

async function streamInto(path,body,selector){
  const box=$(selector);

  const b=el(
    'div',
    'msg assistant streaming',
    ''
  );

  box.appendChild(b);

  box.scrollTop=box.scrollHeight;

  setBusy(true);

  try{
    const r=await fetch(
      path,
      {
        method:'POST',
        headers:{
          'Content-Type':'application/json'
        },
        body:JSON.stringify(body||{})
      }
    );

    if(!r.ok||!r.body){
      throw new Error(
        `request failed: ${r.status} ${await r.text().catch(()=> '')}`
      );
    }

    const reader=r.body.getReader();
    const dec=new TextDecoder();

    let buf='';
    let full='';

    while(true){
      const {
        value,
        done
      }=await reader.read();

      if(done)
        break;

      buf+=dec.decode(
        value,
        {stream:true}
      );

      let i;

      while(
        (i=buf.indexOf('\n\n'))>=0
      ){
        const raw=buf.slice(0,i);

        buf=buf.slice(i+2);

        const line=raw.replace(
          /^data:\s*/,
          ''
        );

        if(!line)
          continue;

        let p;

        try{
          p=JSON.parse(line);
        }catch{
          continue;
        }

        if(p.delta){
          full+=p.delta;

          b.textContent=full;

          box.scrollTop=
            box.scrollHeight;

        }else if(p.error){
          b.textContent=
            `[error: ${p.error}]`;
        }
      }
    }

    b.classList.remove('streaming');

  }catch(e){
    b.textContent=
      `[connection error: ${e.message}]`;

    b.classList.remove('streaming');

  }finally{
    setBusy(false);
  }
}

async function sendCharacter(){
  const input=$('#composer-input');
  const text=input.value.trim();

  if(
    !text ||
    state.streaming ||
    !state.activeConversationId
  )
    return;

  $('#messages').appendChild(
    renderMessageBubble({
      role:'user',
      content:text
    })
  );

  input.value='';

  autoGrow(input);

  await streamInto(
    `/api/conversations/${state.activeConversationId}/chat`,
    {message:text},
    '#messages'
  );
}

async function regenerate(){
  if(
    !state.activeConversationId ||
    state.streaming
  )
    return;

  const last=$(
    '#messages .msg.assistant:last-of-type'
  );

  if(last)
    last.remove();

  await streamInto(
    `/api/conversations/${state.activeConversationId}/regenerate`,
    {},
    '#messages'
  );
}

async function continueReply(){
  if(
    !state.activeConversationId ||
    state.streaming
  )
    return;

  await streamInto(
    `/api/conversations/${state.activeConversationId}/continue`,
    {},
    '#messages'
  );
}

function autoGrow(t){
  t.style.height='auto';

  t.style.height=
    Math.min(
      180,
      t.scrollHeight
    )+'px';
}


/* ========================= LORE / MEMORY ========================= */

async function openLoreModal(){
  if(!state.activeCharacter)
    return;

  try{
    const es=await api(
      `/api/characters/${state.activeCharacter.id}/lorebook`
    );

    const box=$('#lore-list');

    box.innerHTML='';

    es.forEach(e=>{
      const r=el(
        'div',
        'list-row',
        `${e.title} [${e.keywords.join(', ')}]`
      );

      const d=el(
        'button',
        null,
        'Delete'
      );

      d.onclick=async()=>{
        await api(
          `/api/characters/lorebook/${e.id}`,
          {
            method:'DELETE'
          }
        );

        openLoreModal();
      };

      r.appendChild(d);
      box.appendChild(r);
    });

    $('#lore-modal').classList.remove('hidden');

  }catch(e){
    alert(e.message);
  }
}

async function addLore(){
  const title=$('#lore-title').value.trim();

  const keywords=$('#lore-keywords').value
    .split(',')
    .map(x=>x.trim())
    .filter(Boolean);

  const content=$('#lore-content').value.trim();

  if(
    !title ||
    !keywords.length ||
    !content
  ){
    alert(
      'Fill title, keywords and content'
    );

    return;
  }

  await api(
    `/api/characters/${state.activeCharacter.id}/lorebook`,
    {
      method:'POST',
      body:JSON.stringify({
        title,
        keywords,
        content
      })
    }
  );

  $('#lore-title').value='';
  $('#lore-keywords').value='';
  $('#lore-content').value='';

  openLoreModal();
}

async function openMemoryModal(){
  if(!state.activeCharacter)
    return;

  const fs=await api(
    `/api/characters/${state.activeCharacter.id}/memories`
  );

  const box=$('#memory-list');

  box.innerHTML='';

  fs.forEach(f=>{
    box.appendChild(
      el(
        'div',
        'list-row',
        f.fact
      )
    );
  });

  $('#memory-modal').classList.remove('hidden');
}

async function addMemory(){
  const fact=$('#memory-fact').value.trim();

  if(!fact)
    return;

  await api(
    `/api/characters/${state.activeCharacter.id}/memories`,
    {
      method:'POST',
      body:JSON.stringify({
        fact
      })
    }
  );

  $('#memory-fact').value='';

  openMemoryModal();
}


/* ========================= PROFILE IMAGE CROP ========================= */

function openCropModal(url,characterId=null){
  if(!url){
    alert('No image selected to crop.');
    return;
  }

  const modal=$('#crop-modal');
  const img=$('#crop-source');

  cropState.sourceUrl=url;
  cropState.targetCharacterId=
    characterId
      ?Number(characterId)
      :null;

  cropState.scale=1;
  cropState.x=0;
  cropState.y=0;
  cropState.dragging=false;

  img.onload=()=>{
    fitCropImage();
    renderCrop();
  };

  img.src=
    url+
    (url.includes('?')?'&':'?')+
    'crop='+
    Date.now();

  $('#crop-zoom').value='1';

  modal.classList.remove('hidden');
}

function fitCropImage(){
  const stage=$('#crop-stage');
  const img=$('#crop-source');

  if(
    !stage ||
    !img.naturalWidth
  )
    return;

  const w=stage.clientWidth;
  const h=stage.clientHeight;

  cropState.baseScale=
    Math.max(
      w/img.naturalWidth,
      h/img.naturalHeight
    );

  cropState.scale=1;
  cropState.x=0;
  cropState.y=0;
}

function renderCrop(){
  const img=$('#crop-source');

  if(!img)
    return;

  const stage=$('#crop-stage');

  const w=stage.clientWidth;
  const h=stage.clientHeight;

  const scale=
    cropState.baseScale*
    cropState.scale;

  const iw=
    img.naturalWidth*
    scale;

  const ih=
    img.naturalHeight*
    scale;

  const maxX=
    Math.max(
      0,
      (iw-w)/2
    );

  const maxY=
    Math.max(
      0,
      (ih-h)/2
    );

  cropState.x=
    Math.max(
      -maxX,
      Math.min(
        maxX,
        cropState.x
      )
    );

  cropState.y=
    Math.max(
      -maxY,
      Math.min(
        maxY,
        cropState.y
      )
    );

  img.style.width=iw+'px';
  img.style.height=ih+'px';

  img.style.left=
    `calc(50% + ${cropState.x}px)`;

  img.style.top=
    `calc(50% + ${cropState.y}px)`;
}

function cropPointerDown(e){
  const img=$('#crop-source');

  if(
    !img ||
    img.classList.contains('hidden')
  )
    return;

  cropState.dragging=true;

  cropState.startX=
    e.clientX-
    cropState.x;

  cropState.startY=
    e.clientY-
    cropState.y;

  img.setPointerCapture?.(
    e.pointerId
  );
}

function cropPointerMove(e){
  if(!cropState.dragging)
    return;

  cropState.x=
    e.clientX-
    cropState.startX;

  cropState.y=
    e.clientY-
    cropState.startY;

  renderCrop();
}

function cropPointerUp(){
  cropState.dragging=false;
}

function resetCrop(){
  cropState.scale=1;
  cropState.x=0;
  cropState.y=0;

  $('#crop-zoom').value='1';

  renderCrop();
}

async function applyCrop(){
  const src=$('#crop-source');
  const stage=$('#crop-stage');

  if(!src.naturalWidth)
    return;

  const size=512;

  const canvas=
    document.createElement('canvas');

  canvas.width=size;
  canvas.height=size;

  const ctx=
    canvas.getContext('2d');

  const scale=
    cropState.baseScale*
    cropState.scale;

  const stageW=
    stage.clientWidth;

  const stageH=
    stage.clientHeight;

  const left=
    (stageW-
      (src.naturalWidth*scale)
    )/2+
    cropState.x;

  const top=
    (stageH-
      (src.naturalHeight*scale)
    )/2+
    cropState.y;

  const ratio=
    size/stageW;

  ctx.fillStyle='#111';

  ctx.fillRect(
    0,
    0,
    size,
    size
  );

  ctx.drawImage(
    src,
    left*ratio,
    top*ratio,
    src.naturalWidth*
      scale*
      ratio,
    src.naturalHeight*
      scale*
      ratio
  );

  try{
    const saved=await api(
      '/api/characters/avatar/crop',
      {
        method:'POST',
        body:JSON.stringify({
          data_url:
            canvas.toDataURL(
              'image/png'
            )
        })
      }
    );

    if(cropState.targetCharacterId){
      const character=
        state.characters.find(
          c=>c.id===
            cropState.targetCharacterId
        );

      if(character){
        const updated=await api(
          `/api/characters/${character.id}`,
          {
            method:'PUT',
            body:JSON.stringify({
              avatar_path:saved.url
            })
          }
        );

        state.activeCharacter=
          state.activeCharacter?.id===
          character.id
            ?updated
            :state.activeCharacter;

        await loadCharacters();

        populateImageCharacterSelect();

        if(
          state.activeCharacter?.id===
          character.id
        )
          updateCharacterHeader();

        setStatus(
          `Avatar updated for ${character.name}.`
        );
      }

    }else if(
      $('#f-avatar') &&
      !$('#char-modal').classList.contains('hidden')
    ){
      $('#f-avatar').value=saved.url;
    }

    $('#crop-modal').classList.add('hidden');

  }catch(e){
    alert(
      `Could not save cropped image: ${e.message}`
    );
  }
}


/* ========================= MODELS / IMAGES ========================= */

async function openModelModal(){
  try{
    const info=await api('/api/models');

    $('#models-dir-path').textContent=
      info.models_dir||'';

    $('#model-loaded').textContent=
      info.llama_cpp_installed
        ?`GPU layers: ${info.gpu_layers} · Context: ${info.context_tokens} · Loaded: ${info.loaded||'none'}`
        :`AI engine error: ${info.llama_cpp_error||'llama-cpp-python unavailable'}`;

    const box=$('#model-list');

    box.innerHTML='';

    (info.available||[]).forEach(f=>{
      const r=el(
        'div',
        'list-row',
        f
      );

      const b=el(
        'button',
        null,
        'Load'
      );

      b.onclick=async()=>{
        b.disabled=true;

        try{
          const result=await api(
            '/api/models/load',
            {
              method:'POST',
              body:JSON.stringify({
                filename:f
              })
            }
          );

          $('#model-loaded').textContent=
            `Loaded: ${result.loaded||f}`;

        }catch(e){
          $('#model-loaded').textContent=
            `Load failed: ${e.message}`;

        }finally{
          b.disabled=false;
        }
      };

      r.appendChild(b);
      box.appendChild(r);
    });

    if(!info.available?.length){
      box.appendChild(
        el(
          'div',
          'empty-list',
          'No GGUF models found.'
        )
      );
    }

    $('#model-modal').classList.remove('hidden');

  }catch(e){
    alert(e.message);
  }
}

async function openImageStudio(){
  try{
    const info=await api('/api/images');

    const sel=$('#image-model-select');

    sel.innerHTML='';

    (info.models||[]).forEach(m=>{
      const o=document.createElement('option');

      o.value=m;
      o.textContent=m;

      sel.appendChild(o);
    });

    if(!info.models?.length){
      const o=document.createElement('option');

      o.value='';
      o.textContent=
        'No local image model';

      sel.appendChild(o);
    }

    populateImageCharacterSelect();

    setStatus(
      info.backend_available
        ?`Backend ready${info.loaded?' · Loaded: '+info.loaded:''}`
        :`Image backend unavailable. ${info.error||''}`
    );

    showMode('images');

  }catch(e){
    setStatus(
      `Image Studio error: ${e.message}`
    );

    showMode('images');
  }
}

function populateImageCharacterSelect(){
  const sel=$('#image-character-select');

  if(!sel)
    return;

  sel.innerHTML='';

  const first=
    document.createElement('option');

  first.value='';

  first.textContent=
    'Select a character…';

  sel.appendChild(first);

  state.characters.forEach(c=>{
    const o=
      document.createElement('option');

    o.value=c.id;
    o.textContent=c.name;

    sel.appendChild(o);
  });

  if(state.activeCharacter)
    sel.value=
      String(state.activeCharacter.id);
}

async function loadImageModel(){
  const n=
    $('#image-model-select').value;

  if(!n)
    return;

  try{
    const r=await api(
      '/api/images/load',
      {
        method:'POST',
        body:JSON.stringify({
          name:n
        })
      }
    );

    setStatus(
      `Loaded: ${r.loaded}`
    );

  }catch(e){
    setStatus(
      `Load failed: ${e.message}`
    );
  }
}

function fileToDataURL(file){
  return new Promise(
    (resolve,reject)=>{
      if(!file)
        return reject(
          new Error(
            'Choose an image first.'
          )
        );

      const r=
        new FileReader();

      r.onload=()=>{
        resolve(r.result);
      };

      r.onerror=()=>{
        reject(
          new Error(
            'Could not read image.'
          )
        );
      };

      r.readAsDataURL(file);
    }
  );
}


/* ========================= INPAINT ========================= */

function updateImageEditUI(){
  const mode=
    $('#image-edit-mode')?.value||
    'txt2img';

  $('#source-image-field')?.classList.toggle(
    'hidden',
    mode==='txt2img'
  );

  $('#inpaint-mask-field')?.classList.toggle(
    'hidden',
    mode!=='inpaint'
  );

  $('#edit-strength-field')?.classList.toggle(
    'hidden',
    mode==='txt2img'
  );

  const v=
    $('#image-strength')?.value||
    '0.55';

  if($('#image-strength-value'))
    $('#image-strength-value').textContent=v;

  if($('#generate-image'))
    $('#generate-image').textContent=
      mode==='txt2img'
        ?'Generate'
        :mode==='img2img'
          ?'Edit image'
          :'Inpaint';

  if(mode==='inpaint'){
    const file=
      $('#source-image-file')
        ?.files?.[0];

    if(
      file &&
      !inpaintState.image
    ){
      initInpaintCanvasFromFile(file)
        .catch(
          e=>setStatus(
            `Mask error: ${e.message}`
          )
        );
    }
  }
}

function initInpaintCanvasFromFile(file){
  return new Promise(
    (resolve,reject)=>{
      if(!file)
        return reject(
          new Error(
            'Choose a source image first.'
          )
        );

      const img=new Image();

      img.onload=()=>{
        const canvas=
          $('#inpaint-mask-canvas');

        const preview=
          $('#mask-source-preview');

        if(!canvas||!preview){
          return reject(
            new Error(
              'Inpaint canvas is missing from the page.'
            )
          );
        }

        preview.src=img.src;

        preview.onload=()=>{
          const maxSide=1024;

          const scale=
            Math.min(
              1,
              maxSide/
                Math.max(
                  img.naturalWidth,
                  img.naturalHeight
                )
            );

          const w=
            Math.max(
              256,
              Math.round(
                img.naturalWidth*
                scale
              )
            );

          const h=
            Math.max(
              256,
              Math.round(
                img.naturalHeight*
                scale
              )
            );

          canvas.width=w;
          canvas.height=h;

          canvas.style.width='100%';
          canvas.style.height='100%';

          preview.style.width='100%';
          preview.style.height='auto';

          canvas
            .getContext('2d')
            .clearRect(
              0,
              0,
              w,
              h
            );

          inpaintState.image={
            width:w,
            height:h
          };

          inpaintState.drawing=false;

          resolve();
        };
      };

      img.onerror=()=>{
        reject(
          new Error(
            'Could not load source image.'
          )
        );
      };

      const reader=
        new FileReader();

      reader.onload=()=>{
        img.src=reader.result;
      };

      reader.onerror=()=>{
        reject(
          new Error(
            'Could not read source image.'
          )
        );
      };

      reader.readAsDataURL(file);
    }
  );
}

function getMaskPoint(e){
  const canvas=
    $('#inpaint-mask-canvas');

  const rect=
    canvas.getBoundingClientRect();

  return {
    x:
      (e.clientX-rect.left)*
      (canvas.width/rect.width),

    y:
      (e.clientY-rect.top)*
      (canvas.height/rect.height)
  };
}

function drawMaskAt(x,y){
  const canvas=
    $('#inpaint-mask-canvas');

  if(!canvas)
    return;

  const ctx=
    canvas.getContext('2d');

  const brush=
    Number(
      $('#inpaint-brush-size')?.value||
      55
    );

  ctx.fillStyle=
    'rgba(255,255,255,0.82)';

  ctx.beginPath();

  ctx.arc(
    x,
    y,
    brush/2,
    0,
    Math.PI*2
  );

  ctx.fill();
}

function drawMaskLine(x1,y1,x2,y2){
  const canvas=
    $('#inpaint-mask-canvas');

  if(!canvas)
    return;

  const ctx=
    canvas.getContext('2d');

  const brush=
    Number(
      $('#inpaint-brush-size')?.value||
      55
    );

  ctx.strokeStyle=
    'rgba(255,255,255,0.82)';

  ctx.lineWidth=brush;
  ctx.lineCap='round';
  ctx.lineJoin='round';

  ctx.beginPath();

  ctx.moveTo(x1,y1);
  ctx.lineTo(x2,y2);

  ctx.stroke();
}

function maskPointerDown(e){
  const canvas=
    $('#inpaint-mask-canvas');

  if(!canvas)
    return;

  e.preventDefault();

  inpaintState.drawing=true;

  const p=getMaskPoint(e);

  inpaintState.lastX=p.x;
  inpaintState.lastY=p.y;

  canvas.setPointerCapture?.(
    e.pointerId
  );

  drawMaskAt(
    p.x,
    p.y
  );
}

function maskPointerMove(e){
  if(!inpaintState.drawing)
    return;

  e.preventDefault();

  const p=getMaskPoint(e);

  drawMaskLine(
    inpaintState.lastX,
    inpaintState.lastY,
    p.x,
    p.y
  );

  inpaintState.lastX=p.x;
  inpaintState.lastY=p.y;
}

function maskPointerUp(){
  inpaintState.drawing=false;
}

function clearInpaintMask(){
  const canvas=
    $('#inpaint-mask-canvas');

  if(canvas){
    canvas
      .getContext('2d')
      .clearRect(
        0,
        0,
        canvas.width,
        canvas.height
      );
  }
}

function fillInpaintMask(){
  const canvas=
    $('#inpaint-mask-canvas');

  if(!canvas)
    return;

  const ctx=
    canvas.getContext('2d');

  ctx.fillStyle=
    'rgba(255,255,255,0.82)';

  ctx.fillRect(
    0,
    0,
    canvas.width,
    canvas.height
  );
}

function maskToDataURL(){
  const canvas=
    $('#inpaint-mask-canvas');

  if(!canvas)
    return '';

  const out=
    document.createElement('canvas');

  out.width=canvas.width;
  out.height=canvas.height;

  const ctx=
    out.getContext('2d');

  ctx.fillStyle='#000';

  ctx.fillRect(
    0,
    0,
    out.width,
    out.height
  );

  const data=
    canvas
      .getContext('2d')
      .getImageData(
        0,
        0,
        canvas.width,
        canvas.height
      );

  const od=
    ctx.getImageData(
      0,
      0,
      out.width,
      out.height
    );

  for(
    let i=0;
    i<data.data.length;
    i+=4
  ){
    const v=
      Math.round(
        255*
        (
          data.data[i+3]/
          255
        )
      );

    od.data[i]=v;
    od.data[i+1]=v;
    od.data[i+2]=v;
    od.data[i+3]=255;
  }

  ctx.putImageData(
    od,
    0,
    0
  );

  return out.toDataURL(
    'image/png'
  );
}


/* ========================= IMAGE EDIT ========================= */

async function editImage(){
  const prompt=
    $('#image-prompt').value.trim();

  const mode=
    $('#image-edit-mode').value;

  if(!prompt)
    return alert(
      'Enter a prompt'
    );

  const source=
    $('#source-image-file')
      ?.files?.[0];

  if(!source)
    return alert(
      'Choose a source image first.'
    );

  if(
    mode==='inpaint' &&
    !inpaintState.image
  ){
    await initInpaintCanvasFromFile(
      source
    );
  }

  const mask=
    mode==='inpaint'
      ?maskToDataURL()
      :'';

  if(
    mode==='inpaint' &&
    !mask
  ){
    return alert(
      'Paint the area you want to change first.'
    );
  }

  const button=
    $('#generate-image');

  button.disabled=true;

  setStatus(
    mode==='img2img'
      ?'Editing locally…'
      :'Inpainting locally…'
  );

  try{
    const payload={
      prompt,

      negative_prompt:
        $('#image-negative')
          .value
          .trim(),

      image_data:
        await fileToDataURL(
          source
        ),

      strength:
        Number(
          $('#image-strength').value
        ),

      steps:
        Number(
          $('#image-steps').value
        ),

      guidance:
        Number(
          $('#image-guidance').value
        ),

      seed:
        Number(
          $('#image-seed').value
        )
    };

    const endpoint=
      mode==='inpaint'
        ?'/api/images/inpaint'
        :'/api/images/img2img';

    if(mode==='inpaint'){
      payload.mask_data=mask;

      payload.strength=
        Math.max(
          payload.strength,
          0.55
        );
    }

    const result=
      await api(
        endpoint,
        {
          method:'POST',
          body:JSON.stringify(
            payload
          )
        }
      );

    $('#generated-image').src=
      result.url+
      '?t='+
      Date.now();

    $('#generated-image')
      .classList
      .remove('hidden');

    $('#image-placeholder')
      .classList
      .add('hidden');

    $('#image-actions')
      .classList
      .remove('hidden');

    setStatus(
      mode==='inpaint'
        ?'Inpaint completed successfully.'
        :'Image edited successfully.'
    );

  }catch(e){
    setStatus(
      `Editing failed: ${e.message}`
    );

  }finally{
    button.disabled=false;
  }
}


/* ========================= IMAGE GENERATION ========================= */

async function generateImage(){
  if(
    (
      $('#image-edit-mode')
        ?.value||
      'txt2img'
    )!=='txt2img'
  ){
    return editImage();
  }

  const prompt=
    $('#image-prompt')
      .value
      .trim();

  if(!prompt){
    alert('Enter a prompt');
    return;
  }

  const button=
    $('#generate-image');

  button.disabled=true;

  setStatus(
    'Generating locally…'
  );

  try{
    const result=
      await api(
        '/api/images/generate',
        {
          method:'POST',
          body:JSON.stringify({
            prompt,

            negative_prompt:
              $('#image-negative')
                .value
                .trim(),

            width:
              Number(
                $('#image-width').value
              ),

            height:
              Number(
                $('#image-height').value
              ),

            steps:
              Number(
                $('#image-steps').value
              ),

            guidance:
              Number(
                $('#image-guidance').value
              ),

            seed:
              Number(
                $('#image-seed').value
              )
          })
        }
      );

    $('#generated-image').src=
      result.url+
      '?t='+
      Date.now();

    $('#generated-image')
      .classList
      .remove('hidden');

    $('#image-placeholder')
      .classList
      .add('hidden');

    $('#image-actions')
      .classList
      .remove('hidden');

    setStatus(
      'Image generated successfully.'
    );

  }catch(e){
    setStatus(
      `Generation failed: ${e.message}`
    );

  }finally{
    button.disabled=false;
  }
}

function useGeneratedImageForCharacter(){
  const sel=
    $('#image-character-select');

  const selectedId=
    sel?.value
      ?Number(sel.value)
      :null;

  const character=
    state.characters.find(
      c=>c.id===selectedId
    )||
    state.activeCharacter;

  if(!character){
    alert(
      'Select a character to use this image for.'
    );

    return;
  }

  const src=
    $('#generated-image')
      .getAttribute('src')
      ?.split('?')[0];

  if(src)
    openCropModal(
      src,
      character.id
    );
}


/* ========================= WIRING ========================= */

function wire(){

  $$('.mode-btn').forEach(b=>{
    b.onclick=()=>{
      b.dataset.mode==='images'
        ?openImageStudio()
        :showMode(
          b.dataset.mode
        );
    };
  });

  $('#new-char-btn')?.addEventListener(
    'click',
    ()=>openCharModal()
  );

  $('#edit-char-btn')?.addEventListener(
    'click',
    ()=>state.activeCharacter&&
      openCharModal(
        state.activeCharacter
      )
  );

  $('#char-cancel-btn')?.addEventListener(
    'click',
    ()=>$('#char-modal')
      .classList
      .add('hidden')
  );

  $('#char-cancel-btn-bottom')?.addEventListener(
    'click',
    ()=>$('#char-modal')
      .classList
      .add('hidden')
  );

  $('#char-save-btn')?.addEventListener(
    'click',
    saveCharacter
  );

  $('#char-delete-btn')?.addEventListener(
    'click',
    deleteCharacter
  );

  $$('.editor-tab').forEach(b=>{
    b.addEventListener(
      'click',
      ()=>setEditorTab(
        b.dataset.tab
      )
    );
  });


  $('#manage-personas-btn')?.addEventListener(
    'click',
    openPersonaModal
  );

  $('#manage-character-personas-btn')?.addEventListener(
    'click',
    openPersonaModal
  );

  $('#assistant-persona-top')?.addEventListener(
    'click',
    openPersonaModal
  );

  $('#persona-close')?.addEventListener(
    'click',
    ()=>$('#persona-modal')
      .classList
      .add('hidden')
  );

  $('#persona-new')?.addEventListener(
    'click',
    ()=>{
      clearPersonaForm();
      $('#p-name').focus();
    }
  );

  $('#persona-save')?.addEventListener(
    'click',
    savePersona
  );

  $('#persona-select')?.addEventListener(
    'change',
    async e=>{
      state.activePersonaId=
        e.target.value
          ?+e.target.value
          :null;

      syncPersonaSelectors();

      if(
        state.assistantConversationId
      ){
        try{
          await api(
            `/api/assistant/conversations/${state.assistantConversationId}`,
            {
              method:'PUT',
              body:JSON.stringify({
                persona_id:
                  state.activePersonaId||
                  null
              })
            }
          );
        }catch(e){
          console.warn(e);
        }
      }
    }
  );

  $('#character-persona-select')?.addEventListener(
    'change',
    async e=>{
      state.activePersonaId=
        e.target.value
          ?+e.target.value
          :null;

      syncPersonaSelectors();

      await updateActiveConversationPersona();
    }
  );


  $('#new-conv-btn')?.addEventListener(
    'click',
    startCharacterConversation
  );

  $('#send-btn')?.addEventListener(
    'click',
    sendCharacter
  );

  $('#regen-btn')?.addEventListener(
    'click',
    regenerate
  );

  $('#continue-btn')?.addEventListener(
    'click',
    continueReply
  );

  $('#assistant-send')?.addEventListener(
    'click',
    sendAssistant
  );

  $('#new-assistant-btn')?.addEventListener(
    'click',
    createAssistantConversation
  );


  $('#lore-btn')?.addEventListener(
    'click',
    openLoreModal
  );

  $('#lore-close')?.addEventListener(
    'click',
    ()=>$('#lore-modal')
      .classList
      .add('hidden')
  );

  $('#lore-add')?.addEventListener(
    'click',
    addLore
  );


  $('#memory-btn')?.addEventListener(
    'click',
    openMemoryModal
  );

  $('#memory-close')?.addEventListener(
    'click',
    ()=>$('#memory-modal')
      .classList
      .add('hidden')
  );

  $('#memory-add')?.addEventListener(
    'click',
    addMemory
  );


  $('#model-manager-btn')?.addEventListener(
    'click',
    openModelModal
  );

  $('#model-close')?.addEventListener(
    'click',
    ()=>$('#model-modal')
      .classList
      .add('hidden')
  );


  $('#crop-avatar-btn')?.addEventListener(
    'click',
    ()=>openCropModal(
      $('#f-avatar').value.trim(),
      state.activeCharacter?.id||null
    )
  );

  $('#crop-generated-image')?.addEventListener(
    'click',
    ()=>{
      const src=
        $('#generated-image')
          .getAttribute('src')
          ?.split('?')[0];

      if(src)
        openCropModal(
          src,
          $('#image-character-select')
            ?.value||
          state.activeCharacter?.id||
          null
        );
    }
  );

  $('#crop-close')?.addEventListener(
    'click',
    ()=>$('#crop-modal')
      .classList
      .add('hidden')
  );

  $('#crop-cancel')?.addEventListener(
    'click',
    ()=>$('#crop-modal')
      .classList
      .add('hidden')
  );

  $('#crop-apply')?.addEventListener(
    'click',
    applyCrop
  );

  $('#crop-reset')?.addEventListener(
    'click',
    resetCrop
  );

  $('#crop-zoom')?.addEventListener(
    'input',
    e=>{
      cropState.scale=
        Number(e.target.value);

      renderCrop();
    }
  );

  $('#crop-stage')?.addEventListener(
    'pointerdown',
    cropPointerDown
  );

  $('#crop-stage')?.addEventListener(
    'pointermove',
    cropPointerMove
  );

  window.addEventListener(
    'pointerup',
    cropPointerUp
  );


  /* ========================= INPAINT CANVAS ========================= */

  $('#inpaint-mask-canvas')?.addEventListener(
    'pointerdown',
    maskPointerDown
  );

  $('#inpaint-mask-canvas')?.addEventListener(
    'pointermove',
    maskPointerMove
  );

  $('#inpaint-mask-canvas')?.addEventListener(
    'pointerup',
    maskPointerUp
  );

  $('#inpaint-mask-canvas')?.addEventListener(
    'pointercancel',
    maskPointerUp
  );

  $('#inpaint-clear')?.addEventListener(
    'click',
    clearInpaintMask
  );

  $('#inpaint-fill')?.addEventListener(
    'click',
    fillInpaintMask
  );


  /* ========================= IMAGE STUDIO ========================= */

  $('#load-image-model')?.addEventListener(
    'click',
    loadImageModel
  );

  $('#generate-image')?.addEventListener(
    'click',
    generateImage
  );

  $('#image-edit-mode')?.addEventListener(
    'change',
    updateImageEditUI
  );

  $('#image-strength')?.addEventListener(
    'input',
    updateImageEditUI
  );

  $('#source-image-file')?.addEventListener(
    'change',
    async e=>{
      const f=e.target.files?.[0];

      if(f){
        $('#source-image-preview').src=
          await fileToDataURL(f);

        $('#edit-source-preview')
          .classList
          .remove('hidden');

        inpaintState.image=null;

        if(
          $('#image-edit-mode')
            ?.value==='inpaint'
        ){
          try{
            await initInpaintCanvasFromFile(f);
          }catch(err){
            setStatus(
              `Mask error: ${err.message}`
            );
          }
        }
      }
    }
  );

  $('#regenerate-image')?.addEventListener(
    'click',
    generateImage
  );

  $('#use-character-image')?.addEventListener(
    'click',
    useGeneratedImageForCharacter
  );

  $('#image-character-select')?.addEventListener(
    'change',
    e=>{
      const c=
        state.characters.find(
          x=>x.id===
            Number(e.target.value)
        );

      if(c)
        state.activeCharacter=c;
    }
  );


  /* ========================= INPUTS ========================= */

  [
    '#assistant-input',
    '#composer-input'
  ].forEach(sel=>{
    const i=$(sel);

    if(!i)
      return;

    i.addEventListener(
      'input',
      ()=>autoGrow(i)
    );

    i.addEventListener(
      'keydown',
      e=>{
        if(
          e.key==='Enter' &&
          !e.shiftKey
        ){
          e.preventDefault();

          sel==='#assistant-input'
            ?sendAssistant()
            :sendCharacter();
        }
      }
    );
  });
}


/* ========================= STARTUP ========================= */

(async()=>{
  try{
    wire();

    await loadPersonas();

    await loadCharacters();

    await loadAssistantConversations();

    showMode('assistant');

  }catch(e){
    console.error(
      'newAIr startup error:',
      e
    );
  }
})();