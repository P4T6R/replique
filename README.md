# Réplique · prototype

## Bêta hébergée

Le déploiement Docker de ce dépôt est préparé pour `replique.duckdns.org` avec
une session ChatGPT privée du propriétaire côté serveur, des comptes Réplique
sur invitation et 20 crédits d’essai. Voir [HOSTED.md](HOSTED.md). La session
doit être autorisée en local par le propriétaire, puis transférée chiffrée au
VPS ; aucun compte ChatGPT n’est demandé aux visiteurs. L’abonnement payant
n’est pas ouvert et le fournisseur réel doit être validé avant toute invitation.

Un atelier français pour préparer une réponse qui respecte votre intention et vos limites. Nom de travail, disponibilité de marque non vérifiée.

## Connexion ChatGPT (parcours local historique)

Le parcours OAuth local et Responses est implémenté et vérifié sur des services simulés. Il n’a pas encore été connecté à un compte réel ; la bêta hébergée utilise une session créée par ce parcours, jamais la connexion des visiteurs. [OAUTH.md](OAUTH.md) décrit le parcours local et ses limites.

## Ce que vous pouvez essayer

- Coller une conversation en attribuant les messages à `Moi :` et `Autre personne :`.
- Importer une capture PNG/JPEG/WebP, extraire son texte avec Tesseract local ou, en mode ChatGPT, avec OpenAI après un accord distinct, puis corriger le texte et confirmer les auteurs.
- Choisir une intention, un ton, des préférences de style et l’utilisation d’un emoji.
- Lire trois formulations et une brève explication éditoriale, les modifier, les copier ou les exporter en texte.
- Effacer la session. L’utilisateur garde la décision et envoie lui-même dans sa messagerie.

### Démonstration ≠ IA

Par défaut, aucun modèle n’est appelé. Seuls les exemples fictifs accessibles par « Essayer un exemple », « Réponses courtes », « Sans réponse » et « Un refus » permettent de générer des formulations préécrites. Coller votre propre conversation et en extraire le texte reste possible, mais obtenir des réponses adaptées nécessite une connexion ChatGPT ou un fournisseur IA configuré. Les préférences libres ne sont pas comprises en mode démo. La démo n’est pas une preuve de compréhension contextuelle. Une demande explicite de ne plus être contacté est traitée côté serveur et apparaît comme un bref conseil dans la zone de résultat habituelle, sans scénario visible dédié ni message à copier.

L’adaptateur de fournisseur compatible Chat Completions est implémenté et testé avec des réponses simulées. Aucun appel payant ni test avec un fournisseur réel n’a été réalisé. La qualité rédactionnelle, le respect complet des faits et les garde-fous sémantiques du modèle restent à évaluer. Les validations de schéma ne constituent pas une garantie de sécurité ou d’exactitude.

## Installation locale

Pour l'installation Docker sur un serveur, voir [DOCKER.md](DOCKER.md).
La bêta hébergée utilise une session créée par le propriétaire sur son ordinateur
privé puis transférée chiffrée au VPS ; aucun tunnel SSH permanent n’est requis
pour les visiteurs. Le callback OAuth historique reste limité à `127.0.0.1`.

Prérequis : Python 3.11+, Node.js 22.12+ ou 24, npm. Tesseract est facultatif pour l’OCR. Installez-le depuis le gestionnaire officiel de votre système, avec les langues française et anglaise si possible.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
./run.sh
```

Ouvrir http://127.0.0.1:8000. Sous Windows, activer `.venv\Scripts\activate` puis lancer `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --no-access-log` à la place du script shell.

Ce lancement local sert le frontend compilé sur `127.0.0.1` et ne doit pas être
exposé directement sur Internet. La bêta hébergée utilise le déploiement HTTPS,
les comptes et les protections décrits dans [HOSTED.md](HOSTED.md).

## Fournisseur réel, facultatif

Lire `backend/README.md` pour les variables d’environnement. Les secrets restent côté serveur. Le programme ne charge pas automatiquement de fichier `.env`. Ne jamais mettre une clé dans le frontend, un commit ou une capture.

Le mode `live` facultatif nécessite un fournisseur compatible, un modèle
disponible et éventuellement un compte facturé par ce fournisseur. La bêta
hébergée utilise plutôt la session propriétaire créée séparément avec ChatGPT.
Avant chaque génération distante, l’interface indique la destination et exige
le consentement à l’envoi du texte. Une erreur fournisseur est affichée sans
substitution silencieuse par la démo.

## Vie privée et limites

- Mode temporaire par défaut : aucune génération, copie ou extraction OCR n’enregistre de conversation. La mémoire locale SQLite est alimentée uniquement par « Retenir ce choix » ou un enregistrement explicite du profil. Le témoin d’accueil peut rester dans localStorage ; aucun texte de conversation n’y est conservé.
- Les conversations sont en mémoire dans le navigateur et traversent le serveur pour l’OCR/génération. En mode réel, elles sont envoyées au fournisseur configuré.
- Les images OCR sont bornées en taille et dimensions et normalisées sans métadonnées. En mode ChatGPT, l’image est envoyée à OpenAI uniquement après un accord distinct ; ailleurs, l’OCR est local. Le fournisseur applique ses propres conditions de traitement et conservation.
- Effacer annule l’affichage des requêtes en cours et enlève l’état de cet atelier ; cela ne supprime pas les exports, le presse-papiers, les données déjà reçues par un fournisseur, les caches système ou les éventuels journaux d’une infrastructure externe.
- Évitez les captures de tiers non nécessaires et retirez les coordonnées et données sensibles.
- Tesseract est absent de certains environnements ; le mode ChatGPT peut alors demander une transcription OpenAI avec consentement distinct. Les petites polices et bulles complexes peuvent être mal lues. Relecture et attribution des auteurs obligatoires.
- Les règles conservatrices de refus ne couvrent pas toutes les formulations possibles. Les instructions du fournisseur demandent de respecter un refus, de ne pas faire pression et de ne pas inventer faits ou sentiments. La décision finale reste humaine.
- Aucun clavier natif, plugin de messagerie, envoi automatique, paiement ou hébergement n’est inclus. Le compte ChatGPT reste géré par OpenAI.

## Tests et état de validation

Version 0.2 : voir `evidence/backend-v02-tests.log` pour les tests backend OAuth/Responses et `OAUTH.md` pour les limites de validation réelle. Les rapports 0.1 ci-dessous restent historiques.

```sh
python -m unittest backend.test_app -v
cd frontend
npm run build
npm test
```

`npm test` teste le bundle React dans jsdom avec une API simulée : confirmation du contexte, formulaire bloqué pendant génération, modification, invalidation des résultats, effacement pendant requête et consentement fournisseur. Ce n’est pas un test de rendu navigateur.

Scénario navigateur fourni : démarrer le serveur compilé puis `cd frontend && CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e`. Sans `CHROMIUM_PATH`, Playwright attend son navigateur installé. Le scénario produit des captures desktop/mobile dans `evidence/` et vérifie l’absence de débordement à 320, 768, 1024 et 1440 px.

État exact des vérifications et blocages : `evidence/QA.md`.

## Structure

- `frontend/` : React, TypeScript, Vite, styles responsives et tests DOM/navigateur.
- `backend/` : FastAPI, modèles de validation, démo déterministe, adaptateur fournisseur et OCR.
- `PRODUCT.md` : brief produit et périmètre.
- `run.sh` : lancement local de la version compilée.

## Prochain jalon utile

Tester la version dans un vrai navigateur sur mobile et desktop, puis évaluer un fournisseur explicitement choisi avec un jeu de conversations fictives (ambiguïté, refus, attribution erronée, négations, injection d’instructions), avant d’envisager des données réelles ou un lancement public.

### Polices locales
DM Sans et DM Serif Display sont livrées localement dans `frontend/public/fonts/`, avec leurs licences SIL Open Font License. Aucun service de polices tiers n’est appelé. L’aperçu HTML intègre les fichiers de polices pour fonctionner hors connexion.


## Mémoire locale v0.4

Le bouton « Retenir ce choix » conserve seulement la réponse relue, son retour explicite et, si vous le choisissez, un extrait de contexte relu. L’extrait est vide par défaut. Un retour négatif peut être conservé pour consultation mais n’est jamais utilisé comme exemple. Seuls les exemples explicitement validés et évalués positivement ou corrigés sont sélectionnés. Copier, générer et utiliser l’OCR ne sont pas des signaux d’apprentissage. Aucune identité, émotion, donnée sensible ou préférence n’est automatiquement déduite d’un échange.

Le profil de style contient trois préférences explicites bornées (longueur, registre, emojis). Les réglages de la génération actuelle priment toujours. Les exemples expirent après 30 jours : ils ne sont plus récupérés après cette échéance et sont supprimés physiquement de la base active lors du prochain accès à la mémoire. Les préférences restent jusqu’à leur suppression. L’application éteinte n’exécute aucune purge en arrière-plan.

« Utiliser ma mémoire » est désactivé par défaut. Un aperçu montre les exemples sélectionnés et le profil avant la génération ; l’accord d’envoi au fournisseur couvre aussi ces éléments. La sélection est bornée à trois exemples, 6 000 caractères au maximum (4 500 par défaut), de même intention et même variante de français. La révision est vérifiée avant l’appel : si la mémoire a changé, relisez l’aperçu. En cas d’erreur mémoire, la génération avec mémoire est bloquée clairement ; désactivez son utilisation pour continuer. Aucun enregistrement réussi n’est annoncé avant validation de la transaction.

Les données sont locales à cette installation et partagées par toute personne ayant accès à ce serveur local. Ce n’est pas un coffre lié au compte ChatGPT ni une isolation multi-utilisateur : un changement de compte ne change pas le propriétaire du profil local. La connexion OAuth et ses jetons restent séparés, et les jetons ne sont jamais écrits dans SQLite. La base n’est pas chiffrée par l’application ; utilisez la protection du compte et du disque du système d’exploitation.

Emplacement de la base :
- Linux : `$XDG_DATA_HOME/replique/memory.sqlite3`, ou `~/.local/share/replique/memory.sqlite3`.
- macOS : `~/Library/Application Support/Replique/memory.sqlite3`.
- Windows : `%LOCALAPPDATA%/Replique/memory.sqlite3`.
- Surcharge : `REPLIQUE_DATA_DIR` doit être un chemin absolu vers un répertoire privé local. Évitez un dossier partagé, synchronisé ou le dossier des sources. La base et ses fichiers annexes doivent être exclus des archives distribuées.

La base n’est créée ni au démarrage, ni à la consultation initiale, ni à une génération temporaire. Elle est créée au premier enregistrement explicite, avec une migration versionnée, des clés étrangères activées et des transactions atomiques. Quota : 500 exemples. Exporter télécharge le contenu de la mémoire locale sans jetons OAuth. Supprimer un exemple efface ses retours et invalide les versions dérivées correspondantes ; tout effacer retire aussi le profil et les versions locales. L’effacement logique ne garantit pas l’écrasement des blocs du disque et n’efface pas les sauvegardes externes, exports ou données déjà reçues par le fournisseur. « Effacer l’atelier » reste distinct de « Effacer la mémoire ».

Cette personnalisation sélectionne du contexte ; elle ne réentraîne pas les poids du modèle et ne prouve pas une amélioration de qualité. Les exemples sauvegardés restent des données non fiables dans le JSON utilisateur et ne peuvent modifier les instructions de sécurité.

Tests mémoire synthétiques : `python -m unittest backend.test_memory -v`.
