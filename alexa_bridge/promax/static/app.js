'use strict';
let state = {csrf:'',cameras:[],status:{}};
const $ = id => document.getElementById(id);
const toast = message => { $('toast').textContent = message; $('toast').hidden = false; setTimeout(()=>$('toast').hidden=true,4200); };
async function api(path, method='GET', data=null) {
  const opt = {method, headers:{}};
  if (state.csrf) opt.headers['X-Bridge-CSRF'] = state.csrf;
  if (method !== 'GET') { opt.headers['Content-Type']='application/json'; opt.body=JSON.stringify(data||{}); }
  const res = await fetch(path,opt);
  const parsed = await res.json().catch(()=>({error:'Server did not return JSON'}));
  if(!res.ok) throw new Error(parsed.error||'Request failed');
  return parsed;
}
function button(label, fn, extra='') {const b=document.createElement('button');b.className='button '+extra;b.textContent=label;b.onclick=fn;return b;}
async function refresh() {
  try {state = await api('api/state');draw();maybeOpenWizard();}catch(e){toast('Could not reach the gateway: '+e.message);}
}
function draw() {
  $('count').textContent=state.cameras.length;
  $('online').textContent=Object.values(state.status).filter(s=>s.running).length;
  $('uptime').textContent=Math.floor(state.uptime_seconds/60)+' min';
  const root=$('cameras');root.replaceChildren();
  if(!state.cameras.length){const p=document.createElement('p');p.textContent='No cameras configured yet. Add your first RTSP camera.';root.append(p);return;}
  state.cameras.forEach(cam=>{
    const st=state.status[cam.slug]||{};
    const card=document.createElement('article');card.className='camera';
    const thumb=document.createElement('div');thumb.className='thumb';
    const placeholder=document.createElement('span');placeholder.textContent='◉ Camera snapshot';thumb.append(placeholder);
    const body=document.createElement('div');body.className='camera-body';
    const title=document.createElement('div');title.className='cam-title';
    const name=document.createElement('b');name.textContent=cam.name;
    const badge=document.createElement('span');badge.className='badge'+(st.running?' online':'');badge.textContent=st.running?'● STREAMING':'○ IDLE';title.append(name,badge);
    const meta=document.createElement('p');meta.className='meta';meta.textContent=cam.slug+' · '+cam.mode.toUpperCase()+(st.mode?' → '+st.mode:'')+' · '+(st.starts||0)+' starts';
    const actions=document.createElement('div');actions.className='actions';
    actions.append(
      button('Snapshot',async()=>{try{
        const r=await fetch('api/snapshot/'+cam.slug,{headers:{'X-Bridge-CSRF':state.csrf}});
        if(!r.ok)throw new Error('Snapshot unavailable');
        const url=URL.createObjectURL(await r.blob());const img=document.createElement('img');
        img.src=url;img.onload=()=>{thumb.replaceChildren(img);setTimeout(()=>URL.revokeObjectURL(url),30000);};
      }catch(e){toast(e.message);}}),
      button('Probe',async()=>{try{const p=await api('api/probe/'+cam.slug,'POST');toast(`${cam.name}: ${p.codec} / ${p.profile} — ${p.recommended_mode}`);}catch(e){toast(e.message);}}),
      button('Test HLS',async()=>{
        try{
          const result=await api('api/sign/'+cam.slug,'POST');
          const base=prompt('Local HLS base (e.g. http://127.0.0.1:8090). This generates a PRIVATE link:', 'http://127.0.0.1:8090');
          if(!base)return;
          if(!/^https?:\/\/[^\s]+$/.test(base)) throw new Error('Enter a valid local HLS base URL');
          await navigator.clipboard.writeText(base.replace(/\/$/,'')+result.path);
          toast('Signed playback URL copied (10-minute expiry). Keep it private.');
        }catch(e){toast(e.message);}
      }),
      button('Edit',()=>edit(cam)),
      button('⋯',async()=>{if(confirm('Delete '+cam.name+'?')){try{await api('api/cameras/'+cam.slug,'DELETE');refresh();}catch(e){toast(e.message);}}})
    );
    body.append(title,meta,actions);card.append(thumb,body);root.append(card);
  });
}
function edit(cam=null){const form=$('camera-form');form.reset();$('form-error').textContent='';
  if(cam){for(const k of ['slug','name','alexa_endpoint_id','mode','fps','width','height','bitrate_kbps']) form.elements[k].value=cam[k];form.elements.slug.readOnly=true;}
  else form.elements.slug.readOnly=false;
  $('editor').showModal();
}
$('new').onclick=()=>edit();$('close').onclick=()=>closeCameraEditor();$('cancel').onclick=()=>closeCameraEditor();
function closeCameraEditor(){ $('editor').close(); if(wizardCameraEditor){wizardCameraEditor=false;wizardStep=1;openWizard();} }

$('camera-form').onsubmit=async event=>{event.preventDefault();const f=event.target;const obj={};
  for(const k of ['slug','name','alexa_endpoint_id','mode','rtsp_url']) obj[k]=f.elements[k].value;
  for(const k of ['fps','width','height','bitrate_kbps']) obj[k]=Number(f.elements[k].value);
  try{await api('api/cameras','POST',obj);$('editor').close();toast('Camera saved');await refresh();
    if(wizardCameraEditor){wizardCameraEditor=false;wizardStep=2;openWizard();}
  }
  catch(e){$('form-error').textContent=e.message;}
};
$('map').onclick=async()=>{try{const map=await api('api/endpoint-map');await navigator.clipboard.writeText(JSON.stringify(map));toast('Endpoint map copied. Paste it into CAMERA_ENDPOINT_MAP_JSON.');}catch(e){toast(e.message);}};
$('key').onclick=async()=>{if(!confirm('The signing key grants temporary access to your streams. Only copy it into your private Lambda configuration. Continue?'))return;
  try{const val=await api('api/secret','POST',{confirm:'I_UNDERSTAND'});await navigator.clipboard.writeText(val.key);toast('Private signing key copied. Do not share this clipboard content.');}catch(e){toast(e.message);}};
refresh();setInterval(refresh,10000);

// The setup wizard is a browser-side guide. Secrets remain in the existing gateway store.
let wizardStep = 0;
let wizardCameraEditor = false;
let wizardInitialCheck = false;
const WIZARD_FLAG = 'alexa_bridge_pro_setup_seen_v1';
function wizardSeen(){try{return localStorage.getItem(WIZARD_FLAG)==='yes';}catch(e){return true;}}
function markWizardSeen(){try{localStorage.setItem(WIZARD_FLAG,'yes');}catch(e){ /* Browsers may block local storage. */ }}
function maybeOpenWizard(){
  if(wizardInitialCheck) return;
  wizardInitialCheck=true;
  if(state.cameras.length===0 && !wizardSeen()) openWizard();
}
function openWizard(){renderWizard();if(!$('setup-wizard').open)$('setup-wizard').showModal();}
function closeWizard(){markWizardSeen();$('setup-wizard').close();}
function copyWizardMap(){return api('api/endpoint-map').then(m=>navigator.clipboard.writeText(JSON.stringify(m))).then(()=>toast('Endpoint map copied. Keep this with your private Lambda configuration.'))}
function wizardButton(label, fn){return button(label,fn);}
function createWizardContent(){
  const root=$('wizard-content');root.replaceChildren();
  const addText=(tag,text,cls='')=>{const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;root.append(e);return e;};
  const actions=()=>{const e=document.createElement('div');e.className='inline-actions';root.append(e);return e;};
  if(wizardStep===0){
    addText('h3','Welcome to Alexa RTSP Bridge Pro');
    addText('p','This guide connects a running gateway, helps you add cameras, and prepares the separate Alexa configuration. No passwords are required here.');
    addText('p','Already running Docker? Your gateway is reachable and you can continue.', 'setup-ok');
    addText('p','Home Assistant Marketplace (or HACS on older versions) installs only the optional integration. Docker, HTTPS and the Alexa skill are configured separately.', 'setup-note');
    addText('p','Keep this management panel behind Home Assistant Ingress, a local SSH tunnel, or Cloudflare Access. Never expose an unprotected admin port.', 'setup-warning');
  } else if(wizardStep===1){
    addText('h3','Add your cameras');
    addText('p',`Configured cameras: ${state.cameras.length}. Start with one RTSP stream; you can add more after checking the connection.`);
    const a=actions(); a.append(wizardButton('+ Add a camera',()=>{
      $('setup-wizard').close();wizardCameraEditor=true;edit();
    }));
    if(state.cameras.length) addText('p','Existing cameras are preserved. You can continue to connection tests.', 'setup-ok');
    addText('p','Use the local RTSP address of your camera or NVR. Credentials are stored in the gateway data volume; the camera list never returns them.', 'setup-note');
  } else if(wizardStep===2){
    addText('h3','Verify your first stream');
    if(state.cameras.length===0){addText('p','Add a camera in the previous step to enable the connection test.');return;}
    addText('p','Choose a camera, check its codec and request a JPEG snapshot. HLS playback should also be tested from the Docker host.');
    const lab=addText('label','Camera');const sel=document.createElement('select');sel.id='wizard-camera';sel.className='wizard-input';
    state.cameras.forEach(c=>{const opt=document.createElement('option');opt.value=c.slug;opt.textContent=c.name+' ('+c.slug+')';sel.append(opt);});lab.append(sel);
    const result=addText('p','Waiting for a test…');result.id='wizard-test-result';
    const a=actions();
    a.append(wizardButton('Check RTSP codec',async()=>{
      result.textContent='Checking…';try{const c=await api('api/probe/'+sel.value,'POST');result.textContent=`${c.codec} / ${c.profile || 'unknown profile'} · ${c.width}×${c.height} · ${c.recommended_mode}`;}catch(e){result.textContent='Probe failed: '+e.message;}
    }));
    a.append(wizardButton('Get snapshot',async()=>{
      result.textContent='Capturing JPEG…';try{const r=await fetch('api/snapshot/'+sel.value,{headers:{'X-Bridge-CSRF':state.csrf}});if(!r.ok)throw new Error('JPEG unavailable');
        const img=document.createElement('img');const u=URL.createObjectURL(await r.blob());img.src=u;img.className='wizard-preview';img.alt='RTSP camera snapshot';img.onload=()=>setTimeout(()=>URL.revokeObjectURL(u),60000);root.querySelectorAll('.wizard-preview').forEach(x=>x.remove());root.append(img);result.textContent='Snapshot received.';
      }catch(e){result.textContent='Snapshot failed: '+e.message;}
    }));
    addText('p','The gateway serves signed HLS on its own port (8090 inside the container). A snapshot is not the same as verified Alexa playback.', 'setup-note');
  } else {
    addText('h3','Connect Alexa when you are ready');
    addText('p','Camera video is ready for local tests. Alexa requires additional account-linked configuration. The wizard does not change your existing Alexa skill.');
    const ul=document.createElement('ol');ul.className='setup-list';
    ['Publish the HLS port through HTTPS with a valid certificate; use a separate hostname from the Access-protected admin panel.',
     'Create or use a test Alexa Smart Home skill and test Lambda; do not overwrite a working production skill.',
     'Confirm each Alexa endpoint ID from Home Assistant discovery, then copy the endpoint mapping.',
     'Configure the shared HLS signing key privately in AWS Lambda and test playback on an Alexa device.'].forEach(s=>{const li=document.createElement('li');li.textContent=s;ul.append(li);});root.append(ul);
    const a=actions();a.append(wizardButton('Copy endpoint map',()=>copyWizardMap().catch(e=>toast(e.message))));
    const doc=document.createElement('a');doc.href='https://github.com/RenanEspinar/Alexa-RTSP-Bridge/blob/main/docs/GUIA_COMPLETA_ES.md';doc.target='_blank';doc.rel='noopener noreferrer';doc.textContent='Complete installation guide';a.append(doc);
    addText('p','Finishing this guide does not mean Alexa is configured or validated. Keep the old skill active until a separate test passes.', 'setup-warning');
  }
}
function renderWizard(){
  const progress=$('wizard-progress');progress.replaceChildren();
  for(let i=0;i<4;i++){const el=document.createElement('span');el.className='step'+(i<wizardStep?' finished':i===wizardStep?' active':'');el.setAttribute('aria-label',`Step ${i+1} of 4`);progress.append(el);}
  createWizardContent();
  $('wizard-back').disabled=wizardStep===0;
  $('wizard-next').textContent=wizardStep===3?'Finish local setup':'Continue';
}
$('setup-open').onclick=()=>{wizardStep=0;openWizard();};
$('setup-close').onclick=closeWizard;
$('wizard-back').onclick=()=>{wizardStep=Math.max(0,wizardStep-1);renderWizard();};
$('wizard-next').onclick=()=>{if(wizardStep===3){closeWizard();toast('Local setup guide completed. Alexa configuration is separate.');return;}wizardStep++;renderWizard();};
$('setup-wizard').addEventListener('close',markWizardSeen);
