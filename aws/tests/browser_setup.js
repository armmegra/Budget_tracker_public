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

let ONLY_ONE = false;
const SAVED = [];
const major = (name, label, limit, minors, extra) => Object.assign({
  name, label, tier: "NECESSARY", limit, limit_label: null, income: false, fixed: null,
  minors: minors.map(([n, l]) => ({ name: n, label: l || n })),
}, extra || {});
const config = () => ({
  majors: ONLY_ONE ? [
    major("Pantry", "Road", null, [["Pantry", "Road"]]),
    major("Rebates", "Rebates", null, [["Rebates"]], { income: true }),
  ] : [
    major("Pantry", "Road", null, [["Pantry", "Road"]]),
    major("Utilities", "Food", 7, [["Heating"], ["Fibre"], ["SIM plan"], ["Bins"]]),
    major("Health", "Health", 2, [["Physio"], ["Dentist"]]),
    major("Lido", "Lido", null, [["Lido"]]),
    major("Rebates", "Rebates", null, [["Rebates"]], { income: true }),
  ],
  limit_order: ["Utilities", "Health"],
  left: { slots: [
    { id: "wallet", label: "purse", kind: "cash", place: "before", join: " " },
    { id: "debit", label: "debit", kind: "card", place: "before", join: " " },
  ], kinds: ["card", "cash", "purse", "carry"] },
  words: [],
  overlay: {}, versions: [], closed: [],
});

window.call = async function (body) {
  if (body.action === "periods")
    return [{ identity: "salary:3", span: "10.03..27.03", month: "March", year: 2026, days: 18 }];
  if (body.action === "config") return config();
  if (body.action === "configure") {
    if (!body.ops) { SAVED.push(body); return config(); }
    return { pending: true, scope: body.scope, from: "March 2026",
             months: ["March 2026"], ops: body.ops };
  }
  throw new Error("unexpected action " + body.action);
};

async function openEditor(target, heading, mode) {
  configMenu(document.body, target);
  await until(() => card() && /which months/i.test(card().textContent));
  const scope = card().querySelector(`input[name=scope][value="${mode}"]`);
  if (!scope.checked) {
    scope.checked = true;
    scope.dispatchEvent(new Event("change"));
  }
  drop(card().querySelector(`[data-go="${target}"]`));
  await until(() => card() && heading.test(card().textContent));
}

const close = async () => {
  drop(card() && card().querySelector('[data-act="done"]'));
  await until(() => !card());
};

(async () => {
  try {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});

  await openEditor("majors", /Major groups/, "always");
  const remove = card().querySelector('[data-major="Utilities"] [data-act="remove-major"]');
  say("Remove is offered on a group that holds minor groups", !!remove);
  drop(remove);
  await until(() => card().querySelector('[data-major="Utilities"] select'));
  const where = card().querySelector('[data-major="Utilities"] select');
  const offered = where ? [...where.options].map(o => o.textContent) : [];
  say("it asks where its minor groups go, naming them",
      !!where && /Heating, Fibre, SIM plan, Bins/.test(said()), said());
  say("only among groups counted the same way",
      offered.includes("Road") && offered.includes("Health") && !offered.includes("Rebates") &&
      !offered.includes("Food"), offered.join(" | "));
  where.value = "Health";
  where.dispatchEvent(new Event("change"));
  await until(() => SAVED.length === 1);
  const gone = SAVED[0] || {};
  say("choosing sends the removal with the move",
      gone.op === "remove_major" && gone.major === "Utilities" && gone.minors_to === "Health",
      JSON.stringify(gone));
  await close();

  ONLY_ONE = true;
  await openEditor("majors", /Major groups/, "always");
  say("the last group spending can go to has no Remove",
      !card().querySelector('[data-major="Pantry"] [data-act="remove-major"]') &&
      !!card().querySelector('[data-major="Rebates"] [data-act="remove-major"]'));
  await close();
  ONLY_ONE = false;

  await openEditor("limits", /Add a limit/, "always");
  const pick = () => card().querySelector("#new-limit-major");
  say("the group list starts on Choose a group…",
      pick().value === "" && pick().selectedIndex === 0 &&
      /Choose a group/.test(pick().options[0].textContent),
      pick().options[pick().selectedIndex].textContent);
  const add = async (name, value, label) => {
    card().querySelector("#new-limit-name").value = name;
    card().querySelector("#new-limit-value").value = value;
    card().querySelector("#new-limit-label").value = label || "";
    drop(card().querySelector('[data-act="add"]'));
    await wait(60);
  };
  await add("", "10", "Road");
  say("a boxed name alone chooses no group", SAVED.length === 1 && /Pick a group/.test(said()), said());
  await add("road", "10");
  await until(() => SAVED.length === 2);
  const set = SAVED[1] || {};
  say("a name typed that is a group's - in any case - is that group",
      set.op === "set_limit" && set.major === "Pantry" && set.value === 10, JSON.stringify(set));
  pick().value = "Lido";
  await add("Road", "10");
  say("a group chosen and another typed: keep one",
      SAVED.length === 2 && /You chose Lido and typed Road/.test(said()), said());
  pick().value = "";
  await add("Health", "5");
  say("a group that has a limit is sent to its Value",
      SAVED.length === 2 && /Health already has a limit/.test(said()), said());
  await add("Kayak club", "4");
  await until(() => SAVED.length === 3);
  const fresh = SAVED[2] || {};
  say("a new name makes the group with its limit",
      fresh.op === "add_major" && fresh.name === "Kayak club" && fresh.limit === 4,
      JSON.stringify(fresh));
  await close();

  await openEditor("majors", /Major groups/, "month");
  drop(card().querySelector('[data-major="Utilities"] [data-act="remove-major"]'));
  await until(() => card().querySelector('[data-major="Utilities"] select'));
  const move = card().querySelector('[data-major="Utilities"] select');
  move.value = "Pantry";
  move.dispatchEvent(new Event("change"));
  await until(() => card().querySelector("ol.staged"));
  const listed = (card().querySelector("ol.staged") || {}).textContent || "";
  say("a staged removal reads with the shown names",
      /remove the group Food, its minor groups to Road/.test(listed) && SAVED.length === 3, listed);
  drop(card().querySelector("[data-staged=discard]"));
  await until(() => !card().querySelector("ol.staged"));
  await close();

  await openEditor("left", /The Left line/, "month");
  drop(card().querySelector('[data-slot="debit"] [data-act="side"]'));
  await until(() => card().querySelector("ol.staged"));
  drop(card().querySelector('[data-slot="wallet"] [data-act="drop"]'));
  await until(() => card().querySelectorAll("ol.staged li").length === 2);
  const left = [...card().querySelectorAll("ol.staged li")].map(li => li.textContent);
  say("moving a name to the other side reads as a move, not a rename",
      left[0] === "debit: its name after the figure",
      left.join(" | ") || (card() ? card().textContent.slice(0, 300) : "no card"));
  say("a renamed figure is named as shown",
      left[1] === "remove purse from the Left line", left.join(" | "));

  } catch (e) {
    say("the setup editors are there to drive", false, (e && e.message) || String(e));
  }
  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
