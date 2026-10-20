/**
 * Décision du PO sur une recette : Accepter / Refuser (même principe que les tickets Converge).
 *
 * Les boutons de la carte Teams ouvrent GET /api/decision?id=KEY:env&a=accept|refuse&exp=&sig= ; la page affiche une
 * confirmation (un simple GET -- aperçu de lien, antivirus -- ne décide jamais), le bouton envoie un POST.
 * Authentification par lien signé : HMAC-SHA256 de "id|action|exp" avec QA_LINK_SECRET, validité 7 jours.
 * Effet du POST : commentaire Jira + transition vers le statut configuré. Aucun label : une décision n'a lieu qu'une fois parce que
 * le ticket doit encore être dans le statut de la carte ; après la transition, un second clic est refusé.
 *
 * Variables d'environnement (Vercel) : QA_LINK_SECRET, JIRA_SITE, JIRA_EMAIL, JIRA_TOKEN,
 *   QA_WORKFLOW_JSON = {"stg":{"statut":"11408","accept":{"id":"11409","nom":"…"},"refuse":{"id":"11406","nom":"…"}}, …}
 *   UAS_MB_TEAMS_WEBHOOK (optionnel : carte « décision enregistrée »).
 */
const crypto = require("crypto");

const ACTIONS = { accept: "Accepté", refuse: "Refusé" };
const VERBE = { accept: "Accepter", refuse: "Refuser" };
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const signe = (id, a, exp) => crypto.createHmac("sha256", process.env.QA_LINK_SECRET || "").update(`${id}|${a}|${exp}`).digest("hex");

function lienValide(q) {
  const { id, a, exp, sig } = q;
  if (!process.env.QA_LINK_SECRET || !id || !ACTIONS[a] || !/^\d+$/.test(String(exp)) || !sig) return false;
  if (Number(exp) < Date.now()) return false;
  const attendu = Buffer.from(signe(id, a, exp)), recu = Buffer.from(String(sig));
  return attendu.length === recu.length && crypto.timingSafeEqual(attendu, recu);
}

function page(res, code, titre, corps, formulaire) {
  res.setHeader("content-type", "text/html; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.status(code).send(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recette</title>
<body style="font:16px/1.5 system-ui,sans-serif;background:#f6f6f8;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0">
<div style="background:#fff;border-radius:18px;box-shadow:0 10px 40px rgba(30,20,70,.12);padding:28px 32px;max-width:460px;margin:16px">
<h2 style="margin:0 0 8px;font-size:20px">${esc(titre)}</h2><div style="color:#4b4b4f">${corps}</div>${formulaire || ""}</div></body>`);
}

const jira = async (path, opts = {}) => {
  const auth = Buffer.from(`${process.env.JIRA_EMAIL}:${process.env.JIRA_TOKEN}`).toString("base64");
  const r = await fetch(`${process.env.JIRA_SITE}/rest/api/3${path}`, {
    ...opts, headers: { Authorization: `Basic ${auth}`, "Content-Type": "application/json", Accept: "application/json", ...(opts.headers || {}) },
  });
  const txt = await r.text();
  if (!r.ok) throw new Error(`Jira ${r.status} sur ${path}`);
  return txt ? JSON.parse(txt) : {};
};
const adf = t => ({ type: "doc", version: 1, content: [{ type: "paragraph", content: [{ type: "text", text: t }] }] });

module.exports = async function handler(req, res) {
  const q = req.method === "POST" ? { ...(req.query || {}), ...(req.body && typeof req.body === "object" ? req.body : {}) } : (req.query || {});
  if (!lienValide(q)) return page(res, 400, "Lien invalide ou expiré", "Ce lien n'est plus valable. Utilise la carte la plus récente.");
  const [key, env] = String(q.id).split(":");
  let wf;
  try { wf = JSON.parse(process.env.QA_WORKFLOW_JSON || "{}")[env]; } catch { wf = null; }
  if (!/^[A-Z][A-Z0-9]+-\d+$/.test(key || "") || !wf || !wf[q.a]) return page(res, 400, "Décision impossible", "Ticket ou environnement inconnu.");
  try {
    const issue = await jira(`/issue/${key}?fields=status,summary`);
    if (wf.statut && issue.fields.status.id !== String(wf.statut))
      return page(res, 200, "Ticket déjà passé à autre chose", `${esc(key)} est maintenant « ${esc(issue.fields.status.name)} » : cette carte n'est plus d'actualité.`);
    const cible = wf[q.a];
    if (req.method !== "POST") {
      const champs = ["id", "a", "exp", "sig"].map(k => `<input type="hidden" name="${k}" value="${esc(q[k])}">`).join("");
      const couleur = q.a === "accept" ? "#2b8f62" : "#c24a44";
      return page(res, 200, `${VERBE[q.a]} la recette ?`,
        `<b>${esc(key)}</b> — ${esc(issue.fields.summary)}<br><span style="font-size:14px;color:#6d727a">Environnement ${esc(env)} · le ticket passera en « ${esc(cible.nom)} ».</span>`,
        `<form method="post" style="margin-top:16px">${champs}<button style="font:600 15px system-ui;border:0;border-radius:12px;padding:11px 20px;color:#fff;background:${couleur};cursor:pointer">Confirmer : ${VERBE[q.a]}</button></form>`);
    }
    const { transitions } = await jira(`/issue/${key}/transitions`);
    const t = (transitions || []).find(x => x.to && String(x.to.id) === String(cible.id));
    if (!t) return page(res, 409, "Transition indisponible", `Jira ne permet pas de passer ${esc(key)} en « ${esc(cible.nom)} » depuis son statut actuel.`);
    await jira(`/issue/${key}/comment`, { method: "POST", body: JSON.stringify({ body: adf(`Recette ${env.toUpperCase()} : ${ACTIONS[q.a].toLowerCase()} par le PO (carte Teams). Statut → ${cible.nom}.`) }) });
    await jira(`/issue/${key}/transitions`, { method: "POST", body: JSON.stringify({ transition: { id: t.id } }) });
    if (process.env.UAS_MB_TEAMS_WEBHOOK) {
      const txt = (x, o = {}) => ({ type: "TextBlock", wrap: true, text: x, ...o });
      await fetch(process.env.UAS_MB_TEAMS_WEBHOOK, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        type: "message", attachments: [{ contentType: "application/vnd.microsoft.card.adaptive", content: { $schema: "http://adaptivecards.io/schemas/adaptive-card.json", type: "AdaptiveCard", version: "1.4",
          body: [txt(`${q.a === "accept" ? "✅ Accepté" : "❌ Refusé"} — ${key}`, { weight: "Bolder", size: "Medium" }), txt(`[${key}](${process.env.JIRA_SITE}/browse/${key}) · ${issue.fields.summary.replace(/^(\s*\[[^\]]*\]\s*)+/, "")}`), txt(`Le ticket est passé en « ${cible.nom} ».`)] } }] }) }).catch(() => {});
    }
    return page(res, 200, "Décision enregistrée", `${esc(key)} : ${ACTIONS[q.a].toLowerCase()}. Statut Jira → ${esc(cible.nom)}.`);
  } catch (e) {
    return page(res, 502, "Erreur", "La décision n'a pas pu être enregistrée. Réessaie dans un instant ou utilise Jira directement.");
  }
};
