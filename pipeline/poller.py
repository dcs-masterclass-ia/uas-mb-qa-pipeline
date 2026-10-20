#!/usr/bin/env python3
"""Poller Jira -> recette -> cartes Teams.

Modes :
  (défaut)   SIMULATION : lit Jira, lance la recette SANS parcours funnel (aucun dossier créé), n'écrit ni n'envoie rien.
  --cartes   envoie les cartes Teams (webhook de test) mais n'écrit RIEN dans Jira ; parcours funnel désactivé.
  --apply    réel : parcours funnel (dossiers de TEST en preview), cartes Teams, label « déjà testé » dans Jira.

  --ticket KEY --env stg|ppr|prod   force un ticket (ignore statut et label) — pour essayer sans attendre un déploiement.
Le code de la recette vient du dépôt privé « core » (PYTHONPATH).
"""
import argparse
import os
import sys

from pipeline import cards
from pipeline.jira import load_workflow, tickets_a_tester, add_label, search

try:
    from mbqa.run import run_ticket
    from mbqa.resume import resume
except ImportError:
    sys.exit("Dépôt privé « core » introuvable : ajouter son chemin au PYTHONPATH (voir le workflow).")


def sujets(wf, a):
    if a.ticket:
        if not a.env:
            sys.exit("--ticket demande --env")
        it = search(f"key = {a.ticket}")
        resume = it[0]["fields"]["summary"] if it else a.ticket
        return [{"key": a.ticket, "summary": resume, "status": "(forcé)", "env": a.env, "env_actif": True, "deja_teste": False,
                 "label": wf["label_deja_teste"].format(env=a.env)}]
    return tickets_a_tester(wf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cartes", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ticket")
    ap.add_argument("--env", choices=["stg", "ppr", "prod"])
    a = ap.parse_args()
    wf = load_workflow()
    reel = a.apply
    envoie = a.apply or a.cartes
    base, secret, hook = os.environ.get("DECISION_BASE_URL", "https://example.com"), os.environ.get("QA_LINK_SECRET", ""), os.environ.get("UAS_MB_TEAMS_WEBHOOK", "")
    if envoie and not (secret and hook):
        sys.exit("QA_LINK_SECRET et UAS_MB_TEAMS_WEBHOOK requis pour envoyer des cartes")
    if a.apply and "example.com" in base:
        sys.exit("--apply refusé : DECISION_BASE_URL non défini (les boutons ne marcheraient pas)")

    tickets = sujets(wf, a)
    print(f"{len(tickets)} ticket(s) à traiter  [mode : {'APPLY' if a.apply else 'CARTES' if a.cartes else 'SIMULATION'}]")
    for t in tickets:
        if t["deja_teste"]:
            print(f"  {t['key']} [{t['env']}] déjà testé → ignoré"); continue
        if not t["env_actif"]:
            print(f"  {t['key']} [{t['env']}] environnement inactif → ignoré"); continue
        st = next((v for k, v in wf["statuts"].items() if v["env"] == t["env"]), None)
        print(f"  {t['key']} [{t['env']}] {t['summary'][:60]}")
        if envoie:
            print("     carte « recette lancée » :", cards.envoie(hook, cards.card_lancee(t["key"], t["summary"], t["env"])))
        r = run_ticket(t["key"], t["env"], wf, reel=reel)
        print(f"     recette : {r['ok']} OK · {r['ko']} KO · {r['warn']} à regarder · {r['skip']} ignorés"
              + ("" if r["ticket_yml"] else "  (pas de test propre au ticket : contrôles génériques seulement)"))
        for an in r["anomalies"][:6]:
            print("       -", an)
        if envoie:
            cid = f"{t['key']}:{t['env']}"
            payload = cards.card_resultat(t["key"], t["summary"], t["env"], resume(r),
                                          cards.link(base, secret, cid, "accept"), cards.link(base, secret, cid, "refuse"),
                                          st["accept"]["nom"], st["refuse"]["nom"])
            print("     carte « résultat » :", cards.envoie(hook, payload))
        if a.apply:
            add_label(t["key"], t["label"])
            print("     label posé :", t["label"])


if __name__ == "__main__":
    main()
