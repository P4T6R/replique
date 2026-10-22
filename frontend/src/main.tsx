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
class HttpRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}
type Reply = { id: string; title: string; text: string; why: string };
type Result = {
  mode: string;
  notice: string;
  insight: string;
  boundary: boolean;
  replies: Reply[];
  memory_used?: { item_ids: string[]; profile_used: boolean; revision: number; notice: string };
};
type ExtractedPhoto = { text: string; warning?: string };
type ResultContext = { conversation: string; intent: string; tone: string; locale: string };
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
  let r: Response;
  try {
    r = await fetch(url, options);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new HttpRequestError("Connexion au service impossible. Vérifiez votre réseau, puis réessayez.", 0);
  }
  let data;
  try {
    data = await r.json();
  } catch {
    throw new HttpRequestError(
      r.status === 413 ? "L’envoi dépasse la taille autorisée. Choisissez une capture plus petite."
        : r.status === 429 ? "Trop de demandes. Réessayez dans un instant."
          : "Le serveur ne répond pas correctement. Réessayez dans un instant.",
      r.status,
    );
  }
  if (!r.ok)
    throw new HttpRequestError(
      typeof data.detail === "string"
        ? data.detail
        : typeof data.detail?.message === "string"
          ? data.detail.message
          : "Les informations envoyées ne sont pas valides. Vérifiez les champs.",
      r.status,
    );
  return data;
}
function App() {
  const [account, setAccount] = useState<AccountStatus | null>(null);
  const [accountError, setAccountError] = useState("");
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
  const [ocrError, setOcrError] = useState("");
  const [selectedPhoto, setSelectedPhoto] = useState<File | null>(null);
  const [selectedPhotoUrl, setSelectedPhotoUrl] = useState("");
  const [retryablePhoto, setRetryablePhoto] = useState(false);
  const [extractedPhoto, setExtractedPhoto] = useState<ExtractedPhoto | null>(null);
  const [resultStale, setResultStale] = useState(false);
  const [resultContext, setResultContext] = useState<ResultContext | null>(null);
  const [resetPrompt, setResetPrompt] = useState(false);
  const [copyStatus, setCopyStatus] = useState<{ id: string; message: string } | null>(null);
  const [useMemory, setUseMemory] = useState(false), [memoryPreview, setMemoryPreview] = useState<MemoryPreview | null>(null), [memoryError, setMemoryError] = useState(""), [memoryRevision, setMemoryRevision] = useState(0);
  const memoryChanged = () => { setMemoryRevision(v => v + 1); setConsent(false); setUseMemory(false); setMemoryPreview(null); setResultStale(true); };
  useEffect(() => {
    let current = true; setConsent(false); setMemoryPreview(null); setMemoryError("");
    if (useMemory) memoryRequest<MemoryPreview>("/api/memory/preview?" + new URLSearchParams({ intent, tone, locale })).then(data => { if (current) setMemoryPreview(data); }).catch(e => { if (current) setMemoryError((e as Error).message); });
    return () => { current = false; };
  }, [useMemory, intent, tone, locale, memoryRevision]);
  const file = useRef<HTMLInputElement>(null),
    conversationInput = useRef<HTMLTextAreaElement>(null),
    pendingPhoto = useRef<File | null>(null),
    generation = useRef(0),
    abort = useRef<AbortController | null>(null),
    results = useRef<HTMLElement>(null);
  const isHosted = health?.mode === "local" || health?.mode === "hosted";
  const directPhoto = health?.mode === "hosted";
  const usesCloudOcr = health?.mode === "chatgpt";
  useEffect(() => {
    if (!selectedPhoto || !URL.createObjectURL) { setSelectedPhotoUrl(""); return; }
    const url = URL.createObjectURL(selectedPhoto);
    setSelectedPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selectedPhoto]);
  const connect = () => {
    setConnection("");
    request<Health>("/api/health")
      .then(data => { setHealth(data); if (data.mode === "local" || data.mode === "hosted") void refreshAccount(); else void refreshAuth(); })
      .catch(error => setConnection((error as Error).message));
  };
  async function refreshAccount() {
    try {
      setAccount(await request<AccountStatus>("/api/account/status"));
      setAccountError("");
    } catch (error) {
      if (error instanceof HttpRequestError && error.status === 401) {
        setAccount(null);
        setResult(null);
        setResultContext(null);
        setConversation("");
        setAccountError("");
      } else {
        setAccountError("Impossible d’actualiser votre solde. Votre conversation est conservée ; réessayez.");
      }
    }
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
      setResultContext(null);
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
    pendingPhoto.current = null;
    setRetryablePhoto(false);
    setExtractedPhoto(null);
    setConversation(value);
    setConfirmed(false);
    setConsent(false);
    setResult(null);
    setResultContext(null);
    setResultStale(false);
    setCopyStatus(null);
    setError("");
    setOcrError("");
    setOcrNotice("");
  }
  function chooseHostedPhoto(f: File | undefined) {
    if (!f) return;
    const fileType = (f.type && f.type !== "application/octet-stream") ? f.type :
      (/\.heic$/i.test(f.name) ? "image/heic" : /\.heif$/i.test(f.name) ? "image/heif" : "");
    if (!["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"].includes(fileType) || f.size > 10 * 1024 * 1024) {
      setOcrError("Choisissez une image PNG, JPG, WebP ou HEIC de 10 Mo maximum.");
      return;
    }
    setSelectedPhoto(f.type === fileType ? f : new File([f], f.name, { type: fileType }));
    setOcrError("");
    setConsent(false);
    setResult(null);
    setResultContext(null);
    setResultStale(false);
    if (file.current) file.current.value = "";
  }
  function attributeLine(speaker: "Moi" | "Autre personne") {
    const input = conversationInput.current;
    if (!input || !conversation.trim()) return;
    const lineStart = conversation.lastIndexOf("\n", Math.max(0, input.selectionStart - 1)) + 1;
    const lineEnd = conversation.indexOf("\n", lineStart);
    const end = lineEnd < 0 ? conversation.length : lineEnd;
    const line = conversation.slice(lineStart, end);
    if (!line.trim()) return;
    const leading = line.match(/^\s*/)?.[0] || "";
    const message = line.slice(leading.length).replace(/^(?:Moi|Autre personne)\s*:\s*/i, "");
    const replacement = `${leading}${speaker} : ${message}`;
    if (conversation.length - line.length + replacement.length > 12000) return;
    updateConversation(conversation.slice(0, lineStart) + replacement + conversation.slice(end));
    setTimeout(() => {
      input.focus();
      const cursor = lineStart + replacement.length;
      input.setSelectionRange(cursor, cursor);
    }, 0);
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
    setResultContext(null);
    setResultStale(false);
    setResetPrompt(false);
    setCopyStatus(null);
    setError("");
    setOcrNotice("");
    setOcrError("");
    setSelectedPhoto(null);
    setRetryablePhoto(false);
    setExtractedPhoto(null);
    pendingPhoto.current = null;
    setNotice(
      isHosted
        ? "Conversation effacée de cet appareil. Les fichiers déjà exportés restent sur votre appareil."
        : "Session effacée de cet atelier. Votre mémoire de style reste conservée ; utilisez « Effacer toute la mémoire » pour la supprimer. Les fichiers exportés et le presse-papiers restent sur votre appareil. Les données déjà transmises à un fournisseur restent soumises à ses règles de conservation.",
    );
    if (file.current) file.current.value = "";
  }
  async function generate(e: React.FormEvent) {
    e.preventDefault();
    if (!health || !canGenerate) return;
    const currentContext = { conversation, intent, tone, locale };
    const id = ++generation.current;
    abort.current?.abort();
    abort.current = new AbortController();
    setBusy("generate");
    setError("");
    setNotice("");
    try {
      const payload = {
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
        context_confirmed: directPhoto ? consent : confirmed,
        ...(health.mode === "chatgpt" ? { model } : {}),
      };
      const form = new FormData();
      if (directPhoto && selectedPhoto) {
        form.append("file", selectedPhoto);
        form.append("options", JSON.stringify(payload));
      }
      const data = await request<Result>(directPhoto && selectedPhoto ? "/api/generate-image" : "/api/generate", {
        method: "POST",
        headers: directPhoto && selectedPhoto ? authHeaders : { "Content-Type": "application/json", ...authHeaders },
        body: directPhoto && selectedPhoto ? form : JSON.stringify(payload),
        signal: abort.current.signal,
      });
      if (id === generation.current) {
        setAbstention(data.replies.every((r) => !r.text.trim()));
        setResult(data);
        setResultContext(currentContext);
        setResultStale(false);
        setCopyStatus(null);
        setUseMemory(false);
        setConsent(false);
        setTimeout(() => results.current?.focus(), 0);
      }
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
      setOcrError("Connectez ChatGPT et choisissez un modèle avant d’utiliser l’OCR OpenAI.");
      return;
    }
    if (usesCloudOcr && !ocrConsent) {
      setOcrError("Autorisez l’envoi de cette capture à OpenAI avant de lancer la lecture.");
      return;
    }
    const fileType = (f.type && f.type !== "application/octet-stream") ? f.type :
      (/\.heic$/i.test(f.name) ? "image/heic" : /\.heif$/i.test(f.name) ? "image/heif" : "");
    if (!["image/png", "image/jpeg", "image/webp", "image/heic", "image/heif"].includes(fileType) || f.size > 10 * 1024 * 1024) {
      pendingPhoto.current = null;
      setRetryablePhoto(false);
      setOcrError("Choisissez une image PNG, JPG, WebP ou HEIC de 10 Mo maximum. Recadrez une photo trop grande.");
      return;
    }
    pendingPhoto.current = f;
    setRetryablePhoto(false);
    setExtractedPhoto(null);
    const id = ++generation.current;
    abort.current?.abort();
    abort.current = new AbortController();
    setBusy("ocr");
    setOcrError("");
    setOcrNotice("");
    const form = new FormData();
    form.append("file", fileType === f.type ? f : new File([f], f.name, { type: fileType }));
    form.append("consent", String(usesCloudOcr && ocrConsent));
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
        if (conversation.trim()) {
          setExtractedPhoto(data);
          setOcrNotice("Texte extrait. Choisissez si vous voulez l’ajouter ou remplacer votre brouillon ; rien n’a encore été modifié.");
          setTimeout(() => document.querySelector<HTMLElement>("#photo-preview")?.focus(), 0);
        } else {
          updateConversation(data.text);
          setOcrNotice(data.warning || "Texte extrait. Relisez-le et vérifiez qui a écrit chaque message avant de continuer.");
          setTimeout(() => document.querySelector<HTMLTextAreaElement>("#conversation")?.focus(), 0);
        }
      }
    } catch (e) {
      if (
        id === generation.current &&
        !(e instanceof DOMException && e.name === "AbortError")
      ) {
        setOcrError((e as Error).message);
        setRetryablePhoto(true);
      }
    } finally {
      if (id === generation.current) {
        setBusy("");
        setOcrConsent(false);
        if (file.current) file.current.value = "";
      }
    }
  }
  function applyPhoto(choice: "append" | "replace") {
    if (!extractedPhoto) return;
    const next = choice === "append" ? conversation.trimEnd() + "\n\n" + extractedPhoto.text : extractedPhoto.text;
    updateConversation(next);
    setOcrNotice(extractedPhoto.warning || "Texte ajouté. Relisez-le et vérifiez qui a écrit chaque message avant de continuer.");
    setTimeout(() => document.querySelector<HTMLTextAreaElement>("#conversation")?.focus(), 0);
  }
  async function copy(id: string, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopyStatus({ id, message: "Copié" });
      setNotice(
        "Réponse copiée. Relisez-la dans votre messagerie avant de l’envoyer.",
      );
    } catch {
      setCopyStatus({ id, message: "Copie impossible. Sélectionnez le texte ci-dessous." });
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
  const generationBlock = (() => {
    if (!health) return "Vérification du service en cours.";
    if (authBusy) return "Connexion en cours.";
    if (busy === "ocr") return "Lecture de la photo en cours.";
    if (busy === "generate") return "Génération en cours.";
    if (isHosted && !account) return "Connectez-vous ou créez un compte pour continuer.";
    if (isHosted && account && !account.subscription_active && account.trial_remaining === 0) return "Vos crédits d’essai sont épuisés.";
    if (health.mode === "chatgpt" && (!auth?.sharing || auth.status !== "connected" || !model)) return "Connectez ChatGPT et choisissez un modèle.";
    if (directPhoto) {
      if (!selectedPhoto && conversation.trim().length < 5) return "Ajoutez une capture ou collez le dernier message reçu.";
      if (useMemory && memoryError) return "La mémoire est indisponible. Désactivez son utilisation ou réessayez.";
      if (useMemory && !memoryPreview) return "Vérification de votre mémoire en cours.";
      if (!consent) return "Confirmez l’analyse de votre capture ou de votre texte pour continuer.";
      return null;
    }
    if (conversation.trim().length < 5) return "Ajoutez le message auquel vous voulez répondre.";
    if (health.mode === "demo" && ![sample, brief, unanswered, refusal].includes(conversation)) return "La démo accepte uniquement les exemples fictifs proposés.";
    if (!/^\s*(?:Moi|Autre personne)\s*:/i.test(conversation)) return "Commencez par un message attribué : retirez les en-têtes, puis cliquez dans la première phrase et choisissez son auteur ci-dessus.";
    if (!/^\s*Autre personne\s*:/im.test(conversation)) return "Attribuez au moins un message reçu avec le bouton « Autre personne ».";
    if (!confirmed) return "Relisez l’échange et cochez la confirmation sous le texte.";
    if (useMemory && memoryError) return "La mémoire est indisponible. Désactivez son utilisation ou réessayez.";
    if (useMemory && !memoryPreview) return "Vérification de votre mémoire en cours.";
    if (health.mode !== "demo" && !consent) return "Confirmez le traitement du texte avant de continuer.";
    return null;
  })();
  const canGenerate = generationBlock === null;
  const generationHint = generationBlock || "Prêt à générer trois propositions. Une génération peut utiliser un crédit d’essai.";
  const photoHint = directPhoto ? (!account ? "Connectez-vous pour ajouter une capture." : account && !account.subscription_active && account.trial_remaining === 0 ? "Vos crédits d’essai sont épuisés." : "")
    : health && !health.ocr_available ? "La lecture des photos est indisponible sur ce serveur. Vous pouvez coller le texte à la place."
    : isHosted && !account ? "Connectez-vous pour importer une photo."
      : isHosted && account && !account.subscription_active && account.trial_remaining === 0 ? "Vos crédits d’essai sont épuisés ; l’import de photos est suspendu."
        : health?.mode === "chatgpt" && (auth?.status !== "connected" || !auth.sharing || !model) ? "Connectez ChatGPT et choisissez un modèle pour importer une photo."
        : usesCloudOcr && !ocrConsent ? "Cochez l’autorisation ci-dessus pour activer l’import de la photo."
        : "";
  return (
    <div className="app">
      <a className="skip-link" href="#conversation">Aller à la conversation</a>
      <header className="topbar">
        <a className="brand" href="#atelier" aria-label="Réplique, accueil"><span className="brand-mark" aria-hidden="true">r</span>réplique<span className="brand-period">.</span></a>
        <span className="brand-caption">L’ATELIER DES CONVERSATIONS</span>
        <button className="quiet" onClick={() => conversation.trim() || selectedPhoto || result || style.trim() ? setResetPrompt(true) : reset()} disabled={authBusy} aria-label="Effacer la session et commencer une nouvelle conversation">Nouvelle conversation <span aria-hidden="true">＋</span></button>
      </header>
      {resetPrompt && <div className="reset-confirm" role="group" aria-label="Confirmer une nouvelle conversation"><p>Effacer le brouillon et les réponses de cette session ?</p><div><button type="button" className="text-button" onClick={reset}>Effacer et recommencer</button><button type="button" className="text-button" onClick={() => setResetPrompt(false)}>Garder ma conversation</button></div></div>}
      <main id="atelier">
        <section className="intro">
          <div><p className="eyebrow">UN MESSAGE PEUT TOUT CHANGER. RESTEZ VOUS-MÊME.</p><h1>Ça se dit.<br /><em>À votre façon.</em><span className="heading-star" aria-hidden="true">✳</span></h1></div>
          <div className="intro-aside"><p>Vous avez le fond.<br />Trouvons les mots.</p><span>Un peu de recul, trois pistes.<br />Et toujours le dernier mot pour vous.</span></div>
        </section>
        <div className="atelier-bar"><span className="eyebrow">VOTRE ESPACE POUR RÉPONDRE</span>{!directPhoto && <span className={"mode " + (health && health.mode !== "demo" ? "live" : "")}><span className="dot" aria-hidden="true" />{health?.mode === "local" ? "IA · modèle sur Réplique" : health?.mode === "chatgpt" ? "IA · forfait ChatGPT" : health?.mode === "live" ? "IA · fournisseur configuré" : health ? "Démo · exemples préécrits" : "Vérification du service…"}</span>}</div>
        {connection && (
          <div className="error" role="alert">
            {connection} <button onClick={connect}>Réessayer</button>
          </div>
        )}
        {isHosted ? <><AccountPanel account={account} disabled={!!busy} onChange={next => { reset(); setAccount(next); setAccountError(""); }} />{accountError && <p className="error" role="alert">{accountError} <button type="button" onClick={() => void refreshAccount()}>Réessayer</button></p>}</> : health && <details className="account-disclosure" open={!!authError || auth?.status === "reauth_required"}><summary><span className="account-summary-icon" aria-hidden="true">◎</span><span>{auth?.status === "connected" ? "Votre compte ChatGPT est connecté" : "Envie d’utiliser vos propres conversations ?"}<small>{auth?.status === "connected" ? "Compte, modèles et utilisation" : "Connexion ChatGPT et état du service"}</small></span><span className="disclosure-plus" aria-hidden="true">＋</span></summary>
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
              {usesCloudOcr && <label className="check ocr-consent"><input type="checkbox" checked={ocrConsent} disabled={!!busy || (isHosted ? !account : auth?.status !== "connected" || !auth.sharing || !model)} onChange={(e) => setOcrConsent(e.target.checked)} /><span>J’autorise l’envoi de cette capture à OpenAI pour en extraire le texte. Je relirai le résultat avant de demander des réponses.</span></label>}
              <button
                type="button"
                className="text-button"
                disabled={!!busy || (isHosted && (!account || (!account.subscription_active && account.trial_remaining === 0))) || (health?.mode === "chatgpt" && (auth?.status !== "connected" || !auth.sharing || !model)) || (usesCloudOcr && !ocrConsent) || (!directPhoto && !health?.ocr_available)}
                onClick={() => file.current?.click()}
              >
                Importer une capture
              </button>
              <button
                type="button"
                className="text-button"
                disabled={!!busy}
                onClick={() => {
                  setSelectedPhoto(null);
                  updateConversation(sample);
                  setOcrNotice("Exemple entièrement fictif.");
                }}
              >
                Essayer un exemple
              </button>
              <input
                ref={file}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/heic,image/heif,.heic,.heif"
                hidden
                onChange={(e) => directPhoto ? chooseHostedPhoto(e.target.files?.[0]) : void upload(e.target.files?.[0])}
              />
            </div>
            <p className="upload-info">{directPhoto ? "Capture PNG, JPG, WebP ou HEIC · 10 Mo max. Elle sera analysée quand vous cliquerez sur « Trouver mes mots »." : usesCloudOcr ? "Capture ou photo PNG, JPG, WebP ou HEIC · 10 Mo max. Après votre accord, l’image est envoyée à OpenAI ; relisez le texte extrait avant de demander des réponses." : "Capture ou photo PNG, JPG, WebP ou HEIC · 10 Mo max. Extraction locale, puis suppression du fichier temporaire."}</p>
            {photoHint && <p className="upload-hint" role="status">{photoHint}</p>}
            {busy === "ocr" && <p className="ocr-note" role="status">Lecture de la capture en cours…</p>}
            {ocrError && <div className="error" role="alert">{ocrError} {!directPhoto && "Votre texte saisi reste disponible."}
              {retryablePhoto && <><br />{usesCloudOcr && !ocrConsent && <span>Pour réessayer cette même photo, autorisez à nouveau son envoi ci-dessus. </span>}
                <button type="button" disabled={!!busy || (usesCloudOcr && !ocrConsent)} onClick={() => void upload(pendingPhoto.current || undefined)}>Réessayer la lecture</button>
              </>}
            </div>}
            {ocrNotice && <p className="ocr-note" role="status">{ocrNotice}</p>}
            {directPhoto && selectedPhoto && <div className="selected-photo" role="status">
              {selectedPhotoUrl && <img src={selectedPhotoUrl} alt="Capture sélectionnée pour l’analyse" />}
              <div><strong>Capture ajoutée</strong><span>{selectedPhoto.name}</span><button type="button" className="text-button" disabled={!!busy} onClick={() => { setSelectedPhoto(null); setConsent(false); setResult(null); }}>Retirer la capture</button></div>
            </div>}
            {extractedPhoto && <div id="photo-preview" className="photo-preview" tabIndex={-1} aria-label="Texte extrait de la photo">
              <strong>Texte lu sur la photo</strong>
              <p>Votre brouillon actuel est conservé. Vérifiez le texte ci-dessous avant de choisir.</p>
              <pre>{extractedPhoto.text}</pre>
              <div className="photo-actions">
                <button type="button" disabled={!!busy || conversation.trimEnd().length + 2 + extractedPhoto.text.length > 12000} onClick={() => applyPhoto("append")}>Ajouter au brouillon</button>
                <button type="button" disabled={!!busy} onClick={() => applyPhoto("replace")}>Remplacer le brouillon</button>
                <button type="button" disabled={!!busy} onClick={() => { setExtractedPhoto(null); setOcrNotice("Texte extrait ignoré. Votre brouillon est conservé."); }}>Ignorer</button>
              </div>
              {conversation.trimEnd().length + 2 + extractedPhoto.text.length > 12000 && <p>Le texte réuni dépasserait 12 000 caractères. Raccourcissez le brouillon ou remplacez-le.</p>}
            </div>}
            <label className="sr-only" htmlFor="conversation">{directPhoto ? "Dernier message reçu ou précision facultative" : "Votre conversation"}</label>
            <textarea
              id="conversation"
              ref={conversationInput}
              disabled={!!busy}
              className="conversation"
              maxLength={12000}
              required={!directPhoto || !selectedPhoto}
              value={conversation}
              onChange={(e) => updateConversation(e.target.value)}
              placeholder={directPhoto ? "Sinon, collez le dernier message reçu ici. Avec une capture, vous pouvez ajouter une précision facultative." : "Collez votre échange ici…\n\nMoi : Ça m’a fait plaisir de te voir.\nAutre personne : Moi aussi. On remet ça ?"}
              aria-describedby="context-help"
            />
            {!directPhoto && !!conversation.trim() && <div className="speaker-tools" role="group" aria-label="Attribuer le message sélectionné">
              <span>Qui a écrit la ligne où se trouve le curseur ?</span>
              <div>
                <button type="button" disabled={!!busy} onClick={() => attributeLine("Moi")}>Moi</button>
                <button type="button" disabled={!!busy} onClick={() => attributeLine("Autre personne")}>Autre personne</button>
              </div>
              <small>Cliquez dans chaque message au changement d’auteur. Retirez les numéros et les en-têtes ; les lignes suivantes gardent le même auteur jusqu’au prochain repère.</small>
            </div>}
            <div className="input-caption">
              <span id="context-help">
                {directPhoto ? "Vous pouvez retirer les détails sensibles avant de coller un texte." : "Retirez les noms et détails sensibles. Indiquez qui parle."}
              </span>
              <span>
                {conversation.length.toLocaleString("fr-FR")} / 12 000
              </span>
            </div>
            {!directPhoto && <label className="check">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                disabled={!conversation.trim() || !!busy}
              />
              <span>
                J’ai relu le texte et vérifié qui a écrit chaque message.
              </span>
            </label>}
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
                setResultStale(true);
                setConsent(false);
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
                        setResultStale(true);
                        setConsent(false);
                      }}
                    />
                    {t}
                  </label>
                ))}
              </div>
            </fieldset>
            <details className="personalize"><summary>Affiner ma façon d’écrire <span aria-hidden="true">＋</span></summary><div className="personalize-body">
            <label className="field-label" htmlFor="locale">Le contexte linguistique</label>
            <select id="locale" disabled={!!busy} value={locale} onChange={(e) => { setLocale(e.target.value); setResultStale(true); setConsent(false); }}><option value="fr_neutre">Français neutre</option><option value="afrique_ouest">Français · Afrique de l’Ouest</option><option value="burkina_faso">Français · contexte Burkina Faso</option></select>
            <label className="field-label" htmlFor="familiarity">Le degré de familiarité</label>
            <select id="familiarity" disabled={!!busy} value={familiarity} onChange={(e) => { setFamiliarity(e.target.value); setResultStale(true); setConsent(false); }}><option value="neutre">Courant, sans familiarité ajoutée</option><option value="familier">Familier, si l’échange s’y prête</option></select>
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
                setResultStale(true);
                setConsent(false);
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
                  setResultStale(true);
                  setConsent(false);
                }}
              />
              <span>Un emoji, si le contexte s’y prête</span>
            </label>
            </div></details>
            </div>
            {health && (!isHosted || account) && <><MemoryPanel key={isHosted ? account?.email : "local"} hosted={isHosted} revision={memoryRevision} changed={memoryChanged} disabled={!!busy || authBusy} />
            <details className="advanced-memory" open={!directPhoto}>{directPhoto && <summary>Utiliser ma mémoire de style (facultatif)</summary>}
            <div className="memory-use"><label className="check"><input id="use-memory" type="checkbox" checked={useMemory} disabled={!!busy || authBusy} onChange={e => { setUseMemory(e.target.checked); setConsent(false); setResultStale(true); }} /><span>Utiliser ma mémoire pour cette génération seulement</span></label><p className="preference-help">Désactivé par défaut. Enregistrer un exemple et l’utiliser sont deux choix séparés.</p>
            {useMemory && <div className="memory-selection" aria-live="polite">{memoryError ? <p className="error" role="alert">{memoryError}</p> : memoryPreview ? <><p>{memoryPreview.examples.length} exemple(s) validé(s) sélectionné(s){memoryPreview.profile ? " et vos préférences enregistrées" : ""}.</p>{memoryPreview.examples.map(item => <details key={item.id}><summary>Voir l’exemple sélectionné</summary><p>{item.reply}</p>{item.conversation && <p>Extrait : {item.conversation}</p>}</details>)}{memoryPreview.profile && <p>Préférences : {memoryPreview.profile.length === "short" ? "phrases courtes" : "longueur équilibrée"}, {memoryPreview.profile.register === "familiar" ? "familier si adapté" : "registre courant"}, {memoryPreview.profile.emoji === "allowed" ? "emoji si adapté" : "sans emoji"}.</p>}<p>{memoryPreview.notice}</p></> : <p>Vérification des exemples à utiliser…</p>}</div>}</div></details></>}
            {health?.mode === "chatgpt" && <div className="model-field">
              <label className="field-label" htmlFor="model">Modèle · forfait ChatGPT</label>
              <select id="model" value={model} disabled={!!busy || authBusy || !models.length} onChange={(e) => { setModel(e.target.value); setResultStale(true); setConsent(false); setOcrConsent(false); setUseMemory(false); setMemoryPreview(null); }}>
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
                <span>{directPhoto
                  ? <>J’ai vérifié la capture ou le texte choisi et j’autorise son envoi avec mes préférences pour obtenir des réponses. <a href="/confidentialite.html" target="_blank" rel="noopener noreferrer">Comment mes données sont traitées</a>.</>
                  : health.mode === "local"
                  ? "J’accepte le traitement de ce texte et de mes préférences par le modèle hébergé sur Réplique. Le texte reste sur ce serveur."
                  : <>J’accepte d’envoyer ce texte et mes préférences{useMemory ? ", ainsi que les exemples sauvegardés et les préférences de mémoire sélectionnés ci-dessus," : ""} à {health.provider || "mon fournisseur IA configuré"}. Ses règles de conservation s’appliquent.</>}</span>
              </label>
            ) : (
              <div className="demo-note"><strong>Vous explorez la démo.</strong> Elle utilise des exemples fictifs et des réponses préécrites. Pour une réponse à votre échange, connectez ChatGPT ou configurez un fournisseur IA. Les préférences libres ne sont pas interprétées.</div>
            )}
            <button
              className="primary"
              disabled={!canGenerate}
            >
              {busy === "ocr"
                ? "Lecture de la capture…"
                : busy === "generate"
                  ? "Préparation des réponses…"
                  : "Trouver mes mots"}{" "}
              <span aria-hidden="true">↗</span>
            </button>
            <p className="generation-hint" role="status">{generationHint}</p>
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
              seuls vos enregistrements confirmés alimentent votre mémoire {isHosted ? "séparée par compte sur Réplique" : "locale"}.
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
                {resultStale && <p className="outdated-note" role="status">Ces réponses ont été créées avec vos réglages précédents. Vous pouvez encore les copier ou les modifier ; relancez la génération pour appliquer les nouveaux réglages.</p>}
                {busy === "generate" && <p className="outdated-note" role="status">Nouvelles propositions en cours. Les réponses précédentes restent disponibles.</p>}
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
                          onClick={() => copy(r.id, r.text)}
                        >
                          {copyStatus?.id === r.id && copyStatus.message === "Copié" ? "Copié" : "Copier"} <span aria-hidden="true">↗</span>
                        </button>
                      </div>
                      <label className="sr-only" htmlFor={"reply-" + r.id}>
                        Modifier la réponse {index + 1}
                      </label>
                      <textarea
                        id={"reply-" + r.id}
                        disabled={busy === "generate"}
                        placeholder="Ne pas envoyer de message"
                        value={r.text}
                        maxLength={1500}
                        onChange={(e) => {
                          setCopyStatus(null);
                          setResult({
                            ...result,
                            replies: result.replies.map((x) =>
                              x.id === r.id
                                ? { ...x, text: e.target.value }
                                : x,
                            ),
                          });
                        }}
                      />
                      {copyStatus?.id === r.id && <p className="copy-feedback" role="status">{copyStatus.message}</p>}
                      {health && (!isHosted || account) && <SaveMemory hosted={isHosted} reply={r.text} conversation={resultContext?.conversation || conversation} intent={resultContext?.intent || intent} tone={resultContext?.tone || tone} locale={resultContext?.locale || locale} changed={memoryChanged} />}
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
          <span>Une aide pour écrire. Jamais un envoi automatique.{directPhoto && <> <a href="/confidentialite.html">Confidentialité</a></>}</span>
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
