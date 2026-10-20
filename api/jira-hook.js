/**
 * Réception du webhook Jira : un ticket vient d'entrer dans un statut de déploiement -> on lance la recette tout de suite.
 *
 * Jira (webhook « issue updated », filtré par JQL) appelle POST /api/jira-hook?k=<JIRA_HOOK_KEY>.
 * La clé dans l'URL est le seul secret (les webhooks Jira créés par API ne sont pas signés) : elle est comparée à temps constant.
 * On ne déclenche QUE si le changelog contient un changement de statut vers un statut déclencheur ; tout autre événement
 * (commentaire, label, modification de champ…) est ignoré. Le travail est fait par GitHub Actions (workflow_dispatch).
 *
 * Variables : JIRA_HOOK_KEY, QA_WORKFLOW_JSON (statut -> environnement), GITHUB_DISPATCH_TOKEN (fine-grained, Actions:write
 * sur le seul dépôt du pipeline), GITHUB_REPO ("owner/repo"), QA_PRODUIT (défaut "DCS White label Factory"), QA_PRODUIT_FIELD (défaut customfield_10065), QA_TITRE_FILTRE (optionnel).
 */
const crypto = require("crypto");

const egal = (a, b) => { const x = Buffer.from(String(a || "")), y = Buffer.from(String(b || "")); return x.length === y.length && crypto.timingSafeEqual(x, y); };

module.exports = async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ ok: false });
  if (!process.env.JIRA_HOOK_KEY || !egal((req.query || {}).k, process.env.JIRA_HOOK_KEY)) return res.status(401).json({ ok: false });
  const b = req.body && typeof req.body === "object" ? req.body : {};
  const key = b.issue && b.issue.key;
  if (!/^[A-Z][A-Z0-9]+-\d+$/.test(key || "")) return res.status(200).json({ ok: true, ignore: "pas un ticket" });
  // périmètre : champ « Product(s) » (liste d'options) contient le produit voulu ; titre optionnel en plus
  const champ = process.env.QA_PRODUIT_FIELD || "customfield_10065", produit = process.env.QA_PRODUIT || "DCS White label Factory";
  const valeurs = [].concat((b.issue.fields || {})[champ] || []).map(o => (o && o.value) || o);
  if (!valeurs.includes(produit)) return res.status(200).json({ ok: true, ignore: "hors périmètre (produit)" });
  if (process.env.QA_TITRE_FILTRE && !String((b.issue.fields || {}).summary || "").includes(process.env.QA_TITRE_FILTRE)) return res.status(200).json({ ok: true, ignore: "hors périmètre (titre)" });

  let wf = {};
  try { wf = JSON.parse(process.env.QA_WORKFLOW_JSON || "{}"); } catch { /* config absente */ }
  const parEnv = Object.entries(wf).reduce((m, [env, v]) => (m[String(v.statut)] = env, m), {});
  const items = ((b.changelog || {}).items || []).filter(i => i.field === "status");
  if (!items.length) return res.status(200).json({ ok: true, ignore: "pas de changement de statut" });
  const env = parEnv[String(items[items.length - 1].to)];
  if (!env) return res.status(200).json({ ok: true, ignore: "statut non déclencheur" });

  const event = String((b.changelog || {}).id || b.timestamp || Date.now());
  if (!process.env.GITHUB_DISPATCH_TOKEN) return res.status(500).json({ ok: false, erreur: "GITHUB_DISPATCH_TOKEN absent" });
  // dédoublonnage sans rien écrire dans Jira : le workflow est nommé « QA <ticket> <événement> » ; si une exécution récente porte déjà ce nom, on ignore
  const gh = { Authorization: `Bearer ${process.env.GITHUB_DISPATCH_TOKEN}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" };
  const titre = `QA ${key} ${event}`;
  const runs = await fetch(`https://api.github.com/repos/${process.env.GITHUB_REPO}/actions/workflows/qa.yml/runs?event=workflow_dispatch&per_page=30`, { headers: gh });
  if (runs.ok && ((await runs.json()).workflow_runs || []).some(w => w.display_title === titre && Date.now() - Date.parse(w.created_at) < 3600e3))
    return res.status(200).json({ ok: true, ignore: "doublon" });
  const r = await fetch(`https://api.github.com/repos/${process.env.GITHUB_REPO}/actions/workflows/qa.yml/dispatches`, {
    method: "POST",
    headers: { ...gh, "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { ticket: key, env, event } }),
  });
  if (r.status !== 204) return res.status(502).json({ ok: false, erreur: `GitHub ${r.status}` });
  return res.status(202).json({ ok: true, ticket: key, env, event });
};
