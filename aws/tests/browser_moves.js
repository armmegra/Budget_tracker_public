const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));

const mark = (raw, occurrence, kind, candidates) =>
  [{ raw, occurrence, kind, candidates: candidates || [], date: "09.09" }];

let MOVES = [];
let UNANSWERS = [];
let ANSWERS = [];
window.call = async function (body) {
  if (body.action === "periods")
    return [{ identity: "salary:1", span: "12.07..11.08", month: "July", year: 2026, days: 27 }];
  if (body.action === "move") { MOVES.push(body); return { moved: body.group }; }
  if (body.action === "unanswer") { UNANSWERS.push(body); return { removed: 1 }; }
  if (body.action === "questions")
    return [{ number: 9, raw: "1900 boat hire", occurrence: 0,
              candidates: ["Hobbies", "Days out"] }];
  if (body.action === "answer") { ANSWERS.push(body); return "answered"; }
  if (body.action === "day") {
    (window.DAYS = window.DAYS || []).push(body);
    return [{ date: "09.09", lines: [
      { text: "300 bread", this: false }, { text: "", this: false },
      ...body.entries.map(e => ({ text: e.raw, this: true })),
      { text: "Left: 61240, 6.8", this: false }] }];
  }
  if (body.action === "left_value") { LEFTS.push(body); return { slot: body.slot, value: body.value }; }
  if (body.action === "totals") return {
    span: "12.07..11.08",
    majors: [
      { name: "Food", value: 13.8, limit: 12, income: false, chart: true },
      { name: "Parcels", value: 2.1, limit: null, income: false, chart: true },
    ],
    minors: [
      { name: "Parcels", amounts: [1260, 870], total: 2130,
        marks: [mark("1260 plant food card", 0, "rule"),
                mark("870 door mat parcel", 0, "rule", ["Parcels"])] },
      { name: "Home", amounts: [2150], total: 2150,
        marks: [mark("2150 bookshelf", 0, "moved")] },
      { name: "Hobbies", amounts: [1900], total: 1900,
        marks: [mark("1900 boat hire", 0, "answered", ["Hobbies", "Days out"])] },
      { name: "Radio", amounts: [930], total: 930,
        marks: [mark("930 parcel radio", 0, "answered")] },
    ],
    limits: [{ label: "Food", group: "Food", value: 12 }],
    totals: { necessary: 13.8, appended: 2.1, grand: 15.9 },
    appended: [],
    questions: 0,
    closed: false,
    left: { raw: "Left: card 61240, 6.8 cash", text: "Left: card 50000, 6.8 cash, — box",
            extra: 0, date: "11.08", days_after: 0, cells: [
      { id: "card", label: "card", place: "before", join: " ", figure: "50000",
        value: 50000, set: true, noted: "61240" },
      { id: "cash", label: "cash", place: "after", join: " ", figure: "6.8", value: 6.8 },
      { id: "box", label: "box", place: "after", join: " ", figure: "—", value: null },
    ] },
  };
  throw new Error("unexpected action " + body.action);
};
const LEFTS = [];

const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));
const drop = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) {
    if (test()) return true;
    await wait(10);
  }
  return false;
}
const pop = () => document.querySelector(".mover");

(async () => {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});
  VIEW = "month";
  await render();
  await until(() => app().querySelector(".minors"));

  const cells = kind => [...app().querySelectorAll("." + kind)];
  say("a rule-placed figure is clickable", cells("plcd").length === 2,
      String(cells("plcd").length));
  say("a moved figure wears the mark", cells("movd").length === 1);
  say("an answered figure still dims", cells("ansd").length === 2,
      String(cells("ansd").length));

  drop(cells("plcd")[1]);
  await until(() => pop());
  say("clicking it opens the move popup", !!pop());
  say("it shows the line it will move", pop().textContent.includes("870 door mat parcel"));
  await until(() => pop().querySelector(".day"));
  const day = pop().querySelector(".day");
  const asked = (window.DAYS || [])[0];
  say("and the day that line was written on, as written, the line in bold",
      !!day && day.querySelector(".day-date")?.textContent === "09.09"
      && !!asked && day.querySelector(".this")?.textContent === asked.entries[0].raw
      && /300 bread/.test(day.textContent) && /Left: 61240/.test(day.textContent),
      day ? day.textContent.replace(/\s+/g, " ") : pop().innerHTML);
  say("asked for with the figure's own marks",
      !!asked && pop().textContent.includes(asked.entries[0].raw)
      && asked.entries[0].occurrence === 0 && asked.period === "July",
      JSON.stringify(asked));
  drop(pop().querySelector("[data-prompt]"));
  await wait();
  const field = pop().querySelector("input");
  field.value = "Decorating";
  field.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => MOVES.length === 1);
  say("it calls move, not answer",
      MOVES.length === 1 && ANSWERS.length === 0 && UNANSWERS.length === 0,
      JSON.stringify(MOVES));
  say("with the entry's own key and the typed group",
      MOVES[0].raw === "870 door mat parcel" && MOVES[0].occurrence === 0 &&
      MOVES[0].group === "Decorating" && MOVES[0].new === true);

  await until(() => !pop() && app().querySelector(".movd"));
  MOVES = [];
  drop(app().querySelector(".movd"));
  await until(() => pop());
  const lift = pop().querySelector("[data-lift]");
  say("a moved figure offers Put it back", !!lift);
  drop(lift);
  await until(() => MOVES.length === 1);
  say("putting back sends group null",
      MOVES[0].raw === "2150 bookshelf" && MOVES[0].group === null,
      JSON.stringify(MOVES));

  await until(() => !pop() && app().querySelector(".ansd"));
  MOVES = [];
  drop(app().querySelector(".ansd"));
  await until(() => pop());
  say("its popup offers the question's own buttons",
      !!pop().querySelector('[data-group="Days out"]'));
  say("and no Put it back - it is an answer, not a move",
      !pop().querySelector("[data-lift]"));
  drop(pop().querySelector('[data-group="Days out"]'));
  await until(() => ANSWERS.length === 1);
  say("it re-answers rather than moving",
      UNANSWERS.length === 1 && ANSWERS[0].group === "Days out" && MOVES.length === 0,
      JSON.stringify({ un: UNANSWERS.length, ans: ANSWERS }));

  await until(() => !pop() && app().querySelector(".ansd"));
  await wait(80);
  MOVES = []; ANSWERS = []; UNANSWERS = [];
  const again = cells("ansd").find(el =>
    decodeURIComponent(el.dataset.src).includes("930 parcel radio"));
  drop(again);
  await until(() => pop());
  drop(pop().querySelector("[data-prompt]"));
  await wait();
  const typed = pop().querySelector("input");
  typed.value = "Audio";
  typed.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => MOVES.length === 1);
  say("with no question to answer, it moves the line instead",
      UNANSWERS.length === 1 && ANSWERS.length === 0 && MOVES.length === 1,
      JSON.stringify({ un: UNANSWERS, ans: ANSWERS, mv: MOVES }));
  say("to the group chosen, under the line's own key",
      MOVES[0] && MOVES[0].raw === "930 parcel radio" && MOVES[0].occurrence === 0 &&
      MOVES[0].group === "Audio" && MOVES[0].new === true,
      JSON.stringify(MOVES));

  VIEW = "month";
  await render();
  await until(() => document.querySelector(".left [data-slot]"));
  const leftOf = slot => document.querySelector(`.left [data-slot="${slot}"]`);
  say("a Left figure the notes give is clickable",
      leftOf("cash")?.classList.contains("lfig") && leftOf("cash").textContent === "6.8",
      leftOf("cash")?.outerHTML);
  say("one typed by hand wears the Totals' mark and says what the notes make it",
      leftOf("card")?.classList.contains("setby") && /61240/.test(leftOf("card").title),
      leftOf("card")?.outerHTML);
  say("one with no value is a value button",
      leftOf("box")?.tagName === "BUTTON" && /value/.test(leftOf("box").textContent),
      leftOf("box")?.outerHTML);
  drop(leftOf("box"));
  let typing = document.querySelector(".left input");
  typing.value = "abc";
  typing.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await wait(30);
  say("something that is not a number is not sent",
      LEFTS.length === 0 && /number/i.test(document.getElementById("left-said")?.textContent || ""),
      document.getElementById("left-said")?.textContent);
  typing.value = "3,5";
  typing.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => LEFTS.length === 1);
  say("a number typed there sets that month's figure",
      LEFTS[0] && LEFTS[0].slot === "box" && LEFTS[0].value === 3.5 && LEFTS[0].period === "July",
      JSON.stringify(LEFTS));
  await until(() => leftOf("card"));
  drop(leftOf("card"));
  typing = document.querySelector(".left input");
  say("changing a typed figure starts from it", typing && typing.value === "50000", typing?.value);
  drop(document.querySelector(".left [data-back]"));
  await until(() => LEFTS.length === 2);
  say("and it can go back to the notes' figure",
      LEFTS[1] && LEFTS[1].slot === "card" && LEFTS[1].value === null, JSON.stringify(LEFTS[1]));

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
