# Réplique · bêta hébergée avec le forfait ChatGPT du propriétaire

Une fois publié, le domaine `https://replique.duckdns.org` reçoit des comptes Réplique sur invitation.
Chaque compte dispose de 20 générations d’essai. Le navigateur du visiteur ne
voit ni connexion ChatGPT, ni jeton OAuth, ni identité du propriétaire. Après
confirmation, le texte est envoyé par le serveur à OpenAI ; cette destination
est annoncée dans l’interface. Une génération réussie consomme un crédit ; un
échec rend la réservation. La mémoire de style est facultative et séparée par
compte Réplique ; seuls les exemples enregistrés volontairement peuvent être
réutilisés après un nouvel accord pour chaque génération.

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
```

Choisir **un modèle affiché par cette commande**, écrire `REPLIQUE_MODEL=son-slug`
dans le `.env` privé du VPS, puis recréer le service et vérifier sa santé :

```sh
docker compose up -d --force-recreate
curl -fsS -H 'Host: replique.duckdns.org' http://127.0.0.1:18081/api/health
```

La commande `backend.owner_provider` liste uniquement les modèles accessibles
au compte ; elle vérifie le renouvellement de la session et une connexion
réelle à OpenAI, sans afficher les jetons. Le service exige maintenant un modèle
fixé par le propriétaire et vérifie son éligibilité à chaque génération. Avant
ce choix, le contrôle de santé reste volontairement en erreur. Si le catalogue ou la
génération est refusé, corriger l’autorisation du compte avant d’inviter des
visiteurs. Un `GET /api/health` sain vérifie le fichier chiffré et sa clé,
mais ne garantit pas à lui seul qu’OpenAI acceptera une génération.

Sur le VPS, vérifier quel fichier Nginx sert actuellement
`replique.duckdns.org` avec `sudo nginx -T`. Sauvegarder ce fichier, remplacer sa
configuration active par `deploy/nginx-https.conf`, désactiver l’ancien bloc qui
sert `deploy/index.html` afin de ne garder qu’un serveur pour ce nom, puis faire
`sudo nginx -t && sudo systemctl reload nginx`. Ne recharger que si le contrôle
réussit. Le certificat TLS du domaine doit être valide. Réplique écoute uniquement
sur `127.0.0.1:18081` de l’hôte. Les routes OAuth du propriétaire sont bloquées
sur le domaine public ; le secret n’est monté que dans le conteneur backend.
Depuis une autre machine, vérifier la publication sans envoyer de données privées :

```sh
python deploy/verify_public.py
```

Le contrôle doit afficher `OK`. S’il voit encore la page demandant un tunnel SSH,
le fichier Nginx actif est l’ancien site privé. Si `/api/health` échoue, vérifier
le conteneur, le modèle fixé et la session propriétaire chiffrée avant d’ouvrir
les invitations. Le contrôle ne prouve pas qu’OpenAI acceptera les images : faire
ensuite l’essai avec une capture fictive depuis un compte invité.
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
Sur téléphone, la page publique peut être ajoutée à l’écran d’accueil depuis
le menu du navigateur. Ce raccourci ouvre l’interface sans clavier natif ni
lecture automatique des messageries ; une connexion réseau reste nécessaire.

Pour une capture de conversation, le visiteur accepte séparément l’envoi de
l’image à OpenAI. Le modèle `REPLIQUE_MODEL` doit prendre en charge les images.
La lecture remplit le champ texte, sans produire immédiatement de réponse : le
visiteur relit et attribue les messages, confirme l’envoi du texte, puis clique
sur « Trouver mes mots ». L’extraction ne retire pas de crédit d’essai, mais
utilise le forfait ChatGPT du propriétaire et est limitée à 30 images par jour
et par compte. Les captures PNG/JPG/WebP et les photos HEIC/HEIF de 10 Mo
maximum sont acceptées. Une photo sans texte de conversation lisible doit être
remplacée par une capture plus nette ou transcrite manuellement. En cas d’échec,
le brouillon reste visible et la même image peut être relue après un nouvel accord.

L’abonnement payant n’est pas ouvert : après 20 crédits, Réplique l’indique
sans accepter de paiement. Avant une offre commerciale mondiale, choisir un
prestataire de paiement, obtenir une base fournisseur autorisée et vérifier
les conditions d’utilisation d’OpenAI pour ce cas d’usage. Le forfait personnel
peut être limité ou refusé ; la réussite de tests ne garantit pas qu’il couvre
un SaaS payant.

## Limites et suivi privé

Avec `deploy/nginx-https.conf`, Nginx limite par adresse IP les connexions à
5/minute, les générations et l’OCR à 12/minute, avec de petites rafales. Le
backend borne aussi chaque compte à 6 demandes de génération par minute,
10 OCR par minute et 30 OCR par jour. Un dépassement renvoie HTTP 429 ; les échecs de mot de passe ne
verrouillent plus le compte d’une victime. Vérifier `nginx -t` avant de recharger
la configuration, puis vérifier une erreur 429 contrôlée en environnement de
test. Ajuster ces valeurs après avoir mesuré la charge réelle du KVM 2.

Les générations et lectures de photos écrivent seulement l’heure, le fournisseur, une catégorie de
résultat et la durée dans `data/operations.sqlite3`. Aucun texte de conversation,
e-mail, identifiant de compte ou jeton n’y est enregistré. Les événements de
plus de 30 jours sont supprimés lors du prochain enregistrement. Lire les
comptages d’échecs, les limites OpenAI et la médiane/p95 des succès pour les réponses
et les photos :

```sh
docker compose exec replique python -m backend.operations report --days 7
```

Le relevé est local et agrégé ; il ne remplace pas une alerte externe. Une
limite `quota` répétée ou un temps p95 trop long doit interrompre l’invitation
de nouveaux testeurs jusqu’au diagnostic.

## Sauvegarde et restauration vérifiée

Arrêter brièvement les écritures pendant la copie, car les bases de mémoire sont
distinctes de la base des comptes. Créer un dossier privé et un instantané
cohérent de SQLite. Le snapshot contient
**la base des comptes, les mémoires par compte, la session propriétaire et sa clé** : son accès équivaut
à celui du compte propriétaire. Le transférer hors du VPS vers un stockage
chiffré contrôlé par vous, puis supprimer la copie temporaire du VPS. Ne jamais
le placer dans Git, dans l’image Docker ou sur un espace public.

```sh
cd /opt/replique
(
  set -e
  trap 'docker compose up -d --no-build' EXIT
  docker compose stop replique
  docker compose run --rm --no-deps --entrypoint sh replique -c 'umask 077; mkdir -p /data/backups'
  snapshot="snapshot-$(date -u +%Y%m%dT%H%M%SZ)"
  docker compose run --rm --no-deps replique python -m backend.backup create "/data/backups/$snapshot"
  docker compose run --rm --no-deps replique python -m backend.backup drill "/data/backups/$snapshot"
)
```

`drill` restaure dans un dossier privé temporaire, compare les fichiers de base
et toutes les mémoires de compte présentes, puis efface le dossier temporaire.
Faire ce contrôle après chaque sauvegarde, puis transférer le
snapshot. Par exemple, depuis votre ordinateur privé, copier le dossier
`/opt/replique/data/backups/snapshot-...` avec `scp -r` vers un disque chiffré
hors du dépôt, puis ne garder sur le VPS que les copies nécessaires. Conserver
aussi le slug `REPLIQUE_MODEL` pour reconstruire le `.env`.

En cas de perte du VPS, récupérer ce dossier, arrêter Réplique et créer des
dossiers `data` et `secrets` vides et privés appartenant à UID 10001. Restaurer
hors ligne avec la même image, en adaptant `SNAPSHOT` au chemin absolu du dossier
de sauvegarde récupéré :

```sh
cd /opt/replique
docker compose stop replique
snapshot_dir=/chemin/prive/snapshot-YYYYMMDDTHHMMSSZ
mkdir -p data secrets
chown -R 10001:10001 "$snapshot_dir"
chmod 700 "$snapshot_dir"
chmod 600 "$snapshot_dir"/*
chown 10001:10001 data secrets
chmod 700 data secrets
docker compose build replique
docker run --rm --network none --user 10001:10001 \
  -v "$PWD/data:/data" -v "$PWD/secrets:/secrets" -v "$snapshot_dir:/snapshot:ro" \
  replique:local python -m backend.backup restore /snapshot /data /secrets/credential.key
docker compose up -d
```

La restauration refuse d’écraser des fichiers existants ; en cas de récupération
sur un VPS encore rempli, conserver d’abord ses anciens fichiers hors de ces
dossiers. Vérifier `GET /api/health`, puis une génération fictive et le solde
d’un compte avant de rouvrir le service.

## Mesurer la bêta avec deux personnes

Faire tester le même modèle fixé à deux personnes invitées. Le corpus
`backend/evals/conversation_cases.json` contient 15 échanges fictifs ; chaque
testeur dispose de 20 crédits. Créer une feuille de notation sans stocker les
réponses ni les conversations :

```sh
python -m backend.quality_review template --model SLUG --output /chemin/prive/replique-review.csv
```

Chaque testeur lit indépendamment les trois réponses pour chaque cas et note de 1 à 5 la
fidélité aux faits, le naturel, la différence utile des variantes et le respect
des limites. Il marque `passes_case` avec `yes` ou `no` après lecture des
critères `must` / `must_not` du corpus. Remplir toutes les lignes puis calculer :

```sh
python -m backend.quality_review report --input /chemin/prive/replique-review.csv
docker compose exec replique python -m backend.operations report --days 1
```

Faire quelques demandes en même temps pour observer la file d’attente et le
p95, sans épuiser le forfait. Le rapport indique aussi les cas validés par les
deux personnes et leur taux d’accord ; examiner toute divergence avant d’élargir
la bêta. Ces notes humaines et mesures réelles restent à
produire avec le compte propriétaire ; les tests automatisés utilisent un
fournisseur simulé.
