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
    const meta=document.createElement('p');meta.className='meta';meta.textContent=cam.slug+' · '+cam.mode.toUpperCase()+(st.mode?' → '+st.mode:'')+' · AUDIO '+(cam.audio_mode==='aac'?'AAC':'OFF')+' · AI BOXES '+(cam.overlay_mode==='boxes'?'ON':'OFF')+' · '+(st.starts||0)+' starts' + (st.recoveries ? ' · '+st.recoveries+' recoveries' : '');
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
  if(cam){for(const k of ['slug','name','alexa_endpoint_id','mode','audio_mode','overlay_mode','fps','width','height','bitrate_kbps']) form.elements[k].value=cam[k];form.elements.slug.readOnly=true;}
  else form.elements.slug.readOnly=false;
  $('editor').showModal();
}
$('new').onclick=()=>edit();$('close').onclick=()=>closeCameraEditor();$('cancel').onclick=()=>closeCameraEditor();
function closeCameraEditor(){ $('editor').close(); if(wizardCameraEditor){wizardCameraEditor=false;wizardStep=1;openWizard();} }

$('camera-form').onsubmit=async event=>{event.preventDefault();const f=event.target;const obj={};
  for(const k of ['slug','name','alexa_endpoint_id','mode','audio_mode','overlay_mode','rtsp_url']) obj[k]=f.elements[k].value;
  for(const k of ['fps','width','height','bitrate_kbps']) obj[k]=Number(f.elements[k].value);
  try{await api('api/cameras','POST',obj);$('editor').close();toast('Camera saved');await refresh();
    if(wizardCameraEditor){wizardCameraEditor=false;wizardStep=2;openWizard();}
  }
  catch(e){$('form-error').textContent=e.message;}
};
$('map').onclick=async()=>{try{const map=await api('api/endpoint-map');await navigator.clipboard.writeText(JSON.stringify(map));toast('Endpoint map copied. Includes AAC only for audio-enabled cameras. Update your private Lambda variables.');}catch(e){toast(e.message);}};
$('key').onclick=async()=>{if(!confirm('The signing key grants temporary access to your streams. Only copy it into your private Lambda configuration. Continue?'))return;
  try{const val=await api('api/secret','POST',{confirm:'I_UNDERSTAND'});await navigator.clipboard.writeText(val.key);toast('Private signing key copied. Do not share this clipboard content.');}catch(e){toast(e.message);}};

// Guided setup for a fresh installation. No AWS or Cloudflare credentials are stored here.
const WIZARD_DATA_KEY = 'alexa_pro_wizard_v04_nonsecret';
const WIZARD_PROGRESS_KEY = 'alexa_pro_wizard_v04_steps';
const WIZARD_COUNT = 11;
const WIZARD_STEPS = [
  ['Antes de comenzar', 'Before you begin'],
  ['Agregar cámaras', 'Add your cameras'],
  ['Comprobar video', 'Check your video'],
  ['Preparar Home Assistant', 'Prepare Home Assistant'],
  ['HTTPS y Cloudflare', 'HTTPS and Cloudflare'],
  ['Crear Alexa Smart Home Skill', 'Create your Alexa Smart Home Skill'],
  ['Crear AWS Lambda', 'Create AWS Lambda'],
  ['Conectar Lambda y cámaras', 'Connect Lambda and cameras'],
  ['Vincular cuentas OAuth', 'Set up OAuth account linking'],
  ['Probar Alexa de verdad', 'Test Alexa end to end'],
  ['Resumen y siguientes pasos', 'Summary and next steps']
];
const OFFICIAL = {
  ha: 'https://www.home-assistant.io/integrations/alexa.smart_home/',
  haCamera: 'https://www.home-assistant.io/integrations/ffmpeg/',
  haMarket: 'https://www.home-assistant.io/integrations/marketplace/',
  cloud: 'https://developers.cloudflare.com/tunnel/get-started/',
  access: 'https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/',
  alexa: 'https://developer.amazon.com/alexa/console/ask',
  skillDocs: 'https://developer.amazon.com/en-US/alexa/devices/connected-devices/development-resources/smart-home-skills',
  aws: 'https://console.aws.amazon.com/lambda/',
  iam: 'https://console.aws.amazon.com/iam/',
  lambdaDoc: 'https://docs.aws.amazon.com/lambda/latest/dg/python-package.html',
  envDoc: 'https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html',
  source: 'https://github.com/RenanEspinar/Alexa-RTSP-Bridge/blob/main/aws/lambda_function.py',
  manual: 'https://github.com/RenanEspinar/Alexa-RTSP-Bridge/blob/main/docs/WIZARD_DESDE_CERO_ES.md',
  manualEn: 'https://github.com/RenanEspinar/Alexa-RTSP-Bridge/blob/main/docs/START_FROM_ZERO_EN.md'
};
function loadWizardObject(key, fallback) {
  try { const v = JSON.parse(localStorage.getItem(key)); return v && typeof v === 'object' ? v : fallback; }
  catch (_) { return fallback; }
}
let wizardData = loadWizardObject(WIZARD_DATA_KEY, {lang:'es', ha:'', hls:'', skill:'', arn:'', region:'us'});
let wizardDone = loadWizardObject(WIZARD_PROGRESS_KEY, {});
let wizardStep = 0, wizardCameraEditor = false, wizardInitialCheck = false;
let wizardTest = {probe:false, snapshot:false, hls:false};
function w(es, en) { return wizardData.lang==='en' ? en : es; }
function wizardSave() {
  try {
    const allowed = {lang:wizardData.lang,ha:wizardData.ha,hls:wizardData.hls,skill:wizardData.skill,arn:wizardData.arn,region:wizardData.region};
    localStorage.setItem(WIZARD_DATA_KEY, JSON.stringify(allowed));
    localStorage.setItem(WIZARD_PROGRESS_KEY, JSON.stringify(wizardDone));
  } catch (_) { /* Private browsing may disable local storage. */ }
}
function wn(tag, content, className) {
  const el = document.createElement(tag);
  if (content!==undefined && content!==null) el.textContent = content;
  if (className) el.className = className;
  return el;
}
function wp(text, className) {const e=wn('p',text,className);$('wizard-content').append(e);return e;}
function wh(text){const e=wn('h3',text);$('wizard-content').append(e);return e;}
function wa(url,label){const a=wn('a',label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}
function wlinks(items) { const d=wn('div',null,'wizard-links');items.forEach(([url,text])=>d.append(wa(url,text)));$('wizard-content').append(d); }
function wbutton(text,callback,alt='') {const b=button(text,callback,alt);b.type='button';return b;}
function wactions() {const d=wn('div',null,'inline-actions');$('wizard-content').append(d);return d;}
function wlist(items) {const e=wn('ol',null,'setup-list');items.forEach(x=>e.append(wn('li',x)));$('wizard-content').append(e);}
function wcode(label,makeValue) {
  const group=wn('section',null,'wizard-copy');
  group.append(wn('b',label));
  const text=wn('code',makeValue());group.append(text);
  group.append(wbutton(w('Copiar','Copy'), async()=>{
    try {await navigator.clipboard.writeText(makeValue());toast(w('Copiado. Pégalo solo en la consola correspondiente.','Copied. Paste only into the appropriate console.'));}
    catch (e) {toast(w('No se pudo copiar. Selecciona el texto manualmente.','Clipboard unavailable. Select the text manually.'));}
  }));
  $('wizard-content').append(group);
}
function wfield(label,key,placeholder='https://example.com',help='') {
  const wrap=wn('label',label,'wizard-field');
  const input=wn('input');input.type='text';input.autocomplete='off';input.placeholder=placeholder;input.value=wizardData[key]||'';input.spellcheck=false;
  input.addEventListener('change',()=>{let v=input.value.trim();
    if ((key==='ha'||key==='hls') && v && (!/^https:\/\/[a-z0-9.-]+(?::443)?\/?$/i.test(v) || /\.\.|localhost|127\.0\.0\.1/i.test(v))) {
      toast(w('Usa un dominio HTTPS público, sin ruta ni credenciales.','Use a public HTTPS hostname with no path or credentials.'));return;
    }
    wizardData[key]=v.replace(/\/$/,'');wizardSave();
  });wrap.append(input);
  if(help) wrap.append(wn('small',help));$('wizard-content').append(wrap);
  return input;
}
function wcheckManual() {
  if(wizardStep===WIZARD_COUNT-1)return;
  const check=wn('label',null,'wizard-verify');const cb=wn('input');cb.type='checkbox';cb.checked=Boolean(wizardDone[wizardStep]);
  cb.onchange=()=>{wizardDone[wizardStep]=cb.checked;wizardSave();renderWizard();};
  check.append(cb,wn('span',w('Realicé este paso y comprobé su resultado (confirmación manual).','I completed this step and checked its result (manual confirmation).')));
  $('wizard-content').append(check);
}
function wizardSeen(){try{return localStorage.getItem('alexa_bridge_pro_setup_seen_v1')==='yes';}catch(_){return true;}}
function markWizardSeen(){try{localStorage.setItem('alexa_bridge_pro_setup_seen_v1','yes');}catch(_){}}
function maybeOpenWizard(){if(wizardInitialCheck)return;wizardInitialCheck=true;if(state.cameras.length===0&&!wizardSeen())openWizard();}
function openWizard(){renderWizard();if(!$('setup-wizard').open)$('setup-wizard').showModal();}
function closeWizard(){markWizardSeen();$('setup-wizard').close();}
function publicMap(){return api('api/endpoint-map');}
async function copyWizardMap(){const m=await publicMap();await navigator.clipboard.writeText(JSON.stringify(m));toast(w('Mapa copiado. Verifica los endpointId reales de Alexa.','Map copied. Verify the actual Alexa endpointIds.'));}
function getHABase(){return (wizardData.ha||'https://YOUR-HA-DOMAIN').replace(/\/$/,'');}
function getHLSBase(){return (wizardData.hls||'https://YOUR-HLS-DOMAIN').replace(/\/$/,'');}
function wStepContent(){
  const root=$('wizard-content');root.replaceChildren();
  switch(wizardStep){
    case 0: {
      wh(w('Instalación desde cero: sin conocimientos de programación','Fresh install: no programming experience required'));
      wp(w('Este asistente te acompaña desde la primera cámara hasta pedirle a Alexa que la muestre. Las cuentas de Amazon, AWS y Cloudflare se crean en sus sitios oficiales; no nos entregas sus contraseñas.','This assistant takes you from your first camera to Alexa playback. You create your Amazon, AWS and Cloudflare accounts on their official websites; never share their passwords with this app.'));
      wp(w('Necesitarás: un Home Assistant accesible por HTTPS, al menos una cámara RTSP, Docker o Home Assistant OS, una cuenta Amazon Developer, una cuenta AWS y una forma de publicar HLS por HTTPS.','You need: Home Assistant reachable over HTTPS, an RTSP camera, Docker or HA OS, Amazon Developer and AWS accounts, and an HTTPS route for HLS.'),'setup-note');
      wp(w('El gateway ya responde: estás viendo su panel web. Marketplace/HACS añade la integración opcional a Home Assistant; no crea Docker, Lambda ni la Skill.','The gateway is responding: you are looking at its web dashboard. Marketplace/HACS installs an optional Home Assistant integration, not Docker, Lambda or the Skill.'),'setup-ok');
      wlinks([[OFFICIAL.manual,w('Manual completo en español','Full Spanish manual')],[OFFICIAL.manualEn,'English guide'],[OFFICIAL.haMarket,'Home Assistant Marketplace']]);
      break;
    }
    case 1: {
      wh(w('Agrega tu primera cámara RTSP','Add your first RTSP camera'));
      wp(w(`Cámaras registradas: ${state.cameras.length}. Solo necesitas una para continuar.`,`${state.cameras.length} cameras already registered. You only need one to continue.`),'setup-ok');
      wlist(wizardData.lang==='en' ? ['Find the RTSP URL in your camera or NVR settings.','Enter its private IP, user, password and stream path in Add camera.','Leave Video mode on Auto and Audio OFF initially; save the camera.'] : ['Busca la URL RTSP en tu cámara o grabador NVR.','Pulsa Agregar cámara e introduce la IP local, usuario, contraseña y canal.','Deja Video mode en Auto y Audio OFF al principio. Activa AAC solo si la cámara tiene micrófono.']);
      wactions().append(wbutton(w('+ Agregar cámara','+ Add camera'),()=>{$('setup-wizard').close();wizardCameraEditor=true;edit();}));
      wp(w('Audio OFF transmite solo video. Audio AAC añade el micrófono; puede requerir actualizar Lambda y no garantiza que la música de Fire TV siga sonando.','Audio OFF carries video only. AAC adds microphone sound but requires Lambda matching and cannot guarantee Fire TV music keeps playing.'),'setup-note');
      wp(w('Las contraseñas RTSP quedan en el volumen privado del gateway. Nunca las pegues en GitHub ni en un comentario público.','RTSP credentials stay in the private gateway volume. Never post them on GitHub or public forums.'),'setup-warning');
      break;
    }
    case 2: {
      wh(w('Comprueba una cámara automáticamente','Run camera checks automatically'));
      if(!state.cameras.length){wp(w('Primero agrega una cámara en el paso anterior.','Add a camera in the previous step first.'),'setup-warning');break;}
      const label=wn('label',w('Cámara de prueba','Camera to test'));
      const sel=wn('select');sel.id='wizard-camera';sel.className='wizard-input';
      state.cameras.forEach(c=>{const opt=wn('option',c.name+' ('+c.slug+')');opt.value=c.slug;sel.append(opt);});label.append(sel);root.append(label);
      const result=wp(w('Sin pruebas todavía.','No tests run yet.'));result.id='wizard-test-result';
      const a=wactions();
      a.append(wbutton(w('1. Detectar códec','1. Detect codec'),async()=>{
        result.textContent=w('Analizando RTSP...','Probing RTSP...');
        try {const c=await api('api/probe/'+sel.value,'POST');result.textContent=`${c.codec} / ${c.profile||'?'} · ${c.width}×${c.height} · ${c.recommended_mode}`;wizardTest.probe=true;}
        catch(e){result.textContent=e.message;wizardTest.probe=false;}
      }));
      a.append(wbutton(w('2. Capturar JPEG','2. Capture JPEG'),async()=>{
        result.textContent=w('Capturando imagen...','Capturing image...');
        try {const r=await fetch('api/snapshot/'+sel.value,{headers:{'X-Bridge-CSRF':state.csrf}});
          if(!r.ok)throw new Error('HTTP '+r.status);
          const img=wn('img');const u=URL.createObjectURL(await r.blob());img.src=u;img.alt='RTSP snapshot';img.className='wizard-preview';img.onload=()=>setTimeout(()=>URL.revokeObjectURL(u),60000);
          root.querySelectorAll('.wizard-preview').forEach(x=>x.remove());root.append(img);result.textContent=w('Snapshot JPEG recibido.','JPEG snapshot received.');wizardTest.snapshot=true;
        }catch(e){result.textContent=e.message;wizardTest.snapshot=false;}
      }));
      a.append(wbutton(w('3. Comprobar HLS','3. Check HLS'),async()=>{
        result.textContent=w('Esperando el primer segmento HLS...','Waiting for the first HLS segment...');
        try{const r=await api('api/check-hls/'+sel.value,'POST');result.textContent=w(`HLS correcto: ${r.segment_bytes} bytes en ${r.elapsed_s} s. No se ha probado Alexa.`,`HLS OK: ${r.segment_bytes} bytes in ${r.elapsed_s} s. Alexa is not tested yet.`);wizardTest.hls=true;}
        catch(e){result.textContent=w('Error HLS: ','HLS error: ')+e.message;wizardTest.hls=false;}
      }));
      wp(w('Detectar una imagen y un segmento HLS no demuestra que Alexa pueda reproducirlos: eso se verificará en el último paso.','A snapshot and an HLS segment do not prove Alexa playback. You will test that at the end.'),'setup-note');
      break;
    }
    case 3: {
      wh(w('Prepara Home Assistant','Prepare Home Assistant'));
      wlist(wizardData.lang==='en' ? ['Open Home Assistant and confirm you can log in through a public HTTPS address.','Make sure the camera exists as a Home Assistant camera entity, such as camera.front_door.','Enable the Alexa Smart Home configuration and expose only the intended entities. Check YAML configuration and restart if required.'] : ['Abre Home Assistant y comprueba que puedes iniciar sesión desde una dirección HTTPS pública.','Confirma que tu cámara aparece como entidad, por ejemplo camera.entrada.','Activa Alexa Smart Home y expón solamente las entidades que deseas controlar. Valida el YAML y reinicia si corresponde.']);
      wfield(w('URL pública de Home Assistant (sin / al final)','Public Home Assistant URL'),'ha','https://ha.example.com',w('No pegues tokens ni contraseñas.','Do not enter tokens or passwords.'));
      wcode('configuration.yaml',()=> 'alexa:\n  smart_home:\n    filter:\n      include_entities:\n        - camera.REEMPLAZAR_CON_ENTIDAD_REAL');
      wp(w('Si ya tienes un bloque alexa:, edítalo; NO agregues una segunda clave alexa: al YAML. Sustituye el identificador por el de tu cámara.','If you already have an alexa: section, edit it. Do not add a duplicate YAML key. Replace the camera entity ID.'),'setup-warning');
      wlinks([[OFFICIAL.ha,w('Guía oficial Home Assistant + Alexa','Official Home Assistant + Alexa guide')],[OFFICIAL.haCamera,'Home Assistant FFmpeg cameras']]);
      break;
    }
    case 4: {
      wh(w('Publica HLS con HTTPS, sin exponer el panel','Publish HLS over HTTPS without exposing the dashboard'));
      wlist(wizardData.lang==='en' ? ['Create a Cloudflare account and add your domain.','Create a Tunnel, install cloudflared on the gateway host and wait for Healthy.','Publish an HLS hostname pointing to the HOST media port (usually http://127.0.0.1:18090 if cloudflared runs on Ubuntu).','Keep the ADMIN hostname protected by Cloudflare Access: email-only policy. The media hostname must not require an interactive login.'] : ['Crea tu cuenta Cloudflare y añade un dominio propio.','En Networking → Tunnels, crea un túnel, instala cloudflared en el servidor y espera a que esté Healthy.','Publica un hostname exclusivo para HLS que apunte al puerto de medios del HOST (habitualmente http://127.0.0.1:18090 si cloudflared corre en Ubuntu).','Protege el hostname del panel con Cloudflare Access limitado a tu correo. El hostname HLS NO debe exigir inicio de sesión interactivo.']);
      wfield(w('Dirección HTTPS pública del VIDEO, distinta del panel','Public HTTPS VIDEO hostname, separate from admin'),'hls','https://hls.example.com');
      wp(w('Si cloudflared está en otro contenedor, 127.0.0.1 apunta a ese contenedor. Consulta la guía para resolver la red de Docker.','If cloudflared runs in another container, 127.0.0.1 refers to that container. Use an appropriate private Docker network.'),'setup-warning');
      wcode(w('Verificación del HLS sin firma (403 esperado)','Unsigned HLS check (403 expected)'),()=>`curl -sS -o /dev/null -w '%{http_code}\\n' '${getHLSBase()}/s/test'`);
      wp(w('403 es correcto para una URL sin firma. Un 302 hacia Cloudflare Access es incorrecto para el reproductor Alexa; un 200 inesperado requiere revisar la protección.','403 is expected for unsigned media. A 302 to Cloudflare Access will block Alexa; an unexpected 200 needs investigation.'),'setup-note');
      wlinks([[OFFICIAL.cloud,'Cloudflare Tunnel — guía oficial'],[OFFICIAL.access,'Cloudflare Access — panel privado']]);
      break;
    }
    case 5: {
      wh(w('Crea la Skill de Alexa desde cero','Create an Alexa Smart Home Skill from scratch'));
      wlist(wizardData.lang==='en' ? ['Open Alexa Developer Console with the SAME Amazon account used by your Alexa devices.','Select Create Skill, choose a name and your Alexa language/locale.','Select Smart Home (not Custom) and Provision your own hosting.','Verify payload version v3; copy the Skill ID. Keep the console tab open.'] : ['Abre Amazon Developer Console con la MISMA cuenta de Amazon que utilizas en tus dispositivos Alexa.','Pulsa Create Skill, ponle un nombre y selecciona el idioma de tus dispositivos.','Selecciona Smart Home (NO Custom) y Provision your own hosting.','Comprueba Payload version v3 y copia el Skill ID. Mantén la pestaña abierta.']);
      wfield('Skill ID (amzn1.ask.skill.…)', 'skill','amzn1.ask.skill.00000000-0000-0000-0000-000000000000');
      wp(w('La Skill todavía no funciona. Primero necesitamos desplegar Lambda y enlazar cuentas.','The Skill is not ready yet. Next, deploy Lambda and configure account linking.'),'setup-note');
      wlinks([[OFFICIAL.alexa,'Abrir Alexa Developer Console'],[OFFICIAL.skillDocs,'Smart Home Skill — documentación Amazon']]);
      break;
    }
    case 6: {
      wh(w('Crea tu función AWS Lambda','Create your AWS Lambda function'));
      wlist(wizardData.lang==='en' ? ['Sign in to AWS; review billing and budgets first.','Go to IAM → Roles → Create role → AWS service → Lambda. Assign AWSLambdaBasicExecutionRole only.','Go to Lambda → Create function → Author from scratch, choose Python 3.13 (or a supported Python 3.x), and select your new IAM role.','Choose an AWS region supported for your Alexa skill locale (see the Home Assistant reference).','In Code, replace lambda_function.py with the project code and choose Deploy.','Add the Alexa Smart Home trigger limited to your Skill ID. Copy the Lambda ARN.'] : ['Inicia sesión en AWS y revisa primero los presupuestos y límites de facturación.','En IAM → Roles → Create role → AWS service → Lambda, crea un rol con AWSLambdaBasicExecutionRole únicamente.','En Lambda → Create function → Author from scratch, selecciona Python 3.13 (u otra versión 3.x compatible) y el rol anterior.','Elige una región AWS compatible con el idioma de tu Skill (consulta la tabla oficial).','En Code, reemplaza lambda_function.py por el código de nuestro repositorio y pulsa Deploy.','Añade el trigger Alexa Smart Home, restringido a tu Skill ID. Copia el ARN de Lambda.']);
      wfield('Lambda ARN (arn:aws:lambda:...)','arn','arn:aws:lambda:us-east-1:123456789012:function:alexa-rtsp-bridge');
      wcode(w('Nombre del archivo y handler','Filename and handler'),()=> 'lambda_function.py  →  lambda_function.lambda_handler');
      wlinks([[OFFICIAL.aws,'Abrir AWS Lambda'],[OFFICIAL.iam,'Abrir AWS IAM'],[OFFICIAL.source,'Código de Lambda — GitHub'],[OFFICIAL.lambdaDoc,'AWS — Cómo subir Python']]);
      wp(w('El despliegue en tu cuenta AWS requiere tu autorización. El gateway jamás necesita tus claves de acceso AWS.','Deployment to your AWS account requires your authorization. The gateway never needs your AWS access keys.'),'setup-warning');
      break;
    }
    case 7: {
      wh(w('Configura las variables de Lambda','Set your Lambda environment variables'));
      wlist(wizardData.lang==='en' ? ['In AWS Lambda → Configuration → Environment variables, add the four values shown below.','The camera endpoint mapping must contain EXACT Alexa endpointIds from discovery, not guessed names.','Copy the gateway signing key privately; do not screenshot, log or paste it into GitHub.','Select Save, then return to Alexa Developer Console and set the Skill default endpoint to your Lambda ARN.'] : ['En AWS Lambda → Configuration → Environment variables agrega las cuatro variables siguientes.','El mapa de cámaras debe usar los endpointId EXACTOS descubiertos por Alexa; no inventes nombres.','Copia la clave de firma de forma privada: no la publiques ni la muestres en capturas.','Guarda y vuelve a Alexa Developer Console para colocar el ARN de Lambda en Default endpoint.']);
      wcode('HOME_ASSISTANT_URL',getHABase);
      wcode('ALEXA_HLS_BASE',getHLSBase);
      const a=wactions();a.append(wbutton('CAMERA_ENDPOINT_MAP_JSON — '+w('Copiar mapa','Copy mapping'),()=>copyWizardMap().catch(e=>toast(e.message))));
      a.append(wbutton('HLS_SIGNING_KEY — '+w('Copiar secreto','Copy secret'),async()=>{
        if(!confirm(w('Esta clave permite firmar acceso a tus videos. Cópiala solo en AWS Lambda y no la compartas. ¿Continuar?','This key can sign camera stream URLs. Copy it only into AWS Lambda. Continue?')))return;
        try {const r=await api('api/secret','POST',{confirm:'I_UNDERSTAND'});await navigator.clipboard.writeText(r.key);toast(w('Clave privada copiada. Guárdala exclusivamente en AWS.','Private signing key copied. Paste it only into AWS.'));}
        catch(e){toast(e.message);}
      }));
      wp(w('IMPORTANTE: si el mapa está vacío, debes descubrir primero los ID de las cámaras en Alexa; las entidades de Home Assistant no siempre coinciden con los endpointId.','IMPORTANT: If the map is empty, discover the real Alexa endpointIds first; Home Assistant entity IDs are not always identical.'),'setup-warning');
      wlinks([[OFFICIAL.envDoc,'AWS Lambda — Variables de entorno'],[OFFICIAL.manual,'Guía — Discovery y mapeo']]);
      break;
    }
    case 8: {
      wh(w('Vincula Alexa con Home Assistant por OAuth','Link Alexa to Home Assistant with OAuth'));
      wlist(wizardData.lang==='en' ? ['In Alexa Developer Console open ACCOUNT LINKING and enable linking.','Use Authorization Code Grant and Credentials in request body; do not use HTTP Basic.','Enter the Authorization URI, Access Token URI, Client ID, Client Secret and scope below.','Choose the Client ID for your Alexa account geography (US/BR, EU or JP/AU), not merely your physical location.','Save. Test account linking in the Alexa mobile app; do not paste OAuth tokens here.'] : ['En Alexa Developer Console abre ACCOUNT LINKING y activa la vinculación.','Selecciona Authorization Code Grant y Credentials in request body; no utilices HTTP Basic.','Introduce Authorization URI, Access Token URI, Client ID, Client Secret y scope.','Elige Client ID según la región de tu cuenta Alexa (EE. UU./Brasil, Europa o Japón/Australia), no solamente tu ubicación física.','Guarda. La vinculación se prueba desde la app Alexa; nunca pegues tokens OAuth aquí.']);
      wcode('Authorization URI',()=>getHABase()+'/auth/authorize');
      wcode('Access Token URI',()=>getHABase()+'/auth/token');
      const selectLabel=wn('label',w('Región de tu cuenta Alexa / Client ID','Alexa account region / Client ID'));
      const select=wn('select');[['us','América / Brasil'],['eu','Europa'],['jp','Japón / Australia (verificar)']].forEach(([value,label])=>{const o=wn('option',label);o.value=value;select.append(o);});select.value=wizardData.region||'us';select.onchange=()=>{wizardData.region=select.value;wizardSave();renderWizard();};selectLabel.append(select);root.append(selectLabel);
      wcode('Client ID',()=>wizardData.region==='eu'?'https://layla.amazon.com/':wizardData.region==='jp'?'https://alexa.amazon.co.jp/':'https://pitangui.amazon.com/');
      wcode('Scope',()=> 'smart_home');
      wp(w('Client Secret: establece un valor privado en el formulario de Amazon según la guía de Home Assistant. No lo guardamos aquí. NO confundas ese campo con HLS_SIGNING_KEY.','Client Secret: set a private value in the Amazon form as described by Home Assistant. We do not store it. It is NOT the HLS signing key.'),'setup-note');
      wlinks([[OFFICIAL.ha,'Home Assistant — Account linking'],[OFFICIAL.alexa,'Alexa Developer Console']]);
      break;
    }
    case 9: {
      wh(w('Comprueba la instalación completa con Alexa','Validate real Alexa playback'));
      wlist(wizardData.lang==='en' ? ['In the Alexa app: More → Skills & Games → Your Skills → Dev.','Enable your new Skill and sign in to Home Assistant when prompted.','Ask Alexa to discover devices; verify the camera appears.','Say “Alexa, show [camera name]” on a Fire TV or Echo Show.','Confirm visible video, not just a JPEG; inspect Lambda logs and gateway status if it fails.'] : ['En la app Alexa: Más → Skills y juegos → Tus Skills → Dev.','Activa tu Skill nueva e inicia sesión en Home Assistant cuando se solicite.','Pide «Alexa, descubre dispositivos» y confirma que aparece la cámara.','Di «Alexa, muéstrame [nombre de la cámara]» en Fire TV o Echo Show.','Confirma video en movimiento, no solo una fotografía. Si falla, revisa logs de Lambda y del gateway.']);
      wp(w('Si Alexa descubre la cámara pero no muestra video: revisa que la URL HLS sea HTTPS, que el túnel no exija Access, que la firma coincida y que el segmento H.264 MPEG-TS sea reproducible.','If Alexa discovers a camera but shows no video, check HTTPS reachability, Access on the media hostname, matching signatures and H.264 MPEG-TS.'),'setup-warning');
      wlinks([[OFFICIAL.manual,w('Solución de problemas completa','Full troubleshooting')],[OFFICIAL.ha,'Home Assistant — Alexa troubleshooting']]);
      break;
    }
    default: {
      wh(w('Tu hoja de ruta: lo que realmente quedó configurado','Your installation status: what was actually completed'));
      const total=Object.keys(wizardDone).filter(k=>Number(k)<10&&wizardDone[k]).length;
      wp(w(`${total} de 10 etapas marcadas como completadas. Estas marcas son declaraciones del usuario; no son verificaciones automáticas de AWS/Alexa.`,`${total} of 10 steps marked complete. These checkmarks are manual, not automatic verification of AWS or Alexa.`),'setup-note');
      const list=wn('ul',null,'wizard-summary');
      WIZARD_STEPS.slice(0,10).forEach((titles,i)=>{const li=wn('li',(wizardDone[i]?'✓ ':'○ ')+titles[wizardData.lang==='en'?1:0]);list.append(li);});root.append(list);
      wp(w('Cuando puedas abrir una cámara con una orden de voz y ver video continuo, habrás validado también el recorrido de extremo a extremo. Conserva copias de seguridad y no publiques secretos.','Once a voice request actually plays moving video, you have verified the end-to-end path. Keep backups and never publish secrets.'));
      wlinks([[OFFICIAL.manual,w('Manual completo','Full guide')],[OFFICIAL.manualEn,'English guide']]);
    }
  }
  wcheckManual();
}
function renderWizard(){
  const progress=$('wizard-progress');progress.replaceChildren();
  for(let i=0;i<WIZARD_COUNT;i++){
    const el=wn('span',null,'step'+(wizardDone[i]?' finished':i===wizardStep?' active':''));
    el.title=WIZARD_STEPS[i][wizardData.lang==='en'?1:0];progress.append(el);
  }
  let h=$('wizard-step-label');if(!h){h=wn('div',null,'wizard-step-label');h.id='wizard-step-label';progress.before(h);}
  h.textContent=w(`Paso ${wizardStep+1} de ${WIZARD_COUNT}`,`Step ${wizardStep+1} of ${WIZARD_COUNT}`);
  let switcher=$('wizard-language');
  if(!switcher){switcher=wn('select');switcher.id='wizard-language';switcher.setAttribute('aria-label','Language / Idioma');
    const a=wn('option','Español');a.value='es';const b=wn('option','English');b.value='en';switcher.append(a,b);
    $('setup-wizard').querySelector('.modalhead').append(switcher);
    switcher.onchange=()=>{wizardData.lang=switcher.value;wizardSave();renderWizard();};
  }
  switcher.value=wizardData.lang;
  $('wizard-title').textContent=w('Instalar Alexa RTSP Bridge','Install Alexa RTSP Bridge');
  wStepContent();
  $('wizard-back').disabled=wizardStep===0;
  $('wizard-back').textContent=w('Atrás','Back');
  $('wizard-next').textContent=wizardStep===WIZARD_COUNT-1?w('Cerrar asistente','Close wizard'):w('Continuar','Continue');
}
$('setup-open').onclick=()=>{wizardStep=0;openWizard();};
$('setup-close').onclick=closeWizard;
$('wizard-back').onclick=()=>{wizardStep=Math.max(0,wizardStep-1);renderWizard();};
$('wizard-next').onclick=()=>{
  if(wizardStep===WIZARD_COUNT-1){closeWizard();return;}
  wizardStep++;renderWizard();
};
$('setup-wizard').addEventListener('close',markWizardSeen);
refresh();setInterval(refresh,10000);


// Diagnostics are isolated from the setup wizard and do not poll RTSP sources.
let diagActive = false;
const pretty = value => value == null ? '—' : String(value);
function makeDiagNode(tag, text, cls='') {
  const el = document.createElement(tag);
  el.textContent = text;
  if (cls) el.className = cls;
  return el;
}
async function loadDiagnostics(){
  if (!diagActive) return;
  const summary = $('diagnostics-summary');
  summary.textContent = 'Reading gateway metrics…';
  try {
    const data = await api('api/diagnostics');
    const sys = data.system || {};
    summary.textContent = `Active streams: ${data.active} · CPU: ${pretty(sys.cpu_percent_one_core)}% of one logical core · RAM: ${pretty(sys.memory_mib)} MiB · Watchdog: ${data.watchdog_enabled ? 'on' : 'off'}`;
    const cameras = $('diagnostics-cameras');
    cameras.replaceChildren();
    state.cameras.forEach(cam=>{
      const st = (data.cameras || {})[cam.slug] || {};
      const card = document.createElement('article');card.className='diag-camera';
      card.append(makeDiagNode('strong',cam.name));
      card.append(makeDiagNode('p', `Audio ${cam.audio_mode === 'aac'?'AAC':'OFF'} · ${st.running?'STREAMING':'IDLE'} · Starts ${st.starts||0} · Recoveries ${st.recoveries||0} · Stalls ${st.stalls||0} · Segment age ${pretty(st.segment_age_seconds)} s · Cooldown ${st.cooldown_seconds||0} s`));
      if (st.last_error) card.append(makeDiagNode('p','Last issue: '+st.last_error,'diag-warning'));
      const buttons=document.createElement('div');buttons.className='actions';
      buttons.append(button('Probe A/V', async()=>{
        try{const result=await api('api/diagnostics/camera/'+cam.slug,'POST');
          toast(`${cam.name}: ${result.video.codec_name} ${result.video.profile || ''} · audio ${result.audio ? result.audio.codec_name : 'not detected'} · ${result.audio_warning || 'OK'}`);
        }catch(e){toast('Probe: '+e.message);}
      }));
      buttons.append(button('Test local HLS', async()=>{
        toast('Checking MPEG-TS and decoding the first video segment…');
        try{const result=await api('api/diagnostics/hls/'+cam.slug,'POST');
          toast(`${cam.name}: TS ${result.first_ts_seconds}s · ${result.segment_bytes} bytes · H.264/${result.audio_codec} · decode OK`);
          await loadDiagnostics();
        }catch(e){toast('Local HLS: '+e.message);}
      }));
      buttons.append(button('Restart if active',async()=>{
        if(!confirm('Restart the active FFmpeg worker for '+cam.name+'?'))return;
        try{const result=await api('api/restart/'+cam.slug,'POST');
          toast(result.restarted?'Worker restarted':'Camera is idle; nothing changed');
          await loadDiagnostics();
        }catch(e){toast('Restart: '+e.message);}
      }));
      card.append(buttons);cameras.append(card);
    });
    const events=$('diagnostics-events');events.replaceChildren();
    if(!(data.events||[]).length)events.append(makeDiagNode('p','No recent events.'));
    (data.events||[]).forEach(e=>events.append(makeDiagNode('p',`${e.utc} · ${e.camera} · ${e.event} ${e.detail||''}`)));
  }catch(e){summary.textContent='Diagnostics unavailable: '+e.message;}
}
$('diagnostics-open').onclick=()=>{
  diagActive = !diagActive;
  $('diagnostics-panel').hidden = !diagActive;
  if(diagActive){$('diagnostics-panel').scrollIntoView({behavior:'smooth'});loadDiagnostics();}
};
$('diag-refresh').onclick=loadDiagnostics;
setInterval(()=>{if(diagActive)loadDiagnostics();},15000);

// Viewer is opt-in and short-lived. It never sends images through the public HLS endpoint.
let aiLiveSlug = '', aiLiveTimer = null, aiLiveRefreshCount = 0;
let aiLiveUrl = '';
async function stopAiLive(){
  const slug=aiLiveSlug;
  aiLiveSlug='';
  if(aiLiveTimer){clearInterval(aiLiveTimer);aiLiveTimer=null;}
  $('ai-live').hidden=true;
  $('ai-live-image').hidden=true;
  if(aiLiveUrl){URL.revokeObjectURL(aiLiveUrl);aiLiveUrl='';}
  if(slug)try{await api('api/ai/watch/'+slug,'POST',{watch:false});}catch(_e){}
}
async function pollAiLive(){
  const slug=aiLiveSlug;if(!slug)return;
  try{
    // Renew only every 20 seconds: preview files are written only while viewed.
    if(++aiLiveRefreshCount%5===0) await api('api/ai/watch/'+slug,'POST',{watch:true});
    const r=await api('api/ai/preview-status/'+slug);
    if(slug!==aiLiveSlug)return;
    if(!r.preview){$('ai-live-status').textContent='Esperando fotograma de '+slug+' (modelo en ejecución)…';return;}
    const m=r.preview;
    const res=await fetch('api/ai/preview/'+slug,{headers:{'X-Bridge-CSRF':state.csrf}});
    if(!res.ok)throw new Error('JPEG '+res.status);
    const url=URL.createObjectURL(await res.blob());
    if(slug!==aiLiveSlug){URL.revokeObjectURL(url);return;}
    const img=$('ai-live-image');const prev=aiLiveUrl;aiLiveUrl=url;img.src=url;img.hidden=false;
    if(prev)URL.revokeObjectURL(prev);
    const objs=m.objects||[];
    $('ai-live-status').textContent=`${slug} · hace ${m.age_seconds}s · ${objs.length} objeto(s) · ${m.analyzed?'modelo ejecutado':'sin inferencia'} · ${m.inference_ms} ms`+(objs.length?' · '+objs.map(o=>o.category+' '+Math.round(o.confidence*100)+'%').join(', '):'');
  }catch(e){if(slug===aiLiveSlug)$('ai-live-status').textContent='Vista no disponible: '+e.message;}
}
async function startAiLive(slug){
  if(aiLiveSlug)await stopAiLive();
  try{
    await api('api/ai/watch/'+slug,'POST',{watch:true});
    aiLiveSlug=slug;aiLiveRefreshCount=0;
    $('ai-live').hidden=false;
    $('ai-live').scrollIntoView({behavior:'smooth',block:'center'});
    $('ai-live-status').textContent='Conectando con '+slug+'…';
    await pollAiLive();
    aiLiveTimer=setInterval(pollAiLive,4000);
  }catch(e){toast('No se pudo abrir el visor: '+e.message);}
}
$('ai-live-stop').onclick=stopAiLive;
window.addEventListener('pagehide',()=>{if(aiLiveSlug)api('api/ai/watch/'+aiLiveSlug,'POST',{watch:false}).catch(()=>{});});
// Optional AI detector: all requests remain behind the admin/CSRF surface.
let aiActive=false;
const aiNode=(tag, value, cls='')=>{
  const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;
};
async function loadAI(){
  if(!aiActive)return;
  const status=$('ai-status');
  try{
    const data=await api('api/ai/config');
    const cfg=data.config||{};const worker=data.status||{};
    status.textContent=`Worker: ${worker.state||'unknown'} · ${worker.healthy?'heartbeat OK':'offline / no heartbeat'} · Model: ${worker.model_loaded?'loaded':'not loaded'} · Events: ${worker.detections||0}`+(worker.message?' · '+worker.message:'');
    $('ai-global').checked=!!cfg.enabled;
    $('ai-interval').value=cfg.interval_seconds||3;
    $('ai-confidence').value=cfg.confidence||0.45;
    const cameras=$('ai-cameras');cameras.replaceChildren();
    state.cameras.forEach(cam=>{
      const conf=(cfg.cameras||{})[cam.slug]||{};
      const card=aiNode('article','','diag-camera');
      card.append(aiNode('strong',cam.name));
      const wrap=aiNode('div','','actions');
      const label=aiNode('label',' Analyze this camera ');
      const cb=document.createElement('input');cb.type='checkbox';cb.checked=!!conf.enabled;label.prepend(cb);
      wrap.append(label);
      const roadLabel=aiNode('label',' Road mode (1s sampling; high-confidence traffic alerts) ');
      const roadCB=document.createElement('input');roadCB.type='checkbox';roadCB.checked=!!conf.road_mode;roadLabel.prepend(roadCB);
      wrap.append(roadLabel);
      const subLabel=aiNode('label','AI RTSP substream (optional; stored privately)');
      const input=document.createElement('input');input.type='password';input.autocomplete='new-password';
      input.placeholder=conf.substream_configured?'Substream saved — blank keeps it':'rtsp://camera:554/substream';
      subLabel.append(input);card.append(wrap,subLabel);
      const controls=aiNode('div','','actions');
      controls.append(button('Save camera AI',async()=>{
        const payload={camera:{slug:cam.slug,enabled:cb.checked,road_mode:roadCB.checked}};
        if(input.value.trim())payload.camera.substream=input.value.trim();
        try{await api('api/ai/config','POST',payload);toast('AI camera saved');loadAI();}catch(e){toast(e.message);}
      }));
      controls.append(button('View AI boxes',()=>startAiLive(cam.slug)));
      controls.append(button('Clear substream',async()=>{
        if(!confirm('Use the original RTSP stream for AI on '+cam.name+'?'))return;
        try{await api('api/ai/config','POST',{camera:{slug:cam.slug,substream:''}});loadAI();}catch(e){toast(e.message);}
      }));
      card.append(controls);cameras.append(card);
    });
    const events=$('ai-events');events.replaceChildren();
    const dataEvents=await api('api/ai/events');
    const summary=dataEvents.summary||{};
    const labels=Object.entries(summary.categories||{}).map(([name,n])=>name+': '+n).join(' · ');
    $('ai-summary').textContent=`Last 24h: ${summary.total||0} events · Confirmed ${summary.feedback?.confirmed||0} · False alarms ${summary.feedback?.false_positive||0}`+(labels?' · '+labels:'');
    if(!(dataEvents.events||[]).length)events.append(aiNode('p','No detections yet. Enable the AI worker and one camera.'));
    (dataEvents.events||[]).forEach(ev=>{
      const card=aiNode('article','','ai-event');
      const top=aiNode('div','','actions');
      top.append(aiNode('b',`${ev.category.toUpperCase()} · ${ev.camera} · ${Math.round(ev.confidence*100)}%`));
      top.append(aiNode('span',ev.created_at+' · '+ev.feedback));card.append(top);
      const img=document.createElement('img');img.alt=`${ev.category} detected at ${ev.camera}`;
      img.className='ai-preview';img.loading='lazy';
      fetch('api/ai/snapshot/'+ev.id,{headers:{'X-Bridge-CSRF':state.csrf}})
        .then(r=>{if(!r.ok)throw new Error('No image');return r.blob();})
        .then(b=>{const url=URL.createObjectURL(b);img.src=url;img.onload=()=>URL.revokeObjectURL(url);})
        .catch(()=>{img.alt='Snapshot unavailable';});
      card.append(img);
      const actions=aiNode('div','','actions');
      for(const [key,title] of [['confirmed','✓ Correct'],['false_positive','✕ False positive'],['pending','Undo']]){
        actions.append(button(title,async()=>{
          try{await api('api/ai/feedback/'+ev.id,'POST',{feedback:key});loadAI();}catch(e){toast(e.message);}
        }));
      }
      card.append(actions);events.append(card);
    });
  }catch(e){status.textContent='AI unavailable: '+e.message;}
}
$('ai-open').onclick=()=>{
  aiActive=!aiActive;$('ai-panel').hidden=!aiActive;
  if(!aiActive)stopAiLive();
  if(aiActive){$('ai-panel').scrollIntoView({behavior:'smooth'});loadAI();}
};
$('ai-refresh').onclick=loadAI;
$('ai-save').onclick=async()=>{
  const interval=Number($('ai-interval').value),confidence=Number($('ai-confidence').value);
  try{await api('api/ai/config','POST',{enabled:$('ai-global').checked,interval_seconds:interval,confidence});toast('AI settings updated');loadAI();}catch(e){toast(e.message);}
};
setInterval(()=>{if(aiActive && !$('ai-panel').contains(document.activeElement))loadAI();},25000);
