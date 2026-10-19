# Réplique — refonte de l’atelier

## Direction et parcours
- Palette papier crème, encre espresso, accents terre cuite et sauge ; titrage éditorial DM Serif Display, texte DM Sans, polices TTF auto-hébergées, licences SIL OFL incluses. L’aperçu les intègre en base64 et ne dépend d’aucun service distant.
- Point d’entrée centré sur la conversation : import de capture ou exemple, texte corrigible, confirmation de relecture. L’intention et le ton viennent ensuite ; préférences avancées repliées par défaut.
- Compte ChatGPT dans un volet distinct, visible au besoin, avec états OAuth conservés. Une erreur de compte ou session expirée ouvre le volet. La barre d’état distingue démo préécrite, fournisseur configuré et forfait ChatGPT.
- Trois propositions modifiables ; copie manuelle et export. L’abstention est un conseil unique sans carte vide ni copie/export. Effacer le texte d’une proposition reste possible sans faire disparaître son champ.
- Contexte linguistique optionnel : français neutre, Afrique de l’Ouest, contexte Burkina Faso ; familiarité séparée. Aucun argot forcé ni promesse d’authenticité régionale. Les démos indiquent leurs limites.
- Adaptation à 320/768/1024/1440 via points de rupture CSS. Un seul flux sur mobile ; boutons tactiles, champs 16px sur mobile, focus visible, lien d’évitement, vrais boutons/details, réduction des animations respectée.

## Preuves exécutées
- `npm run build` : TypeScript + production Vite réussis.
- `npm test` : tests DOM avec API simulée : relecture, consentement, génération, édition, invalidation des résultats, annulation/effacement ; états OAuth, modèle, quota, expiration, redirections refusées ; nouveaux champs région/familiarité, verrouillage en génération, réinitialisation et abstention.
- `node tests/preview.mjs` : génère `evidence/replique-apercu.html` à partir du DOM du bundle construit. Trois états fictifs inspectables : accueil, propositions, abstention. Commandes métier désactivées dans cet aperçu ; choix de l’état et volets fonctionnels. Aucun appel modèle ni connexion réelle.

## Limite de vérification
Aucune capture d’écran ni validation de mise en page dans un navigateur réel n’a été effectuée : le lancement navigateur de cet environnement est bloqué. Les vérifications responsive ci-dessus sont structurelles/CSS, pas un résultat Playwright ou une preuve de rendu visuel. L’aperçu HTML est livré pour revue directe, et n’est pas une capture d’écran.
