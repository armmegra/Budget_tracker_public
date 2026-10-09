const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));

let ANSWERED = [];
let QUESTIONS = [
  { number: 3, raw: "1800 corner shop wine", review: "alcohol - Food, or a celebration of its own?",
    candidates: ["Food", "Celebrations"] },
  { number: 7, raw: "250 tip", review: "a tip, with nothing before it saying what for",
    candidates: ["Eating out", "Market"] },
  { number: 9, raw: "640 key cutting", review: "no rule matched", candidates: [] },
];

const MONTHS = [
  { identity: "salary:1", span: "12.03..11.04", month: "March", year: 2026, days: 19 },
  { identity: "salary:2", span: "12.04..11.05", month: "April", year: 2026, days: 24 },
  { identity: "salary:3", span: "12.05..11.06", month: "May",   year: 2026, days: 17 },
  { identity: "salary:4", span: "12.06..11.07", month: "June",  year: 2026, days: 27 },
];

const TABLE = [
  "                       March 2026    April 2026      May 2026     June 2026",
  "Food                         19.6          18.9          20.2          19.2",
  "Rent                          5.8           5.8           5.8           5.8",
  "",
  "Total                        38.9          37.1          40.5          38.3",
  "Total + occasional           39.5          38.4          41.9          39.0",
  "",
  "Average of 4 months of 2026",
  "Total                        38.7",
  "Total + occasional           39.7",
].join("\n");

let CALLS = [];
window.call = async function (body) {
  CALLS.push(body);
  if (body.action === "periods") return MONTHS;
  if (body.action === "questions") return QUESTIONS;
  if (body.action === "answer") {
    ANSWERED.push(body);
    QUESTIONS = QUESTIONS.filter(q => q.number !== body.number);
    return "answered";
  }
  if (body.action === "compare") return TABLE;
  if (body.action === "export")
    return { name: "budget-compare." + body.format, format: body.format, body: "PAGE" };
  if (body.action === "totals") return { majors: [], minors: [], limits: [], appended: [],
                                         totals: { necessary: 0, appended: 0, grand: 0 } };
  if (body.action === "config") return { majors: [
    { name: "Food", label: "Food", tier: "NECESSARY", minors: [{ name: "Food", label: "Food" }] },
    { name: "Skitles", label: "Skitles", tier: "FREQUENT", limit: 5, minors: [] },
  ] };
  throw new Error("unexpected action " + body.action);
};

let CAPTURED = null;
window.download = (name, body, type) => { CAPTURED = { name, body, type }; };

const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));
const drop = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) {
    if (test()) return true;
    await wait(10);
  }
  return false;
}

(async () => {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});

  VIEW = "questions";
  await viewQuestions("June");
  await until(() => app().querySelector(".q"));

  const mark = () => document.querySelector('nav button[data-view="questions"] .qmark');
  say("questions waiting put a small red ! on the Questions button",
      !!mark() && mark().textContent === "!" && getComputedStyle(mark()).position === "absolute"
      && /3 unanswered/.test(document.querySelector('nav button[data-view="questions"]').title),
      mark() ? mark().outerHTML : "no mark");
  const kept = QUESTIONS;
  QUESTIONS = [];
  await viewQuestions("June");
  say("with none waiting, the ! goes", !mark(), mark() ? mark().outerHTML : "");
  QUESTIONS = kept;
  await viewQuestions("June");
  await until(() => app().querySelectorAll(".q").length === 3);
  const boxes = [...app().querySelectorAll(".q")];
  say("every question is drawn", boxes.length === 3, String(boxes.length));

  const wine = boxes[0];
  const offered = [...wine.querySelectorAll("button[data-group]")].map(b => b.textContent);
  say("a question that names a suspicion offers it",
      JSON.stringify(offered) === '["Food","Celebrations"]', JSON.stringify(offered));
  say("and Other is still there", !!wine.querySelector("[data-prompt]"));
  say("a question with no suspicion offers only Other",
      boxes[2].querySelectorAll("button[data-group]").length === 0 &&
      !!boxes[2].querySelector("[data-prompt]"));
  say("a tip offers the restaurant first",
      boxes[1].querySelector("button[data-group]").textContent === "Eating out");

  drop(wine.querySelector("button[data-group]"));
  await until(() => ANSWERED.length === 1);
  say("clicking a suggestion answers with it",
      ANSWERED[0].group === "Food" && ANSWERED[0].new === false,
      JSON.stringify(ANSWERED[0]));

  await until(() => app().querySelectorAll(".q").length === 2);
  const other = app().querySelectorAll(".q")[1].querySelector("[data-prompt]");
  drop(other);
  await wait();
  const field = app().querySelector(".q input[type=text]");
  say("Other opens a field, focused", !!field && document.activeElement === field);
  say("the field says Enter works", /Enter/.test(field.placeholder), field.placeholder);
  const size = parseFloat(getComputedStyle(field).fontSize);
  const body = parseFloat(getComputedStyle(document.body).fontSize);
  say("the field is two sizes up from the body text", size >= body + 2, size + " vs " + body);
  say("and wide enough for a group name",
      field.getBoundingClientRect().width >= 180,
      String(Math.round(field.getBoundingClientRect().width)));

  ANSWERED = [];
  field.value = "Lakeside";
  field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => ANSWERED.length === 1);
  say("Enter confirms what was typed",
      ANSWERED[0].group === "Lakeside" && ANSWERED[0].new === true,
      JSON.stringify(ANSWERED[0]));

  await wait(120);
  say("a second Enter does not answer the next question", ANSWERED.length === 1,
      JSON.stringify(ANSWERED.map(a => a.group)));

  const typeIn = async (name) => {
    await until(() => app().querySelector(".q [data-prompt]"));
    drop(app().querySelector(".q [data-prompt]"));
    await wait();
    const box = app().querySelector(".q input[type=text]");
    box.value = name;
    box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  };
  QUESTIONS = [
    { number: 11, raw: "2700 skittles", review: "no rule matched", candidates: [] },
    { number: 12, raw: "1100 skittles", review: "no rule matched", candidates: [] },
    { number: 13, raw: "700 skittles", review: "no rule matched", candidates: [] },
  ];
  ANSWERED = [];
  await viewQuestions("June");
  await typeIn("Skittles");
  await until(() => app().querySelector(".q .near"));
  const near = app().querySelector(".q .near");
  say("a name one letter off a group asks whether that group was meant, and sends nothing yet",
      !!near && /Did you mean Skitles\?/.test(near.textContent) && ANSWERED.length === 0,
      near ? near.textContent.replace(/\s+/g, " ") : "no question");
  drop(near.querySelector('[data-near="yes"]'));
  await until(() => ANSWERED.length === 1);
  say("Yes books it to that group",
      ANSWERED[0] && ANSWERED[0].group === "Skitles" && ANSWERED[0].new === true,
      JSON.stringify(ANSWERED[0]));
  await typeIn("Skittles");
  await until(() => app().querySelector(".q .near"));
  drop(app().querySelector('.q .near [data-near="no"]'));
  await until(() => ANSWERED.length === 2);
  say("No makes the new group as typed",
      ANSWERED[1] && ANSWERED[1].group === "Skittles" && ANSWERED[1].new === true,
      JSON.stringify(ANSWERED[1]));
  await typeIn("skitles");
  await until(() => ANSWERED.length === 3);
  say("a group's own name, in any case, asks nothing",
      ANSWERED[2] && ANSWERED[2].group === "skitles" && !app().querySelector(".q .near"),
      JSON.stringify(ANSWERED[2]));

  QUESTIONS = [{ number: 21, raw: "3600 choir fees", review: "no rule matched", candidates: [],
    occurrence: 0, date: "14.05", day: [
      ...["26 bus", "410 vegetables", "", "1975 grocer card", "26 bus", "+ 4700", "",
          "760 lemonade", "520 rolls", "45 train ticket", "", "310 bird seed",
          "1900 market"].map(text => ({ text, this: false })),
      { text: "3600 choir fees", this: true },
      { text: "Left: purse 3.1, account 41800", this: false }] }];
  await viewQuestions("June");
  await until(() => app().querySelector(".q .day"));
  const dayOf = app().querySelector(".q .day");
  const lines = dayOf.querySelector(".day-lines");
  const bold = lines.querySelector(".this");
  say("a question shows its date and its day as written, its own line in bold",
      dayOf.querySelector(".day-date").textContent === "14.05" && bold.textContent === "3600 choir fees"
      && bold.tagName === "B" && lines.children.length === 15 && /\+ 4700/.test(lines.textContent),
      dayOf.textContent.replace(/\s+/g, " "));
  say("that line is bigger than its neighbours, and underlined",
      parseFloat(getComputedStyle(bold).fontSize) > parseFloat(getComputedStyle(lines).fontSize)
      && /underline/.test(getComputedStyle(bold).textDecorationLine),
      getComputedStyle(bold).fontSize + " " + getComputedStyle(bold).textDecorationLine);
  say("the day scrolls, and opens on the line asked about",
      getComputedStyle(lines).overflowY === "auto" && lines.scrollHeight > lines.clientHeight
      && lines.scrollTop > 0 && bold.offsetTop >= lines.scrollTop
      && bold.offsetTop + bold.offsetHeight <= lines.scrollTop + lines.clientHeight,
      [lines.scrollTop, lines.clientHeight, lines.scrollHeight, bold.offsetTop].join(","));

  VIEW = "compare";
  await viewCompare(MONTHS);
  await until(() => app().querySelector("#compare-out .cmp"));

  const names = app().querySelector(".cmp .names");
  const figs = app().querySelector(".cmp .figs");
  say("the table splits into names and figures", !!names && !!figs);
  say("the names are the group names",
      names.textContent.includes("Food") && names.textContent.includes("Total + occasional"),
      JSON.stringify(names.textContent.split("\n").slice(0, 3)));
  const left = names.textContent.split("\n");
  say("no figure leaked into the names column",
      left.every(l => /^Average of /.test(l) || !/\d/.test(l)),
      JSON.stringify(left));
  say("the average heading is not cut in half",
      left.some(l => l === "Average of 4 months of 2026"), JSON.stringify(left));
  say("the figures carry the months",
      figs.textContent.includes("March 2026") && figs.textContent.includes("39.0"));
  say("the figures are the part that scrolls",
      getComputedStyle(figs).overflowX === "auto");
  say("the names stay put while it does",
      getComputedStyle(names).position === "sticky");

  const nLines = names.textContent.split("\n");
  const fLines = figs.textContent.split("\n");
  say("both columns have the same number of lines",
      nLines.length === fLines.length, `${nLines.length} vs ${fLines.length}`);
  say("the header row has no name beside it",
      nLines[0].trim() === "", JSON.stringify(nLines[0]));
  say("the header row carries the months",
      fLines[0].includes("March 2026"), JSON.stringify(fLines[0]));
  for (const [name, figure] of [["Food", "19.6"], ["Rent", "5.8"],
                                ["Total", "38.9"], ["Total + occasional", "39.5"]]) {
    const i = nLines.findIndex(l => l.trim() === name);
    say(`${name} lines up with its own figures`,
        i >= 0 && fLines[i].trim().startsWith(figure),
        `row ${i}: ${JSON.stringify(fLines[i] || "")}`);
  }

  const print = document.getElementById("print-compare");
  say("Print is offered once a table is drawn", !!print && !print.disabled);
  drop(print);
  await until(() => document.querySelector(".mover"));
  const pop = document.querySelector(".mover");
  const fmts = [...pop.querySelectorAll("button[data-fmt]")].map(b => b.dataset.fmt);
  say("it offers both formats", JSON.stringify(fmts) === '["rtf","txt"]', JSON.stringify(fmts));
  CALLS = [];
  drop(pop.querySelector('[data-fmt="txt"]'));
  await until(() => CAPTURED);
  const sent = CALLS.find(c => c.action === "export");
  const ticked = [...app().querySelectorAll(".chooser input:checked")].map(b => b.value);
  say("it prints the table on screen, not whatever is ticked now",
      sent && JSON.stringify(sent.periods) === JSON.stringify(ticked),
      sent && JSON.stringify(sent.periods) + " vs " + JSON.stringify(ticked));
  say("and it downloads what came back",
      CAPTURED.name === "budget-compare.txt" && CAPTURED.body === "PAGE");

  CALLS = [];
  drop(app().querySelector(".years button"));
  await until(() => CALLS.some(c => c.action === "compare"));
  const asked = CALLS.find(c => c.action === "compare");
  say("a year button asks by identity, never by name",
      asked.periods.every(p => p.startsWith("salary:")) &&
      new Set(asked.periods).size === asked.periods.length,
      JSON.stringify(asked.periods));
  say("and asks for the averages", asked.average === true);

  const yearTicked = [...app().querySelectorAll(".chooser input:checked")].map(b => b.value);
  const drop1 = app().querySelector(`.chooser input[value="${yearTicked[yearTicked.length - 1]}"]`);
  drop1.checked = false;
  drop1.dispatchEvent(new Event("change"));
  CALLS = [];
  drop(document.getElementById("do-average"));
  await until(() => CALLS.some(c => c.action === "compare"));
  const avg = CALLS.find(c => c.action === "compare");
  say("Average asks for exactly the months still ticked",
      JSON.stringify(avg.periods) === JSON.stringify(yearTicked.slice(0, -1)),
      JSON.stringify(avg.periods) + " vs " + JSON.stringify(yearTicked.slice(0, -1)));
  say("as an average, not a comparison", avg.average === true);
  CALLS = []; CAPTURED = null;
  drop(document.getElementById("print-compare"));
  await until(() => document.querySelector(".mover"));
  drop(document.querySelector('.mover [data-fmt="txt"]'));
  await until(() => CAPTURED);
  const printed = CALLS.find(c => c.action === "export");
  say("Print then prints that average, over those months",
      printed && printed.average === true
        && JSON.stringify(printed.periods) === JSON.stringify(avg.periods),
      printed && JSON.stringify([printed.average, printed.periods]));
  app().querySelectorAll(".chooser input").forEach(b => {
    b.checked = false; b.dispatchEvent(new Event("change"));
  });
  drop(document.getElementById("do-average"));
  await wait(60);
  say("with nothing ticked it refuses rather than asking the server",
      /no months|tick/i.test(document.getElementById("compare-said").textContent),
      document.getElementById("compare-said").textContent);

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
