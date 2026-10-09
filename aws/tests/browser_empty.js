const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));

let ASKED = [];
window.call = async function (body) {
  ASKED.push(body.action);
  if (body.action === "periods") return [];
  if (body.action === "config") return {
    majors: [
      { name: "Food", label: "Food", tier: "NECESSARY", limit: 200,
        minors: [{ name: "groceries", label: "groceries" }] },
      { name: "Transport", label: "Transport", tier: "NECESSARY", limit: 50,
        minors: [{ name: "fuel", label: "fuel" }] },
    ],
    limits: [{ group: "Food", label: "Food", value: 200 }],
    left: { slots: [{ id: "card", label: "", place: "before", join: " ", kind: "card" }],
            kinds: ["card", "cash", "purse", "carry"],
            start: { raw: "", text: "Left: —", extra: 0, date: null, days_after: 0,
                     cells: [{ id: "card", label: "", place: "before", join: " ",
                               figure: "—", value: null }] } },
    overlay: {},
  };
  if (body.action === "left_value") { STARTS.push(body); return { slot: body.slot, value: body.value, start: true }; }
  throw new Error("unexpected action " + body.action);
};
const STARTS = [];

const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));
const drop = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) { if (test()) return true; await wait(10); }
  return false;
}

(async () => {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});
  VIEW = "month";
  await render();

  const app = document.getElementById("app");

  say("an empty app draws an example, not an empty page",
      !!app.querySelector(".sample"), app.innerHTML.slice(0, 80));
  say("and says so in a banner",
      /this is an example/i.test(app.querySelector(".banner")?.textContent || ""));
  say("the server was never asked for a month it does not have",
      !ASKED.includes("totals"), ASKED.join(","));

  for (const id of ["edit-majors", "edit-limits", "edit-minors", "edit-left"]) {
    say(`${id} is present on the example`, !!app.querySelector("#" + id));
  }

  say("the chart is painted", (app.querySelector(".chart")?.innerHTML || "").includes("<svg"));

  const startBtn = app.querySelector('.banner .left [data-slot="card"]');
  say("the banner offers the starting figures, each a value button",
      /Where your money stands now/.test(app.querySelector(".banner")?.textContent || "") &&
      startBtn?.tagName === "BUTTON", app.querySelector(".banner .left")?.outerHTML);
  drop(startBtn);
  const startField = app.querySelector(".banner .left input");
  startField.value = "5,5";
  startField.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => STARTS.length === 1);
  say("a value typed there is a starting figure, for no month",
      STARTS[0] && STARTS[0].slot === "card" && STARTS[0].value === 5.5 && !("period" in STARTS[0]),
      JSON.stringify(STARTS));

  const tierOne = SAMPLE.majors
    .filter(m => m.limit !== null && !m.saved && !m.overspent)
    .reduce((n, m) => n + m.value, 0);
  say("the first Total is the sum of the limited groups",
      Math.abs(tierOne - SAMPLE.totals.necessary) < 0.05,
      `${tierOne.toFixed(1)} vs ${SAMPLE.totals.necessary}`);
  say("the second Total is the first plus the unlimited one",
      Math.abs(SAMPLE.totals.necessary + SAMPLE.totals.appended - SAMPLE.totals.grand) < 0.05);
  const saved = SAMPLE.majors
    .filter(m => m.limit && m.value < m.limit)
    .reduce((n, m) => n + (m.limit - m.value), 0);
  const over = SAMPLE.majors
    .filter(m => m.limit && m.value > m.limit)
    .reduce((n, m) => n + (m.value - m.limit), 0);
  const savedRow = SAMPLE.majors.find(m => m.saved).value;
  const overRow = SAMPLE.majors.find(m => m.overspent).value;
  say("Totally saved is the room under every limit",
      Math.abs(saved - savedRow) < 0.05, `${saved.toFixed(1)} vs ${savedRow}`);
  say("Totally overspent is the distance past every limit",
      Math.abs(over - overRow) < 0.05, `${over.toFixed(1)} vs ${overRow}`);

  const sum = xs => xs.reduce((n, x) => n + x, 0);
  const wrong = SAMPLE.minors.filter(m => sum(m.amounts) !== m.total);
  say("every group's figures sum to its own total", wrong.length === 0,
      wrong.map(m => `${m.name}: ${sum(m.amounts)} vs ${m.total}`).join("; "));
  say("and the groups together sum to the second Total",
      sum(SAMPLE.minors.map(m => m.total)) === Math.round(SAMPLE.totals.grand * 1000),
      `${sum(SAMPLE.minors.map(m => m.total))} vs ${SAMPLE.totals.grand * 1000}`);
  const many = SAMPLE.minors.filter(m => m.amounts.length >= 5).length;
  const short = SAMPLE.minors.filter(m => m.amounts.length < 5).map(m => m.name);
  say("the groups that are purchases run long, as a real month does",
      many >= 8, `${many} of ${SAMPLE.minors.length} long; short: ${short.join(", ")}`);
  say("and only bills are short",
      short.every(n => ["rent", "water", "broadband", "insurance"].includes(n)),
      short.join(", "));
  say("the whole month is fifty figures or more",
      sum(SAMPLE.minors.map(m => m.amounts.length)) >= 50,
      String(sum(SAMPLE.minors.map(m => m.amounts.length))));
  say("the rows are drawn with all of them",
      (app.querySelector(".minors")?.textContent || "").includes("1375"));

  app.querySelector("#edit-majors").click();
  await wait(60);
  const pop = document.querySelector(".mover");
  say("a door opens the which-months question first",
      /which months/i.test(pop ? pop.textContent : ""),
      pop ? pop.textContent.slice(0, 60) : "no popup");
  say("and offers the editor it belongs to",
      /major groups/i.test(pop && pop.querySelector("[data-go]")
        ? pop.querySelector("[data-go]").textContent : ""));

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
