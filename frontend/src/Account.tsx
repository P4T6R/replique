import { useState } from "react";

export type AccountStatus = {
  email: string;
  trial_remaining: number;
  trial_total: number;
  subscription_active: boolean;
  subscription_available: boolean;
};

type Props = {
  account: AccountStatus | null;
  onChange: (account: AccountStatus | null) => void;
  provider: "local" | "openai";
  disabled?: boolean;
};

const headers = { "Content-Type": "application/json", "X-Replique-Request": "1" };

async function accountRequest(path: string, body?: object): Promise<AccountStatus | null> {
  let response: Response;
  try {
    response = await fetch("/api/account/" + path, {
      method: "POST",
      headers,
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw new Error("Connexion au service impossible. Vérifiez votre réseau, puis réessayez.");
  }
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Le serveur ne répond pas correctement. Réessayez dans un instant."); }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Réessayez dans un instant.");
  return path === "logout" ? null : data as AccountStatus;
}

export function AccountPanel({ account, onChange, provider, disabled = false }: Props) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invitation, setInvitation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (disabled || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await accountRequest(registering ? "register" : "login", { email, password, ...(registering ? { invitation } : {}) });
      onChange(result);
      setPassword("");
      setInvitation("");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    if (disabled || busy) return;
    setBusy(true);
    setError("");
    try {
      await accountRequest("logout");
      onChange(null);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="trial-account" aria-labelledby="trial-account-title">
    <div>
      <span className="eyebrow">VOTRE COMPTE RÉPLIQUE</span>
      <h2 id="trial-account-title">{account ? "Vos mots, vos crédits." : registering ? "Créer votre compte." : "Retrouver votre compte."}</h2>
      <p>{account ? <>Connecté avec {account.email}. Il vous reste <strong>{account.trial_remaining} crédit{account.trial_remaining > 1 ? "s" : ""}</strong> sur {account.trial_total} pour essayer la génération.</> : "La bêta est accessible sur invitation. Chaque compte reçoit 20 générations d’essai."}</p>
      {account && account.trial_remaining === 0 && !account.subscription_active && <p role="status">Vos crédits d’essai sont épuisés. L’abonnement sera proposé après l’ouverture des paiements.</p>}
      <p className="preference-help">{provider === "openai" ? "Réplique transmet les conversations confirmées à OpenAI pour générer les réponses. Aucun compte ChatGPT personnel n’est demandé aux testeurs." : "Le modèle fonctionne sur le serveur Réplique. Aucun compte ChatGPT n’est nécessaire."}</p>
    </div>
    <div className="trial-account-actions">
      {account ? <button type="button" className="text-button" disabled={busy || disabled} onClick={logout}>Se déconnecter</button> : <>
        <form onSubmit={submit}>
          <label>Adresse e-mail<input type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} disabled={busy || disabled} /></label>
          <label>Mot de passe<input type="password" minLength={registering ? 12 : undefined} autoComplete={registering ? "new-password" : "current-password"} required value={password} onChange={event => setPassword(event.target.value)} disabled={busy || disabled} /></label>
          {registering && <label>Code d’invitation<input type="text" autoComplete="off" required value={invitation} onChange={event => setInvitation(event.target.value)} disabled={busy || disabled} /></label>}
          <button type="submit" className="primary" disabled={busy || disabled}>{busy ? "Veuillez patienter…" : registering ? "Créer mon compte" : "Se connecter"}</button>
        </form>
        <button type="button" className="text-button" disabled={busy || disabled} onClick={() => { setRegistering(!registering); setError(""); }}>{registering ? "J’ai déjà un compte" : "J’ai un code d’invitation"}</button>
      </>}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  </section>;
}
