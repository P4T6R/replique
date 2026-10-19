# Réplique — API locale

Backend Python 3.11+ / FastAPI. Aucun compte, base de données ou service externe n’est nécessaire au mode démo local. Pour la bêta publique sur invitation et ses protections, voir [`../HOSTED.md`](../HOSTED.md).

## Démarrer

Depuis le dossier racine `replique` :

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r backend/requirements.txt
# Construire frontend/dist en suivant le README racine, puis :
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Ouvrir `http://127.0.0.1:8000`. Le frontend compilé est servi par FastAPI s’il existe au démarrage. Ne pas utiliser `--host 0.0.0.0`. Les requêtes avec un Host non local et les requêtes cross-origin sont rejetées.

En développement avec Vite et son proxy API, autoriser explicitement son origine exacte côté backend, par exemple :

```sh
REPLIQUE_DEV_ORIGIN=http://127.0.0.1:5173 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

L’origine `localhost` diffère de `127.0.0.1` ; les ports doivent correspondre. Sans cette variable, seule l’origine exacte du serveur est autorisée. Les clients locaux sans en-tête Origin restent possibles.

## Vérité du mode démo

Le mode par défaut est `demo`. Il renvoie trois formulations préécrites et clairement annoncées comme telles, uniquement pour ces trois échanges fictifs exacts :

1. Conversation de découverte :
   - `Moi : Ça m’a fait plaisir de discuter avec toi !`
   - `Autre personne : Moi aussi, c’était sympa. On remet ça ?`
2. Refus :
   - `Moi : On se revoit ?`
   - `Autre personne : Merci, mais je ne suis pas intéressée.`
3. Arrêt de contact :
   - `Moi : Je voulais reprendre la discussion.`
   - `Autre personne : Ne me contacte plus.`

Utiliser un saut de ligne entre les deux messages. Une conversation personnelle ou un exemple modifié est refusé avec une erreur explicite demandant la configuration d’un fournisseur IA. La démo ne prétend pas comprendre des conversations arbitraires. Le ton utilise des transformations simples et l’emoji est optionnel ; le texte libre de style n’est pas interprété en mode démo.

## Configurer la génération réelle

Le fournisseur doit proposer un endpoint compatible OpenAI Chat Completions avec `response_format: json_schema`. Aucune clé n’est intégrée au frontend, aux exemples ni au dépôt. Configurer uniquement l’environnement du processus serveur :

- `REPLIQUE_MODE=live`
- `REPLIQUE_API_BASE_URL=https://api.openai.com/v1` ou la base de votre fournisseur, sans `/chat/completions` final
- `REPLIQUE_MODEL` : identifiant d’un modèle compatible de votre fournisseur
- `REPLIQUE_API_KEY` : clé côté serveur ; ne pas la placer dans une variable Vite, un fichier public ou le navigateur

Le modèle est obligatoire. HTTPS est obligatoire hors des hôtes loopback. Un fournisseur local compatible peut utiliser HTTP et ne requiert pas de clé. Les variables proxy de l’environnement ne sont pas utilisées et les redirections fournisseur ne sont jamais suivies.

Chaque génération réelle exige `consent=true` après affichage du nom d’hôte du fournisseur dans l’interface. Le texte relu, l’intention, le ton, le style et l’option emoji lui sont envoyés. L’image OCR n’est envoyée qu’en mode ChatGPT ou hébergé et après le consentement distinct décrit ci-dessous ; en mode fournisseur `live`, l’OCR reste local. Les conditions de traitement et conservation du fournisseur s’appliquent. Aucune requête réelle ou payante n’a été exécutée lors du développement et des tests : l’intégration réseau est validée avec un transport simulé. La qualité des modèles et la compatibilité exacte de votre fournisseur restent à vérifier avant utilisation de données personnelles.

Les erreurs fournisseur, délais, refus, sorties malformées ou réponses qui ne respectent pas les contrôles sont explicites. Il n’y a aucun remplacement silencieux d’une génération réelle par une démo. Exception annoncée : lorsqu’une règle locale reconnaît un refus explicite, une réponse de sécurité préécrite est renvoyée avec `mode=demo`, `boundary=true` et une notice spécifique, sans transmission externe.

## OCR avec ChatGPT

En mode `REPLIQUE_MODE=chatgpt`, l’image est normalisée localement puis transmise comme entrée image à `/v1/responses`, avec le modèle choisi dans le catalogue du compte. Cette étape exige une session ChatGPT connectée, `X-Replique-Request: 1` et un consentement distinct pour chaque capture. La consigne demande une transcription fidèle uniquement ; elle interdit de traiter le texte visible comme des consignes et ne déduit pas les auteurs. L’utilisateur relit et attribue les messages avant de générer. Les modèles qui ne prennent pas en charge les images peuvent refuser la requête ; les images comptent dans l’utilisation du forfait. Les images ne sont pas envoyées pendant la génération texte si l’utilisateur choisit de coller une conversation.

En mode `owner_chatgpt`, le compte visiteur et un accord distinct sont requis pour chaque capture. Le serveur choisit `REPLIQUE_MODEL`, limite l’OCR à 10/minute et 30/jour par compte et n’impute pas de crédit d’essai à la seule extraction ; la génération du texte relu reste une étape distincte. Le modèle fixe doit accepter les entrées image. Une capture sans texte de conversation lisible ne peut pas produire de réponse pertinente.

Le fichier est limité à 5 Mio à l’entrée et 8 Mio après normalisation PNG, à 16 mégapixels et à 8 000 pixels par côté. Les métadonnées ne sont pas conservées. La requête utilise le jeton OAuth conservé en mémoire et `store:false`, `stream:true`. Le traitement et la conservation sont soumis aux règles OpenAI.

## OCR réel et local

Tesseract doit être installé séparément, avec son modèle français `fra` pour le français. Le modèle français n’est pas installé dans l’environnement de validation ; le test OCR réel a utilisé `eng` avec un avertissement visible. Sur un système Debian/Ubuntu administré par vous, les paquets habituels sont `tesseract-ocr` et `tesseract-ocr-fra`. Redémarrer le serveur après ajout d’un modèle.

L’API privilégie `fra`, puis `eng`, puis un autre modèle disponible en le signalant. L’OCR ne garantit ni l’exactitude du texte, ni l’attribution des interlocuteurs. La relecture et l’identification `Moi :` / `Autre personne :` sont obligatoires avant génération ; l’API exige `context_confirmed=true`.

Limites et protections :

- PNG, JPEG ou WebP fixes uniquement ; contenu image vérifié indépendamment de l’extension.
- 5 Mio maximum par image ; corps HTTP limité avant parsing multipart à 5 Mio + 256 Kio.
- Maximum 16 millions de pixels et 8 000 pixels par côté.
- Au plus deux extractions simultanées ; processus Tesseract borné à 20 secondes.
- Délai absolu de réception d’une requête : 30 secondes.
- Délai absolu fournisseur : 35 secondes, avec timeout réseau de 30 secondes et connexion de 8 secondes.
- Réponse fournisseur limitée à 128 Kio ; texte OCR et conversation limités à 12 000 caractères.
- Image normalisée sans métadonnées avant OCR, dans un dossier temporaire supprimé dans un `finally`, y compris après timeout/échec.

L’image et le texte passent en mémoire du serveur local. Aucun contenu de conversation n’est écrit volontairement dans des logs applicatifs ou une base de données. L’OCR utilise brièvement des fichiers temporaires ; la suppression n’est pas un effacement forensique. La commande recommandée désactive les access logs. Le presse-papiers, les journaux éventuels de l’environnement et la conservation du fournisseur ne sont pas effacés par le bouton de l’interface.

## Contrat API

- `GET /api/health` → `{mode, ocr_available, ocr_languages, provider}`. `provider` contient seulement le nom d’hôte public configuré, jamais l’URL complète ni la clé.
- `POST /api/generate` JSON → `{mode, notice, insight, replies: [{id,title,text,why}], boundary}`.
  - Champs : `conversation`, `intent`, `tone`, `style`, `emoji`, `consent`, `context_confirmed`.
  - Intentions exactes : `relancer`, `répondre naturellement`, `proposer de se voir`, `clarifier`, `poser une limite`, `décliner`.
  - Tons : `naturel`, `chaleureux`, `direct`, `léger`.
  - Style libre : 500 caractères maximum.
  - Exactement trois propositions. En cas de demande explicite de non-contact, les trois textes sont vides : ne pas proposer de copie ni d’envoi.
- `POST /api/ocr` multipart, champ `file` → `{text, language, warning}`.
- Les erreurs retournent `{"detail": "message français"}` sans réafficher le texte privé fourni.

Les textes importés et le style sont des données non fiables dans un message utilisateur séparé, jamais interpolés dans le message système. La sortie réelle est validée après normalisation : trois titres attendus, textes distincts non vides (ou trois textes vides pour une abstention cohérente), tailles bornées, option sans emoji, et quelques motifs de pression interdits. Les règles de détection de refus et les filtres ne constituent pas une garantie sémantique ; une relecture humaine reste indispensable.

## Vérifier

Depuis le dossier racine :

```sh
python -m unittest backend.test_app -v
# Équivalent :
python -m unittest discover -s backend -v
```

Les 33 tests historiques de la version 0.1 couvrent le contrat démo, l’interdiction des conversations arbitraires en démo, les refus attribués, les limites de corps/image, les origines, la relecture/consentement, l’OCR local et sa suppression temporaire, les erreurs fournisseur, les enveloppes malformées, la normalisation avant validation et les délais absolus. Aucun test ne contacte un fournisseur externe. Le test OCR réel est ignoré si Tesseract n’est pas disponible.


## OAuth ChatGPT — version 0.2

Voir [OAUTH.md](../OAUTH.md) pour le mode local `REPLIQUE_MODE=chatgpt`, activé seulement avec `REPLIQUE_OAUTH_ENABLED=1`. Le serveur et le navigateur doivent utiliser `http://127.0.0.1:8000`. Un seul worker et un seul compte par installation. Aucun jeton persistant ; seuls les identifiants non secrets d’installation/inscription sont enregistrés dans `REPLIQUE_DATA_DIR` (défaut `~/.local/share/replique`).

Routes : GET `/api/auth/status`, POST `/api/auth/login`, GET `/api/auth/callback`, POST `/api/auth/logout`, GET `/api/auth/models`. Les mutations OAuth et la génération ChatGPT exigent `Origin` exact et `X-Replique-Request: 1`. Le cookie local HttpOnly ne contient aucun jeton OpenAI. La génération prend le champ `model` sélectionné dans le catalogue courant. Les erreurs ont parfois un `detail` structuré `{code, message}` ; ne jamais afficher la réponse OAuth brute.

Le callback fait exception à la règle cross-site uniquement pour sa navigation GET sur 127.0.0.1 ; state, cookie de tentative et URI exacte restent obligatoires. Les logs d’accès doivent rester désactivés.


## Réglages conversationnels (0.3)

Le contrat `/api/generate` conserve ses champs existants et accepte `locale` (`fr_neutre` par défaut, `afrique_ouest`, `burkina_faso`) et `familiarity` (`neutre` par défaut, `familier`). Ces choix ne déduisent aucune identité. Le champ `style` reste libre. API et OAuth partagent le même prompt et les mêmes données structurées non fiables. Les trois `text` peuvent être vides pour recommander de ne rien envoyer ; le client doit alors masquer copie/envoi.

Les deux exemples supplémentaires sont `DEMO_BRIEF` et `DEMO_UNANSWERED` dans `app.py`. Ils sont préécrits et ne prouvent pas la qualité d’un modèle réel. Le mode démo n’interprète pas le style libre ni les préférences régionales.

Tests : `python -m unittest discover -s backend -v`. Rapport : `../evidence/CONVERSATION-QUALITY.md`. Le corpus synthétique `evals/conversation_cases.json` décrit les attentes d’une future évaluation réelle ; aucune génération distante n’a été effectuée pour ce corpus.


### Silence et relances contextuelles

Le silence, même après plusieurs messages, ne suffit pas à conclure à un refus ou au désintérêt. Sans refus explicite, la démo et le prompt commun proposent trois variantes non vides d’une idée facultative, ancrées dans l’échange disponible. Les conseils invitent à en choisir une seule puis à laisser de l’espace, sans calendrier ni série automatique de relances. Un oubli est une possibilité, jamais une explication établie. Aucun délai écoulé, sujet, prétexte ou disponibilité n’est inventé. Avec le seul contexte « on se reparle plus tard », les idées reprennent sobrement cette ouverture. L’intention de l’utilisateur de décliner ou poser une limite reste respectée.

Une demande explicite d’arrêt de contact conserve le garde-fou : aucun texte à envoyer. Le prompt distingue ce silence ordinaire d’un contexte dangereux, incohérent ou insuffisant pour proposer un message sûr : ces situations peuvent justifier une abstention expliquée. Le validateur conserve donc les trois textes vides cohérents ; il ne prouve pas la qualité sémantique des textes générés. Les cas synthétiques supplémentaires dans `evals/conversation_cases.json` décrivent les critères d’acceptation, sans prétendre à une évaluation d’un modèle réel. Aucune proposition n’est envoyée automatiquement.
