import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
import { MemoryPanel, SaveMemory, memoryRequest, type MemoryPreview } from "./Memory";
import { AccountPanel, type AccountStatus } from "./Account";
type Health = {
  mode: "demo" | "live" | "chatgpt" | "local" | "hosted";
  ocr_available: boolean;
  ocr_languages: string[];
  provider: string | null;
};
type AuthStatus = {
  enabled: boolean;
  status: "disconnected" | "connecting" | "connected" | "reauth_required";
  sharing: boolean;
  identity?: { email?: string };
  error?: { code: string; message: string };
};
type Model = { slug: string; display_name: string };
const usageUrl = "https://chatgpt.com/settings/usage";
const authHeaders = { "X-Replique-Request": "1" };
type Reply = { id: string; title: string; text: string; why: string };
type Result = {
  mode: string;
  notice: string;
  insight: string;
  boundary: boolean;
  replies: Reply[];
  memory_used?: { item_ids: string[]; profile_used: boolean; revision: number; notice: string };
};
const intentions = [
  "répondre naturellement",
  "relancer",
  "proposer de se voir",
  "clarifier",
  "poser une limite",
  "décliner",
];
const refusal =
  "Moi : On se revoit ?\nAutre personne : Merci, mais je ne suis pas intéressée.";
const brief = "Moi : Ça m’a fait plaisir de discuter avec toi.\nAutre personne : Oui, c’était sympa.\nMoi : Ta journée se passe bien ?\nAutre personne : Oui tranquille.";
const unanswered = "Autre personne : On se reparle plus tard.\nMoi : D’accord, à plus.\nMoi : Salut, comment ça va ?\nMoi : Tu as eu le temps de voir mon message ?";
const sample =
  "Moi : Ça m’a fait plaisir de discuter avec toi !\nAutre personne : Moi aussi, c’était sympa. On remet ça ?";
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const r = await fetch(url, options);
  let data;
  try {
    data = await r.json();
  } catch {
    throw new Error(
      "Le serveur ne répond pas correctement. Réessayez dans un instant.",
    );
  }
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : typeof data.detail?.message === "string"
          ? data.detail.message
          : "Les informations envoyées ne sont pas valides. Vérifiez les champs.",
    );
  return data;
}
function App() {
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authError, setAuthError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [models, setModels] = useState<Model[]>([]);
  const [model, setModel] = useState("");
  const [welcome, setWelcome] = useState(false);
  const authEpoch = useRef(0);
  const welcomeDialog = useRef<HTMLDialogElement>(null);
  const [health, setHealth] = useState<Health | null>(null),
    [connection, setConnection] = useState("");
  const [conversation, setConversation] = useState(""),
    [intent, setIntent] = useState(intentions[0]),
    [tone, setTone] = useState("naturel"),
    [style, setStyle] = useState(""),
    [emoji, setEmoji] = useState(false);
  const [abstention, setAbstention] = useState(false);
  const [locale, setLocale] = useState("fr_neutre"), [familiarity, setFamiliarity] = useState("neutre");
  const [confirmed, setConfirmed] = useState(false),
    [consent, setConsent] = useState(false),
    [ocrConsent, setOcrConsent] = useState(false),
    [result, setResult] = useState<Result | null>(null),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [ocrNotice, setOcrNotice] = useState("");
  const [useMemory, setUseMemory] = useState(false), [memoryPreview, setMemoryPreview] = useState<MemoryPreview | null>(null), [memoryError, setMemoryError] = useState(""), [memoryRevision, setMemoryRevision] = useState(0);
  const memoryChanged = () => { setMemoryRevision(v => v + 1); setConsent(false); setUseMemory(false); setMemoryPreview(null); };
  useEffect(() => {
    let current = true; setConsent(false); setMemoryPreview(null); setMemoryError("");
    if (useMemory) memoryRequest<MemoryPreview>("/api/memory/preview?" + new URLSearchParams({ intent, tone, locale })).then(data => { if (current) setMemoryPreview(data); }).catch(e => { if (current) setMemoryError((e as Error).message); });
    return () => { current = false; };
  }, [useMemory, intent, tone, locale, memoryRevision]);
  const file = useRef<HTMLInputElement>(null),
    generation = useRef(0),
    abort = useRef<AbortController | null>(null),
    results = useRef<HTMLElement>(null);
  const isHosted = health?.mode === "local" || health?.mode === "hosted";
  const connect = () => {
    setConnection("");
    request<Health>("/api/health")
      .then(data => { setHealth(data); if (data.mode === "local" || data.mode === "hosted") void refreshAccount(); else void refreshAuth(); })
      .catch(error => setConnection((error as Error).message));
  };
  async function refreshAccount() {
    try { setAccount(await request<AccountStatus>("/api/account/status")); }
    catch { setAccount(null); setResult(null); setConversation(""); }
  }
  async function refreshAuth() {
    const epoch = ++authEpoch.current;
    setModels([]);
    setModel("");
    setConsent(false);
    setUseMemory(false);
    setMemoryPreview(null);
    try {
      const status = await request<AuthStatus>("/api/auth/status");
      if (epoch !== authEpoch.current) return;
      setAuth(status);
      setAuthError(status.error?.message || "");
      if (status.status === "connected" && status.sharing) {
        let seen = false;
        try { seen = localStorage.getItem("replique-plan-welcome") === "seen"; } catch { /* Storage may be disabled. */ }
        if (!seen) setWelcome(true);
        const data = await request<{ models: Model[] }>("/api/auth/models");
        if (epoch !== authEpoch.current) return;
        setModels(data.models);
        setModel((previous) => data.models.some((m) => m.slug === previous) ? previous : data.models[0]?.slug || "");
      } else {
        setModels([]);
        setModel("");
      }
    } catch (e) {
      if (epoch === authEpoch.current) setAuthError((e as Error).message);
    }
  }
  async function login() {
    if (busy || authBusy) return;
    setAuthBusy(true);
    setAuthError("");
    try {
      const data = await request<{ authorization_url: string }>("/api/auth/login", { method: "POST", headers: authHeaders });
      const url = new URL(data.authorization_url);
      if (url.origin !== "https://auth.openai.com" || url.pathname !== "/api/accounts/authorize" || url.username || url.password || url.hash)
        throw new Error("Adresse de connexion refusée : le domaine doit être auth.openai.com.");
      window.location.assign(url.href);
    } catch (e) {
      setAuthError((e as Error).message);
    } finally { setAuthBusy(false); }
  }
  async function logout() {
    if (busy || authBusy) return;
    setAuthBusy(true);
    setAuthError("");
    try {
      const data = await request<{ remote_revoked: boolean }>("/api/auth/logout", { method: "POST", headers: authHeaders });
      authEpoch.current++;
      setAuth({ enabled: !!auth?.enabled, status: "disconnected", sharing: false });
      setModels([]);
      setModel("");
      setConsent(false);
      setOcrConsent(false);
      setUseMemory(false);
      setMemoryPreview(null);
      setResult(null);
      setWelcome(false);
      setNotice(data.remote_revoked ? "Compte ChatGPT déconnecté." : "Connexion locale effacée. Vérifiez les autorisations de Réplique dans les réglages ChatGPT pour révoquer son accès.");
      connect();
    } catch (e) { setAuthError((e as Error).message); }
    finally { setAuthBusy(false); }
  }
  function dismissWelcome() {
    try { localStorage.setItem("replique-plan-welcome", "seen"); } catch { /* No credentials are stored here. */ }
    setWelcome(false);
  }
  useEffect(() => {
    if (welcome) welcomeDialog.current?.showModal?.();
    else welcomeDialog.current?.close?.();
  }, [welcome]);
  useEffect(() => {
    connect();
    const url = new URL(window.location.href);
    if (url.searchParams.has("auth")) {
      url.searchParams.delete("auth");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    }
    return () => abort.current?.abort();
  }, []);
  function updateConversation(value: string) {
    setConversation(value);
    setConfirmed(false);
    setResult(null);
    setError("");
  }
  function reset() {
    generation.current++;
    abort.current?.abort();
    setBusy("");
    setConversation("");
    setStyle("");
    setIntent(intentions[0]);
    setTone("naturel");
    setEmoji(false);
    setLocale("fr_neutre");
    setFamiliarity("neutre");
    setConfirmed(false);
    setConsent(false);
    setOcrConsent(false);
    setUseMemory(false);
    setMemoryPreview(null);
    setResult(null);
    setError("");
    setOcrNotice("");
    setNotice(
      isHosted
        ? "Conversation effacée de cet appareil. Les fichiers déjà exportés restent sur votre appareil."
        : "Session effacée de cet atelier. Votre mémoire de style reste conservée ; utilisez « Effacer toute la mémoire » pour la supprimer. Les fichiers exportés et le presse-papiers restent sur votre appareil. Les données déjà transmises à un fournisseur restent soumises à ses règles de conservation.",
    );
    if (file.current) file.current.value = "";
  }
  async function generate(e: React.FormEvent) {
    e.preventDefault();
    if (busy || authBusy || !health || !confirmed || (health.mode === "chatgpt" && (!auth?.sharing || auth.status !== "connected" || !model)) || (isHosted && (!account || (!account.subscription_active && account.trial_remaining === 0)))) return;
    if (useMemory && !memoryPreview) return;
    const id = ++generation.current;
    abort.current?.abort();
    abort.current = new AbortController();
    setBusy("generate");
    setError("");
    setNotice("");
    setResult(null);
    try {
      const data = await request<Result>("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders },
        body: JSON.stringify({
          conversation,
          intent,
          tone,
          style,
          emoji,
          locale,
          familiarity,
          use_memory: useMemory,
          ...(useMemory && memoryPreview ? { memory_revision: memoryPreview.revision } : {}),
          consent,
          context_confirmed: confirmed,
          ...(health.mode === "chatgpt" ? { model } : {}),
        }),
        signal: abort.current.signal,
      });
      if (id === generation.current) {
        setAbstention(data.replies.every((r) => !r.text.trim()));
        setResult(data);
        setUseMemory(false);
        setConsent(false);
        setTimeout(() => results.current?.focus(), 0);
      }
      if (isHosted) void refreshAccount();
    } catch (e) {
      if (
        id === generation.current &&
        !(e instanceof DOMException && e.name === "AbortError")
      )
        setError((e as Error).message);
    } finally {
      if (id === generation.current) setBusy("");
      if (isHosted) void refreshAccount();
    }
  }
  async function upload(f: File | undefined) {
    if (!f) return;
    if (health?.mode === "chatgpt" && (auth?.status !== "connected" || !auth.sharing || !model)) {
      setError("Connectez ChatGPT et choisissez un modèle avant d’utiliser l’OCR OpenAI.");
      return;
    }
    if (health?.mode === "chatgpt" && !ocrConsent) {
      setError("Autorisez l’envoi de cette capture à OpenAI avant de lancer la transcription.");
      return;
    }
    if (
      !["image/png", "image/jpeg", "image/webp"].includes(f.type) ||
      f.size > 5 * 1024 * 1024
    ) {
      setError("Choisissez une image PNG, JPG ou WebP de moins de 5 Mo.");
      return;
    }
    const id = ++generation.current;
    abort.current?.abort();
    abort.current = new AbortController();
    setBusy("ocr");
    setError("");
    setResult(null);
    setConfirmed(false);
    const form = new FormData();
    form.append("file", f);
    form.append("consent", String(health?.mode === "chatgpt" && ocrConsent));
    if (health?.mode === "chatgpt") form.append("model", model);
    try {
      const data = await request<{
        text: string;
        warning?: string;
        language?: string;
      }>("/api/ocr", {
        method: "POST",
        headers: authHeaders,
        body: form,
        signal: abort.current.signal,
      });
      if (id === generation.current) {
        updateConversation(data.text);
        setOcrNotice(
          data.warning ||
            "Extraction terminée. Corrigez le texte et attribuez chaque message à Moi ou Autre personne.",
        );
      }
    } catch (e) {
      if (
        id === generation.current &&
        !(e instanceof DOMException && e.name === "AbortError")
      )
        setError((e as Error).message);
    } finally {
      if (id === generation.current) setBusy("");
      setOcrConsent(false);
      if (file.current) file.current.value = "";
    }
  }
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNotice(
        "Réponse copiée. Relisez-la dans votre messagerie avant de l’envoyer.",
      );
    } catch {
      setNotice(
        "Copie indisponible. Sélectionnez la réponse et copiez-la manuellement.",
      );
    }
  }
  function exportReplies() {
    if (!result) return;
    const blob = new Blob(
      [
        `Réplique — ${result.mode === "demo" ? "démonstration" : "réponses"}\n\n${result.replies.filter((r) => r.text.trim()).map((r) => r.title + "\n" + r.text + "\n\nPourquoi : " + r.why).join("\n\n")}\n\nÀ relire avant envoi.`,
      ],
      { type: "text/plain;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = "replique-reponses.txt";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(
      "Réponses exportées. Ce fichier reste sur votre appareil après effacement de la session.",
    );
  }
  return (
    <div className="app">
      <a className="skip-link" href="#conversation">Aller à la conversation</a>
      <header className="topbar">
        <a className="brand" href="#atelier" aria-label="Réplique, accueil"><span className="brand-mark" aria-hidden="true">r</span>réplique<span className="brand-period">.</span></a>
        <span className="brand-caption">L’ATELIER DES CONVERSATIONS</span>
        <button className="quiet" onClick={reset} disabled={authBusy} aria-label="Effacer la session et commencer une nouvelle conversation">Nouvelle conversation <span aria-hidden="true">＋</span></button>
      </header>
      <main id="atelier">
        <section className="intro">
          <div><p className="eyebrow">UN MESSAGE PEUT TOUT CHANGER. RESTEZ VOUS-MÊME.</p><h1>Ça se dit.<br /><em>À votre façon.</em><span className="heading-star" aria-hidden="true">✳</span></h1></div>
          <div className="intro-aside"><p>Vous avez le fond.<br />Trouvons les mots.</p><span>Un peu de recul, trois pistes.<br />Et toujours le dernier mot pour vous.</span></div>
        </section>
        <div className="atelier-bar"><span className="eyebrow">VOTRE ESPACE POUR RÉPONDRE</span><span className={"mode " + (health && health.mode !== "demo" ? "live" : "")}><span className="dot" aria-hidden="true" />{health?.mode === "hosted" ? "IA · service Réplique" : health?.mode === "local" ? "IA · modèle sur Réplique" : health?.mode === "chatgpt" ? "IA · forfait ChatGPT" : health?.mode === "live" ? "IA · fournisseur configuré" : health ? "Démo · exemples préécrits" : "Vérification du service…"}</span></div>
        {connection && (
          <div className="error" role="alert">
            {connection} <button onClick={connect}>Réessayer</button>
          </div>
        )}
        {isHosted ? <AccountPanel account={account} provider={health?.mode === "hosted" ? "openai" : "local"} onChange={next => { reset(); setAccount(next); }} /> : health && <details className="account-disclosure" open={!!authError || auth?.status === "reauth_required"}><summary><span className="account-summary-icon" aria-hidden="true">◎</span><span>{auth?.status === "connected" ? "Votre compte ChatGPT est connecté" : "Envie d’utiliser vos propres conversations ?"}<small>{auth?.status === "connected" ? "Compte, modèles et utilisation" : "Connexion ChatGPT et état du service"}</small></span><span className="disclosure-plus" aria-hidden="true">＋</span></summary>
        <section className="account-panel" aria-labelledby="account-title" aria-busy={authBusy}>
          <div>
            <div className="eyebrow">VOTRE COMPTE</div>
            <h2 id="account-title">Votre compte. Votre forfait.</h2>
            <p>La connexion au compte et la génération sont deux étapes distinctes. Les demandes IA éligibles utilisent les limites ou les crédits de votre forfait ChatGPT.</p>
            <p className="account-privacy">La connexion se fait chez OpenAI. Le jeton de renouvellement est conservé dans un stockage protégé sur cette installation. Le jeton d’accès reste temporaire ; aucun jeton n’est stocké dans le navigateur. Aucun texte de conversation n’est envoyé pendant la connexion. Connectez-vous avant de saisir votre texte : il n’est pas conservé pendant la redirection. Une seule session ChatGPT est prise en charge par installation.</p>
          </div>
          <div className="account-actions">
            {auth?.status === "connected" ? <>
              <p className="account-state" role="status">ChatGPT connecté{auth.identity?.email ? ` · ${auth.identity.email}` : ""}</p>
              {!auth.sharing && <p role="alert">Le partage du forfait n’est pas autorisé. Reconnectez-vous pour l’activer.</p>}
              <button type="button" className="text-button" onClick={logout} disabled={!!busy || authBusy}>Déconnecter ChatGPT</button>
            </> : <>
              <button type="button" className="chatgpt-login" onClick={login} disabled={!!busy || authBusy || !auth?.enabled || auth.status === "connecting"}>
                {authBusy ? "Ouverture de la connexion…" : "Continue with ChatGPT"}
              </button>
              {auth?.status === "connecting" && <p role="status">Connexion en attente chez OpenAI. Vous pouvez l’annuler ci-dessous.</p>}
              {(auth?.status === "reauth_required" || auth?.error?.code === "reauth_required" || auth?.error?.code === "session_expired") && <p role="status">Votre session a expiré. Reconnectez-vous pour continuer.</p>}
              {auth?.status === "connecting" && <button type="button" className="text-button" disabled={!!busy || authBusy} onClick={logout}>Annuler la connexion</button>}
              {auth && !auth.enabled && <p>Connexion ChatGPT non configurée sur ce serveur. La démonstration reste disponible ; le responsable du serveur doit activer OAuth pour connecter un compte.</p>}
            </>}
            <a href={usageUrl} target="_blank" rel="noopener noreferrer">Gérer l’utilisation ChatGPT ↗</a>
            <button type="button" className="text-button" disabled={!!busy || authBusy} onClick={() => { connect(); void refreshAuth(); }}>Actualiser la connexion</button>
          </div>
          {authError && <p className="error account-error" role="alert">{authError}</p>}
        </section></details>}
        {health && !isHosted && <dialog ref={welcomeDialog} className="plan-dialog" onCancel={dismissWelcome} aria-labelledby="plan-title">
          <h2 id="plan-title">Vous utilisez votre forfait ChatGPT</h2>
          <p>Les demandes éligibles dans Réplique utilisent votre forfait ChatGPT. Consultez et ajustez vos limites dans les réglages ChatGPT.</p>
          <a href={usageUrl} target="_blank" rel="noopener noreferrer">Gérer l’utilisation ↗</a>
          <button type="button" className="chatgpt-login" onClick={dismissWelcome}>Compris</button>
        </dialog>}
        <div className="workspace">
          <form className="compose" onSubmit={generate}>
            <div className="paper-shell"><div className="context-sheet">
            <div className="section-heading">
              <span className="step">01</span>
              <h2>On vous a écrit quoi ?</h2>
              <span className="tiny">
                Commençons par les mots reçus.
              </span>
            </div>
            <div className="input-tools">
              {health?.mode === "chatgpt" && <label className="check ocr-consent"><input type="checkbox" checked={ocrConsent} disabled={!!busy || auth?.status !== "connected" || !auth.sharing || !model} onChange={(e) => setOcrConsent(e.target.checked)} /><span>J’autorise l’envoi de cette capture à OpenAI pour retranscrire le texte. Relisez et corrigez le résultat avant de continuer.</span></label>}
              <button
                type="button"
                className="text-button"
                disabled={!!busy || (isHosted && !account) || (health?.mode === "chatgpt" ? auth?.status !== "connected" || !auth.sharing || !model || !ocrConsent : !health?.ocr_available)}
                onClick={() => file.current?.click()}
              >
                Importer une capture
              </button>
              <button
                type="button"
                className="text-button"
                disabled={!!busy}
                onClick={() => {
                  updateConversation(sample);
                  setOcrNotice("Exemple entièrement fictif.");
                }}
              >
                Essayer un exemple
              </button>
              <input
                ref={file}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                hidden
                onChange={(e) => upload(e.target.files?.[0])}
              />
            </div>
            <p className="upload-info">{health?.mode === "chatgpt" ? "PNG, JPG ou WebP · 5 Mo max. Après votre accord, la capture est envoyée à OpenAI pour transcription." : "PNG, JPG ou WebP · 5 Mo max. Extraction locale, puis suppression du fichier temporaire."}</p>
            <label className="sr-only" htmlFor="conversation">
              Votre conversation
            </label>
            <textarea
              id="conversation"
              disabled={!!busy}
              className="conversation"
              maxLength={12000}
              required
              value={conversation}
              onChange={(e) => updateConversation(e.target.value)}
              placeholder={
                "Collez votre échange ici…\n\nMoi : Ça m’a fait plaisir de te voir.\nAutre personne : Moi aussi. On remet ça ?"
              }
              aria-describedby="context-help"
            />
            <div className="input-caption">
              <span id="context-help">
                Retirez les noms et détails sensibles. Indiquez qui parle.
              </span>
              <span>
                {conversation.length.toLocaleString("fr-FR")} / 12 000
              </span>
            </div>
            {ocrNotice && (
              <p className="ocr-note" role="status">
                {ocrNotice}
              </p>
            )}
            <label className="check">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                disabled={!conversation.trim() || !!busy}
              />
              <span>
                J’ai relu le texte et vérifié qui a écrit chaque message.
              </span>
            </label>
            </div></div>
            <div className="intention-sheet">
            <div className="section-heading second">
              <span className="step">02</span>
              <h2>Et vous, vous voulez…</h2>
            </div>
            <label className="sr-only" htmlFor="intent">
              Intention
            </label>
            <select
              id="intent"
              disabled={!!busy}
              value={intent}
              onChange={(e) => {
                setIntent(e.target.value);
                setResult(null);
              }}
            >
              {intentions.map((i) => (
                <option key={i}>{i}</option>
              ))}
            </select>
            <fieldset disabled={!!busy}>
              <legend>Le ton qui vous ressemble</legend>
              <div className="tones">
                {["naturel", "chaleureux", "léger", "direct"].map((t) => (
                  <label
                    className={tone === t ? "tone active" : "tone"}
                    key={t}
                  >
                    <input
                      type="radio"
                      name="tone"
                      value={t}
                      checked={tone === t}
                      onChange={() => {
                        setTone(t);
                        setResult(null);
                      }}
                    />
                    {t}
                  </label>
                ))}
              </div>
            </fieldset>
            <details className="personalize"><summary>Affiner ma façon d’écrire <span aria-hidden="true">＋</span></summary><div className="personalize-body">
            <label className="field-label" htmlFor="locale">Le contexte linguistique</label>
            <select id="locale" disabled={!!busy} value={locale} onChange={(e) => { setLocale(e.target.value); setResult(null); }}><option value="fr_neutre">Français neutre</option><option value="afrique_ouest">Français · Afrique de l’Ouest</option><option value="burkina_faso">Français · contexte Burkina Faso</option></select>
            <label className="field-label" htmlFor="familiarity">Le degré de familiarité</label>
            <select id="familiarity" disabled={!!busy} value={familiarity} onChange={(e) => { setFamiliarity(e.target.value); setResult(null); }}><option value="neutre">Courant, sans familiarité ajoutée</option><option value="familier">Familier, si l’échange s’y prête</option></select>
            <p className="preference-help">Votre façon d’écrire passe avant les expressions régionales. Aucun accent ni argot forcé.</p>
            <label className="field-label" htmlFor="style">
              Votre façon d’écrire <span>facultatif</span>
            </label>
            <textarea
              id="style"
              disabled={!!busy}
              className="style-input"
              maxLength={500}
              value={style}
              onChange={(e) => {
                setStyle(e.target.value);
                setResult(null);
              }}
              placeholder="Ex. Des phrases courtes, pas de surnoms. Je dis souvent « ça marche »."
            />
            <label className="check small">
              <input
                type="checkbox"
                disabled={!!busy}
                checked={emoji}
                onChange={(e) => {
                  setEmoji(e.target.checked);
                  setResult(null);
                }}
              />
              <span>Un emoji, si le contexte s’y prête</span>
            </label>
            </div></details>
            </div>
            {health && !isHosted && <><MemoryPanel revision={memoryRevision} changed={memoryChanged} disabled={!!busy || authBusy} />
            <div className="memory-use"><label className="check"><input id="use-memory" type="checkbox" checked={useMemory} disabled={!!busy || authBusy} onChange={e => { setUseMemory(e.target.checked); setConsent(false); }} /><span>Utiliser ma mémoire pour cette génération seulement</span></label><p className="preference-help">Désactivé par défaut. Enregistrer un exemple et l’utiliser sont deux choix séparés.</p>
            {useMemory && <div className="memory-selection" aria-live="polite">{memoryError ? <p className="error" role="alert">{memoryError}</p> : memoryPreview ? <><p>{memoryPreview.examples.length} exemple(s) validé(s) sélectionné(s){memoryPreview.profile ? " et vos préférences enregistrées" : ""}.</p>{memoryPreview.examples.map(item => <details key={item.id}><summary>Voir l’exemple sélectionné</summary><p>{item.reply}</p>{item.conversation && <p>Extrait : {item.conversation}</p>}</details>)}{memoryPreview.profile && <p>Préférences : {memoryPreview.profile.length === "short" ? "phrases courtes" : "longueur équilibrée"}, {memoryPreview.profile.register === "familiar" ? "familier si adapté" : "registre courant"}, {memoryPreview.profile.emoji === "allowed" ? "emoji si adapté" : "sans emoji"}.</p>}<p>{memoryPreview.notice}</p></> : <p>Vérification des exemples à utiliser…</p>}</div>}</div></>}
            {health?.mode === "chatgpt" && <div className="model-field">
              <label className="field-label" htmlFor="model">Modèle · forfait ChatGPT</label>
              <select id="model" value={model} disabled={!!busy || authBusy || !models.length} onChange={(e) => { setModel(e.target.value); setResult(null); setConsent(false); setOcrConsent(false); setUseMemory(false); setMemoryPreview(null); }}>
                {!models.length && <option value="">Aucun modèle disponible</option>}
                {models.map((m) => <option key={m.slug} value={m.slug}>{m.display_name}</option>)}
              </select>
              <p>Utilisation de votre forfait ChatGPT. <a href={usageUrl} target="_blank" rel="noopener noreferrer">Gérer l’utilisation ↗</a></p>
            </div>}
            {health && health.mode !== "demo" ? (
              <label className="check consent">
                <input
                  type="checkbox"
                  disabled={!!busy}
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                <span>{health.mode === "local"
                  ? "J’accepte le traitement de ce texte et de mes préférences par le modèle hébergé sur Réplique. Le texte reste sur ce serveur."
                  : health.mode === "hosted"
                  ? "J’accepte que Réplique envoie ce texte et mes préférences à OpenAI pour générer des réponses. Les règles de traitement d’OpenAI s’appliquent."
                  : <>J’accepte d’envoyer ce texte et mes préférences{useMemory ? ", ainsi que les exemples sauvegardés et les préférences de mémoire sélectionnés ci-dessus," : ""} à {health.provider || "mon fournisseur IA configuré"}. Ses règles de conservation s’appliquent.</>}</span>
              </label>
            ) : (
              <div className="demo-note"><strong>Vous explorez la démo.</strong> Elle utilise des exemples fictifs et des réponses préécrites. Pour une réponse à votre échange, connectez ChatGPT ou configurez un fournisseur IA. Les préférences libres ne sont pas interprétées.</div>
            )}
            <button
              className="primary"
              disabled={
                !health ||
                !!busy ||
                authBusy ||
                (isHosted && (!account || (!account.subscription_active && account.trial_remaining === 0))) ||
                (health.mode === "chatgpt" && (!auth?.sharing || auth.status !== "connected" || !model)) ||
                (useMemory && !memoryPreview) ||
                !confirmed ||
                !conversation.trim() ||
                (health.mode !== "demo" && !consent)
              }
            >
              {busy === "ocr"
                ? "Lecture de la capture…"
                : busy === "generate"
                  ? "Préparation des réponses…"
                  : "Trouver mes mots"}{" "}
              <span aria-hidden="true">↗</span>
            </button>
            {error && (
              <p className="error" role="alert">
                {error}
                {health?.mode === "chatgpt" && <> <a href={usageUrl} target="_blank" rel="noopener noreferrer">Vérifier mes limites ChatGPT ↗</a></>}
              </p>
            )}
            {health?.mode === "demo" && (
              <div className="demo-examples">
                <span>Autres exemples fictifs :</span>
                <button type="button" className="text-button" disabled={!!busy} onClick={() => { updateConversation(brief); setOcrNotice("Exemple fictif : une réponse courte ne dit pas tout."); }}>Réponses courtes</button>
                <button type="button" className="text-button" disabled={!!busy} onClick={() => { updateConversation(unanswered); setOcrNotice("Exemple fictif : plusieurs messages sans réponse."); }}>Sans réponse</button>
                <button
                  type="button"
                  className="text-button"
                  disabled={!!busy}
                  onClick={() => {
                    updateConversation(refusal);
                    setOcrNotice("Exemple fictif : respecter un refus.");
                  }}
                >
                  Un refus
                </button>
              </div>
            )}
            <p className="privacy">
              Aucun envoi à votre place. Échanges temporaires par défaut ;
              seuls vos enregistrements confirmés alimentent la mémoire locale.
            </p>
          </form>
          <section
            className="answers"
            ref={results}
            tabIndex={-1}
            aria-label="Vos propositions de réponse"
            aria-busy={busy === "generate"}
          >
            <div className="section-heading">
              <span className="step">03</span>
              <h2>{abstention && result ? "Une piste pour la suite." : result?.replies.length === 1 ? "Une piste, à votre façon." : result?.replies.length === 2 ? "Vos mots, en deux versions." : "Vos mots, en trois versions."}</h2>
              {result && result.replies.some((r) => r.text.trim()) && (
                <button className="text-button export" onClick={exportReplies}>
                  Exporter ↗
                </button>
              )}
            </div>
            {result ? (
              <>
                <div
                  className="insight"
                >
                  <span className="eyebrow">
                    LE POINT DE REPÈRE
                  </span>
                  <p>{abstention && result.boundary ? "Cette personne demande de ne plus être contactée. Le mieux est de ne pas répondre." : result.insight}</p>
                </div>
                <p className="result-notice">{result.notice}</p>
                {result.memory_used && <p className="result-notice">{result.memory_used.notice || `${result.memory_used.item_ids.length} exemple(s) de mémoire utilisé(s).`}</p>}
                <div className="reply-list">
                  {!abstention && result.replies.map((r, index) => (
                    <article className="reply" key={r.id}>
                      <div className="reply-heading">
                        <span className="reply-number">0{index + 1}</span>
                        <h3>{r.title}</h3>
                        <button
                          className="copy"
                          disabled={!r.text.trim()}
                          onClick={() => copy(r.text)}
                        >
                          Copier <span aria-hidden="true">↗</span>
                        </button>
                      </div>
                      <label className="sr-only" htmlFor={"reply-" + r.id}>
                        Modifier la réponse {index + 1}
                      </label>
                      <textarea
                        id={"reply-" + r.id}
                        placeholder="Ne pas envoyer de message"
                        value={r.text}
                        maxLength={1500}
                        onChange={(e) =>
                          setResult({
                            ...result,
                            replies: result.replies.map((x) =>
                              x.id === r.id
                                ? { ...x, text: e.target.value }
                                : x,
                            ),
                          })
                        }
                      />
                      {health && !isHosted && <SaveMemory reply={r.text} conversation={conversation} intent={intent} tone={tone} locale={locale} changed={memoryChanged} />}
                      <p className="why">
                        <span>Ce que ça change</span>
                        {r.why}
                      </p>
                    </article>
                  ))}
                </div>
                {!abstention && <p className="final-note">
                  Modifiez un mot, gardez une idée, ou ne répondez pas.
                  <br />
                  La décision vous appartient.
                </p>}
              </>
            ) : (
              <div className={"empty " + (busy === "generate" ? "is-loading" : "")}>
                <div className="sample-conversation" aria-hidden="true"><div className="sample-label">LE PETIT MESSAGE. LA GRANDE HÉSITATION.</div><div className="bubble received">On remet ça ?<span>18:42</span></div><div className="bubble draft"><span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" /></div><span className="handwritten">Qu’est-ce que je lui dis ?</span><span className="sketch-arrow">↗</span></div>
                <div className="empty-copy"><span className="eyebrow">UN PEU DE RECUL, ÇA AIDE.</span><h3>{busy === "generate" ? "On cherche les mots…" : "Pas une réponse parfaite.\nUne réponse qui vous ressemble."}</h3><p>{busy === "generate" ? "Vos propositions arrivent ici. Vous pourrez modifier chacune d’elles." : "Simple, chaleureuse ou plus directe : choisissez une piste, changez un mot, faites-la vôtre."}</p></div>
                <div className="principles"><span><i aria-hidden="true">↳</i> Votre contexte</span><span><i aria-hidden="true">≈</i> Votre ton</span><span><i aria-hidden="true">✳</i> Votre décision</span></div>
              </div>
            )}
          </section>
        </div>
        <div className="status" role="status" aria-live="polite">
          {notice}
        </div>
        <footer>
          <span>
            réplique{" "}
            <span className="footer-tag">Vos mots, avec un peu de recul.</span>
          </span>
          <span>Une aide pour écrire. Jamais un envoi automatique.</span>
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
