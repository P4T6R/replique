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

const imageDom = new JSDOM('<div id="root"></div>', { url: "https://replique.duckdns.org/app", runScripts: "outside-only", pretendToBeVisual: true });
const imageWindow = imageDom.window;
const imageDocument = imageWindow.document;
let imageConversation = { id: "image-one", title: "Capture test", intent: "répondre naturellement", tone: "naturel", style: "", revision: 0, updated_at: 1, messages: [], suggestions: null };
let importAttempts = 0;
let completeImport;
let completeGeneration;
imageWindow.fetch = async (url, options = {}) => {
  const path = String(url);
  if (path === "/api/health") return { ok: true, json: async () => ({ mode: "hosted" }) };
  if (path === "/api/account/status") return { ok: true, json: async () => account };
  if (path === "/api/conversations") return { ok: true, json: async () => ({ conversations: [{ id: "image-one", title: imageConversation.title, updated_at: 1 }] }) };
  if (path === "/api/conversations/image-one" && (!options.method || options.method === "GET")) return { ok: true, json: async () => structuredClone(imageConversation) };
  if (path === "/api/conversations/image-one/import-image") {
    importAttempts++;
    if (importAttempts === 1) return new Promise(resolve => { completeImport = resolve; });
    imageConversation = { ...imageConversation, revision: 1, messages: [
      { id: "image-message-1", sender: "me", body: "Salut", created_at: 1 },
      { id: "image-message-2", sender: "other", body: "Coucou", created_at: 2 },
    ] };
    return { ok: true, json: async () => ({ added: 2, conversation: structuredClone(imageConversation) }) };
  }
  if (path === "/api/conversations/image-one/generate") return new Promise(resolve => { completeGeneration = resolve; });
  throw new Error(`Unexpected hosted image request: ${path}`);
};
imageWindow.eval(bundle);
await waitFor(() => imageDocument.querySelector(".conversation-link"));
imageDocument.querySelector(".conversation-link").click();
await waitFor(() => imageDocument.querySelector('.composer-tools input[type="file"]'));
const imageInput = imageDocument.querySelector('.composer-tools input[type="file"]');
Object.defineProperty(imageInput, "files", { configurable: true, value: [new imageWindow.File(["synthetic"], "capture.png", { type: "image/png" })] });
imageInput.dispatchEvent(new imageWindow.Event("change", { bubbles: true }));
await waitFor(() => imageDocument.querySelector(".chat-processing"));
assert.match(imageDocument.querySelector(".chat-processing").textContent, /Lecture de votre capture en cours/);
assert.match(imageDocument.querySelector(".coach-progress").textContent, /Je lis votre capture/);
completeImport({ ok: false, status: 503, json: async () => ({ detail: "Service momentanément indisponible." }) });
await waitFor(() => imageDocument.querySelector(".chat-feedback"));
assert.match(imageDocument.querySelector(".chat-feedback").textContent, /Réessayer cette capture/);
assert.equal(imageDocument.querySelector(".chat-processing"), null);
[...imageDocument.querySelectorAll(".chat-feedback button")].find(button => button.textContent.includes("Saisir son message")).click();
assert.equal(imageDocument.activeElement, imageDocument.querySelector(".composer-row textarea"));
[...imageDocument.querySelectorAll(".chat-feedback button")].find(button => button.textContent.includes("Réessayer cette capture")).click();
await waitFor(() => importAttempts === 2 && imageDocument.querySelector(".chat-processing")?.textContent.includes("Préparation de vos réponses"));
assert.match(imageDocument.querySelector(".coach-progress").textContent, /Je prépare vos réponses/);
const imageSuggestions = { insight: "Coucou est le dernier message.", boundary: false,
  replies: ["Simple", "Chaleureuse", "Directe"].map((title, index) => ({ id: String(index + 1), title, text: `Réponse ${index + 1}`, why: "Suit le fil." })) };
imageConversation = { ...imageConversation, suggestions: imageSuggestions };
completeGeneration({ ok: true, status: 200, json: async () => imageSuggestions });
await waitFor(() => imageDocument.querySelectorAll(".suggestion-card").length === 3);
assert.equal(imageDocument.querySelector(".chat-feedback"), null);
console.log("PASS hosted image progress, persistent error actions, retry and answer generation.");
imageWindow.close();
