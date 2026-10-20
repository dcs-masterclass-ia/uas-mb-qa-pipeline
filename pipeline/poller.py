#!/usr/bin/env python3
"""Poller Jira -> recette. SIMULATION par défaut : n'écrit rien dans Jira, n'envoie aucune carte, ne lance aucun test.

  python -m pipeline.poller            # affiche ce qu'il ferait
"""
from pipeline.jira import load_workflow, tickets_a_tester


def main():
    wf = load_workflow()
    tickets = tickets_a_tester(wf)
    print(f"{len(tickets)} ticket(s) dans un statut déclencheur")
    for t in tickets:
        if t["deja_teste"]:
            etat = "déjà testé → ignoré"
        elif not t["env_actif"]:
            etat = f"env {t['env']} inactif → ignoré"
        else:
            etat = f"→ recette sur {t['env'].upper()}, carte Teams au PO, puis label {t['label']}"
        print(f"  {t['key']:<10} [{t['status']}] {t['summary'][:70]}\n             {etat}")


if __name__ == "__main__":
    main()
