// DOM/CSS token audit, not browser rendering or forced-colours simulation.
import {JSDOM} from 'jsdom';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const source=readFileSync('src/style.css','utf8');
const tokens=Object.fromEntries([...source.matchAll(/(--[\w-]+):([^;}]+)/g)].map(m=>[m[1],m[2]]));
// jsdom does not resolve CSS custom properties. Resolve literal app tokens
// before computing the stylesheet cascade instead of testing invented pairs.
const css=source.replace(/var\((--[\w-]+)\)/g,(_,key)=>tokens[key]);
assert.match(source,/color-scheme:only light/);
assert.match(readFileSync('index.html','utf8'),/name="color-scheme" content="light"/);
const dom=new JSDOM(`<style>${css}</style><main class="app"><button class="primary">Trouver mes mots</button><button class="primary" disabled>Indisponible</button><button class="chatgpt-login">Continue with ChatGPT</button><button class="chatgpt-login" disabled>Indisponible</button><div class="input-tools"><button class="text-button">Importer</button><button class="text-button">Exemple</button><button class="text-button" disabled>Indisponible</button></div><label class="tone active">Naturel</label><label class="tone">Direct</label><button class="copy">Copier</button><button class="quiet">Effacer</button><button class="text-button">Exporter</button><select><option>Choix</option></select><textarea class="style-input">Texte</textarea><textarea class="conversation" disabled>Texte</textarea><dialog open class="plan-dialog">Votre forfait</dialog><p class="preference-help">Aide</p><details open class="memory-panel"><summary>Ma mémoire <span>facultative</span></summary><div class="memory-body"><p class="preference-help">Locale non chiffrée</p><span class="memory-tag">Validé</span><div class="memory-confirm"><p>Confirmer</p><button class="text-button">Supprimer</button></div><button class="text-button" disabled>Enregistrer</button></div></details><div class="memory-selection"><p>Contexte sélectionné</p></div><article class="reply"><textarea class="memory-excerpt">Extrait</textarea></article></main>`);
const w=dom.window;
const rgb=c=>c.match(/[\d.]+/g)?.slice(0,3).map(Number);
const luminance=c=>rgb(c).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0);
const ratio=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
function background(el){for(let p=el;p;p=p.parentElement){const c=w.getComputedStyle(p).backgroundColor;if(c!=='rgba(0, 0, 0, 0)'&&c!=='transparent')return c;}throw Error('No background');}
for(const el of w.document.querySelectorAll('button,label,select,textarea,dialog,p,.memory-tag,.memory-panel>summary,.memory-panel>summary span')){const s=w.getComputedStyle(el),bg=background(el),r=ratio(s.color,bg);assert.ok(r>=4.5,`${el.className}: ${s.color} / ${bg} = ${r}`);assert.notEqual(s.opacity,'0.45');console.log(`PASS ${el.tagName}.${el.className}${el.disabled?' disabled':''}: ${r.toFixed(2)}:1 (${s.color} on ${bg})`);}
for(const bg of [tokens['--canvas'],tokens['--paper'],tokens['--disabled-surface']]){const probe=w.document.createElement('i');probe.style.color=tokens['--focus'];probe.style.backgroundColor=bg;w.document.body.append(probe);const s=w.getComputedStyle(probe);assert.ok(ratio(s.color,s.backgroundColor)>=3);}
console.log('PASS focus token >=3:1 against cream, paper and disabled surfaces. Browser visual/OS dark-mode QA remains unverified.');
w.close();
