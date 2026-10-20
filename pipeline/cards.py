"""Cartes Teams (Adaptive Card via webhook Power Automate) + liens signés Accepter/Refuser (même principe que Converge).

Un webhook ne reçoit pas de clic : les boutons sont des liens (Action.OpenUrl) signés HMAC-SHA256 de "id|action|exp"
(validité 7 jours) vers la page de décision. Un simple GET sur cette page n'agit jamais ; seul son POST décide.
"""
import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests

JIRA_BROWSE = os.environ.get("JIRA_SITE", "https://example.atlassian.net").rstrip("/") + "/browse"
ENV_LABEL = {"stg": "STG", "ppr": "PPR", "prod": "PROD"}


def sign(secret, ticket_id, action, exp):
    return hmac.new(secret.encode(), f"{ticket_id}|{action}|{exp}".encode(), hashlib.sha256).hexdigest()


def link(base, secret, ticket_id, action, days=7):
    exp = int((time.time() + days * 86400) * 1000)
    return f"{base.rstrip('/')}/api/decision?" + urlencode({"id": ticket_id, "a": action, "exp": exp, "sig": sign(secret, ticket_id, action, exp)})


def _card(body, actions=None):
    content = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4", "body": body}
    if actions:
        content["actions"] = actions
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": content}]}


def _txt(t, **kw):
    return {"type": "TextBlock", "text": t, "wrap": True, **kw}


def card_lancee(key, summary, env):
    return _card([_txt(f"🔎 Recette lancée — {key}", weight="Bolder", size="Large"),
                  _txt(summary), _txt(f"Environnement : {ENV_LABEL.get(env, env)}", isSubtle=True, spacing="Small")],
                 [{"type": "Action.OpenUrl", "title": "Ouvrir le ticket", "url": f"{JIRA_BROWSE}/{key}"}])


def card_resultat(key, summary, env, ok, ko, warn, anomalies, accept_url, refuse_url, accept_nom, refuse_nom):
    couleur = "Good" if ko == 0 else "Attention"
    corps = [_txt(f"{'✅' if ko == 0 else '❌'} Recette {ENV_LABEL.get(env, env)} — {key}", weight="Bolder", size="Large", color=couleur),
             _txt(summary),
             {"type": "FactSet", "facts": [{"title": "OK", "value": str(ok)}, {"title": "KO", "value": str(ko)}, {"title": "À regarder", "value": str(warn)}]}]
    if anomalies:
        corps.append(_txt("Anomalies :", weight="Bolder", spacing="Medium"))
        corps += [_txt(f"• {a}", spacing="None") for a in anomalies[:8]]
    corps.append(_txt(f"Accepter → {accept_nom} · Refuser → {refuse_nom}", isSubtle=True, spacing="Medium"))
    return _card(corps, [
        {"type": "Action.OpenUrl", "title": "✅ Accepter", "url": accept_url, "style": "positive"},
        {"type": "Action.OpenUrl", "title": "❌ Refuser", "url": refuse_url, "style": "destructive"},
        {"type": "Action.OpenUrl", "title": "Ouvrir le ticket", "url": f"{JIRA_BROWSE}/{key}"}])


def card_decision(key, choix, par, nouveau_statut):
    ok = choix == "accept"
    return _card([_txt(f"{'✅ Accepté' if ok else '❌ Refusé'} — {key}", weight="Bolder", size="Large", color="Good" if ok else "Attention"),
                  _txt(f"Décision enregistrée{f' par {par}' if par else ''}. Statut Jira → {nouveau_statut}.")],
                 [{"type": "Action.OpenUrl", "title": "Ouvrir le ticket", "url": f"{JIRA_BROWSE}/{key}"}])


def envoie(webhook, payload, timeout=30):
    r = requests.post(webhook, json=payload, timeout=timeout)
    return r.status_code, r.text[:200]
