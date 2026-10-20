"""Lecture Jira pour le poller. Configuration par variables d'environnement : JIRA_SITE, JIRA_EMAIL, JIRA_TOKEN."""
import os
import requests
import yaml


def load_workflow(path=None):
    path = path or os.environ.get("QA_CONFIG", "core/config/workflow.yml")
    with open(path) as f:
        return yaml.safe_load(f)


def _auth():
    email, tok = os.environ.get("JIRA_EMAIL"), os.environ.get("JIRA_TOKEN")
    if not (email and tok):
        raise RuntimeError("JIRA_EMAIL / JIRA_TOKEN manquants")
    return (email, tok)


def search(jql, fields=("summary", "status", "labels", "updated"), max_results=50):
    site = os.environ["JIRA_SITE"].rstrip("/")
    r = requests.post(f"{site}/rest/api/3/search/jql", auth=_auth(), timeout=30,
                      json={"jql": jql, "maxResults": max_results, "fields": list(fields)})
    r.raise_for_status()
    return r.json().get("issues", [])


def tickets_a_tester(wf):
    """Tickets du périmètre dans un statut déclencheur, avec l'état « déjà testé » (label posé après la recette)."""
    ids = ", ".join(wf["statuts"])
    out = []
    for it in search(f'{wf["jql_base"]} AND status in ({ids}) ORDER BY updated DESC'):
        st = wf["statuts"][it["fields"]["status"]["id"]]
        env = st["env"]
        label = wf["label_deja_teste"].format(env=env)
        out.append({"key": it["key"], "summary": it["fields"]["summary"], "status": it["fields"]["status"]["name"], "env": env,
                    "env_actif": wf["envs"][env]["actif"], "deja_teste": label in (it["fields"].get("labels") or []), "label": label})
    return out
