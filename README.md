# uas-mb-qa-pipeline

Mécanique d'une recette automatique déclenchée par les statuts Jira, avec décision du PO sur une carte Teams.
Ce dépôt est **public et ne contient aucune donnée sensible** : hôtes, identifiants de statuts, parcours de test et
secrets vivent dans un dépôt privé (« core ») et dans les secrets GitHub / Vercel.

```
Jira (statut change) → poller (GitHub Actions, ~20 min) → recette (dépôt privé) → carte Teams → [Accepter] [Refuser]
      → lien signé → page de décision (Vercel, api/decision.js) → commentaire + transition Jira
```

| Fichier | Rôle |
|---|---|
| `pipeline/poller.py`, `pipeline/jira.py` | liste les tickets en statut déclencheur (simulation par défaut) |
| `pipeline/cards.py` | cartes Teams (Adaptive Card) et liens signés HMAC |
| `api/decision.js` | page de décision : un GET ne décide jamais, seul le POST agit, une décision une seule fois |
| `.github/workflows/qa.yml` | exécution planifiée, récupère le dépôt privé avec un jeton en secret |
| `config/workflow.example.yml` | exemple de configuration, sans valeur réelle |

## Secrets à définir

GitHub (Actions) : `JIRA_SITE`, `JIRA_EMAIL`, `JIRA_TOKEN`, `QA_LINK_SECRET`, `UAS_MB_TEAMS_WEBHOOK`, `CORE_DEPLOY_KEY` (clé de déploiement en lecture seule sur le dépôt privé) ; variables `CORE_REPO`, `DECISION_BASE_URL`.
Vercel : `QA_LINK_SECRET`, `JIRA_SITE`, `JIRA_EMAIL`, `JIRA_TOKEN`, `QA_WORKFLOW_JSON`, `UAS_MB_TEAMS_WEBHOOK` (optionnel).

## Sécurité

- Les workflows ne tournent que sur `schedule` / `workflow_dispatch` : jamais sur une pull request externe, donc aucun secret exposé.
- Les liens de décision sont signés (HMAC-SHA256, 7 jours) ; la signature couvre l'identifiant, l'action et l'expiration.
- Test : `python3 tests/test_liens.py` (nécessite Node).
