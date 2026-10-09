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
  minors: minors.map(([n, l, own]) => ({ name: n, label: l || n, added: !!own })),
}, extra || {});
const config = () => ({
  majors: ONLY_ONE ? [
    major("Food", "Groceries", null, [["Food", "Groceries"]]),
    major("Refunds", "Refunds", null, [["Refunds"]], { income: true }),
  ] : [
    major("Rent", "Rent", null, []),
    major("Food", "Groceries", 30, [["Food", "Groceries"], ["Bakery", "Bakery", true]]),
    major("Road", "Road", 10, [["Road"]]),
    major("Medicine", "Medicine", null, [["Medicine"]]),
    major("Refunds", "Refunds", null, [["Refunds"]], { income: true }),
  ],
  limit_order: ["Food", "Road"],
  left: { slots: [
    { id: "purse", label: "cash", kind: "cash", place: "before", join: " " },
    { id: "account", label: "account", kind: "card", place: "before", join: " " },
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
  if (mode) {
    await until(() => card() && /which months/i.test(card().textContent));
    const scope = card().querySelector(`input[name=scope][value="${mode}"]`);
    if (!scope.checked) {
      scope.checked = true;
      scope.dispatchEvent(new Event("change"));
    }
    drop(card().querySelector(`[data-go="${target}"]`));
  }
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

  configMenu(document.body, "majors");
  await until(() => card() && /which months/i.test(card().textContent));
  const answers = [...card().querySelectorAll("input[name=scope]")].map(r => r.value);
  say("it offers this month on, and every month - nothing else",
      answers.join(",") === "onward,always", answers.join(","));
  say("this month on is chosen unless another is picked",
      card().querySelector("input[name=scope][value=onward]").checked &&
      SCOPE.mode === "onward" && SCOPE.name === "March", JSON.stringify(SCOPE));
  say("every month warns that earlier months are counted again",
      /earlier months are counted again/i.test(card().textContent), card().textContent.slice(0, 300));
  drop(card().querySelector("[data-cancel]"));
  await until(() => !card());

  await openEditor("majors", /Major groups/, "always");
  const remove = card().querySelector('[data-major="Food"] [data-act="remove-major"]');
  say("Remove is offered on a group that holds minor groups", !!remove);
  say("the help says where their lines go", /go to Questions/.test(card().textContent),
      card().textContent.slice(0, 300));
  drop(remove);
  await until(() => SAVED.length === 1);
  const gone = SAVED[0] || {};
  say("it is removed at once, its minor groups with it, and nothing is asked",
      gone.op === "remove_major" && gone.major === "Food" && !gone.minors_to && !gone.scope &&
      !card().querySelector('[data-major="Food"] select'),
      JSON.stringify(gone));
  await close();

  ONLY_ONE = true;
  await openEditor("majors", /Major groups/, "always");
  say("the last group spending can go to has no Remove",
      !card().querySelector('[data-major="Food"] [data-act="remove-major"]') &&
      !!card().querySelector('[data-major="Refunds"] [data-act="remove-major"]'));
  await close();
  ONLY_ONE = false;

  SCOPE = { mode: "onward", period: "March 2026", name: "March" };
  STAGED = [{ op: "rename_major", major: "Road", name: "Transport" }];
  await openEditor("limits", /Add a limit/);
  say("a limit's editor opens at once, with no question",
      !/which months/i.test(card().textContent) && !card().querySelector("ol.staged"));
  drop(card().querySelector('[data-major="Road"] [data-act="drop"]'));
  await until(() => SAVED.length === 2);
  const freed = SAVED[1] || {};
  say("and a limit is removed straight away, for every month",
      freed.op === "set_limit" && freed.major === "Road" && freed.value === null && !freed.scope,
      JSON.stringify(freed));
  say("the group changes staged for March on are left as they were",
      SCOPE.mode === "onward" && STAGED.length === 1, JSON.stringify(STAGED));
  STAGED = [];

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
  say("a boxed name alone chooses no group", SAVED.length === 2 && /Pick a group/.test(said()), said());
  await add("medicine", "10");
  await until(() => SAVED.length === 3);
  const set = SAVED[2] || {};
  say("a name typed that is a group's - in any case - is that group",
      set.op === "set_limit" && set.major === "Medicine" && set.value === 10, JSON.stringify(set));
  pick().value = "Rent";
  await add("Road", "10");
  say("a group chosen and another typed: keep one",
      SAVED.length === 3 && /You chose Rent and typed Road/.test(said()), said());
  pick().value = "";
  await add("Road", "5");
  say("a group that has a limit is sent to its Value",
      SAVED.length === 3 && /Road already has a limit/.test(said()), said());
  await add("Kayak club", "4");
  await until(() => SAVED.length === 4);
  const fresh = SAVED[3] || {};
  say("a new name makes the group with its limit",
      fresh.op === "add_major" && fresh.name === "Kayak club" && fresh.limit === 4,
      JSON.stringify(fresh));
  await close();

  await openEditor("majors", /Major groups/, "onward");
  drop(card().querySelector('[data-major="Food"] [data-act="remove-major"]'));
  await until(() => card().querySelector("ol.staged"));
  const listed = (card().querySelector("ol.staged") || {}).textContent || "";
  say("a staged removal reads with the shown name",
      /remove the group Groceries/.test(listed) && SAVED.length === 4, listed);
  drop(card().querySelector("[data-staged=discard]"));
  await until(() => !card().querySelector("ol.staged"));
  await close();

  await openEditor("minors", /Minor groups/, "always");
  say("the help says where its lines go", /go\s+to Questions/.test(card().textContent),
      card().textContent.slice(0, 300));
  drop(card().querySelector('[data-minor="Food"] [data-act="remove-minor"]'));
  await until(() => SAVED.length === 5);
  const minor = SAVED[4] || {};
  say("a minor group the rules write into is removed at once, nothing asked",
      minor.op === "remove_minor" && minor.minor === "Food" && !minor.lines_to &&
      !card().querySelector('[data-minor="Food"] select:not([data-act])'),
      JSON.stringify(minor));
  drop(card().querySelector('[data-minor="Bakery"] [data-act="remove-minor"]'));
  await until(() => SAVED.length === 6);
  const own = SAVED[5] || {};
  say("one added by hand goes the same way",
      own.op === "remove_minor" && own.minor === "Bakery" && !own.lines_to,
      JSON.stringify(own));
  await close();

  await openEditor("left", /The Left line/, "onward");
  drop(card().querySelector('[data-slot="account"] [data-act="side"]'));
  await until(() => card().querySelector("ol.staged"));
  drop(card().querySelector('[data-slot="purse"] [data-act="drop"]'));
  await until(() => card().querySelectorAll("ol.staged li").length === 2);
  const left = [...card().querySelectorAll("ol.staged li")].map(li => li.textContent);
  say("moving a name to the other side reads as a move, not a rename",
      left[0] === "account: its name after the figure",
      left.join(" | ") || (card() ? card().textContent.slice(0, 300) : "no card"));
  say("a renamed figure is named as shown",
      left[1] === "remove cash from the Left line", left.join(" | "));

  } catch (e) {
    say("the setup editors are there to drive", false, (e && e.message) || String(e));
  }
  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
