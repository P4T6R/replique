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
window.fetch = async (url, options = {}) => {
  calls.push({ url, options });
  const data = url === "/api/health" ? { mode, provider: mode === "hosted" ? "OpenAI" : "serveur Réplique", ocr_available: true, ocr_languages: ["fra"] }
    : url === "/api/account/status" ? { detail: statusFailure ? "Service indisponible." : "Connectez-vous." }
    : url === "/api/account/register" ? { email: "beta@example.test", trial_remaining: remaining, trial_total: 20, subscription_active: false, subscription_available: false }
    : url === "/api/generate" ? { mode, notice: "Propositions Réplique", insight: "Une proposition", boundary: false, replies: [
      { id: "1", title: "Simple", text: "Bonjour.", why: "Court." },
      { id: "2", title: "Plus chaleureuse", text: "Salut, ça va ?", why: "Amical." },
      { id: "3", title: "Plus directe", text: "On se voit ?", why: "Direct." },
    ] } : {};
  if (url === "/api/generate") remaining--;
  if (url === "/api/account/status" && !statusFailure && calls.some(call => call.url === "/api/account/register")) Object.assign(data, { email: "beta@example.test", trial_remaining: remaining, trial_total: 20, subscription_active: false, subscription_available: false });
  const ok = url !== "/api/account/status" || !!data.email;
  return { ok, status: ok ? 200 : statusFailure ? 503 : 401, json: async () => data };
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
assert.equal(calls.filter(call => call.url === "/api/auth/status").length, 0);
assert.equal(calls.filter(call => call.url === "/api/account/register").length, 1);
if (mode === "hosted") {
  assert.match(document.querySelector(".trial-account")?.textContent || "", /OpenAI/);
  assert.match(document.querySelector(".consent")?.textContent || "", /à OpenAI/);
  assert.doesNotMatch(document.body.textContent, /private-owner@example\.test/);
}
const conversation = document.querySelector("#conversation");
const setConversation = value => {
  Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set.call(conversation, value);
  conversation.dispatchEvent(new window.Event("input", { bubbles: true }));
};
setConversation("Moi : Bonjour\nAutre personne : Salut");
await waitFor(() => conversation.value.includes("Salut"));
const confirmed = document.querySelector(".context-sheet label.check:not(.ocr-consent) input");
const consent = document.querySelector(".consent input");
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
console.log(`PASS ${mode} beta UI: invitation, renewed consent, preserved draft on balance failure, no visitor ChatGPT login.`);
dom.window.close();
