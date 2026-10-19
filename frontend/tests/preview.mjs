import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const fixtures=JSON.parse(execFileSync('python',['-c',`import json
from backend.app import GenerateRequest, demo_answer, boundary_kind, DEMO_CONVERSATION, DEMO_UNANSWERED
print(json.dumps({key:demo_answer(GenerateRequest(conversation=c,intent='répondre naturellement'),boundary_kind(c)).model_dump() for key,c in [('suggestions',DEMO_CONVERSATION),('unanswered',DEMO_UNANSWERED)]},ensure_ascii=False))`],{cwd:'..',encoding:'utf8'}));
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
const asset = (ext) => readFileSync('dist/assets/' + readdirSync('dist/assets').find(f => f.endsWith(ext)), 'utf8');
const js=asset('.js');
const css=asset('.css').replace(/url\((?:[\"'])?\/fonts\/([^\"')]+)(?:[\"'])?\)/g, (_, name) => `url(data:font/ttf;base64,${readFileSync('public/fonts/'+name).toString('base64')})`);
const wait=()=>new Promise(r=>setTimeout(r,40));
const result=fixtures.suggestions;
const dom=new JSDOM('<!doctype html><html lang="fr"><body><div id="root"></div></body></html>',{url:'http://127.0.0.1:8000/',runScripts:'outside-only',pretendToBeVisual:true});
let current=result;
const syntheticMemory = { items: [{id:'synthetic-only',reply:'Ça marche, jeudi me va bien. On se dit 18 h ?',conversation:'',intent:'répondre naturellement',tone:'naturel',locale:'fr_neutre',rating:'positive',feedback:'natural',validated:true,expires_at:'2026-11-17T12:00:00Z'}], profile: {length:'short',register:'neutral',emoji:'none'},revision:1};
dom.window.fetch=async(url)=>({ok:true,json:async()=>url==='/api/health'?{mode:'demo',ocr_available:true,ocr_languages:['fra'],provider:null}:url==='/api/auth/status'?{enabled:false,status:'disconnected',sharing:false}:url==='/api/memory'?syntheticMemory:url.startsWith('/api/memory/preview?')?{examples:syntheticMemory.items,profile:syntheticMemory.profile,revision:1,notice:'État entièrement synthétique : aucun exemple personnel enregistré.'}:current});
dom.window.eval(js);await wait();
const d=dom.window.document;
function snapshot(){d.querySelectorAll('textarea').forEach(el=>el.textContent=el.value);d.querySelectorAll('input').forEach(el=>{if(el.type==='checkbox'||el.type==='radio')el.toggleAttribute('checked',el.checked);else el.setAttribute('value',el.value)});d.querySelectorAll('option').forEach(el=>el.toggleAttribute('selected',el.selected));return d.querySelector('#root').innerHTML;}
const home=snapshot();
[...d.querySelectorAll('button')].find(x=>x.textContent.includes('Essayer un exemple')).click();await wait();d.querySelector('.check input').click();await wait();d.querySelector('.primary').click();await wait();
const suggestions=snapshot();
current=fixtures.unanswered;
[...d.querySelectorAll('button')].find(x=>x.textContent==='Sans réponse').click();await wait();d.querySelector('.check input').click();await wait();d.querySelector('.primary').click();await wait();
assert.equal(d.querySelectorAll('.copy').length,3);assert.equal(d.querySelector('.pause-card'),null);
const unanswered=snapshot();
d.querySelector('.memory-panel').open=true;await wait();
d.querySelector('#use-memory').click();await wait();
const memory=snapshot();
const states=JSON.stringify({home,suggestions,unanswered,memory}).replaceAll('<','\\u003c');
const html=`<!doctype html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Réplique — aperçu de l’atelier</title><style>${css}\n.preview-nav{font-family:'DM Sans',sans-serif;background:#ece9df;color:#302d27;padding:12px 20px;display:flex;gap:12px;align-items:center;justify-content:center;flex-wrap:wrap;font-size:11px}.preview-nav p{margin:0}.preview-nav button{padding:9px 14px;border-radius:30px;background:#465844;color:#fffdf8;font-size:11px}.preview-nav button[aria-pressed=true]{background:#f2e2d7;color:#783321}.preview-note{font-size:10px;opacity:.8;text-align:center;width:100%}#preview-root .intro,#preview-root .workspace{animation:none}</style></head><body><nav class="preview-nav" aria-label="États de l’aperçu"><p>Aperçu du design</p><button data-view="home" aria-pressed="false">L’atelier</button><button data-view="suggestions" aria-pressed="true">Trois propositions</button><button data-view="unanswered" aria-pressed="false">Sans réponse : idées facultatives</button><button data-view="memory" aria-pressed="false">Mémoire · exemple synthétique</button><span class="preview-note">Données fictives · vue statique issue de l’application · aucune connexion ni génération réelle</span></nav><div id="preview-root"></div><script>const states=${states};function show(view){document.getElementById('preview-root').innerHTML=states[view];document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)));document.querySelectorAll('#preview-root button').forEach(b=>{b.title='Commande disponible dans l’application, pas dans cet aperçu statique.';b.addEventListener('click',e=>e.preventDefault())});document.querySelectorAll('#preview-root textarea').forEach(t=>t.readOnly=true);document.querySelectorAll('#preview-root input,#preview-root select').forEach(t=>{t.addEventListener('click',e=>e.preventDefault());t.addEventListener('keydown',e=>e.preventDefault())});}document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>show(b.dataset.view)));show('suggestions');</script></body></html>`;
assert.deepEqual(Object.keys({home,suggestions,unanswered,memory}),['home','suggestions','unanswered','memory']);
assert.equal((html.match(/<button data-view=/g)||[]).length,4);
assert.ok(!html.includes('Une limite claire'));
assert.ok(!html.includes('data-view="stop"'));
assert.ok(!html.includes('Respecter sa demande.'));
assert.ok(!html.includes('/fonts/'));assert.equal((css.match(/data:font\/ttf;base64/g)||[]).length,3);
writeFileSync('../evidence/replique-apercu.html',html);
console.log('Preview generated from built React DOM: home, backend demo suggestions, optional unanswered suggestions. Four views including clearly labelled synthetic memory. No browser screenshot or real provider call.');dom.window.close();
