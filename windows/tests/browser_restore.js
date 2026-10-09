const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));

const SIX = ["January", "February", "March", "April", "May", "June"].map((month, i) =>
  ({ identity: "salary:" + (i + 1), span: "x", month, year: 2026, days: 27 }));
const sel = () => document.getElementById("period");
const fresh = () => { sel().innerHTML = ""; };

(async () => {
  try { localStorage.clear(); } catch (e) { say("localStorage is usable in the harness", false, String(e)); }

  fresh(); PERIODS = SIX; fillPeriods();
  say("a fresh page opens on the NEWEST month",
      sel().value === "June", `opened on ${sel().value}`);

  localStorage.setItem("budget-period", "March");
  fresh(); PERIODS = SIX; fillPeriods();
  say("an old remembered month does not win over the newest",
      sel().value === "June", `opened on ${sel().value}`);

  fresh(); PERIODS = SIX.slice(0, 3); fillPeriods();
  say("with fewer months, the newest of them",
      sel().value === "March", `opened on ${sel().value}`);

  fresh(); PERIODS = SIX; fillPeriods();
  sel().value = "April";
  PERIODS = SIX; fillPeriods();
  say("refilling during a session keeps the month on screen",
      sel().value === "April", `now on ${sel().value}`);

  sel().value = "April";
  PERIODS = SIX.filter(p => p.month !== "April");
  fillPeriods();
  say("if the month on screen disappears, the newest takes over",
      sel().value === "June", `now on ${sel().value}`);

  remember("view", "questions");
  say("remember() writes where remembered() reads",
      remembered("view") === "questions", String(remembered("view")));

  fresh(); PERIODS = []; fillPeriods();
  say("an empty store leaves the select empty rather than throwing",
      sel().value === "" && sel().options.length === 0);

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
