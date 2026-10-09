const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));

let RESETS = [];
let STORED = [
  { identity: "salary:1", span: "10.01..27.01", month: "January", year: 2026, days: 20 },
  { identity: "salary:2", span: "10.02..27.02", month: "February", year: 2026, days: 20 },
];
window.call = async function (body) {
  if (body.action === "periods") return STORED;
  if (body.action === "reset") {
    RESETS.push(body);
    STORED = [];
    return { scope: "all", wiped: { months: 3, answers: 14, group_edits: 0, scoped_edits: 0 } };
  }
  if (body.action === "config") return { majors: [], limits: [], left: { slots: [], kinds: [] }, overlay: {} };
  throw new Error("unexpected action " + body.action);
};

const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));
const click = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) { if (test()) return true; await wait(10); }
  return false;
}

(async () => {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});
  VIEW = "month";

  const said = document.getElementById("wipe-said");
  const apply = document.getElementById("do-wipe");
  const gear = document.getElementById("gear");

  say("Apply is disarmed until a scope is chosen", apply.disabled);

  const all = document.querySelector('input[name=wipe][value="all"]');
  all.checked = true;
  all.dispatchEvent(new Event("change"));
  say("choosing a scope arms Apply", !apply.disabled);

  click(apply);
  say("Apply asks, with both answers on screen",
      /cannot be undone/i.test(said.textContent) && !!document.getElementById("wipe-yes")
        && !!document.getElementById("wipe-no"));

  click(gear);
  say("closing the panel takes the question away", !document.getElementById("wipe-yes")
      && said.textContent === "" && !apply.hidden, JSON.stringify(said.textContent));

  all.checked = true;
  all.dispatchEvent(new Event("change"));
  click(apply);
  click(document.getElementById("wipe-yes"));
  await until(() => RESETS.length === 1 && /Wiped|Nothing/.test(said.textContent));

  say("the wipe was sent once, for everything, with its confirmation",
      RESETS.length === 1 && RESETS[0].scope === "all" && RESETS[0].confirm === "RESET",
      JSON.stringify(RESETS));
  say("what went is said in words, and only what was there",
      said.textContent === "Wiped 3 months, 14 answers.", JSON.stringify(said.textContent));
  say("no field name from the server reaches the screen",
      !/group_edits|scoped_edits|_/.test(said.textContent), said.textContent);
  say("the message is marked as a result, not a warning", said.className === "ok");

  await until(() => !!document.querySelector(".sample"));
  say("with nothing left, the app shows its example", !!document.querySelector(".sample"));

  say("the result is still there before the panel is touched", said.textContent !== "");
  click(gear);
  say("opening or closing the panel puts the result away", said.textContent === "",
      JSON.stringify(said.textContent));

  window.call = async function (body) {
    if (body.action === "periods") return [];
    if (body.action === "reset")
      return { scope: "all", wiped: { months: 0, answers: 0, group_edits: 0, scoped_edits: 0 } };
    if (body.action === "config") return { majors: [], limits: [], left: { slots: [], kinds: [] }, overlay: {} };
    throw new Error("unexpected action " + body.action);
  };
  all.checked = true;
  all.dispatchEvent(new Event("change"));
  click(apply);
  click(document.getElementById("wipe-yes"));
  await until(() => /Nothing/.test(said.textContent));
  say("wiping an empty store says so, instead of four zeros",
      said.textContent === "Nothing to wipe.", JSON.stringify(said.textContent));

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
