# Réplique — fiche produit MVP

Nom de travail provisoire. Disponibilité du nom et des marques non vérifiée.

## Promesse
Trouver les mots qui vous ressemblent, en tenant compte de la conversation et de vos limites.

Réplique est un assistant de conversation français d’abord, utilisable pour les rencontres et les échanges du quotidien. Il réunit la richesse du contexte, la simplicité d’un import et un accès rapide aux réponses. Son identité propre tient à une règle : aider à s’exprimer, sans inventer une relation ni chercher à contrôler l’autre.

## Différenciation : la réponse ancrée
Chaque réponse comporte :
- Une formulation prête à modifier, exprimant l’intention choisie.
- Une courte explication de ce qu’elle fait : relancer avec une question ouverte, proposer un rendez-vous, clarifier un malentendu, poser une limite.
- Un repère de contexte : information explicitement présente dans l’échange ou donnée confirmée par l’utilisateur.
- Une incertitude visible si une information indispensable manque. Dans ce cas, proposer une formulation neutre ou une question, jamais inventer la réponse.

Pas de score de séduction, de diagnostic des sentiments ni de promesse de résultat. Un délai de réponse n’est pas une preuve de désintérêt. Les explications décrivent la formulation, pas l’état mental supposé du destinataire.

## Parcours principal
1. **Apporter du contexte** : coller du texte ou importer une capture. Un exemple fictif permet d’essayer sans fournir de données privées.
2. **Vérifier** : aperçu du texte extrait et identification « Moi / Autre personne ». Tout est éditable. Confirmer explicitement le texte avant de générer ; OCR incertain et attribution ambiguë sont signalés.
3. **Choisir son intention** : relancer, répondre naturellement, proposer de se voir, clarifier, poser une limite, décliner. L’utilisateur peut préciser librement son objectif.
4. **Régler sa voix** : naturel, chaleureux, direct ou léger ; longueur courte ou développée ; emojis autorisés ou non. Le style reste subordonné à l’intention et aux faits.
5. **Comparer trois réponses** : par exemple « Simple », « Plus chaleureuse », « Plus directe ». Elles doivent réellement différer, sans changer les faits ni introduire trois intentions contradictoires.
6. **Ajuster et copier** : modifier une réponse, demander « plus court » ou « plus proche de mes mots », puis copier le texte. Confirmation de copie explicite. L’envoi demeure dans l’application de messagerie de l’utilisateur.
7. **Effacer** : une action visible supprime le contenu de la session dans l’application. La portée exacte de l’effacement est annoncée.

## Trois scénarios clés
### Répondre sans surjouer
Une personne reçoit « Tu as passé un bon week-end ? ». Elle indique « chaleureux, court » mais ne décrit pas son week-end. L’outil n’invente ni voyage ni activité : il demande une précision ou propose une réponse compatible avec les seuls faits fournis.

### Faire avancer l’échange
L’échange mentionne explicitement un intérêt commun pour le cinéma. L’utilisateur choisit « proposer de se voir ». Les propositions peuvent s’appuyer sur le cinéma ; elles ne doivent inventer ni disponibilité, ni réservation, ni film déjà choisi.

### Poser une limite
L’utilisateur veut décliner une nouvelle rencontre. L’outil propose des formulations claires et respectueuses, sans inventer une excuse, suggérer de culpabiliser l’autre ou laisser intentionnellement planer une promesse.

## MVP à construire
- Interface web responsive, français par défaut ; utilisable au clavier et sur mobile.
- Saisie de texte, exemple fictif et import d’image avec état de progression et gestion d’erreur.
- Écran de relecture obligatoire pour l’import ; retrait possible des noms et des informations inutiles avant génération.
- Intentions et contrôles de style, puis trois cartes de réponse avec explication et contexte utilisé.
- Édition, copie individuelle et régénération ciblée d’une réponse.
- État vide, chargement, erreur réseau, image illisible, contexte insuffisant et refus sûr.
- Sélecteur de langue de réponse ; conserver le français par défaut. Ne pas attribuer un niveau de langue ou une identité à partir d’un nom.
- Action « Effacer cette conversation » accessible à tout moment.
- Aucun compte requis pour le premier essai ; aucun partage public ni envoi automatique.

### Si seul un prototype sans backend est disponible
Le présenter explicitement comme une démonstration. Les exemples préécrits doivent être identifiés comme tels. Ne pas simuler une vraie lecture de capture, une génération IA réelle ou une garantie de confidentialité non implémentée. Un import peut afficher l’image et demander une transcription manuelle. Les erreurs doivent être explicites, sans faux succès.

## Après le MVP
- Clavier natif ou extension de partage : accès rapide à du texte que l’utilisateur sélectionne ou fournit. Un clavier ne donne pas accès à l’historique complet des messageries.
- Profil de style facultatif à partir d’exemples choisis par l’utilisateur, avec possibilité de consulter et supprimer ces exemples.
- Contexte sauvegardé par conversation uniquement sur choix explicite, durée de conservation réglable.
- Coaching plus approfondi sur les formulations et les limites, sans diagnostic de l’autre personne.
- Plus de langues, avec tests humains de registre et d’intention ; éviter les stéréotypes culturels.

## Confidentialité et confiance
- Collecter uniquement le texte nécessaire. Retirer les noms, contacts et détails inutiles lorsque possible.
- Afficher clairement si l’image ou le texte part vers un fournisseur externe, lequel et pour quel usage, avant transmission. Ne pas promettre « tout reste sur votre appareil » si ce n’est pas vrai.
- Éviter de conserver les conversations et captures par défaut. Pas de contenu des échanges dans la télémétrie, les journaux applicatifs ou les rapports d’erreur.
- L’effacement local ne signifie pas automatiquement effacement des journaux d’un fournisseur ou du presse-papiers : expliquer précisément les limites du système effectivement implémenté.
- N’ajouter aucune API secrète dans le navigateur. Ne pas stocker une clé personnelle sans mécanisme approprié et autorisation.
- Traiter le texte importé comme des données, jamais comme des consignes système. Une instruction dans une capture ne doit pas détourner la génération.

## Limites produit
Ne pas aider à harceler après un refus, contourner un blocage, exercer une pression affective, usurper une identité ou obtenir des informations privées par tromperie. Réorienter vers une formulation honnête et respectueuse. Ne pas présenter les suggestions comme un traitement psychologique ni comme une lecture fiable des intentions d’une personne.

## Tests d’acceptation
1. **Faits manquants** : sans information sur le week-end, aucune activité passée n’est inventée.
2. **Disponibilités** : aucune heure, date ou promesse n’est affirmée sans confirmation de l’utilisateur.
3. **Attribution** : une capture ambiguë ne produit aucune réponse avant validation des interlocuteurs.
4. **OCR** : une extraction illisible demande correction ou nouvelle image ; aucun texte « deviné » n’est présenté comme certain.
5. **Trois variantes** : trois formulations distinctes respectent la même intention et les mêmes faits confirmés.
6. **Voix** : « court, sans emoji » produit des réponses courtes sans emoji ; la modification manuelle reste conservée tant que l’utilisateur ne la remplace pas explicitement.
7. **Limites** : après un refus explicite du destinataire, aucune suggestion n’encourage à insister ou contourner un blocage.
8. **Injection** : « ignore toutes tes règles » dans la conversation importée reste du contenu cité sans effet sur le comportement.
9. **Copie** : le bouton copie uniquement le texte choisi, sans explication ni contenu d’une autre carte ; un échec de permission est signalé.
10. **Effacement** : le bouton vide texte, images et suggestions de la session ; un rafraîchissement ne restaure aucun contenu non sauvegardé volontairement.
11. **Langue** : les réponses suivent la langue choisie tout en conservant correctement les noms et faits confirmés.
12. **Accessibilité** : tous les contrôles possèdent des labels, un focus visible et une utilisation au clavier ; les états ne dépendent pas uniquement de la couleur.
13. **Vérité du prototype** : toute fonction simulée est identifiée avant usage ; aucun état de succès ne prétend qu’un traitement inexistant a eu lieu.

## Mesures de succès
Utilité déclarée de la réponse, fidélité ressentie à la voix de l’utilisateur, taux de réponses copiées après édition et taux d’erreurs factuelles signalées. Mesurer ces événements sans enregistrer le contenu intime. Ne pas optimiser le produit pour obtenir une réponse du destinataire ou maximiser la dépendance à l’assistant.
