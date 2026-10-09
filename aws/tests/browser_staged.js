const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));
const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));
const drop = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) { if (test()) return true; await wait(10); }
  return false;
}
const card = () => document.querySelector(".mover");
const said = () => ((card() && card().querySelector(".said")) || {}).textContent || "";

let LIMITS = { Pantry: 24, Cat: 3 };
let WORDS = [];
const PREVIEWS = [];
const APPLIED = [];
const SAVED = [];
const config = () => ({
  majors: [
    { name: "Pantry", label: "Pantry", tier: "NECESSARY", limit: LIMITS.Pantry, limit_label: null,
      income: false, fixed: null, minors: [{ name: "Pantry", label: "Pantry" }] },
    { name: "Cat", label: "Cat", tier: "NECESSARY", limit: LIMITS.Cat, limit_label: null,
      income: false, fixed: null, minors: [{ name: "Cat", label: "Cat" }, { name: "Vet", label: "Vet" }] },
    { name: "Lido", label: "Lido", tier: "NECESSARY", limit: null, limit_label: null,
      income: false, fixed: null, minors: [{ name: "Lido", label: "Lido" }] },
  ],
  limit_order: ["Pantry", "Cat"],
  left: { slots: [], kinds: ["card", "cash", "purse", "carry"] },
  words: WORDS,
  overlay: {}, versions: [], closed: [],
});

window.call = async function (body) {
  if (body.action === "periods")
    return [{ identity: "salary:3", span: "10.03..27.03", month: "March", year: 2026, days: 18 }];
  if (body.action === "config") return config();
  if (body.action === "configure") {
    if (!body.ops) { SAVED.push(body); return config(); }
    if (!body.confirm) {
      PREVIEWS.push(body);
      return { pending: true, scope: body.scope, from: "March 2026",
               months: ["March 2026"], ops: body.ops };
    }
    APPLIED.push(body);
    body.ops.forEach(o => { if (o.op === "set_limit") LIMITS[o.major] = o.value; });
    return Object.assign(config(), { applied: { scope: body.scope, months: ["March 2026"] } });
  }
  throw new Error("unexpected action " + body.action);
};

async function openEditor(target, heading) {
  configMenu(document.body, target);
  await until(() => card() && /which months/i.test(card().textContent));
  const month = card().querySelector('input[name=scope][value="month"]');
  if (!month.checked) {
    month.checked = true;
    month.dispatchEvent(new Event("change"));
  }
  drop(card().querySelector(`[data-go="${target}"]`));
  await until(() => card() && heading.test(card().textContent));
}

(async () => {
  try {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});

  await openEditor("limits", /Pantry/);
  say("a month-only scope is chosen", SCOPE.mode === "month" && SCOPE.name === "March",
      JSON.stringify(SCOPE));
  drop(card().querySelector('[data-major="Pantry"] [data-act="value"]'));
  const field = card().querySelector(".erow input[type=text]:not([id])");
  field.value = "26";
  drop(field.parentElement.querySelector("[data-go]"));
  await until(() => card().querySelector("ol.staged"));
  say("the change is staged, not saved",
      /Pantry to 26/.test(card().querySelector("ol.staged").textContent) && SAVED.length === 0,
      card().querySelector("ol.staged") && card().querySelector("ol.staged").textContent);

  drop(card().querySelector("[data-staged=apply]"));
  await until(() => card().querySelector("[data-go=yes]"));
  say("Apply asks which months, and names them",
      PREVIEWS.length === 1 && /March 2026/.test(said()), said());
  drop(card().querySelector("[data-go=yes]"));
  await until(() => APPLIED.length === 1);
  const sent = APPLIED[0] || {};
  say("Yes sends the one staged change for that month",
      sent.scope === "month" && sent.period === "March" && sent.confirm === true &&
      sent.ops.length === 1 && sent.ops[0].op === "set_limit" &&
      sent.ops[0].major === "Pantry" && sent.ops[0].value === 26,
      JSON.stringify(sent));
  await until(() => !card().querySelector("ol.staged"));
  say("and the staged list is empty afterwards", !card().querySelector("ol.staged"));

  await openEditor("words", /Words you teach/);
  card().querySelector("#new-word").value = "grocer";
  card().querySelector("#new-word-group").value = "Pantry";
  drop(card().querySelector('[data-act="teach"]'));
  await until(() => card().querySelector("ol.staged"));
  say("a word is staged too", !!card().querySelector("ol.staged") && SAVED.length === 0);
  drop(card().querySelector("[data-staged=apply]"));
  await until(() => card().querySelector("[data-go=no]"));
  say("its Apply previews, instead of checking the word box",
      PREVIEWS.length === 2 && /March 2026/.test(said()) && !/three letters/i.test(said()), said());
  drop(card().querySelector("[data-go=no]"));
  drop(card().querySelector("[data-staged=discard]"));
  await until(() => !card().querySelector("ol.staged"));
  say("Discard empties the list and sends nothing",
      !card().querySelector("ol.staged") && APPLIED.length === 1 && SAVED.length === 0);

  } catch (e) {
    say("the staged editors are there to drive", false, (e && e.message) || String(e));
  }
  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
