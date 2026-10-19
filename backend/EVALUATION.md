# Évaluations locales et versions contrôlées

Ce module est une **CLI locale**, sans interface de notation, sans appel fournisseur et sans coût d’inférence. Il ne réentraîne aucun modèle et ne réécrit aucun code. Le jeu `evals/learning_holdout_v1.json` contient six cas synthétiques réservés aux évaluations. Les tests unitaires simulent les déclarations d’un opérateur : leur succès ne mesure aucune qualité conversationnelle réelle.

## Ce qui peut changer

Une version immuable (identifiant SHA-256 du contenu) contient uniquement `max_examples` (0–3), `max_context_chars` (500–6000) et les identifiants des sources ayant motivé cette modification. La mémoire applique la version active à la sélection du contexte. La configuration initiale `builtin` est 3 exemples / 4500 caractères. La mémoire reste soumise à son activation et à l’autorisation d’envoi pour chaque génération.

Les opérations utilisent la même base SQLite que la mémoire. La CLI exige un fichier existant et ne crée ni active une mémoire personnelle silencieusement. Remplacer `$DB` par le chemin de cette base, travailler depuis la racine du projet :

```
python -m backend.evaluation --db "$DB" active
python -m backend.evaluation --db "$DB" candidate --config candidate.json --source ID_SOURCE
python -m backend.evaluation --db "$DB" evaluate --baseline builtin --candidate HASH_CANDIDATE --dataset backend/evals/learning_holdout_v1.json --outputs outputs.json --ratings ratings.json --training-manifest training.json
python -m backend.evaluation --db "$DB" promote --version HASH_CANDIDATE --run HASH_RAPPORT --approve
python -m backend.evaluation --db "$DB" rollback --approve
```

`candidate.json` : `{"max_examples":2,"max_context_chars":4000}`. Plusieurs `--source` sont possibles. Aucun changement de code, de prompt libre ou de permission n’est accepté.

## Préparer une comparaison honnête

1. Figé avant l’amélioration, le jeu tenu à l’écart ne doit jamais devenir un exemple d’apprentissage/retrieval. Le manifeste `training.json` est une liste d’objets `{"id":"…","input":"…","source_ids":["…"]}` décrivant le corpus de développement utilisé ; `[]` signifie explicitement aucun corpus supplémentaire. Le module ajoute automatiquement les conversations présentes dans la mémoire. Il refuse les recouvrements d’ID, de texte normalisé Unicode/casse/espacement et de source de conversation. Une paraphrase sans provenance peut échapper à ces contrôles : ils ne prouvent pas l’indépendance sémantique. Ne pas réutiliser des cas après avoir optimisé dessus ; créer un nouveau holdout.
2. Produire séparément les sorties des deux configurations avec le même modèle/prompt et des conditions comparables. La CLI n’effectue pas ces appels. Conserver modèle exact, hash du prompt, date de génération et seed si disponible. Aucun secret d’authentification dans ces fichiers.
3. `outputs.json` est un objet dont les deux clés sont `builtin` et le hash candidat. Chaque valeur associe chaque ID du jeu à une sortie texte. Un cas absent ou supplémentaire bloque le rapport.
4. Un humain lit chaque sortie à l’aide du champ `rubric` et attribue de 1 (échec) à 5 (excellent) dans les dimensions `relevance`, `naturalness`, `groundedness`, `context_boundaries`. La note est un jugement humain, jamais un score inventé par les contrôles de longueur ou de mots interdits.

Format `ratings.json` (remplacer les points de suspension et renseigner tous les cas/dimensions) :

```
{
  "reviewer": "Identifiant du relecteur",
  "human_reviewed": true,
  "output_origin": "saved_model",
  "generation_metadata": {
    "builtin": {"model":"modèle exact", "prompt_hash":"SHA-256", "generated_at":"date ISO", "seed":null},
    "HASH_CANDIDATE": {"model":"modèle exact", "prompt_hash":"SHA-256", "generated_at":"date ISO", "seed":null}
  },
  "scores": {
    "builtin": {"lh-time":{"relevance":4,"naturalness":4,"groundedness":5,"context_boundaries":5}},
    "HASH_CANDIDATE": {"lh-time":{"relevance":4,"naturalness":4,"groundedness":5,"context_boundaries":5}}
  }
}
```

La provenance `saved_model` et la relecture sont des déclarations de l’opérateur, pas une attestation cryptographique du fournisseur. Utiliser `fixture` pour les sorties artificielles : elles ne peuvent jamais qualifier une promotion. Sans notation complète, les notes non disponibles sont nulles et la promotion est bloquée. Les règles mécaniques vérifient uniquement longueur, présence de texte, nombre de questions et littéraux interdits ; elles ne détectent pas toutes les violations de limite ni hallucinations.

Le rapport associe hashes du jeu, des sorties, des notes, du manifeste et des versions, plus métadonnées de génération. Il ne stocke pas les sorties brutes ni le contenu privé du corpus. Pour qualifier une promotion : les contrôles candidat passent, toutes les notes humaines sont complètes, chaque moyenne candidat vaut au moins 4/5 sans régression sur la moyenne de référence, et la provenance/métadonnées sont renseignées. Les identifiants de modèle et de prompt doivent être identiques entre les versions ; les seeds doivent correspondre quand tous deux sont connus. Il faut encore l’action explicite `--approve` et la référence doit toujours être la version active. Ce seuil est une règle locale conservatrice, pas une preuve statistique d’amélioration.

## Suppression et rollback

La suppression d’une source supprime les versions qui en dérivent et leurs entrées d’historique ; tous les rapports sont effacés conservativement. Une version active invalidée revient à `builtin`. Une source expirée ne peut plus activer sa version. Un rollback explicite ne restaure jamais un exemple supprimé : il ne fait que reprendre une configuration retenue valide. Effacer toute la mémoire efface également versions, rapports et historique.

La suppression SQLite ne constitue pas un effacement forensique des sauvegardes disque ni des exports que l’utilisateur conserve. Les fichiers d’entrée CLI restent sous son contrôle et doivent être supprimés séparément si nécessaire.

## Vérifier sans compte ni coût

```
python -m unittest backend.test_evaluation -v
```

Ces tests couvrent blocage sans notes, fixtures, activation et rollback simulés, sources supprimées/expirées, contamination, intégrité des hashes, sorties incomplètes, règles et métadonnées manquantes. Ils ne justifient aucune affirmation de progrès d’un modèle réel.
