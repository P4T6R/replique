import { useEffect, useRef, useState } from "react";
import { AccountPanel, type AccountStatus } from "./Account";
import "./hosted.css";

type Message = { id: string; sender: "me" | "other"; body: string; created_at: number };
type Reply = { id: string; title: string; text: string; why: string };
type Suggestions = { insight: string; replies: Reply[]; boundary: boolean };
type Conversation = { id: string; title: string; intent: string; tone: string; style: string; revision: number; updated_at: number; messages: Message[]; suggestions: Suggestions | null };
type Summary = { id: string; title: string; updated_at: number };
const jsonHeaders = { "Content-Type": "application/json", "X-Replique-Request": "1" };

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, init);
  let data: any;
  try { data = await response.json(); }
  catch { throw new Error("Le service ne répond pas correctement. Réessayez."); }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Une erreur est survenue. Réessayez.");
  return data as T;
}

export function HostedLanding() {
  return <div className="hosted-root landing-page">
    <header className="hosted-nav"><a className="hosted-brand" href="/"><span>r</span> réplique.</a><nav aria-label="Navigation principale"><a href="#comment-ca-marche">Comment ça marche</a><a href="/app">Se connecter</a><a className="hosted-nav-cta" href="/app?register=1">S’inscrire <span aria-hidden="true">↗</span></a></nav></header>
    <main>
      <section className="landing-hero"><div className="landing-copy"><span className="landing-kicker">L’ATELIER DE VOS CONVERSATIONS</span><h1>La suite de la conversation commence ici<span>.</span></h1><p>Un échange en capture ou en texte. Trois façons de répondre. Et quand la conversation continue, Réplique garde le fil.</p><div className="landing-actions"><a className="landing-primary" href="/app?register=1">Trouver mes mots <span aria-hidden="true">↗</span></a><a className="landing-secondary" href="#comment-ca-marche">Voir comment ça marche ↓</a></div><small>Vous gardez le dernier mot. Réplique n’envoie jamais de message à votre place.</small></div>
        <div className="landing-preview" aria-label="Aperçu d’une conversation fictive dans Réplique"><div className="preview-top"><div className="preview-avatar">A</div><div><strong>Une conversation</strong><span>Vos échanges, au même endroit</span></div><i aria-hidden="true">•••</i></div><div className="preview-messages"><div className="preview-bubble mine">Alors, cette expo ?</div><div className="preview-bubble theirs">Super bien passée !</div><div className="preview-bubble theirs">Mon tableau a même été choisi pour l’affiche 😄</div></div><div className="preview-suggestion"><span>UNE PISTE POUR CONTINUER</span><strong>Ah, la classe ! Tu me montres l’affiche ?</strong><div>Simple · Chaleureuse · Directe</div></div></div>
      </section>
      <section id="comment-ca-marche" className="landing-steps"><div className="landing-section-head"><span className="landing-kicker">SIMPLE, DU PREMIER MESSAGE AU SUIVANT</span><h2>Une conversation. Plusieurs possibilités.</h2></div><div className="step-grid"><article><span>01</span><h3>Ajoutez l’échange</h3><p>Importez une capture ou collez des messages. Réplique les place dans une conversation à retrouver plus tard.</p></article><article><span>02</span><h3>Choisissez vos mots</h3><p>Définissez l’objectif et le ton, puis comparez les propositions en tenant compte du dernier message reçu.</p></article><article><span>03</span><h3>Continuez naturellement</h3><p>Copiez une idée, indiquez ce que vous avez vraiment envoyé, puis ajoutez sa réponse. Le contexte reste là.</p></article></div></section>
      <section className="landing-final"><span className="landing-kicker">À VOTRE FAÇON</span><h2>Vous écrivez l’histoire.<br/><em>On vous aide à trouver la suite.</em></h2><a className="landing-primary" href="/app?register=1">Commencer <span aria-hidden="true">↗</span></a></section>
    </main><footer className="hosted-footer"><span>réplique.</span><span>Une aide pour écrire. Aucun envoi automatique. <a href="/confidentialite.html">Confidentialité</a></span></footer>
  </div>;
}

function parseExchange(raw: string): { sender: "me" | "other"; body: string }[] {
  const lines = raw.trim().split(/\r?\n/);
  const messages: { sender: "me" | "other"; body: string }[] = [];
  for (const line of lines) {
    const match = line.match(/^\s*(Moi|Je|Elle|Lui|Autre personne)\s*:\s*(.+)$/i);
    if (match) messages.push({ sender: /^(moi|je)$/i.test(match[1]) ? "me" : "other", body: match[2].trim() });
    else if (line.trim() && messages.length) messages[messages.length - 1].body += "\n" + line.trim();
    else if (line.trim()) messages.push({ sender: "other", body: line.trim() });
  }
  return messages.filter(message => message.body.length > 0);
}

export function HostedWorkspace() {
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<Summary[]>([]);
  const [active, setActive] = useState<Conversation | null>(null);
  const [draft, setDraft] = useState("");
  const [sender, setSender] = useState<"me" | "other">("other");
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [settings, setSettings] = useState({ title: "", intent: "répondre naturellement", tone: "naturel", style: "" });
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [editingMessage, setEditingMessage] = useState<{ id: string; sender: "me" | "other"; body: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api<AccountStatus>("/api/account/status").then(setAccount).catch(() => setAccount(null)).finally(() => setLoading(false)); }, []);
  useEffect(() => { if (account) void refreshList(); else { setItems([]); setActive(null); } }, [account?.email]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [active?.messages.length]);

  async function refreshList() {
    try { const data = await api<{ conversations: Summary[] }>("/api/conversations"); setItems(data.conversations); }
    catch (reason) { setError((reason as Error).message); }
  }
  function show(conversation: Conversation) {
    setActive(conversation); setSettings({ title: conversation.title, intent: conversation.intent, tone: conversation.tone, style: conversation.style });
    setEdits(Object.fromEntries((conversation.suggestions?.replies || []).map(reply => [reply.id, reply.text])));
    setDraft(""); setPaste(""); setEditingMessage(null); setError(""); setNotice("");
  }
  async function choose(id: string) {
    if (busy) return;
    setBusy("open"); setError("");
    try { show(await api<Conversation>(`/api/conversations/${id}`)); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }
  async function create() {
    if (busy) return;
    setBusy("create"); setError("");
    try { show(await api<Conversation>("/api/conversations", { method: "POST", headers: jsonHeaders, body: JSON.stringify({ title: "Nouvelle conversation" }) })); await refreshList(); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }
  async function saveSettings() {
    if (!active || busy) return;
    setBusy("settings"); setError("");
    try { show(await api<Conversation>(`/api/conversations/${active.id}`, { method: "PATCH", headers: jsonHeaders, body: JSON.stringify(settings) })); await refreshList(); setNotice("Réglages enregistrés pour cette conversation."); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }
  async function generate(conversation: Conversation) {
    setBusy("generate"); setError(""); setNotice("");
    try {
      const result = await api<Suggestions>(`/api/conversations/${conversation.id}/generate`, { method: "POST", headers: jsonHeaders });
      const latest = await api<Conversation>(`/api/conversations/${conversation.id}`);
      show({ ...latest, suggestions: result });
      const status = await api<AccountStatus>("/api/account/status"); setAccount(status);
      await refreshList();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }
  async function addMessage(body = draft, who = sender, thenGenerate = true) {
    if (!active || !body.trim() || busy) return;
    setBusy("message"); setError(""); setNotice("");
    try {
      const updated = await api<Conversation>(`/api/conversations/${active.id}/messages`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ sender: who, body: body.trim() }) });
      show(updated); await refreshList();
      if (thenGenerate && who === "other") await generate(updated);
      else setBusy("");
    } catch (reason) { setError((reason as Error).message); setBusy(""); }
  }
  async function importText() {
    if (!active || !paste.trim() || busy) return;
    const messages = parseExchange(paste);
    if (!messages.length) { setError("Aucun message à importer."); return; }
    setBusy("import"); setError("");
    try {
      const data = await api<{ added: number; conversation: Conversation }>(`/api/conversations/${active.id}/import-text`, { method: "POST", headers: jsonHeaders, body: JSON.stringify({ revision: active.revision, messages }) });
      show(data.conversation); await refreshList();
      if (data.added) await generate(data.conversation);
      else { setNotice("Ces messages sont déjà dans la conversation."); setBusy(""); }
    } catch (reason) { setError((reason as Error).message); setBusy(""); }
  }
  async function importImage(file?: File) {
    if (!active || !file || busy) return;
    setBusy("import"); setError(""); setNotice("");
    const body = new FormData(); body.append("file", file);
    try {
      const data = await api<{ added: number; conversation: Conversation }>(`/api/conversations/${active.id}/import-image`, { method: "POST", headers: { "X-Replique-Request": "1" }, body });
      show(data.conversation); await refreshList();
      if (data.added) await generate(data.conversation);
      else { setNotice("Cette capture n’ajoute aucun nouveau message."); setBusy(""); }
    } catch (reason) { setError((reason as Error).message); setBusy(""); }
    finally { if (fileRef.current) fileRef.current.value = ""; }
  }
  async function remove() {
    if (!active || busy || !window.confirm(`Supprimer définitivement « ${active.title} » et ses messages ?`)) return;
    setBusy("delete"); setError("");
    try { await api(`/api/conversations/${active.id}`, { method: "DELETE", headers: jsonHeaders }); setActive(null); await refreshList(); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }
  async function correctMessage(removeMessage = false) {
    if (!active || !editingMessage || busy) return;
    setBusy("correction"); setError("");
    try {
      const updated = await api<Conversation>(`/api/conversations/${active.id}/messages/${editingMessage.id}`, {
        method: removeMessage ? "DELETE" : "PATCH", headers: jsonHeaders,
        ...(!removeMessage ? { body: JSON.stringify({ sender: editingMessage.sender, body: editingMessage.body.trim() }) } : {}),
      });
      show(updated); await refreshList(); setNotice(removeMessage ? "Message retiré." : "Message corrigé.");
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  }

  return <div className="hosted-root workspace-page">
    <header className="hosted-nav"><a className="hosted-brand" href="/"><span>r</span> réplique.</a><div className="workspace-account">{account && <span>{account.trial_remaining} crédit{account.trial_remaining > 1 ? "s" : ""}</span>}<a href="/">Accueil ↗</a></div></header>
    {loading ? <main className="workspace-loading">Ouverture de votre espace…</main> : !account ? <main className="hosted-auth"><div><span className="landing-kicker">VOTRE ESPACE RÉPLIQUE</span><h1>Retrouvez le fil de vos conversations.</h1><p>Connectez-vous pour reprendre un échange, importer une capture ou trouver la suite.</p></div><AccountPanel account={null} onChange={setAccount} startRegistering={new URLSearchParams(window.location.search).has("register")} /></main> :
      <main className="conversation-layout"><aside className="conversation-sidebar"><div className="sidebar-heading"><span className="landing-kicker">VOTRE ESPACE</span><h1>Conversations</h1></div><button className="new-conversation" onClick={() => void create()} disabled={!!busy}>＋ Nouvelle conversation</button><nav aria-label="Vos conversations">{items.map(item => <button key={item.id} className={item.id === active?.id ? "conversation-link active" : "conversation-link"} onClick={() => void choose(item.id)}><span className="conversation-initial">{item.title.slice(0, 1).toUpperCase()}</span><span><strong>{item.title}</strong><small>{new Date(item.updated_at * 1000).toLocaleDateString("fr-FR")}</small></span></button>)}</nav><div className="sidebar-bottom"><span>{account.email}</span><button onClick={async () => { await api("/api/account/logout", { method: "POST", headers: jsonHeaders }); setAccount(null); }}>Se déconnecter</button></div></aside>
        <section className="chat-panel">{active ? <><div className="chat-header"><div className="chat-avatar">{active.title.slice(0, 1).toUpperCase()}</div><div><h2>{active.title}</h2><span>Réplique garde le contexte de cet échange</span></div><button className="chat-settings-button" onClick={() => void remove()} disabled={!!busy} title="Supprimer cette conversation">Supprimer</button></div>
          <div className="chat-scroll"><div className="chat-intro">Les messages que vous ajoutez restent dans cette conversation. Les propositions ne sont jamais envoyées automatiquement.</div>{active.messages.map(message => <div key={message.id} className={`chat-row ${message.sender === "me" ? "mine" : "theirs"}`}><div className="chat-bubble">{editingMessage?.id === message.id ? <div className="bubble-edit"><select aria-label="Auteur du message" value={editingMessage.sender} onChange={event => setEditingMessage({ ...editingMessage, sender: event.target.value as "me" | "other" })}><option value="other">Message reçu</option><option value="me">Mon message</option></select><textarea aria-label="Corriger le message" value={editingMessage.body} maxLength={2000} rows={3} onChange={event => setEditingMessage({ ...editingMessage, body: event.target.value })}/><div><button onClick={() => void correctMessage()} disabled={!!busy || !editingMessage.body.trim()}>Enregistrer</button><button onClick={() => setEditingMessage(null)}>Annuler</button><button onClick={() => void correctMessage(true)} disabled={!!busy}>Retirer</button></div></div> : <>{message.body}<button className="bubble-correct" onClick={() => setEditingMessage({ id: message.id, sender: message.sender, body: message.body })}>Corriger</button></>}</div></div>)}<div ref={bottomRef}/></div>
          <div className="composer"><div className="sender-switch" role="group" aria-label="Auteur du message"><button className={sender === "other" ? "selected" : ""} onClick={() => setSender("other")}>Message reçu</button><button className={sender === "me" ? "selected" : ""} onClick={() => setSender("me")}>Mon message</button></div><div className="composer-row"><textarea aria-label={sender === "other" ? "Nouvelle réponse reçue" : "Message que j'ai envoyé"} placeholder={sender === "other" ? "Elle a répondu… Écrivez son message ici." : "Ce que vous avez réellement envoyé…"} value={draft} onChange={event => setDraft(event.target.value)} maxLength={2000} rows={2}/><button onClick={() => void addMessage()} disabled={!draft.trim() || !!busy}>{busy === "message" || busy === "generate" ? "Analyse…" : sender === "other" ? "Ajouter et répondre ↗" : "Ajouter ↗"}</button></div><div className="composer-tools"><input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif" className="sr-only" onChange={event => void importImage(event.target.files?.[0])}/><button onClick={() => fileRef.current?.click()} disabled={!!busy}>＋ Ajouter une capture</button><span>Une idée copiée n’est ajoutée à l’échange que si vous confirmez l’avoir envoyée.</span></div></div>
        </> : <div className="chat-start"><div className="chat-start-icon">✳</div><span className="landing-kicker">CHAQUE ÉCHANGE A SA SUITE</span><h2>Reprenez une conversation.<br/><em>À votre façon.</em></h2><p>Créez un échange, ajoutez une capture ou les messages en texte, puis découvrez vos réponses.</p><button className="landing-primary" onClick={() => void create()} disabled={!!busy}>Créer une conversation ↗</button></div>}</section>
        <aside className="coach-panel">{active ? <><div className="coach-heading"><span className="landing-kicker">L’ATELIER</span><h2>Trouvons les mots.</h2><p>Le dernier message et l’ensemble de l’échange guident les propositions.</p></div><details className="coach-settings"><summary>Objectif et style <span>＋</span></summary><div className="coach-settings-body"><label>Nom de l’échange<input value={settings.title} maxLength={80} onChange={event => setSettings({ ...settings, title: event.target.value })}/></label><label>Je veux…<select value={settings.intent} onChange={event => setSettings({ ...settings, intent: event.target.value })}><option>répondre naturellement</option><option>relancer</option><option>proposer de se voir</option><option>clarifier</option><option>poser une limite</option><option>décliner</option></select></label><label>Ton<select value={settings.tone} onChange={event => setSettings({ ...settings, tone: event.target.value })}><option value="naturel">Naturel</option><option value="chaleureux">Chaleureux</option><option value="léger">Taquin et léger</option><option value="direct">Direct</option></select></label><label>Votre façon d’écrire (facultatif)<textarea value={settings.style} maxLength={500} rows={2} onChange={event => setSettings({ ...settings, style: event.target.value })} placeholder="Ex. phrases courtes, pas de surnoms…"/></label><button onClick={() => void saveSettings()} disabled={!!busy || !settings.title.trim()}>Enregistrer</button></div></details>
          {!active.messages.length && <div className="coach-first"><strong>Commencez avec une capture</strong><p>Utilisez « Ajouter une capture » sous la conversation, ou collez un échange en texte ci-dessous.</p></div>}
          <details className="coach-import"><summary>Coller un échange en texte <span>＋</span></summary><textarea value={paste} onChange={event => setPaste(event.target.value)} rows={5} placeholder={"Moi : Salut !\nAutre personne : Coucou, ça va ?"}/><button onClick={() => void importText()} disabled={!paste.trim() || !!busy}>Importer et trouver des réponses ↗</button><small>Une ligne « Moi : » ou « Autre personne : » par message.</small></details>
          {active.messages.length > 0 && <button className="coach-generate" onClick={() => void generate(active)} disabled={!!busy}>{busy === "generate" ? "Réplique réfléchit…" : "Trouver des réponses ↗"}</button>}
          {active.suggestions && <div className="coach-results"><div className="coach-insight"><span>LE POINT DE REPÈRE</span><p>{active.suggestions.insight}</p></div><h3>{active.suggestions.replies.length > 1 ? "Trois façons de répondre" : "Une piste pour répondre"}</h3>{active.suggestions.replies.map((reply, index) => <article className="suggestion-card" key={reply.id}><div className="suggestion-meta"><span>0{index + 1} · {reply.title}</span><button onClick={async () => { try { await navigator.clipboard.writeText(edits[reply.id] ?? reply.text); setNotice("Réponse copiée. Elle n’a pas été ajoutée à la conversation."); } catch { setError("Copie impossible. Sélectionnez le texte manuellement."); } }} disabled={!reply.text}>Copier ↗</button></div><textarea aria-label={`Proposition ${index + 1}`} value={edits[reply.id] ?? reply.text} onChange={event => setEdits({ ...edits, [reply.id]: event.target.value })} rows={3}/><p>{reply.why}</p>{reply.text && <button className="sent-action" onClick={() => void addMessage(edits[reply.id] ?? reply.text, "me", false)} disabled={!!busy || !(edits[reply.id] ?? reply.text).trim()}>J’ai envoyé ce texte</button>}</article>)}</div>}
          <p className="coach-privacy">Vos messages sont analysés pour proposer une réponse. <a href="/confidentialite.html">Comment vos données sont traitées</a></p>
        </> : <div className="coach-empty"><span className="landing-kicker">UN PEU DE RECUL, ÇA AIDE.</span><h2>Les bonnes réponses gardent le fil.</h2><p>Une conversation suivie, des propositions adaptées, et toujours votre décision.</p></div>}</aside>
      </main>}
    {error && <div className="hosted-toast error" role="alert">{error}<button onClick={() => setError("")} aria-label="Fermer">×</button></div>}{notice && <div className="hosted-toast" role="status">{notice}<button onClick={() => setNotice("")} aria-label="Fermer">×</button></div>}
  </div>;
}
