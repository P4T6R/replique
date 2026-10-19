# Validation · 17 octobre 2026

## Réussis

- Build TypeScript strict + Vite production.
- Tests DOM jsdom du bundle : confirmation contexte, choix exemple, chargement, verrouillage champs, trois réponses, focus résultats, édition, invalidation contexte, suppression pendant réponse retardée, consentement et domaine fournisseur. API simulée.
- Relecture indépendante sécurité/API effectuée ; détails dans le rapport final.

## Non validés

- Appel à un fournisseur réel : aucun secret configuré, aucun appel payant.
- Rendu navigateur réel, responsive visuel, presse-papiers natif, téléchargement navigateur et accessibilité assistive.
- Qualité OCR français : Tesseract eng uniquement disponible. Extraction à relire impérativement.
- Résistance sémantique complète du modèle aux injections, refus, hallucinations et faits inventés.

## Blocage navigateur constaté

Chromium lancé par Playwright échoue avant ouverture : création de socket interdite dans cet environnement. Une tentative d’exécution autorisée hors sandbox échoue au démarrage bwrap sur une cible système en lecture seule. Aucune modification de sécurité ni contournement effectué. Le navigateur cloud CUA a été essayé mais ne peut pas joindre le serveur loopback de l’environnement de code (ERR_CONNECTION_REFUSED).

Le script de test navigateur `frontend/tests/e2e.mjs` est livré mais n’a pas pu être exécuté avec succès ici. Aucune capture d’écran navigateur n’est fournie ; aucune image artificielle n’est présentée comme preuve de test.

## Vérification finale supplémentaire

- 33 tests backend unittest réussis (`backend-test-output.txt`), dont OCR local réel sur texte synthétique, limites fichiers/images, nettoyage après timeout, refus des origines non autorisées, échéances absolues, mode réel simulé, erreurs fournisseur et nettoyage/validation de sorties.
- Test HTTP réel dans le même environnement réseau : démarrage Uvicorn, GET /api/health, GET / frontend compilé, POST /api/generate sur exemple fictif => trois réponses. Réussi.
- La séparation réseau entre appels de l’outillage explique l’impossibilité de joindre le serveur depuis le navigateur cloud. Le serveur n’est pas publié.

## Mise à jour v0.2 · 18 octobre 2026

- 68 tests backend exécutés de nouveau avec succès après intégration OAuth.
- Build TypeScript/Vite et tests DOM incluant OAuth réexécutés avec succès.
- Revue indépendante : voir OAUTH-REVIEW.md.
- Aucun parcours OAuth réel ni appel modèle n'a été effectué. Les limites navigateur et OCR français ci-dessus restent applicables.
- Lire OAUTH.md pour le périmètre personnel local et l’activation volontaire.
