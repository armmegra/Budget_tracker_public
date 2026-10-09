const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));
const wait = (ms) => new Promise(r => setTimeout(r, ms || 40));
const drop = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
async function until(test, tries = 200) {
  for (let i = 0; i < tries; i++) { if (test()) return true; await wait(10); }
  return false;
}
const card = () => document.querySelector(".mover");

let WORDS = [{ word: "bakery", group: "Market", label: "Food · Market" }];
const SENT = [];
const config = () => ({
  majors: [
    { name: "Food", label: "Food", tier: "NECESSARY", limit: 12, limit_label: null,
      income: false, fixed: null,
      minors: [{ name: "Market", label: "Market" }, { name: "Delivery", label: "Delivery" }] },
    { name: "Leisure", label: "Leisure", tier: "OCCASIONAL", limit: null, limit_label: null,
      income: false, fixed: null, minors: [{ name: "Leisure", label: "Leisure" }] },
  ],
  limit_order: ["Food"],
  left: { slots: [], kinds: ["card", "cash", "purse", "carry"] },
  words: WORDS,
  overlay: {}, versions: [], closed: [],
});

window.call = async function (body) {
  if (body.action === "periods")
    return [{ identity: "salary:1", span: "12.07..11.08", month: "July", year: 2026, days: 27 }];
  if (body.action === "config") return config();
  if (body.action === "configure") {
    SENT.push(body);
    if (body.op === "learn_word") WORDS = WORDS.concat(
      [{ word: body.word, group: body.group, label: body.group }]);
    if (body.op === "forget_word") WORDS = WORDS.filter(w => w.word !== body.word);
    return config();
  }
  throw new Error("unexpected action " + body.action);
};

(async () => {
  try {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});

  const button = document.getElementById("open-words");
  say("the gear panel offers the words", !!button);
  drop(button);
  await until(() => card());
  say("it asks which months first", /which months/i.test(card().textContent));
  const go = card().querySelector('[data-go="words"]');
  say("and offers the words editor", !!go, card().textContent.slice(0, 80));
  drop(go);
  await until(() => card() && /Words you teach/.test(card().textContent));

  say("a word already taught is listed with its group",
      /bakery/.test(card().textContent) && /Market/.test(card().textContent));

  card().querySelector("#new-word").value = "zorba";
  card().querySelector("#new-word-group").value = "Leisure";
  drop(card().querySelector('[data-act="teach"]'));
  await until(() => SENT.length === 1);
  say("teaching sends the word and the group it chose",
      SENT[0].op === "learn_word" && SENT[0].word === "zorba" && SENT[0].group === "Leisure",
      JSON.stringify(SENT[0]));
  await until(() => /zorba/.test(card().textContent));
  say("and the list shows it straight away", /zorba/.test(card().textContent));

  const before = SENT.length;
  card().querySelector("#new-word").value = "ab";
  drop(card().querySelector('[data-act="teach"]'));
  await wait(120);
  say("two letters is refused in the page", SENT.length === before &&
      /three letters/i.test(card().querySelector(".said").textContent),
      card().querySelector(".said").textContent);

  const row = [...card().querySelectorAll("[data-word]")].find(r => r.dataset.word === "bakery");
  drop(row.querySelector('[data-act="forget"]'));
  await until(() => SENT.length === before + 1);
  const last = SENT[SENT.length - 1];
  say("forgetting names the word", last.op === "forget_word" && last.word === "bakery",
      JSON.stringify(last));
  await until(() => !/bakery/.test(card().textContent));
  say("and it leaves the list", !/bakery/.test(card().textContent));

  } catch (e) {
    say("the words editor is there to drive", false, (e && e.message) || String(e));
  }
  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
