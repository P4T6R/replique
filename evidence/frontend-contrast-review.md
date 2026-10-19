# Contrastes et états de réponse

Mise en page, typographies et palette crème / terracotta / sauge conservées. Les boutons de compte et le ton sélectionné passent du fond charbon à la sauge existante. Couleurs explicites pour boutons, champs, options et dialogue ; color-scheme limité au clair ; texte désactivé lisible, sans opacité globale de 45 %. Focus conservé et vérifié numériquement.

Audit CSS : tokens de la vraie feuille résolus avant calcul de cascade dans jsdom (jsdom ne résout pas les variables CSS). Tous les couples testés dépassent 4,5:1 ; bouton principal 6,11:1, sauge 7,54:1, désactivés 4,89:1, aide sur crème 4,74:1. Focus >3:1 sur crème, papier et surface désactivée.

Tests React DOM : génération, édition, réinitialisation, consentement, erreurs, OAuth simulé, préférences ; propositions facultatives après silence copiables et éditables ; réponse unique sans fausse annonce de trois versions ; demande explicite de ne plus contacter sans copie/export.

Aperçu HTML autonome généré depuis le DOM React compilé, trois polices embarquées, quatre vues : atelier, propositions, sans réponse (idées facultatives), demande explicite de ne plus contacter. Fixtures des réponses obtenues de la fonction démo réelle du backend, sans réseau. L’aperçu garde les couleurs/états des boutons de l’application au lieu de tous les griser artificiellement ; actions de génération non disponibles dans la vue statique.

Limites : pas de navigateur réel utilisable dans cet environnement. Aucune capture ni validation visuelle, responsive, moteur navigateur ou mode sombre système revendiquée. Aucun appel OAuth ni fournisseur réel effectué.
