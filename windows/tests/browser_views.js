const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));
const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));

let SLOW = 0;
window.call = async function (body) {
  if (body.action === "periods")
    return [{ identity: "salary:0", span: "13.06..11.07", month: "June", year: 2026, days: 30 },
            { identity: "salary:1", span: "12.07..11.08", month: "July", year: 2026, days: 27 }];
  if (body.action === "compare") {
    await wait(SLOW);
    return "                 June 2026   July 2026\nFood                   9.4        11.3\n";
  }
  if (body.action === "totals") {
    await wait(SLOW);
    return {
      span: "12.07..11.08",
      majors: [{ name: "Food", value: 11.3, limit: 12, income: false, chart: true }],
      minors: [{ name: "Market", amounts: [4500, 1200], total: 5700,
                 marks: [[{ raw: "4500 market", occurrence: 0, kind: "rule", candidates: [] }],
                         [{ raw: "1200 bakery", occurrence: 0, kind: "rule", candidates: [] }]] }],
      limits: [{ label: "Food", group: "Food", value: 12 }],
      totals: { necessary: 11.3, appended: 0, grand: 11.3 },
      appended: [], questions: 0, closed: false,
      held: [{ raw: "+ 1800 ladder, do not count refers to August", date: "09.07",
               amount: -1800, month: "August" }],
    };
  }
  if (body.action === "questions") return [];
  if (body.action === "config") return { majors: [], left: { slots: [] }, limits: [] };
  throw new Error("unexpected action " + body.action);
};

async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) { if (test()) return true; await wait(10); }
  return false;
}
const nav = (view) => document.querySelector(`nav button[data-view="${view}"]`).click();

(async () => {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});
  VIEW = "month";
  document.querySelectorAll("nav button[data-view]").forEach(b => {
    b.onclick = () => { VIEW = b.dataset.view; render(); };
  });

  await render();
  say("the month draws", !!app().querySelector(".minors"));
  say("a month with notes of its own carries no such note", !app().querySelector(".moved"));
  PERIODS[1].moved = true;
  await render();
  await until(() => app().querySelector(".minors"));
  say("a month made only of lines from other months says so, and how to fill it in",
      /Only lines written in other months/.test(app().querySelector(".moved")?.textContent || ""),
      app().querySelector(".moved")?.textContent);
  PERIODS[1].moved = false;
  const held = app().querySelector(".held");
  say("a line held for another month is listed under the minor groups, with its month",
      !!held && /Moved to another month/.test(held.textContent)
      && /\+ 1800 ladder, do not count refers to August/.test(held.textContent)
      && /→ August/.test(held.textContent) && /09\.07/.test(held.textContent),
      held ? held.textContent.replace(/\s+/g, " ") : "no .held");

  SLOW = 400;
  nav("month");
  await wait(60);
  nav("add");
  await wait(900);
  const error = /Cannot set properties|TypeError|null/.test(app().textContent);
  say("the view asked for is the one shown", !!document.getElementById("shots"),
      app().textContent.replace(/\s+/g, " ").slice(0, 160));
  say("and no error stands in its place", !error, app().textContent.replace(/\s+/g, " ").slice(0, 160));

  nav("compare");
  await wait(100);
  nav("add");
  await wait(900);
  say("leaving Compare before its table arrives keeps the view you went to",
      !!document.getElementById("shots") && !/Cannot set properties|TypeError/.test(app().textContent),
      app().textContent.replace(/\s+/g, " ").slice(0, 160));

  nav("month"); nav("add"); nav("month");
  await wait(1200);
  say("a burst of clicks ends on the last view", !!app().querySelector(".minors") && !document.getElementById("shots"));

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
