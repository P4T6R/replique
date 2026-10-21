import { JSDOM } from "jsdom";
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";
const bundle = readFileSync(
  "dist/assets/" + readdirSync("dist/assets").find((x) => x.endsWith(".js")),
  "utf8",
);
const wait = () => new Promise((r) => setTimeout(r, 30));
async function waitFor(predicate, timeout = 1500) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  assert.ok(predicate(), "Timed out waiting for the expected UI state");
}
const response = {
  mode: "demo",
  notice: "Réponses de démonstration.",
  insight: "Une invitation sans pression.",
  boundary: false,
  replies: [1, 2, 3].map((n) => ({
    id: String(n),
    title: ["Simple", "Plus chaleureuse", "Plus directe"][n - 1],
    text: "Ça me ferait plaisir.",
    why: "Une formulation ouverte.",
  })),
};
async function setup(mode = "demo", auth = { enabled: true, status: "disconnected", sharing: false }, query = "") {
  const dom = new JSDOM('<div id="root"></div>', {
    url: "http://127.0.0.1:8000/" + query,
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  let pending,
    calls = [];
  dom.window.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url === "/api/auth/status") return { ok: true, json: async () => auth };
    if (url === "/api/auth/models") return { ok: true, json: async () => ({ models: [{ slug: "test-model", display_name: "Test model" }, { slug: "second-model", display_name: "Second model" }] }) };
    if (url === "/api/auth/logout") { auth = { enabled: true, status: "disconnected", sharing: false }; mode = "demo"; return { ok: true, json: async () => ({ remote_revoked: false }) }; }
    if (url === "/api/health")
      return {
        ok: true,
        json: async () => ({
          mode,
          provider: "example.invalid",
          ocr_available: true,
          ocr_languages: ["eng"],
        }),
      };
    return new Promise(
      (resolve) =>
        (pending = () => resolve({ ok: true, json: async () => response })),
    );
  };
  dom.window.eval(bundle);
  await waitFor(() => calls.some((call) => call.url === "/api/health") && calls.some((call) => call.url === "/api/auth/status"));
  if (auth.status === "connected" && auth.sharing) {
    await waitFor(() => dom.window.document.querySelector("#model")?.value === "test-model");
  } else {
    await waitFor(() => {
      const login = dom.window.document.querySelector(".chatgpt-login");
      return login && (auth.status === "connecting" ? login.disabled : auth.enabled ? !login.disabled : login.disabled);
    });
  }
  return {
    dom,
    w: dom.window,
    d: dom.window.document,
    calls,
    resolve: () => pending(),
  };
}
const click = async (el) => {
  assert.ok(el);
  el.click();
  await wait();
};
function fill(w, el, value) {
  Object.getOwnPropertyDescriptor(
    w.HTMLTextAreaElement.prototype,
    "value",
  ).set.call(el, value);
  el.dispatchEvent(new w.Event("input", { bubbles: true }));
}
const test = await setup();
const { d, w } = test;
const button = () => d.querySelector(".primary");
assert.equal(button().disabled, true);
await click(
  [...d.querySelectorAll("button")].find((x) =>
    x.textContent.includes("Essayer un exemple"),
  ),
);
assert.ok(d.querySelector("#conversation").value.includes("Autre personne"));
assert.equal(button().disabled, true);
await click(d.querySelector(".check input"));
assert.equal(button().disabled, false);
await click(button());
assert.ok(d.querySelector("#conversation").disabled);
assert.ok(d.querySelector("#intent").disabled);
assert.ok(d.querySelector("#style").disabled);
const request = JSON.parse(
  test.calls.find((x) => x.url === "/api/generate").options.body,
);
assert.equal(request.context_confirmed, true);
assert.equal(request.consent, false);
test.resolve();
await waitFor(() => d.querySelectorAll(".reply").length === 3);
assert.equal(d.querySelectorAll(".reply").length, 3);
assert.equal(d.activeElement, d.querySelector(".answers"));
fill(w, d.querySelector(".reply textarea"), "Ma version personnelle.");
await wait();
assert.equal(
  d.querySelector(".reply textarea").value,
  "Ma version personnelle.",
);
await click([...d.querySelectorAll(".tone input")].find(input => input.value === "chaleureux"));
assert.equal(d.querySelector(".reply textarea").value, "Ma version personnelle.");
assert.match(d.querySelector(".outdated-note").textContent, /réglages précédents/);
fill(
  w,
  d.querySelector("#conversation"),
  "Moi : Bonjour\nAutre personne : Salut",
);
await wait();
assert.equal(d.querySelectorAll(".reply").length, 0);
assert.equal(button().disabled, true);
await click(d.querySelector(".check input"));
await click(button());
await click(d.querySelector(".quiet"));
assert.equal(d.querySelector("#conversation").value, "Moi : Bonjour\nAutre personne : Salut");
await click([...d.querySelectorAll(".reset-confirm button")].find(button => button.textContent.includes("Garder")));
assert.equal(d.querySelector("#conversation").value, "Moi : Bonjour\nAutre personne : Salut");
await click(d.querySelector(".quiet"));
await click([...d.querySelectorAll(".reset-confirm button")].find(button => button.textContent.includes("Effacer")));
test.resolve();
await wait();
assert.equal(d.querySelector("#conversation").value, "");
assert.equal(d.querySelectorAll(".reply").length, 0);
assert.equal(button().disabled, true);
assert.match(d.querySelector(".status").textContent, /fournisseur/);
test.dom.window.close();
const live = await setup("live");
await click(
  [...live.d.querySelectorAll("button")].find((x) =>
    x.textContent.includes("Essayer un exemple"),
  ),
);
await click(live.d.querySelector(".check input"));
assert.equal(live.d.querySelector(".primary").disabled, true);
await click(live.d.querySelector(".consent input"));
assert.equal(live.d.querySelector(".primary").disabled, false);
assert.match(live.d.querySelector(".consent").textContent, /example.invalid/);
live.dom.window.close();
const failure = await setup();
const normalFetch = failure.w.fetch;
failure.w.fetch = async (url, options) => {
  if (url !== "/api/generate") return normalFetch(url, options);
  return { ok: false, json: async () => ({ detail: "Erreur contr\u00f4l\u00e9e du fournisseur." }) };
};
await click(
  [...failure.d.querySelectorAll("button")].find((x) =>
    x.textContent.includes("Essayer un exemple"),
  ),
);
await click(failure.d.querySelector(".check input"));
await click(failure.d.querySelector(".primary"));
assert.match(
  failure.d.querySelector("[role=alert]").textContent,
  /Erreur contrôlée/,
);
assert.equal(failure.d.querySelector(".primary").disabled, false);
assert.equal(failure.d.querySelectorAll(".reply").length, 0);
failure.dom.window.close();
console.log(
  "PASS: DOM checks: review, generation, editing, stale invalidation, reset race, provider consent. Mock API only; not browser rendering.",
);

const connected = await setup("chatgpt", { enabled: true, status: "connected", sharing: true, identity: { email: "test@example.invalid" } }, "?auth=connected");
await waitFor(() => connected.w.location.search === "");
assert.equal(connected.w.location.search, "");
await waitFor(() => connected.d.querySelector(".account-state") && connected.d.querySelector("#model").value === "test-model");
assert.match(connected.d.querySelector(".account-state").textContent, /test@example.invalid/);
assert.equal(connected.d.querySelector("#model").value, "test-model");
assert.equal(connected.calls.some((c) => c.url === "/api/auth/login"), false);
await click([...connected.d.querySelectorAll("button")].find((b) => b.textContent.includes("Compris")));
assert.equal(connected.w.localStorage.getItem("replique-plan-welcome"), "seen");
await click([...connected.d.querySelectorAll("button")].find((b) => b.textContent.includes("Essayer un exemple")));
await click(connected.d.querySelector(".context-sheet label.check:not(.ocr-consent) input"));
assert.equal(connected.d.querySelector(".primary").disabled, true);
await click(connected.d.querySelector(".consent input"));
await click(connected.d.querySelector(".primary"));
const generated = connected.calls.find((c) => c.url === "/api/generate");
assert.equal(JSON.parse(generated.options.body).model, "test-model");
assert.equal(generated.options.headers["X-Replique-Request"], "1");
assert.ok(connected.d.querySelector("#model").disabled);
assert.ok([...connected.d.querySelectorAll("button")].find((b) => b.textContent.includes("Déconnecter")).disabled);
connected.resolve(); await wait();
await click([...connected.d.querySelectorAll("button")].find((b) => b.textContent.includes("Déconnecter")));
assert.equal(connected.d.querySelector(".account-state"), null);
assert.equal(connected.d.querySelectorAll(".reply").length, 0);
assert.match(connected.d.querySelector(".status").textContent, /révoquer/);
assert.equal(connected.calls.find((c) => c.url === "/api/auth/logout").options.headers["X-Replique-Request"], "1");
connected.dom.window.close();
const disabled = await setup("demo", { enabled: false, status: "disconnected", sharing: false });
assert.ok(disabled.d.querySelector(".chatgpt-login").disabled);
disabled.dom.window.close();
const denied = await setup("demo", { enabled: true, status: "disconnected", sharing: false, error: { code: "access_denied", message: "Connexion annulée chez OpenAI." } }, "?auth=error");
await waitFor(() => denied.d.querySelector(".account-error"));
assert.match(denied.d.querySelector(".account-error").textContent, /annulée/);
assert.equal(denied.w.location.search, "");
denied.dom.window.close();
const expired = await setup("chatgpt", { enabled: true, status: "reauth_required", sharing: false });
assert.match(expired.d.querySelector(".account-actions").textContent, /expiré/);
assert.ok(expired.d.querySelector(".primary").disabled);
expired.dom.window.close();
for (const url of ["https://evil.invalid/authorize", "https://auth.openai.com.evil.invalid/api/accounts/authorize", "http://auth.openai.com/api/accounts/authorize", "https://auth.openai.com/api/accounts/other", "https://user@auth.openai.com/api/accounts/authorize"]) {
  const unsafe = await setup();
  unsafe.w.fetch = async () => ({ ok: true, json: async () => ({ authorization_url: url }) });
  await click(unsafe.d.querySelector(".chatgpt-login"));
  assert.match(unsafe.d.querySelector(".account-error").textContent, /refusée/);
  assert.equal(unsafe.w.location.hostname, "127.0.0.1");
  unsafe.dom.window.close();
}
console.log("PASS: mocked OAuth status, consent, model, expiry, declined callback, logout, busy lock and unsafe redirects. No real login or model call.");

const quota = await setup("chatgpt", { enabled: true, status: "connected", sharing: true });
await click([...quota.d.querySelectorAll("button")].find((b) => b.textContent.includes("Compris")));
await click([...quota.d.querySelectorAll("button")].find((b) => b.textContent.includes("Essayer un exemple")));
await click(quota.d.querySelector(".context-sheet label.check:not(.ocr-consent) input"));
await click(quota.d.querySelector(".consent input"));
quota.w.fetch = async () => ({ ok: false, json: async () => ({ detail: { code: "subscription_sharing_usage_limit_exceeded", message: "Limite ChatGPT atteinte." } }) });
await click(quota.d.querySelector(".primary"));
assert.match(quota.d.querySelector(".compose .error").textContent, /Limite ChatGPT atteinte/);
assert.equal(quota.d.querySelector(".compose .error a").href, "https://chatgpt.com/settings/usage");
quota.dom.window.close();
const catalogFailure = await setup("chatgpt", { enabled: true, status: "connected", sharing: true });
catalogFailure.w.fetch = async (url) => ({ ok: url !== "/api/auth/models", json: async () => url === "/api/health" ? { mode: "chatgpt", ocr_available: true, ocr_languages: [], provider: "api.openai.com" } : url === "/api/auth/status" ? { enabled: true, status: "connected", sharing: true } : { detail: { message: "Catalogue indisponible." } } });
await click([...catalogFailure.d.querySelectorAll("button")].find((b) => b.textContent.includes("Actualiser la connexion")));
assert.equal(catalogFailure.d.querySelector("#model").value, "");
assert.ok(catalogFailure.d.querySelector("#model").disabled);
assert.match(catalogFailure.d.querySelector(".account-error").textContent, /Catalogue indisponible/);
catalogFailure.dom.window.close();
console.log("PASS: structured quota recovery and stale catalog clearing.");

const regional = await setup();
assert.equal(regional.d.querySelector('#locale').value, 'fr_neutre');
assert.equal(regional.d.querySelector('#familiarity').value, 'neutre');
for (const [id,value] of [['locale','burkina_faso'],['familiarity','familier']]) {
  const el=regional.d.querySelector('#'+id);el.value=value;el.dispatchEvent(new regional.w.Event('change',{bubbles:true}));await wait();
}
await click([...regional.d.querySelectorAll('button')].find(b=>b.textContent.includes('Réponses courtes')));
await click(regional.d.querySelector('.check input'));await click(regional.d.querySelector('.primary'));
const regionRequest=JSON.parse(regional.calls.find(c=>c.url==='/api/generate').options.body);
assert.equal(regionRequest.locale,'burkina_faso');assert.equal(regionRequest.familiarity,'familier');
assert.ok(regional.d.querySelector('#locale').disabled);assert.ok(regional.d.querySelector('#familiarity').disabled);
regional.resolve();await wait();
fill(regional.w, regional.d.querySelector('.reply textarea'), '');await wait();
assert.equal(regional.d.querySelectorAll('.reply').length,3, 'An edited reply must not disappear when its text is cleared');
await click(regional.d.querySelector('.quiet'));
await click([...regional.d.querySelectorAll('.reset-confirm button')].find(button => button.textContent.includes('Effacer')));
assert.equal(regional.d.querySelector('#locale').value,'fr_neutre');assert.equal(regional.d.querySelector('#familiarity').value,'neutre');regional.dom.window.close();
const abstain=await setup();
abstain.w.fetch=async()=>({ok:true,json:async()=>({...response,boundary:true,replies:response.replies.map(r=>({...r,text:''}))})});
assert.ok(![...abstain.d.querySelectorAll('button')].some(b=>b.textContent.trim()==='Une limite claire'));
await click([...abstain.d.querySelectorAll('button')].find(button => button.textContent.trim() === 'Un refus'));
await click(abstain.d.querySelector('.check input'));await click(abstain.d.querySelector('.primary'));await wait();
assert.match(abstain.d.querySelector('.answers h2').textContent,/Une piste pour la suite/);assert.equal(abstain.d.querySelector('.pause-card,.boundary,.final-note'),null);assert.match(abstain.d.querySelector('.insight p').textContent,/Cette personne demande de ne plus être contactée. Le mieux est de ne pas répondre./);assert.equal(abstain.d.querySelector('.insight .eyebrow').textContent.trim(),'LE POINT DE REPÈRE');assert.equal(abstain.d.querySelectorAll('.reply').length,0);assert.equal(abstain.d.querySelectorAll('.copy,.export').length,0);abstain.dom.window.close();
console.log('PASS: regional preferences, familiarity request contract, busy locks, reset defaults, empty edit retained and discreet inline advice without copy/export.');

for (const count of [1, 3]) {
  const optional=await setup();
  optional.w.fetch=async()=>({ok:true,json:async()=>({...response,boundary:false,insight:'Une idée facultative, puis laissez un peu d’espace.',replies:response.replies.slice(0,count)})});
  await click([...optional.d.querySelectorAll('button')].find(b=>b.textContent==='Sans réponse'));await click(optional.d.querySelector('.check input'));await click(optional.d.querySelector('.primary'));await wait();
  assert.equal(optional.d.querySelectorAll('.reply').length,count);assert.equal(optional.d.querySelectorAll('.copy').length,count);assert.equal(optional.d.querySelector('.pause-card'),null);assert.equal(optional.d.querySelector('.boundary'),null);
  assert.match(optional.d.querySelector('.answers h2').textContent,count===1?/Une piste/:/trois versions/);
  fill(optional.w,optional.d.querySelector('.reply textarea'),'Mon idée, à ma façon.');await wait();assert.equal(optional.d.querySelector('.reply textarea').value,'Mon idée, à ma façon.');
  optional.dom.window.close();
}
console.log('PASS: unanswered optional suggestions remain editable/copyable; single-result heading and explicit stop state are distinct.');

const changedModel = await setup("chatgpt", { enabled: true, status: "connected", sharing: true });
changedModel.w.fetch = async () => ({ ok: true, json: async () => ({ examples: [], profile: null, revision: 0, notice: "Synthetic memory preview" }) });
await click([...changedModel.d.querySelectorAll("button")].find(b => b.textContent.includes("Essayer un exemple")));
await click(changedModel.d.querySelector(".context-sheet label.check:not(.ocr-consent) input"));
await click(changedModel.d.querySelector("#use-memory"));
await click(changedModel.d.querySelector(".consent input"));
assert.equal(changedModel.d.querySelector(".consent input").checked, true);
assert.ok(changedModel.d.querySelector(".memory-selection"));
const modelSelect = changedModel.d.querySelector("#model");
Object.getOwnPropertyDescriptor(changedModel.w.HTMLSelectElement.prototype, "value").set.call(modelSelect, "second-model");
modelSelect.dispatchEvent(new changedModel.w.Event("change", { bubbles: true }));
await wait();
assert.equal(changedModel.d.querySelector(".consent input").checked, false);
assert.equal(changedModel.d.querySelector("#use-memory").checked, false);
assert.equal(changedModel.d.querySelector(".memory-selection"), null);
assert.equal(changedModel.d.querySelector(".primary").disabled, true);
changedModel.w.close();
console.log("PASS: changing the target model clears provider consent, one-generation memory permission and selected memory preview.");
