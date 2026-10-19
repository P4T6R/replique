# Réplique 0.2 — connexion locale avec ChatGPT

## État réel

Le chemin OAuth et l’adaptateur Responses sont implémentés et testés avec des réponses simulées. Aucun compte réel n’a été connecté, aucun client enregistré, aucun consentement accepté et aucune inférence facturée exécutée lors de ce développement. Le bouton ne fonctionne que lorsque vous activez volontairement le mode ci-dessous. La démonstration reste disponible par défaut.

Implémentation indépendante du protocole documenté, avec PyJWT/cryptography pour la vérification de signature. Aucun code du devkit SIWC n’est intégré ou redistribué. Aucun fichier de connexion Codex n’est lu.

## Périmètre

Application personnelle exécutée localement, un utilisateur, un compte/workspace, un processus serveur. La documentation officielle inclut les projets personnels locaux. Un service payant ou hébergé à distance nécessite une démarche distincte auprès d’OpenAI. L’éligibilité du compte, les modèles et les limites sont contrôlés par OpenAI au moment de la connexion. Aucune promesse d’accès illimité ou gratuit.

Le jeton d’accès reste en mémoire et est renouvelé auprès d’OpenAI après un redémarrage. Le jeton de renouvellement, l’identifiant de navigateur opaque, le compte vérifié et les scopes sont conservés dans le coffre du système : DPAPI Windows dans `oauth-session.dpapi`, ou trousseau natif macOS/Linux. Aucun jeton n’est conservé dans SQLite ni dans le stockage web. Le cookie HttpOnly/SameSite=Lax contient seulement l’identifiant aléatoire local et expire après un an pour retrouver la session protégée. La déconnexion tente la révocation chez OpenAI et supprime le jeton protégé localement. L’application utilise HTTP sur 127.0.0.1, donc le cookie n’a pas Secure ; ne pas exposer le serveur au réseau.

## Lancement volontaire après lecture

1. Installer les dépendances backend/requirements.txt, compiler le frontend selon README.md.
2. Configurer REPLIQUE_MODE=chatgpt et REPLIQUE_OAUTH_ENABLED=1 dans l’environnement de lancement.
3. Lancer ./run.sh, qui écoute uniquement 127.0.0.1:8000. Ne pas lancer plusieurs workers.
4. Ouvrir http://127.0.0.1:8000, puis Continue with ChatGPT. localhost n’est pas accepté pour OAuth.
5. Vous réalisez vous-même la connexion et le consentement sur auth.openai.com. Le retour exact est http://127.0.0.1:8000/api/auth/callback. Aucun mot de passe n’est saisi dans Réplique.
6. Sélectionner un modèle de votre catalogue. Pour une capture, cocher le consentement OCR distinct : l’image normalisée est alors envoyée à OpenAI pour transcription. Relire et attribuer les auteurs, puis confirmer séparément l’envoi du texte et des réglages avant chaque génération.

Le processus doit rester sur votre ordinateur, y compris la fenêtre de navigateur. Ce n’est pas un callback cloud ou un proxy de connexion.

## Sécurité et limites

- PKCE S256, state et nonce aléatoires, tentative à usage unique expirant après cinq minutes, liée au navigateur local.
- Validation cryptographique RS256 du jeton d’identité avec les clés JWKS publiées ; issuer, audience, expiration, nonce et identité de retour vérifiés.
- Scopes du forfait vérifiés séparément de l’identité. Aucun appel Chat Completions avec OAuth.
- Endpoint public Responses fixé, store:false, stream:true ; pas de température ou limite de sortie non prise en charge. Une sortie n’est acceptée qu’après response.completed avec statut completed. Les interruptions et erreurs tardives n’affichent pas de résultat partiel.
- Modèles chargés depuis le catalogue du compte ; pas de substitution silencieuse par une démo.
- Renouvellement sérialisé avec remplacement des jetons tournants. Les appels en cours sont annulés lors de la déconnexion locale.
- Déconnexion : tentative de révocation distante puis suppression locale des jetons, même si le réseau échoue. L’interface signale si la révocation n’est pas confirmée. Vous pouvez retirer l’accès dans les paramètres ChatGPT.
- Après arrêt brutal, le jeton d’accès temporaire disparaît et sera renouvelé au prochain usage depuis le jeton protégé. L’arrêt ne révoque pas l’accès distant ; utilisez la déconnexion dans Réplique ou gérez l’accès dans ChatGPT.
- Un seul compte par installation dans cette version. Pour changer volontairement de compte : se déconnecter, arrêter le serveur, retirer uniquement registration.json, puis relancer. Conserver host-id. Ce retrait ne supprime pas l’inscription distante ; la gérer dans ChatGPT.
- Ne pas utiliser sur une machine partagée avec des logiciels ou utilisateurs locaux non fiables : les autres processus du même utilisateur restent dans le périmètre de confiance.
- Les logs d’accès sont désactivés par run.sh pour ne pas enregistrer les codes de callback. Ne pas activer de journalisation des corps, en-têtes ou URLs OAuth.

## Vérification

Tests : python -m unittest discover -s backend -v. Ils utilisent des transports HTTP simulés, des clés RSA de test et un répertoire temporaire. Voir evidence/backend-v02-tests.log. La validation réelle navigateur → OpenAI → callback → modèle → génération reste à effectuer volontairement par l’utilisateur. Un résultat de test simulé n’est jamais une preuve de connexion réelle.

## Sources officielles consultées le 18 octobre 2026

- https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt
- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations

Limites de récupération de cette version : la révocation distante n’est tentée qu’une fois, sans reprise automatique ; un échec est signalé et nécessite de gérer l’accès dans ChatGPT. Si le tout premier échange de code échoue avant validation d’identité, l’inscription n’est pas conservée, donc une nouvelle tentative peut nécessiter une nouvelle inscription. Aucun compte supplémentaire n’est activé silencieusement.
