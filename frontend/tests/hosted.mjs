import { JSDOM } from "jsdom";
import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";

const bundle = readFileSync("dist/assets/" + readdirSync("dist/assets").find(name => name.endsWith(".js")), "utf8");
const waitFor = async predicate => {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.ok(predicate(), "Hosted UI state did not appear");
};
const landing = new JSDOM('<div id="root"></div>', { url: "https://replique.duckdns.org/", runScripts: "outside-only", pretendToBeVisual: true });
landing.window.fetch = async () => ({ ok: true, json: async () => ({ mode: "hosted" }) });
landing.window.eval(bundle);
await waitFor(() => landing.window.document.querySelector(".landing-hero"));
assert.ok(landing.window.document.querySelector('a[href="/app"]'));
assert.ok(landing.window.document.querySelector('a[href="/app?register=1"]'));
assert.match(landing.window.document.body.textContent, /n’envoie jamais de message/);
landing.window.close();

const dom = new JSDOM('<div id="root"></div>', { url: "https://replique.duckdns.org/app", runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
window.HTMLElement.prototype.scrollIntoView = () => {};
const account = { email: "beta@example.test", trial_remaining: 20, trial_total: 20, subscription_active: false, subscription_available: false };
let conversation = null;
let generated = 0;
const calls = [];
window.fetch = async (url, options = {}) => {
  calls.push({ url, options });
  const path = String(url);
  const method = options.method || "GET";
  let data;
  if (path === "/api/health") data = { mode: "hosted" };
  else if (path === "/api/account/status") data = account;
  else if (path === "/api/conversations" && method === "GET") data = { conversations: conversation ? [{ id: "one", title: conversation.title, updated_at: 1 }] : [] };
  else if (path === "/api/conversations" && method === "POST") {
    conversation = { id: "one", title: "Nouvelle conversation", intent: "répondre naturellement", tone: "naturel", style: "", revision: 0, updated_at: 1, messages: [], suggestions: null };
    data = conversation;
  } else if (path === "/api/conversations/one" && method === "GET") data = conversation;
  else if (path === "/api/conversations/one/import-text") {
    const payload = JSON.parse(options.body);
    conversation = { ...conversation, revision: conversation.revision + 1, messages: payload.messages.map((message, index) => ({ ...message, id: String(index), created_at: 1 })) };
    data = { added: payload.messages.length, conversation };
  } else if (path === "/api/conversations/one/messages") {
    const message = JSON.parse(options.body);
    conversation = { ...conversation, revision: conversation.revision + 1, suggestions: null,
      messages: [...conversation.messages, { ...message, id: String(conversation.messages.length), created_at: 2 }] };
    data = conversation;
  } else if (path === "/api/conversations/one/generate") {
    generated++;
    const result = { insight: "La dernière réponse guide les propositions.", boundary: false,
      replies: ["Simple", "Plus chaleureuse", "Plus directe"].map((title, index) => ({ id: String(index + 1), title, text: `Proposition ${index + 1}`, why: "Adaptée à l’échange." })) };
    conversation = { ...conversation, suggestions: result };
    data = result;
  } else data = {};
  return { ok: true, status: 200, json: async () => structuredClone(data) };
};
window.eval(bundle);
await waitFor(() => window.document.querySelector(".new-conversation"));
window.document.querySelector(".new-conversation").click();
await waitFor(() => window.document.querySelector(".coach-import"));
window.document.querySelector(".coach-import summary").click();
const paste = window.document.querySelector(".coach-import textarea");
Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set.call(paste, "Moi : Salut\nAutre personne : Coucou, ça va ?");
paste.dispatchEvent(new window.Event("input", { bubbles: true }));
await waitFor(() => !window.document.querySelector(".coach-import button").disabled);
window.document.querySelector(".coach-import button").click();
await waitFor(() => window.document.querySelectorAll(".suggestion-card").length === 3);
assert.equal(window.document.querySelectorAll(".chat-bubble").length, 2);
assert.equal(conversation.messages.filter(message => message.sender === "me").length, 1);
window.document.querySelector(".sent-action").click();
await waitFor(() => window.document.querySelectorAll(".chat-bubble").length === 3);
assert.equal(conversation.messages[2].body, "Proposition 1");
assert.equal(window.document.querySelectorAll(".suggestion-card").length, 0);
const draft = window.document.querySelector(".composer-row textarea");
Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set.call(draft, "Oui, et toi ?");
draft.dispatchEvent(new window.Event("input", { bubbles: true }));
await waitFor(() => !window.document.querySelector(".composer-row button").disabled);
window.document.querySelector(".composer-row button").click();
await waitFor(() => generated === 2);
assert.equal(conversation.messages[3].sender, "other");
assert.equal(conversation.messages[3].body, "Oui, et toi ?");
assert.equal(window.document.querySelectorAll(".suggestion-card").length, 3);
assert.equal(calls.filter(call => call.url === "/api/conversations/one/generate").length, 2);
console.log("PASS hosted landing and persistent conversation: import, three suggestions, explicit sent message, next received reply.");
window.close();
