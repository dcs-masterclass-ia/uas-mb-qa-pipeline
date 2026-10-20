#!/usr/bin/env python3
"""Recette déclenchée par Jira -> carte Teams au PO.

Deux façons d'être lancé :
  - par le WEBHOOK Jira (api/jira-hook.js -> workflow_dispatch) : `--ticket KEY --env ENV --event ID`
    chaque entrée dans un statut de déploiement est un nouveau cycle : le label « déjà testé » est ignoré,
    l'événement est dédoublonné, la décision précédente est effacée.
  - par le filet de sécurité planifié (sans --ticket) : traite les tickets en statut déclencheur pas encore testés.

Modes : (défaut) SIMULATION, aucune écriture, pas de parcours funnel · --cartes : envoie les cartes, n'écrit rien dans Jira
        · --apply : réel (dossiers de TEST en preview, cartes, labels Jira).
Le code de la recette vient du dépôt privé « core » (PYTHONPATH).
"""
import argparse
import os
import re
import sys
import time

from pipeline import cards
from pipeline.jira import load_workflow, tickets_a_tester, add_label, remove_label, search, event_deja_vu, marque_event

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
        resume_t = it[0]["fields"]["summary"] if it else a.ticket
        return [{"key": a.ticket, "summary": resume_t, "status": "(forcé)", "env": a.env, "env_actif": wf["envs"][a.env]["actif"],
                 "deja_teste": False, "label": wf["label_deja_teste"].format(env=a.env), "force": True}]
    return [{**t, "force": False} for t in tickets_a_tester(wf)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cartes", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ticket")
    ap.add_argument("--env", choices=["stg", "ppr", "prod"])
    ap.add_argument("--event", help="identifiant de l'événement Jira (dédoublonnage)")
    a = ap.parse_args()
    if a.ticket and not re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", a.ticket):
        sys.exit("clé de ticket invalide")
    if a.event and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", a.event):
        sys.exit("identifiant d'événement invalide")
    wf = load_workflow()
    envoie = a.apply or a.cartes
    base, secret, hook = os.environ.get("DECISION_BASE_URL", "https://example.com"), os.environ.get("QA_LINK_SECRET", ""), os.environ.get("UAS_MB_TEAMS_WEBHOOK", "")
    if envoie and not (secret and hook):
        sys.exit("QA_LINK_SECRET et UAS_MB_TEAMS_WEBHOOK requis pour envoyer des cartes")
    if a.apply and "example.com" in base:
        sys.exit("--apply refusé : DECISION_BASE_URL non défini (les boutons ne marcheraient pas)")

    tickets = sujets(wf, a)
    print(f"{len(tickets)} ticket(s) à traiter  [mode : {'APPLY' if a.apply else 'CARTES' if a.cartes else 'SIMULATION'}]")
    for t in tickets:
        env = t["env"]
        if t["deja_teste"]:
            print(f"  {t['key']} [{env}] déjà testé → ignoré"); continue
        if not t["env_actif"]:
            print(f"  {t['key']} [{env}] environnement inactif → ignoré"); continue
        if a.apply and a.event and event_deja_vu(t["key"], a.event):
            print(f"  {t['key']} [{env}] événement {a.event} déjà traité → ignoré"); continue
        print(f"  {t['key']} [{env}] {t['summary'][:60]}")
        delai = int(wf["envs"][env].get("delai_secondes", 0)) if a.apply and t["force"] else 0
        if delai:
            print(f"     attente de {delai}s (laisser finir le déploiement)"); time.sleep(delai)
        r = run_ticket(t["key"], env, wf, reel=a.apply)
        res = resume(r)
        print(f"     verdict : {res['verdict'][1]}  ({r['ok']} OK · {r['ko']} KO · {r['warn']} à regarder)")
        if a.apply and t["force"]:
            remove_label(t["key"], f"qa-decision-{env}")     # nouveau cycle : une nouvelle décision est possible
        if envoie:
            st = next(v for v in wf["statuts"].values() if v["env"] == env)
            cid = f"{t['key']}:{env}"
            code = cards.envoie(hook, cards.card_resultat(t["key"], t["summary"], env, res, cards.link(base, secret, cid, "accept"),
                                                          cards.link(base, secret, cid, "refuse"), st["accept"]["nom"], st["refuse"]["nom"]))
            print(f"     carte envoyée : {code}")
        if a.apply:
            add_label(t["key"], t["label"])
            if a.event:
                marque_event(t["key"], a.event)
            print("     label posé :", t["label"])


if __name__ == "__main__":
    main()
