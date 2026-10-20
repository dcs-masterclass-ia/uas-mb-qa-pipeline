"""Un lien signé par Python doit être accepté par la page de décision JS (et un lien altéré refusé)."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pipeline import cards

NODE = r"""
process.env.QA_LINK_SECRET = "secret-de-test";
const h = require("./api/decision.js");
const url = new URL(process.argv[1]);
const q = Object.fromEntries(url.searchParams);
let out = {};
const res = { setHeader(){}, status(c){ out.code = c; return this; }, send(b){ out.body = b; } };
process.env.QA_WORKFLOW_JSON = "{}";   // pas d'appel Jira : on ne teste que la signature
h({ method: "GET", query: q }, res).then(() => console.log(JSON.stringify({ code: out.code, invalide: /invalide/.test(out.body) })));
"""

def verifie(url):
    r = subprocess.run(["node", "-e", NODE, url], capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
    return json.loads(r.stdout.strip().splitlines()[-1])

def test_signature_valide_et_alteree():
    u = cards.link("https://exemple.test", "secret-de-test", "ABC-1:ppr", "accept")
    assert verifie(u)["invalide"] is False
    assert verifie(u.replace("ABC-1", "ABC-2"))["invalide"] is True
    assert verifie(u.replace("a=accept", "a=refuse"))["invalide"] is True
    assert verifie(cards.link("https://exemple.test", "autre-secret", "ABC-1:ppr", "accept"))["invalide"] is True

if __name__ == "__main__":
    test_signature_valide_et_alteree(); print("OK : signatures Python <-> JS cohérentes")
