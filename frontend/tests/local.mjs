import { JSDOM } from "jsdom";
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";

const bundle = readFileSync("dist/assets/" + readdirSync("dist/assets").find(name => name.endsWith(".js")), "utf8");
const dom = new JSDOM('<div id="root"></div>', { url: "https://replique.duckdns.org/", runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
const mode = process.argv[2] === "hosted" ? "hosted" : "local";
const calls = [];
let remaining = 20;
let statusFailure = false;
let ocrFailure = false;
window.fetch = async (url, options = {}) => {
  calls.push({ url, options });
  const data = url === "/api/health" ? { mode, provider: mode === "hosted" ? "OpenAI" : "serveur Réplique", ocr_available: true, ocr_languages: ["fra"] }
    : url === "/api/account/status" ? { detail: statusFailure ? "Service indisponible." : "Connectez-vous." }
    : url === "/api/account/register" ? { email: "beta@example.test", trial_remaining: remaining, trial_total: 20, subscription_active: false, subscription_available: false }
    : url === "/api/ocr" ? { text: "Bonjour depuis la capture", warning: "Texte extrait. Relisez-le avant de continuer." }
    : url === "/api/generate" || url === "/api/generate-image" ? { mode, notice: "Propositions Réplique", insight: "Une proposition", boundary: false, replies: url === "/api/generate-image" ? [
      { id: "1", title: "Simple", text: "Salut, quoi de neuf ?", why: "Une reprise naturelle." },
    ] : [
      { id: "1", title: "Simple", text: "Bonjour.", why: "Court." },
      { id: "2", title: "Plus chaleureuse", text: "Salut, ça va ?", why: "Amical." },
      { id: "3", title: "Plus directe", text: "On se voit ?", why: "Direct." },
    ] } : {};
  if (url === "/api/generate" || url === "/api/generate-image") remaining--;
  if (url === "/api/account/status" && !statusFailure && calls.some(call => call.url === "/api/account/register")) Object.assign(data, { email: "beta@example.test", trial_remaining: remaining, trial_total: 20, subscription_active: false, subscription_available: false });
  const ok = (url !== "/api/account/status" || !!data.email) && !(url === "/api/ocr" && ocrFailure);
  return { ok, status: ok ? 200 : url === "/api/ocr" || statusFailure ? 503 : 401,
    json: async () => url === "/api/ocr" && ocrFailure ? { detail: "Lecture temporairement indisponible." } : data };
};
window.eval(bundle);
const waitFor = async (predicate) => {
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.ok(predicate(), "UI state did not appear");
};
const document = window.document;
await waitFor(() => document.querySelector(".trial-account"));
assert.equal(document.querySelector(".chatgpt-login"), null);
assert.equal(document.querySelector(".memory-panel"), null);
assert.ok(document.querySelector(".compose .primary")?.disabled);
document.querySelector(".trial-account-actions>.text-button").click();
await waitFor(() => document.querySelector('input[autocomplete="new-password"]'));
const inputs = document.querySelectorAll(".trial-account input");
for (const [input, value] of [[inputs[0], "beta@example.test"], [inputs[1], "strong passphrase"], [inputs[2], "invitation-code"]]) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set.call(input, value);
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
}
document.querySelector(".trial-account form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
await waitFor(() => document.querySelector(".trial-account strong")?.textContent.includes("20 crédits"));
assert.ok(document.querySelector(".memory-panel"));
assert.equal(calls.filter(call => call.url === "/api/auth/status").length, 0);
assert.equal(calls.filter(call => call.url === "/api/account/register").length, 1);
if (mode === "hosted") {
  const taquin = [...document.querySelectorAll('.tone')].find(label => label.querySelector('input[value="léger"]'));
  assert.match(taquin?.textContent || "", /Taquin/);
  taquin.querySelector("input").click();
  assert.doesNotMatch(document.querySelector(".trial-account")?.textContent || "", /OpenAI|ChatGPT/);
  assert.doesNotMatch(document.querySelector(".consent")?.textContent || "", /OpenAI|ChatGPT/);
  assert.doesNotMatch(document.body.textContent, /private-owner@example\.test/);
  assert.equal(document.querySelector(".ocr-consent"), null);
  assert.equal(document.querySelector(".context-sheet label.check"), null);
  const importButton = [...document.querySelectorAll(".input-tools button")].find(button => button.textContent.includes("Importer"));
  assert.equal(importButton.disabled, false);
  const fileInput = document.querySelector('input[type="file"]');
  Object.defineProperty(fileInput, "files", { configurable: true, value: [new window.File(["image"], "capture.png", { type: "image/png" })] });
  fileInput.dispatchEvent(new window.Event("change", { bubbles: true }));
  await waitFor(() => document.querySelector(".selected-photo")?.textContent.includes("capture.png"));
  assert.match(document.querySelector("#conversation")?.placeholder || "", /vocal/);
  assert.equal(calls.filter(call => call.url === "/api/ocr").length, 0);
  assert.ok(document.querySelector(".compose .primary").disabled);
  document.querySelector(".consent input").click();
  await waitFor(() => !document.querySelector(".compose .primary").disabled);
  document.querySelector(".compose").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await waitFor(() => document.querySelectorAll(".reply").length === 1);
  assert.match(document.querySelector(".answers h2")?.textContent || "", /Une piste/);
  const sent = calls.find(call => call.url === "/api/generate-image");
  assert.equal(sent.options.body.get("file").name, "capture.png");
  assert.equal(JSON.parse(sent.options.body.get("options")).context_confirmed, true);
  assert.equal(JSON.parse(sent.options.body.get("options")).consent, true);
  assert.equal(JSON.parse(sent.options.body.get("options")).tone, "léger");
  assert.ok(document.querySelector(".compose .primary").disabled);
  assert.equal(document.querySelector(".selected-photo") !== null, true);
  assert.equal(document.querySelector("a[href='/confidentialite.html']") !== null, true);
  console.log("PASS hosted beta UI: one consent, direct image generation, no OCR or provider branding.");
  dom.window.close();
  process.exit(0);
}
const ocrConsent = document.querySelector(".ocr-consent input");
const importButton = [...document.querySelectorAll(".input-tools button")].find(button => button.textContent.includes("Importer"));
if (mode === "hosted") {
  assert.ok(ocrConsent);
  assert.ok(importButton.disabled);
  ocrConsent.click();
  await waitFor(() => !importButton.disabled);
}
const fileInput = document.querySelector('input[type="file"]');
Object.defineProperty(fileInput, "files", { configurable: true, value: [new window.File(["image"], "capture.png", { type: "image/png" })] });
fileInput.dispatchEvent(new window.Event("change", { bubbles: true }));
await waitFor(() => document.querySelector("#conversation")?.value.includes("Bonjour depuis la capture"));
assert.match(document.querySelector(".ocr-note")?.textContent || "", /Relisez/);
assert.equal(calls.find(call => call.url === "/api/ocr")?.options.body.get("consent"), mode === "hosted" ? "true" : "false");
assert.ok(document.querySelector(".compose .primary").disabled);
const conversation = document.querySelector("#conversation");
const speakerButtons = [...document.querySelectorAll(".speaker-tools button")];
assert.deepEqual(speakerButtons.map(button => button.textContent), ["Moi", "Autre personne"]);
conversation.setSelectionRange(0, 0);
speakerButtons[1].click();
await waitFor(() => conversation.value === "Autre personne : Bonjour depuis la capture");
const confirmed = document.querySelector(".context-sheet label.check:not(.ocr-consent) input");
const consent = document.querySelector(".consent input");
confirmed.click(); consent.click();
await waitFor(() => !document.querySelector(".compose .primary").disabled);
const setConversation = value => {
  Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set.call(conversation, value);
  conversation.dispatchEvent(new window.Event("input", { bubbles: true }));
};
setConversation("En-tête de la capture\nBonjour");
await waitFor(() => conversation.value.includes("En-tête"));
conversation.setSelectionRange(conversation.value.indexOf("Bonjour"), conversation.value.indexOf("Bonjour"));
speakerButtons[1].click();
await waitFor(() => conversation.value.endsWith("Autre personne : Bonjour"));
assert.ok(document.querySelector(".compose .primary").disabled);
assert.match(document.querySelector(".generation-hint").textContent, /en-têtes/);
setConversation("Moi : Bonjour\nAutre personne : Salut");
await waitFor(() => conversation.value.includes("Salut"));
confirmed.click(); consent.click();
await waitFor(() => consent.checked && confirmed.checked);
setConversation("Moi : Salut\nAutre personne : Bonjour");
await waitFor(() => !consent.checked && !confirmed.checked);
assert.ok(document.querySelector(".compose .primary").disabled);
confirmed.click(); consent.click();
await waitFor(() => consent.checked && confirmed.checked);
const style = document.querySelector("#style");
Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set.call(style, "Des phrases courtes.");
style.dispatchEvent(new window.Event("input", { bubbles: true }));
await waitFor(() => !consent.checked);
consent.click();
await waitFor(() => consent.checked);
statusFailure = true;
document.querySelector(".compose").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
await waitFor(() => document.querySelectorAll(".reply").length === 3 && document.querySelector(".trial-account + .error"));
assert.equal(conversation.value, "Moi : Salut\nAutre personne : Bonjour");
assert.match(document.querySelector(".trial-account + .error").textContent, /conservée/);
statusFailure = false;
document.querySelector(".trial-account + .error button").click();
await waitFor(() => !document.querySelector(".trial-account + .error"));
if (mode === "hosted") ocrConsent.click();
ocrFailure = true;
Object.defineProperty(fileInput, "files", { configurable: true, value: [new window.File(["heic"], "photo.HEIC")] });
fileInput.dispatchEvent(new window.Event("change", { bubbles: true }));
await waitFor(() => document.querySelector(".context-sheet .error")?.textContent.includes("Lecture temporairement indisponible"));
assert.equal(conversation.value, "Moi : Salut\nAutre personne : Bonjour");
assert.equal(document.querySelectorAll(".reply").length, 3);
assert.equal(calls.filter(call => call.url === "/api/ocr").at(-1).options.body.get("file").type, "image/heic");
const retry = [...document.querySelectorAll(".context-sheet .error button")].find(button => button.textContent.includes("Réessayer"));
assert.ok(retry);
if (mode === "hosted") { assert.ok(retry.disabled); ocrConsent.click(); await waitFor(() => !retry.disabled); }
ocrFailure = false;
retry.click();
await waitFor(() => document.querySelector("#photo-preview")?.textContent.includes("Bonjour depuis la capture"));
assert.equal(conversation.value, "Moi : Salut\nAutre personne : Bonjour");
document.querySelector(".photo-actions button").click();
await waitFor(() => conversation.value.includes("Bonjour depuis la capture"));
assert.match(conversation.value, /Moi : Salut\nAutre personne : Bonjour/);
assert.ok(document.querySelector(".compose .primary").disabled);
console.log(`PASS ${mode} beta UI: invitation, consent, HEIC photo retry, preserved draft, no visitor ChatGPT login.`);
dom.window.close();
