# Réplique · bêta hébergée avec le forfait ChatGPT du propriétaire

Le domaine `https://replique.duckdns.org` reçoit des comptes Réplique sur invitation.
Chaque compte dispose de 20 générations d’essai. Le navigateur du visiteur ne
voit ni connexion ChatGPT, ni jeton OAuth, ni identité du propriétaire. Après
confirmation, le texte est envoyé par le serveur à OpenAI ; cette destination
est annoncée dans l’interface. Une génération réussie consomme un crédit ; un
échec rend la réservation. La mémoire de style historique est désactivée sur
le domaine public tant qu’elle n’est pas isolée par compte.

**Limite réelle :** ce mode n’a pas encore été vérifié avec un compte ChatGPT
réel. Le forfait, les scopes consentis, le catalogue de modèles et les limites
d’utilisation sont décidés par OpenAI. Le fichier Codex `auth.json` n’est pas
un substitut vérifié à cette autorisation : ne pas le copier dans le projet,
l’image Docker ou un site public. Le parcours ci-dessous crée une session via
« Continue with ChatGPT » sur **l’ordinateur privé du propriétaire**, puis
transfère seulement la session chiffrée et sa clé au VPS. Les visiteurs
n’effectuent jamais ce parcours.

## Créer la session propriétaire en local

Installer les dépendances et compiler l’interface comme dans `README.md`.
Sur un ordinateur que vous contrôlez, préparer un stockage privé :

```sh
mkdir -p "$HOME/.local/share/replique-owner" "$HOME/.config/replique-owner"
chmod 700 "$HOME/.local/share/replique-owner" "$HOME/.config/replique-owner"
.venv/bin/python - <<'PY'
from pathlib import Path
from cryptography.fernet import Fernet
path = Path.home() / '.config/replique-owner/credential.key'
with path.open('xb') as target:
    target.write(Fernet.generate_key())
path.chmod(0o600)
PY
REPLIQUE_MODE=chatgpt REPLIQUE_OAUTH_ENABLED=1 \
REPLIQUE_DATA_DIR="$HOME/.local/share/replique-owner" \
REPLIQUE_CREDENTIAL_KEY_FILE="$HOME/.config/replique-owner/credential.key" \
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Ouvrir `http://127.0.0.1:8000` **sur ce même ordinateur**, cliquer sur
« Continue with ChatGPT », consentir aux autorisations affichées et vérifier
une génération fictive avec un modèle proposé. Si OpenAI ne propose pas
l’autorisation de génération avec le forfait, arrêter ici : aucun code ne peut
la créer. Arrêter le serveur local avant de copier la session. Vérifier que
`$HOME/.local/share/replique-owner/oauth-session.enc` existe. Ne jamais envoyer
ces fichiers dans un dépôt Git, un message ou une archive publique.

## Installer le fournisseur sur le VPS

Dans le répertoire du dépôt sur le VPS (exemple `/opt/replique`), créer les
répertoires privés. Adapter ce chemin à votre installation :

```sh
cd /opt/replique
mkdir -p data secrets
chown 10001:10001 data secrets
chmod 700 data secrets
```

Depuis l’ordinateur privé, transférer les deux fichiers par SSH/SCP ordinaire
vers le VPS ; aucun tunnel de port n’est nécessaire :

```sh
scp "$HOME/.local/share/replique-owner/oauth-session.enc" root@replique.duckdns.org:/opt/replique/data/oauth-session.enc
scp "$HOME/.config/replique-owner/credential.key" root@replique.duckdns.org:/opt/replique/secrets/credential.key
ssh root@replique.duckdns.org 'chown 10001:10001 /opt/replique/data/oauth-session.enc /opt/replique/secrets/credential.key && chmod 600 /opt/replique/data/oauth-session.enc && chmod 400 /opt/replique/secrets/credential.key'
```

Sur le VPS :

```sh
cd /opt/replique
docker compose up -d --build
docker compose exec replique python -m backend.owner_provider
curl -fsS -H 'Host: replique.duckdns.org' http://127.0.0.1:18081/api/health
```

La commande `backend.owner_provider` liste uniquement les modèles accessibles
au compte ; elle vérifie le renouvellement de la session et une connexion
réelle à OpenAI, sans afficher les jetons. Par défaut, Réplique choisit le
premier modèle du catalogue ; pour en fixer un, mettre `REPLIQUE_MODEL=slug`
dans le `.env` privé du VPS puis recréer le conteneur. Si le catalogue ou la
génération est refusé, corriger l’autorisation du compte avant d’inviter des
visiteurs. Un `GET /api/health` sain vérifie le fichier chiffré et sa clé,
mais ne garantit pas à lui seul qu’OpenAI acceptera une génération.

Installer `deploy/nginx-https.conf`, vérifier `nginx -t`, puis recharger Nginx.
Le certificat TLS du domaine doit être valide. Réplique écoute uniquement sur
`127.0.0.1:18081` de l’hôte. Les routes OAuth du propriétaire sont bloquées
sur le domaine public ; le secret n’est monté que dans le conteneur backend.
Après une reconnexion du propriétaire en local, transférer la nouvelle session
chiffrée, puis redémarrer le conteneur. Ne pas réutiliser simultanément
l’ancienne session locale : les jetons de renouvellement tournent.

## Inviter et valider

Créer une invitation unique :

```sh
docker compose exec replique python -m backend.accounts invite
```

Le visiteur s’inscrit avec ce code, voit son solde et confirme explicitement
l’envoi de sa conversation à OpenAI. Vérifier avec un échange fictif que la
réponse arrive, que le solde passe de 20 à 19, qu’un échec ne coûte rien et
qu’une requête sans compte est refusée. Mesurer la vitesse et les limites du
forfait avec deux testeurs. Les comptes sont dans `data/accounts.sqlite3` ;
sauvegarder ce fichier et la session privée comme des données sensibles.

L’abonnement payant n’est pas ouvert : après 20 crédits, Réplique l’indique
sans accepter de paiement. Avant une offre commerciale mondiale, choisir un
prestataire de paiement, obtenir une base fournisseur autorisée et vérifier
les conditions d’utilisation d’OpenAI pour ce cas d’usage. Le forfait personnel
peut être limité ou refusé ; la réussite de tests ne garantit pas qu’il couvre
un SaaS payant.
