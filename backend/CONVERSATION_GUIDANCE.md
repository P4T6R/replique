# Guide de génération : intérêt et conversation

Réplique aide à formuler un message adapté à un échange précis. Aucun texte ne peut garantir qu'une personne répondra ou éprouvera de l'attirance. Les principes ci-dessous servent à mieux choisir le sujet, le ton et l'ouverture ; ils ne constituent pas un diagnostic de la relation.

## Sources examinées

- Huang et al. (2017), *It doesn't hurt to ask: Question-asking increases liking* : dans trois études de conversations, les questions de suivi étaient associées à une meilleure appréciation de l'interlocuteur et à une perception de réactivité. L'étude inclut des rencontres rapides, mais elle ne démontre pas qu'ajouter une question à chaque message améliore un échange par messagerie. https://pubmed.ncbi.nlm.nih.gov/28447835/
- Berrios et al. (2015), *Why Do You Make Us Feel Good?* : dans une petite étude de rencontres rapides (40 participants), la réactivité perçue était associée à l'intérêt romantique. Le contexte oral et la taille de l'échantillon empêchent d'en déduire une formule de message universelle. https://pubmed.ncbi.nlm.nih.gov/25750481/
- Chen et al. (2024), *Trusting strangers: The benefits of reciprocal self-disclosure during online computer-mediated communication* : l'alternance de confidences a été associée à davantage de confiance et d'appréciation dans des échanges en ligne entre inconnus. Cela n'autorise pas Réplique à inventer une confidence au nom de l'utilisateur. https://pubmed.ncbi.nlm.nih.gov/37931920/
- Langley et Shiota (2025), *Funny Date, Creative Mate?* : six expériences sur des profils ou rendez-vous hypothétiques ont trouvé un effet du trait d'humour sur la désirabilité perçue. Elles ne montrent pas qu'une blague forcée dans un message donné obtiendra une réponse. https://pubmed.ncbi.nlm.nih.gov/37837301/

## Traduction dans le produit

Le prompt hébergé doit repérer le dernier message reçu, ce que l'utilisateur a déjà envoyé, un détail concret encore ouvert et l'intention choisie. Il répond au fond avant de proposer une suite. Une question de suivi est permise quand elle reprend un détail réel ; elle reste facultative et unique. L'humour ou la taquinerie dépend du registre déjà partagé. Une proposition de rendez-vous est claire et facile à refuser. Un refus ou une demande d'espace est respecté.

Si une capture ne donne pas de fil exploitable pour une relance, le parcours image présente une seule proposition sobre. Le nom, l'emoji et le ton taquin ne compensent pas l'absence de contexte. Les propositions restent des brouillons à relire par l'utilisateur.

Ces règles sont dans `GROUNDED_CONNECTION_PROMPT` et `SPARSE_PHOTO_FOLLOWUP_PROMPT` dans `app.py`. Les tests vérifient que les parcours texte et image reçoivent les mêmes consignes de contexte. La qualité des messages du modèle doit aussi être appréciée sur de vrais cas, car un test de contrat ne prouve pas la pertinence d'une formulation.
