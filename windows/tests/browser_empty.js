const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));
const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));
const drop = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) { if (test()) return true; await wait(10); }
  return false;
}
const card = () => document.querySelector(".mover");

let ASKED = [];
const SAVED = [];
const STARTS = [];
const ROLE = { Salary: "salary", Savings: "savings", Refunds: "reimbursements" };
const major = (name, limit, minors, extra) => Object.assign({
  name, label: name, tier: "NECESSARY", limit, limit_label: null, income: false, fixed: null,
  minors: minors.map(n => ({ name: n, label: n, added: false, role: ROLE[n] || null })),
}, extra || {});
const config = () => ({
  majors: [
    major("Rent", null, []),
    major("Food", 30, ["Food"]),
    major("Road", 10, ["Road"]),
    major("Medicine", 8, ["Medicine"]),
    major("Refunds", null, ["Refunds"], { income: true }),
    major("Set aside", null, ["Salary", "Savings"], { tier: "EXCLUDED" }),
  ],
  limit_order: ["Food", "Road", "Medicine"],
  left: { slots: [{ id: "purse", label: "purse", place: "before", join: " ", kind: "cash" },
                  { id: "account", label: "account", place: "before", join: " ", kind: "card" }],
          kinds: ["card", "cash", "purse", "carry"] },
  words: [], overlay: {}, versions: [], closed: [],
});
const bar = (name, limit, extra) => Object.assign(
  { name, id: name, value: 0, tier: "NECESSARY", limit, income: false, chart: true }, extra || {});
const cell = (id) => ({ id, label: id, place: "before", join: " ", figure: "—",
                        text: id + " —", value: null });
const empty = () => ({
  span: "", empty: true, questions: 0, closed: false,
  majors: [bar("Rent", null), bar("Food", 30), bar("Road", 10), bar("Medicine", 8),
           bar("Refunds", null, { income: true }),
           bar("Set aside", null, { tier: "EXCLUDED", chart: false }),
           bar("Totally saved", null, { tier: "READING", saved: true }),
           bar("Totally overspent", null, { tier: "READING", overspent: true })],
  minors: ["Rent", "Food", "Road", "Medicine", "Refunds", "Withdrawal", "Salary"]
    .map(name => ({ name, amounts: [], marks: [], total: 0 })),
  limits: [{ label: "Food", group: "Food", value: 30 }, { label: "Road", group: "Road", value: 10 },
           { label: "Medicine", group: "Medicine", value: 8 }],
  totals: { necessary: 0, appended: 0, grand: 0 },
  appended: [],
  left: { raw: "", text: "Left: purse —, account —", cells: [cell("purse"), cell("account")],
          extra: 0, date: null, days_after: 0 },
});

window.call = async function (body) {
  ASKED.push(body.action);
  if (body.action === "periods") return [];
  if (body.action === "empty") return empty();
  if (body.action === "config") return config();
  if (body.action === "configure") { SAVED.push(body); return config(); }
  if (body.action === "left_value") { STARTS.push(body); return { slot: body.slot, value: body.value, start: true }; }
  throw new Error("unexpected action " + body.action);
};

(async () => {
  try {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});
  VIEW = "month";
  await render();
  await until(() => app().querySelector(".chart svg"));

  const app_ = document.getElementById("app");
  const text = app_.textContent;
  say("an empty app says what it shows",
      /this is how your month will look/i.test(app_.querySelector(".banner")?.textContent || ""),
      (app_.querySelector(".banner")?.textContent || "").slice(0, 80));
  say("the majors are drawn as bars, at the top",
      ["Rent", "Food", "Road", "Medicine", "Refunds"].every(n =>
        (app_.querySelector(".chart")?.textContent || "").includes(n)),
      (app_.querySelector(".chart")?.textContent || "").slice(0, 160));
  say("the limits sit in their own box",
      /Food\s*30/.test(app_.querySelector(".limits")?.textContent || "") &&
      /Medicine\s*8/.test(app_.querySelector(".limits")?.textContent || ""),
      app_.querySelector(".limits")?.textContent);
  say("the Total is there, at nought",
      /Total:\s*0\.0/.test(app_.querySelector(".totals")?.textContent || ""),
      app_.querySelector(".totals")?.textContent);
  const rows = [...app_.querySelectorAll(".minors .name")].map(n => n.textContent);
  say("the minor groups are listed below, empty",
      rows.join("|") === "Rent:|Food:|Road:|Medicine:|Refunds:|Withdrawal:|Salary:" &&
      [...app_.querySelectorAll(".minors .vals")].every(v => v.textContent.trim() === "—"),
      rows.join("|"));
  say("the Left line comes last, each figure a value button",
      /Left:\s*purse\s*value…,\s*account\s*value…/.test(app_.querySelector(".left")?.textContent || ""),
      app_.querySelector(".left")?.textContent);
  drop(app_.querySelector('.left [data-slot="purse"]'));
  const start = app_.querySelector(".left input");
  start.value = "5,5";
  start.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => STARTS.length === 1);
  say("a value typed on the empty app is a starting figure",
      STARTS[0] && STARTS[0].slot === "purse" && STARTS[0].value === 5.5 && !("period" in STARTS[0]),
      JSON.stringify(STARTS));
  await until(() => app().querySelector(".chart svg"));
  say("nothing of a month that is not there",
      !app_.querySelector(".lockbar") && !/unanswered/.test(text) && !/Total\b.*\+/.test(
        app_.querySelector(".totals")?.textContent || ""));
  say("the server was asked for the empty month, and never for a month's totals",
      ASKED.includes("empty") && !ASKED.includes("totals"), ASKED.join(","));
  for (const id of ["edit-majors", "edit-limits", "edit-minors", "edit-left"]) {
    say(`${id} is where a month has it`, !!app_.querySelector("#" + id));
  }

  drop(app_.querySelector("#edit-majors"));
  await until(() => card() && /Major groups/.test(card().textContent));
  say("with no months, a door opens its editor at once",
      !!card() && /Major groups/.test(card().textContent) && !/which months/i.test(card().textContent),
      card() ? card().textContent.slice(0, 80) : "no popup");
  say("and its changes are for every month", SCOPE.mode === "always", JSON.stringify(SCOPE));

  drop(card().querySelector('[data-major="Medicine"] [data-act="remove-major"]'));
  await until(() => SAVED.length === 1);
  const gone = SAVED[0] || {};
  say("Remove takes a group with its minor group, and asks nothing",
      gone.op === "remove_major" && gone.major === "Medicine" && !gone.minors_to && !gone.scope,
      JSON.stringify(gone));
  drop(card().querySelector('[data-act="done"]'));
  await until(() => !card());

  drop(document.getElementById("app").querySelector("#edit-minors"));
  await until(() => card() && /Minor groups/.test(card().textContent));
  drop(card().querySelector('[data-minor="Food"] [data-act="remove-minor"]'));
  await until(() => SAVED.length === 2);
  const minor = SAVED[1] || {};
  say("a minor group goes the same way",
      minor.op === "remove_minor" && minor.minor === "Food" && !minor.lines_to,
      JSON.stringify(minor));

  await until(() => card() && card().querySelector('[data-minor="Savings"]'));
  const savings = card().querySelector('[data-minor="Savings"]');
  say("the groups set aside are listed, with Rename and Remove but no route",
      !!savings && !!savings.querySelector('[data-act="rename-minor"]')
      && !!savings.querySelector('[data-act="remove-minor"]')
      && !savings.querySelector('[data-act="route"]')
      && /under Set aside/.test(savings.textContent), savings ? savings.outerHTML : "no Savings row");
  drop(savings.querySelector('[data-act="remove-minor"]'));
  await until(() => SAVED.length === 3);
  say("one of them is removed at once",
      SAVED[2] && SAVED[2].op === "remove_minor" && SAVED[2].minor === "Savings",
      JSON.stringify(SAVED[2]));
  await until(() => card() && card().querySelector('[data-minor="Salary"]'));
  drop(card().querySelector('[data-minor="Salary"] [data-act="remove-minor"]'));
  await wait(60);
  const sure = card().querySelector('[data-minor="Salary"] .sure');
  say("Salary asks first, and sends nothing yet",
      SAVED.length === 3 && !!sure && /holds your salary/.test(sure.textContent)
      && /Questions/.test(sure.textContent), sure ? sure.textContent : "no question");
  drop(sure.querySelector('[data-sure="no"]'));
  await wait(30);
  say("No keeps it", SAVED.length === 3 && !card().querySelector('[data-minor="Salary"] .sure')
      && !card().querySelector('[data-minor="Salary"] [data-act="remove-minor"]').hidden);
  drop(card().querySelector('[data-minor="Salary"] [data-act="remove-minor"]'));
  await wait(30);
  drop(card().querySelector('[data-minor="Salary"] [data-sure="yes"]'));
  await until(() => SAVED.length === 4);
  say("Yes removes it",
      SAVED[3] && SAVED[3].op === "remove_minor" && SAVED[3].minor === "Salary",
      JSON.stringify(SAVED[3]));
  drop(card().querySelector('[data-act="done"]'));
  await until(() => !card());

  drop(document.getElementById("app").querySelector("#edit-limits"));
  await until(() => card() && /Add a limit/.test(card().textContent));
  drop(card().querySelector('[data-major="Road"] [data-act="drop"]'));
  await until(() => SAVED.length === 5);
  const freed = SAVED[4] || {};
  say("a limit is removed at once",
      freed.op === "set_limit" && freed.major === "Road" && freed.value === null,
      JSON.stringify(freed));
  } catch (e) {
    say("the empty page is there to drive", false, (e && e.message) || String(e));
  }

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
