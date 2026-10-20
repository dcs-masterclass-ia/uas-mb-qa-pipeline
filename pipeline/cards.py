"""Cartes Teams (Adaptive Card via webhook Power Automate) + liens signés Accepter/Refuser (même principe que Converge).

Un webhook ne reçoit pas de clic : les boutons sont des liens (Action.OpenUrl) signés HMAC-SHA256 de "id|action|exp"
(validité 7 jours) vers la page de décision. Un simple GET sur cette page n'agit jamais ; seul son POST décide.
"""
import hashlib
import hmac
import os
import re
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


def titre_propre(summary):
    """Retire les étiquettes entre crochets du début du titre Jira : « [UAS MB] [x] Titre » -> « Titre »."""
    t = re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", summary or "").strip()
    return t or summary


def _ticket_ligne(key, summary):
    return _txt(f"[{key}]({JIRA_BROWSE}/{key}) · {titre_propre(summary)}", spacing="Small")


def card_lancee(key, summary, env):
    return _card([_txt(f"🔎 Recette {ENV_LABEL.get(env, env)} en cours", weight="Bolder", size="Medium"), _ticket_ligne(key, summary)])


def card_resultat(key, summary, env, res, accept_url, refuse_url, accept_nom, refuse_nom):
    """res = résumé lisible : {verdict:(ton, titre, phrase), verifie:[(ok|ko, texte)], annexes:[texte]} (voir mbqa.resume)."""
    ton, titre, phrase = res["verdict"]
    style = {"ok": "good", "ko": "attention", "neutre": "emphasis"}[ton]
    icone = {"ok": "✅", "ko": "⚠️", "neutre": "ℹ️"}[ton]
    corps = [{"type": "Container", "style": style, "bleed": False, "items": [
        _txt(f"RECETTE {ENV_LABEL.get(env, env)}", isSubtle=True, size="Small", weight="Bolder"),
        _txt(f"{icone} {titre}", size="Large", weight="Bolder", spacing="None"),
        _txt(phrase, spacing="Small")]},
        _ticket_ligne(key, summary)]
    if res["verifie"]:
        corps.append(_txt("Ce qui a été vérifié", weight="Bolder", spacing="Medium"))
        corps += [_txt(f"{'✅' if s == 'ok' else '❌'} {t}", spacing="None") for s, t in res["verifie"]]
    actions = []
    if res["annexes"]:
        corps.append({"type": "Container", "id": "annexes", "isVisible": False, "spacing": "Medium", "items": [
            _txt("Remarques sans lien avec ce ticket", weight="Bolder"),
            *[_txt(f"• {a}", spacing="None") for a in res["annexes"]]]})
    corps.append(_txt(f"✅ **Accepter** : le ticket passe en « {accept_nom} »\n\n❌ **Refuser** : il passe en « {refuse_nom} »", spacing="Medium", isSubtle=True, size="Small"))
    actions += [{"type": "Action.OpenUrl", "title": "✅ Accepter", "url": accept_url, "style": "positive"},
                {"type": "Action.OpenUrl", "title": "❌ Refuser", "url": refuse_url, "style": "destructive"}]
    if res["annexes"]:
        actions.append({"type": "Action.ToggleVisibility", "title": f"Voir les remarques annexes ({len(res['annexes'])})", "targetElements": ["annexes"]})
    return _card(corps, actions)


def card_decision(key, summary, choix, nouveau_statut):
    ok = choix == "accept"
    return _card([_txt(f"{'✅ Accepté' if ok else '❌ Refusé'} — {key}", weight="Bolder", size="Medium"), _ticket_ligne(key, summary),
                  _txt(f"Le ticket est passé en « {nouveau_statut} ».", spacing="Small")])


def envoie(webhook, payload, timeout=30):
    r = requests.post(webhook, json=payload, timeout=timeout)
    return r.status_code, r.text[:200]
