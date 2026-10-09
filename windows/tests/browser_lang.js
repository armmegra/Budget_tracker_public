const MARK = "browser_lang.js - the page in its second language";
const LOG = [];
const ERRORS = [];
window.addEventListener("error", e => ERRORS.push("error: " + e.message));
window.addEventListener("unhandledrejection",
  e => ERRORS.push("rejection: " + ((e.reason && e.reason.message) || e.reason)));
const ascii = s => String(s).replace(/[^\x20-\x7e]/g,
  c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name
  + (detail !== undefined && detail !== "" ? " :: " + ascii(detail) : ""));

const wait = (ms) => new Promise(r => setTimeout(r, ms || 20));
async function until(test, tries = 150) {
  for (let i = 0; i < tries; i++) {
    try { if (test()) return true; } catch (e) { }
    await wait(10);
  }
  return false;
}
const settled = async () => { await until(() => !DRAWING); await wait(30); };
const $ = (sel) => document.querySelector(sel);
const click = (el) => { if (el) el.dispatchEvent(new MouseEvent("click", { bubbles: true })); return !!el; };
const flat = (s) => String(s || "").replace(/\s+/g, " ").trim();
const cyrillic = (s) => /[Ѐ-ӿ]/.test(s || "");

const PERSON = ["Food", "Market", "Delivery", "Rent", "Gifts", "Coffee", "Tea", "card", "cash",
  "bakery", "Food · Market", "Rent · Rent", "Gifts · Gifts", "12.06 1300 taxi", "14.06 900",
  "4500 food", "1200 bakery", "9400 rent"];
const PERSON_WORDS = new Set(PERSON.join(" ").match(/[A-Za-z][A-Za-z0-9]*/g));
const ALLOWED = new Set(["English", "Word", "rtf", "txt", "A4", "JSON", "Enter", "data", "px"]);

const MONTHS = [
  { identity: "undated:1", span: "undated", month: "undated", year: null, days: 2 },
  { identity: "salary:5", span: "12.05..11.06", month: "May", year: 2026, days: 28 },
  { identity: "salary:6", span: "12.06..11.07", month: "June", year: 2026, days: 27 },
];
let STORED = MONTHS;
const cells = [
  { figure: "61 240", label: "card", place: "before", join: " " },
  { figure: "6.8", label: "cash", place: "after", join: " " },
];
const totals = (period) => ({
  span: "12.06..11.07",
  majors: [
    { name: "Food", value: 13.8, limit: 12, income: false, chart: true },
    { name: "Rent", value: 9.4, limit: 10, income: false, chart: true },
    { name: "Gifts", value: 5.0, limit: null, income: false, chart: true },
    { name: "Totally saved", value: 30.0, limit: null, income: false, chart: true, saved: true },
    { name: "Totally overspent", value: 1.8, limit: null, income: false, chart: true, overspent: true },
  ],
  limits: [{ label: "Food", group: "Food", value: 12 }, { label: "Rent", group: "Rent", value: 10 }],
  minors: [
    { name: "Market", amounts: [4500, 1200], total: 5700, marks: [
      [{ raw: "4500 food", occurrence: 0, kind: "answered", candidates: ["Market", "Gifts"] }],
      [{ raw: "1200 bakery", occurrence: 0, kind: "placed", candidates: [] }]] },
    { name: "Rent", amounts: [9400], total: 9400, marks: [
      [{ raw: "9400 rent", occurrence: 0, kind: "moved", candidates: ["Rent"] }]] },
    { name: "Gifts", amounts: [5000], total: 5000 },
  ],
  totals: { necessary: 23.2, appended: 5.0, grand: 28.2 },
  appended: [{ id: "Gifts", name: "Gifts", value: 5.0, actual: 8.0, adjusted: true, counted: true }],
  left: { raw: "Left: card 61 240, 6.8 cash", text: "Left: card 61 240, 6.8 cash", cells,
          computed: { cells }, date: "01.07", days_after: 2 },
  questions: 2,
  closed: period === "May",
});
const EMPTY = {
  span: "", empty: true, questions: 0, closed: false,
  majors: [
    { name: "Food", value: 0, limit: 12, income: false, chart: true },
    { name: "Rent", value: 0, limit: 10, income: false, chart: true },
    { name: "Gifts", value: 0, limit: null, income: false, chart: true },
    { name: "Coffee", value: 0, limit: null, income: false, chart: true },
    { name: "Totally saved", value: 0, limit: null, income: false, chart: true, saved: true },
    { name: "Totally overspent", value: 0, limit: null, income: false, chart: true, overspent: true },
  ],
  limits: [{ label: "Food", group: "Food", value: 12 }, { label: "Rent", group: "Rent", value: 10 }],
  minors: ["Market", "Delivery", "Rent", "Gifts"].map(name => ({ name, amounts: [], total: 0 })),
  totals: { necessary: 0, appended: 0, grand: 0 },
  appended: [],
  left: { raw: "", text: "Left: card —, — cash", extra: 0, date: null, days_after: 0, cells: [
    { figure: "—", label: "card", place: "before", join: " " },
    { figure: "—", label: "cash", place: "after", join: " " }] },
};
const QUESTIONS = [
  { number: 1, raw: "12.06 1300 taxi", review: "проезд без подписи — куда была эта поездка?",
    candidates: ["Food", "Gifts"] },
  { number: 2, raw: "14.06 900", review: "сумма без подписи, которую не к чему отнести",
    candidates: ["Food"] },
];
const CONFIG = {
  majors: [
    { name: "Food", label: "Food", tier: "NECESSARY", limit: 12, limit_label: null,
      minors: [{ name: "Market", label: "Market" }, { name: "Delivery", label: "Delivery" }] },
    { name: "Rent", label: "Rent", tier: "NECESSARY", limit: 10, minors: [{ name: "Rent", label: "Rent" }] },
    { name: "Gifts", label: "Gifts", tier: "OCCASIONAL", limit: null, minors: [{ name: "Gifts", label: "Gifts" }] },
    { name: "Coffee", label: "Coffee", tier: "FREQUENT", limit: null, minors: [] },
  ],
  limit_order: ["Food", "Rent"],
  left: { slots: [{ id: "card", label: "card", place: "before", join: " ", kind: "card" },
                  { id: "cash", label: "cash", place: "after", join: " ", kind: "cash" }],
          kinds: ["card", "cash", "purse", "carry"] },
  words: [{ word: "bakery", group: "Market", label: "Food · Market" }],
};
const COMPARE_TABLE = "               Май 2026  Июнь 2026\n"
  + "Food               13.1       13.8\n" + "Rent                9.4        9.4\n"
  + "Итого              22.5       23.2\n";
const BODIES = [];
let REFUSE = {};
let HOUSEHOLD_REPLY = "en";
let RESTORED = { months: 1, answers: 1 };
let SAVED = null;
window.download = (name, body, type) => { SAVED = { name, body, type }; };

function answer(body) {
  switch (body.action) {
    case "periods": return STORED.map(p => ({ ...p }));
    case "totals": return totals(body.period);
    case "questions": return QUESTIONS;
    case "config": return CONFIG;
    case "empty": return EMPTY;
    case "compare": return COMPARE_TABLE;
    case "household": return { household: HOUSEHOLD_REPLY, offered: ["en", "ru"], swapped: false };
    case "backup":
      return { kind: "budget-backup", version: 1, saved: "2026-02-14T06:00:00+00:00",
               months: 2, answers: 3, server: { periods: {} }, rules: "[groups]\n" };
    case "restore": return { restored: { ...RESTORED }, replaced: {}, saved: "", rules: "absent" };
    case "reset":
      return body.scope === "answers" ? { wiped: { answers: 5 }, questions: 2 }
        : { wiped: { months: 2, answers: 5, group_edits: 1, scoped_edits: 3 },
            months: ["Май 2026", "Июнь 2026"] };
    case "configure":
      if (body.ops) return body.confirm ? {} : { months: ["Июнь 2026", "и все последующие месяцы"] };
      return CONFIG;
    case "import":
      return { month: "June", days_before: 20, days_after: 27,
               carried: [{ span: "undated", outcome: "imported", said: "добавлено" }] };
    default: throw new Error("unexpected action " + body.action);
  }
}
window.fetch = async function (url, init) {
  const body = JSON.parse(init.body);
  BODIES.push(JSON.parse(JSON.stringify(body)));
  let reply;
  if (REFUSE[body.action]) reply = Object.assign({ ok: false }, REFUSE[body.action]);
  else {
    try { reply = { ok: true, result: answer(body) }; }
    catch (e) { reply = { ok: false, error: e.message }; }
  }
  return { ok: true, status: 200, statusText: "OK", json: async () => reply,
           text: async () => JSON.stringify(reply) };
};

function shown(roots) {
  const out = [document.title];
  for (const root of roots) {
    if (!root) continue;
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (n.parentElement && n.parentElement.closest("script,style")) continue;
      const text = flat(n.nodeValue);
      if (text) out.push(text);
    }
    for (const el of [root, ...root.querySelectorAll("[title],[placeholder]")]) {
      for (const attr of ["title", "placeholder"]) {
        const v = el.getAttribute && el.getAttribute(attr);
        if (v) out.push(flat(v));
      }
    }
  }
  return out;
}
const popups = () => [...document.querySelectorAll(".mover")];

function noEnglish(where, roots, { own = PERSON_WORDS, also = [] } = {}) {
  const texts = shown(roots);
  const english = new Map();
  for (const [key, en] of T_SEEN) {
    const ru = T.ru[key];
    const plain = flat(en);
    if (ru === undefined || ru === en || !plain || /[{<&]/.test(plain)) continue;
    english.set(plain, key);
  }
  const same = texts.filter(x => english.has(x) && !PERSON.includes(x)).map(x => english.get(x) + "=" + x);
  say(`${where}: no text is the English of a key`, same.length === 0, same.join(" | "));
  const latin = [];
  for (const x of texts) {
    for (const w of x.match(/[A-Za-z][A-Za-z0-9]*/g) || []) {
      if (!own.has(w) && !ALLOWED.has(w) && !also.includes(w)) latin.push(`${w} in "${x.slice(0, 60)}"`);
    }
  }
  say(`${where}: no English word but a person's own`, latin.length === 0, latin.slice(0, 6).join(" | "));
}

function ownNames() {
  const bars = [...app().querySelectorAll(".chart .bar-name")].map(n => n.textContent);
  return {
    bars: bars.filter(n => !/^(Totally saved|Totally overspent|Всего сэкономлено|Всего перерасходовано)$/.test(n)),
    readings: bars.filter(n => /^(Totally|Всего)/.test(n)),
    minors: [...app().querySelectorAll(".minors .name")].map(n => n.textContent),
    limits: [...app().querySelectorAll(".limits div > span:first-child")].map(n => n.textContent),
    left: [...app().querySelectorAll(".left .lbl")].map(n => n.textContent),
    tail: [...app().querySelectorAll(".totals .setby")].map(n => n.textContent),
  };
}

async function openEditor(button, go) {
  click(button);
  if (go === "limits") {
    await until(() => document.querySelector(".mover h3"));
    await wait(30);
    return "";
  }
  await until(() => document.querySelector(`.mover [data-go="${go}"]`));
  const card = document.querySelector(".mover");
  const cardTexts = card ? flat(card.textContent) : "";
  click(document.querySelector(`.mover [data-go="${go}"]`));
  await until(() => document.querySelector(".mover h3"));
  await wait(30);
  return cardTexts;
}

async function chooseFile(doc) {
  const said = $("#restore-said");
  const dt = new DataTransfer();
  dt.items.add(new File([JSON.stringify(doc)], "b.json", { type: "application/json" }));
  const input = $("#restore-file");
  input.files = dt.files;
  input.dispatchEvent(new Event("change"));
  await until(() => said.querySelector("[data-go=apply]"));
  return flat(said.textContent);
}
async function restore(doc) {
  const said = $("#restore-said");
  const step1 = await chooseFile(doc);
  click(said.querySelector("[data-go=apply]"));
  await until(() => said.querySelector("[data-go=yes]") && !said.querySelector("[data-go=yes]").disabled, 200);
  click(said.querySelector("[data-go=yes]"));
  await until(() => said.className === "ok" || said.className === "err");
  await settled();
  return { step1, done: flat(said.textContent) };
}

function shots(n) {
  const dt = new DataTransfer();
  for (let i = 0; i < n; i++) dt.items.add(new File([new Uint8Array([i])], `s${i}.png`, { type: "image/png" }));
  $("#shots").files = dt.files;
  $("#shots").dispatchEvent(new Event("change"));
  return $("#shots-chosen").textContent;
}

(async () => {
  try {
    await boot();
    await settled();
    say("the page starts in English", LANG === "en" && document.documentElement.lang === "en",
        LANG + "/" + document.documentElement.lang);
    say("the nav says Month", $('nav button[data-view="month"]').textContent === "Month",
        $('nav button[data-view="month"]').textContent);
    say("the window's title is English", document.title === "Budget — June 2026", document.title);
    say("no request carries a language", BODIES.length >= 2 && BODIES.every(b => !("lang" in b)),
        JSON.stringify(BODIES));
    const englishNames = ownNames();
    const englishHeader = $("header").innerHTML;
    say("the English month view names the readings in English",
        englishNames.readings.join("|") === "Totally saved|Totally overspent", englishNames.readings.join("|"));

    const first = $("#settings").firstElementChild;
    say("the language is the first thing in the gear",
        !!$("#lang") && first && first.id === "lang-head" && first.nextElementSibling === $("#lang"));
    say("it offers English and Русский, each in its own language",
        [...$("#lang").options].map(o => o.value + "=" + o.text).join(",") === "en=English,ru=Русский",
        [...$("#lang").options].map(o => o.value + "=" + o.text).join(","));

    const switchedAt = BODIES.length;
    $("#lang").value = "ru";
    $("#lang").dispatchEvent(new Event("change"));
    await until(() => BODIES.slice(switchedAt).some(b => b.action === "totals"));
    await settled();
    say("<html lang> is ru", document.documentElement.lang === "ru" && LANG === "ru");
    const nav = [...document.querySelectorAll("nav button[data-view]")]
      .map(b => [...b.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("")).join("|");
    say("the nav is Russian", nav === "Месяц|Добавить записи|Вопросы|Сравнение", nav);
    say("the Questions button's ! says in Russian how many wait",
        /^2 вопроса без ответа/.test(document.querySelector('nav button[data-view="questions"]').title || ""),
        document.querySelector('nav button[data-view="questions"]').title);
    const heads = ["gear.language", "gear.colours", "gear.words", "gear.account", "gear.backup", "gear.wipe"]
      .map(k => [k, $(`[data-t="${k}"]`).textContent]);
    say("the gear's headings are Russian", heads.every(([k, v]) => v === T.ru[k] && cyrillic(v)),
        heads.map(h => h.join("=")).join(" | "));
    say("the gear's colours and sizes are Russian",
        $("#swatches").textContent.includes(T.ru["gear.colour.green"]) &&
        $("#swatches").textContent.includes(T.ru["gear.sizes"]), flat($("#swatches").textContent).slice(0, 80));
    say("the window's title is Russian", document.title === "Бюджет — Июнь 2026", document.title);
    const options = [...$("#period").options].map(o => `${o.value}=${o.text}=${o.title}`).join(",");
    say("the month labels are Russian and their values stay English",
        options === "undated=без даты=без даты,May=Май 2026=12.05..11.06,June=Июнь 2026=12.06..11.07", options);
    say("the chosen month is kept", $("#period").value === "June", $("#period").value);
    const household = BODIES.slice(switchedAt).filter(b => b.action === "household");
    say("exactly one household request, in Russian", household.length === 1 && household[0].lang === "ru",
        JSON.stringify(household));
    say("every request after the switch carries lang ru",
        BODIES.slice(switchedAt).every(b => b.lang === "ru"), JSON.stringify(BODIES.slice(switchedAt)));

    const russianNames = ownNames();
    for (const part of ["bars", "minors", "limits", "left", "tail"]) {
      say(`a person's names are untouched: ${part}`,
          JSON.stringify(russianNames[part]) === JSON.stringify(englishNames[part]),
          JSON.stringify(englishNames[part]) + " vs " + JSON.stringify(russianNames[part]));
    }
    say("a group named Rent stays Rent", russianNames.minors.includes("Rent:"));
    say("the readings are named by their flags, in Russian",
        russianNames.readings.join("|") === "Всего сэкономлено|Всего перерасходовано", russianNames.readings.join("|"));

    say("the Left line is Russian, its labels the person's",
        flat(app().querySelector(".left").textContent).startsWith("Остаток: card 61 240, 6.8 cash (пересчитано: остаток на 01.07 + ещё 2 дня)"),
        flat(app().querySelector(".left").textContent));
    say("the questions waiting are counted in Russian", app().textContent.includes("2 вопроса без ответа."));
    noEnglish("month view", [$("header"), app()]);

    $("#period").value = "May";
    $("#period").dispatchEvent(new Event("change"));
    await settled();
    say("a closed month says so in Russian", flat($(".lockbar span").innerHTML).startsWith("<b>Май закрыт.</b>") &&
        $("#lock-toggle").textContent === "Открыть этот месяц", flat($(".lockbar").innerHTML).slice(0, 90));
    click($("#lock-toggle"));
    say("and asks before it opens", $("#lock-yes")?.textContent === "Да, открыть" &&
        $("#lock-no")?.textContent === "Нет, пусть останется закрытым");
    noEnglish("closed month", [$("header"), app()]);
    click($("#lock-no"));
    $("#period").value = "June";
    $("#period").dispatchEvent(new Event("change"));
    await settled();

    click(app().querySelector(".ansd"));
    await until(() => popups().length);
    say("the move popup asks in Russian", popups()[0]?.textContent.includes("Куда это отнести?"));
    click(popups()[0]?.querySelector("[data-prompt]"));
    noEnglish("move popup", popups());
    click(popups()[0]?.querySelector("[data-cancel]"));
    click(app().querySelector(".movd"));
    await until(() => popups().length);
    say("a moved figure can be put back, in Russian",
        popups()[0]?.querySelector("[data-lift]")?.textContent === "Вернуть на место");
    noEnglish("move popup of a moved figure", popups());
    click(popups()[0]?.querySelector("[data-cancel]"));

    click($("#pick-appended"));
    await until(() => popups().length);
    noEnglish("second Total's tick list", popups());
    click(popups()[0]?.querySelector("[data-act=cancel]"));

    click($("#export"));
    await until(() => popups().length);
    const what = [...($("#pr-what")?.options || [])].map(o => o.text).join(" | ");
    say("the print list says its months in Russian",
        what === "Весь 2026 год — все месяцы | Май 2026 (28 дней) | Июнь 2026 (27 дней) | без даты — год не записан", what);
    noEnglish("print popup", popups());
    click(popups()[0]?.querySelector("[data-cancel]"));

    await openEditor(app().querySelector("#edit-limits"), "limits");
    say("a limit opens its editor at once",
        /Лимиты/.test(popups()[0]?.textContent || "") &&
        !/К каким месяцам/.test(popups()[0]?.textContent || ""),
        flat(popups()[0]?.textContent).slice(0, 80));
    noEnglish("limits editor", popups());
    const card = await openEditor(app().querySelector("#edit-left"), "left");
    say("the which-months card is Russian",
        card.startsWith("К каким месяцам применить изменения? Июнь 2026 и все последующие месяцы " +
                        "Все месяцы, и прошлые тоже Прошлые месяцы пересчитаются по новым группам"),
        card);
    const kinds = [...(popups()[0]?.querySelectorAll("#new-left-kind option") || [])].map(o => `${o.value}=${o.text}`).join(",");
    say("the Left kinds are said in Russian, their values kept",
        kinds === "card=остаток на карте,cash=наличные на руках,purse=кошелёк на неделю,carry=перенесено", kinds);
    noEnglish("Left line editor", popups());
    await openEditor(app().querySelector("#edit-minors"), "minors");
    noEnglish("minor groups editor", popups());
    await openEditor($("#open-words"), "words");
    noEnglish("words editor", popups());
    await openEditor(app().querySelector("#edit-majors"), "majors");
    const tiers = [...(popups()[0]?.querySelectorAll("#new-major-tier option") || [])].map(o => `${o.value}=${o.text}`).join(",");
    say("the tiers are said in Russian, their values kept",
        tiers === "NECESSARY=необходимая,FREQUENT=частая,OCCASIONAL=разовая", tiers);
    say("a major's row counts its minors in Russian",
        popups()[0]?.textContent.includes("необходимая · лимит 12 · 2 подгруппы"));
    noEnglish("major groups editor", popups());

    click(app().querySelector("#edit-majors"));
    await until(() => document.querySelector('.mover input[value="onward"]'));
    const onward = document.querySelector('.mover input[value="onward"]');
    onward.checked = true;
    onward.dispatchEvent(new Event("change"));
    click(document.querySelector('.mover [data-go="majors"]'));
    await until(() => document.querySelector(".mover p.scope"));
    say("the scope line is one Russian sentence", flat(document.querySelector(".mover p.scope").textContent) ===
        "После применения изменения коснутся месяца Июнь 2026 и всех последующих.",
        flat(document.querySelector(".mover p.scope")?.textContent));
    const row = document.querySelector('.mover [data-major="Coffee"] [data-act="rename-major"]');
    click(row);
    const field = document.querySelector(".mover .erow input[type=text]:not([id])");
    if (field) field.value = "Tea";
    click(field && field.parentElement.querySelector("[data-go]"));
    say("an edit is staged, in Russian", flat(document.querySelector(".mover .said")?.textContent) === "В очереди 1 изменение.",
        flat(document.querySelector(".mover .said")?.textContent));
    await until(() => document.querySelector(".mover ol.staged"));
    say("the staged edit is said in Russian, the names as written",
        flat(document.querySelector(".mover ol.staged")?.textContent) === "переименовать «Coffee» в «Tea»",
        flat(document.querySelector(".mover ol.staged")?.textContent));
    click(document.querySelector(".mover [data-staged=apply]"));
    await until(() => document.querySelector(".mover [data-go=no]"));
    say("Apply names the months, in Russian",
        flat(document.querySelector(".mover .said")?.textContent).startsWith("1 изменение для месяцев: Июнь 2026, и все последующие месяцы."),
        flat(document.querySelector(".mover .said")?.textContent));
    noEnglish("staged edits", popups());
    click(document.querySelector(".mover [data-go=no]"));
    click(document.querySelector(".mover [data-staged=discard]"));
    await wait(40);
    popups().forEach(p => p.remove());
    SCOPE = { mode: "always", period: null };
    STAGED = [];

    click($("#gear"));
    say("the wipe choices name the month in Russian",
        flat($('[data-t-html="gear.wipe.month"]').textContent) === "Июнь 2026 — только он: его записи, ответы и отметки" &&
        flat($('[data-t-html="gear.wipe.onward"]').textContent) === "Июнь 2026 и все последующие месяцы",
        flat($('[data-t-html="gear.wipe.month"]').textContent));
    const all = $('input[name=wipe][value=all]');
    all.checked = true;
    all.dispatchEvent(new Event("change"));
    click($("#do-wipe"));
    say("Start over asks in Russian", $("#wipe-yes")?.textContent === "Да, удалить" &&
        $("#wipe-no")?.textContent === "Нет, оставить всё");
    noEnglish("gear", [$("#settings")]);
    click($("#wipe-yes"));
    await until(() => $("#wipe-said").className === "ok");
    await settled();
    say("Start over says what went, counted in Russian",
        $("#wipe-said").textContent === "Удалено: 2 месяца, 5 ответов, 1 правка групп, 3 правки по месяцам (Май 2026, Июнь 2026).",
        $("#wipe-said").textContent);
    click($("#gear"));

    click($('nav button[data-view="questions"]'));
    await settled();
    await until(() => app().querySelector(".q"));
    say("the questions waiting are said in Russian", flat($(".lockbar span")?.textContent) === "Ещё без ответа: 2 вопроса.",
        flat($(".lockbar span")?.textContent));
    noEnglish("questions", [$("header"), app()]);
    click($("#ask-again"));
    click($("#again-yes"));
    await until(() => $("#again-said")?.className === "ok");
    say("asking again counts in Russian", $("#again-said")?.textContent === "Забыто 5 ответов — снова 2 вопроса.",
        $("#again-said")?.textContent);

    REFUSE.answer = { ok: false, code: "closed",
      error: "Июнь 2026 закрыт: месяц закрывается через 3 месяца после окончания, а этот закрылся 4 месяца назад." };
    click(app().querySelector('.q button[data-group="Food"]'));
    await until(() => app().querySelector(".q .said.err"));
    const refusal = flat(app().querySelector(".q .said.err")?.textContent);
    say("a refusal coded closed shows the Unlock hint, in Russian",
        refusal === "Июнь закрыт — перейдите к нему в разделе «Месяц», нажмите «Открыть этот месяц» и попробуйте ещё раз.",
        refusal);
    REFUSE = {};

    click($('nav button[data-view="compare"]'));
    await settled();
    await until(() => $("#compare-out pre"));
    noEnglish("compare", [$("header"), app()]);

    click($('nav button[data-view="add"]'));
    await settled();
    await until(() => $("#notes"));
    const dated = /^\d{2}\.\d{2}\n/;
    const addHelp = () => $(".add-row p.muted").innerHTML;
    say("an English household is taught with its own Left:, on a Russian screen",
        HOUSEHOLD === "en" && addHelp().includes("<code>Left:</code>") &&
        !addHelp().includes("<code>Остаток:</code>") && cyrillic(addHelp()),
        HOUSEHOLD + " " + addHelp().slice(0, 80));
    say("and its example notes stay in its words",
        dated.test($("#notes").placeholder) && !cyrillic($("#notes").placeholder),
        $("#notes").placeholder);
    const addOptions = [...$("#target").options].map(o => `${o.value}=${o.text}`).join(",");
    say("the Add to list shows month labels and keeps the values",
        addOptions === "=— новый месяц (в записях есть строка с зарплатой) —,undated=без даты,May=Май,June=Июнь", addOptions);
    HOUSEHOLD = "ru";
    await render();
    await until(() => $("#notes"));
    say("the Russian household is taught with Остаток:", $(".add-row p.muted").innerHTML.includes("<code>Остаток:</code>"),
        $(".add-row p.muted").innerHTML.slice(0, 80));
    say("and its example notes are Russian",
        dated.test($("#notes").placeholder) && cyrillic($("#notes").placeholder),
        $("#notes").placeholder);
    say("no screenshots chosen, in Russian", $("#shots-chosen").textContent === "Скриншоты не выбраны");
    const chosen = [1, 2, 5].map(shots).join(" | ");
    say("screenshots chosen are counted in Russian",
        chosen === "Выбран 1 скриншот | Выбрано 2 скриншота | Выбрано 5 скриншотов", chosen);
    noEnglish("Add notes (Russian household)", [$("header"), app()], { also: ["Left"] });
    $("#notes").value = "12.06\n2000 продукты\n";
    click($("#send"));
    await until(() => $("#said").className === "ok");
    say("an import is said in Russian", $("#said").textContent === "Июнь: 20 → 27 дней (следующий месяц: добавлено без даты)",
        $("#said").textContent);
    REFUSE.import = { code: "paste_closed",
      error: "эта вставка перезаписала бы закрытый месяц: Июнь 2026. Сначала откройте его." };
    $("#notes").value = "12.06\n2000 продукты\n";
    click($("#send"));
    await until(() => $("#said").className === "err");
    say("a paste refused by its code says where the Unlock is",
        $("#said").textContent === REFUSE.import.error + " — или сначала перейдите к этому месяцу и нажмите «Открыть этот месяц».",
        $("#said").textContent);
    REFUSE.import = { code: "no_rules", error: "в этих записях нет строки с зарплатой" };
    click($("#send"));
    await until(() => $("#said").textContent === REFUSE.import.error);
    say("any other refusal is shown as the server said it", $("#said").textContent === REFUSE.import.error,
        $("#said").textContent);
    REFUSE = {};
    HOUSEHOLD = "en";

    STORED = [];
    PERIODS = await call({ action: "periods" });
    fillPeriods();
    click($('nav button[data-view="month"]'));
    await settled();
    await until(() => app().querySelector(".chart svg") && app().querySelector(".banner"));
    const rows = [...app().querySelectorAll(".minors .name")].map(n => flat(n.textContent)).join("|");
    say("the empty app draws the month with the person's own groups",
        rows === "Market:|Delivery:|Rent:|Gifts:" &&
        /Food\s*12/.test(app().querySelector(".limits")?.textContent || ""), rows);
    say("the empty app's banner is Russian",
        flat(app().querySelector(".banner").textContent).startsWith(
          "Пока ничего не добавлено — так будет выглядеть ваш месяц. Все группы на своих местах"),
        flat(app().querySelector(".banner").textContent).slice(0, 90));
    noEnglish("the empty app", [$("header"), app()]);
    STORED = MONTHS;
    PERIODS = await call({ action: "periods" });
    fillPeriods();
    await render();
    await settled();

    SAVED = null;
    click($("#do-backup"));
    await until(() => SAVED);
    const file = SAVED ? JSON.parse(SAVED.body) : {};
    say("the backup has a top-level lang ru", file.lang === "ru" && !("lang" in ((file.page || {}).options || {})),
        JSON.stringify({ lang: file.lang, page: file.page }));
    say("and says so in Russian", $("#restore-said").textContent === "Сохранено: 2 месяца и 3 ответа, вместе с вашими цветами и размерами.",
        $("#restore-said").textContent);

    const counted = [];
    for (const [months, answers, lang] of [[1, 21, undefined], [2, 3, "ru"], [5, 11, undefined]]) {
      RESTORED = { months, answers };
      const doc = Object.assign({}, file, { months, answers });
      if (lang) doc.lang = lang; else delete doc.lang;
      counted.push(await restore(doc));
    }
    say("the file's step one counts in Russian",
        counted.map(c => c.step1.split(" Это заменит")[0]).join(" | ") ===
          "b.json — 1 месяц, 21 ответ (сохранён 2026-02-14). | b.json — 2 месяца, 3 ответа (сохранён 2026-02-14). | b.json — 5 месяцев, 11 ответов (сохранён 2026-02-14).",
        counted.map(c => c.step1.split(" Это заменит")[0]).join(" | "));
    say("a restore of 1, 2 and 5 months says месяц, месяца, месяцев",
        counted.map(c => c.done).join(" | ") ===
          "Восстановлено: 1 месяц и 21 ответ. | Восстановлено: 2 месяца и 3 ответа. | Восстановлено: 5 месяцев и 11 ответов.",
        counted.map(c => c.done).join(" | "));
    say("a file without a language keeps the one on screen", LANG === "ru" && document.documentElement.lang === "ru");
    say("every request in Russian carried lang ru", BODIES.slice(switchedAt).every(b => b.lang === "ru"),
        JSON.stringify(BODIES.slice(switchedAt).filter(b => b.lang !== "ru")));

    RESTORED = { months: 3, answers: 4 };
    const backAt = BODIES.length;
    const english = await restore(Object.assign({}, file, { lang: "en", months: 3, answers: 4 }));
    say("a file with lang en switches the page to English",
        LANG === "en" && document.documentElement.lang === "en" && $("#lang").value === "en" &&
        $('nav button[data-view="month"]').textContent === "Month" && document.title === "Budget — June 2026",
        LANG + " " + document.title);
    say("and says what it restored in English", english.done === "Restored 3 month(s) and 4 answer(s).", english.done);
    const bare = html => html.replace(/ (style|class)=""/g, "");
    say("the header is the English markup again", bare($("header").innerHTML) === bare(englishHeader));
    click($("#do-backup"));
    await until(() => BODIES.slice(backAt).some(b => b.action === "backup"));
    say("the restore itself went in Russian, and nothing after it carries a language",
        BODIES[backAt].action === "restore" && BODIES[backAt].lang === "ru" &&
        BODIES.slice(backAt + 1).every(b => !("lang" in b)), JSON.stringify(BODIES.slice(backAt)));

    const names = s => [...new Set([...String(s).matchAll(/\{(\w+)((?:\|[^{}|]*)+)?\}/g)]
      .map(m => m[1]).filter(n => n !== "s"))].sort().join(",");
    const forms = ru => (ru && typeof ru === "object" ? Object.values(ru) : [ru]);
    const parity = (pairs) => pairs.filter(([key, en]) => en !== null && T.ru[key] !== undefined &&
      forms(T.ru[key]).some(f => names(f) !== names(en))).map(([key]) => key);
    const drawn = [...T_SEEN];
    say(`every key drawn (${drawn.length}) has Russian`, drawn.every(([k]) => T.ru[k] !== undefined && T.ru[k] !== ""),
        drawn.filter(([k]) => T.ru[k] === undefined || T.ru[k] === "").map(([k]) => k).join(","));
    say("and the same placeholders as its English", parity(drawn).length === 0, parity(drawn).join(","));
    const whole = [...document.scripts].map(s => s.textContent).find(s => s.includes("const T = { ru: {")) || "";
    let src = whole.slice(0, whole.indexOf(MARK) > 0 ? whole.indexOf(MARK) : whole.length);
    const from = src.indexOf("const T = { ru: {"), to = src.indexOf("\n} };", from);
    if (from >= 0 && to > from) src = src.slice(0, from) + src.slice(to);
    const literal = (at) => {
      const q = src[at];
      if (q !== '"' && q !== "`") return null;
      let out = "";
      for (let i = at + 1; i < src.length; i++) {
        const c = src[i];
        if (c === "\\") { out += src[i + 1] === "n" ? "\n" : src[i + 1]; i++; continue; }
        if (q === "`" && c === "$" && src[i + 1] === "{") return null;
        if (c === q) return out;
        out += c;
      }
      return null;
    };
    const calls = [...src.matchAll(/\bth?\(\s*"([a-z]\w*(?:\.\w+)+)",\s*/g)]
      .map(m => [m[1], literal(m.index + m[0].length)]);
    const markup = [];
    for (const kind of ["text", "html", "title", "placeholder"]) {
      for (const [k, en] of Object.entries(STATIC[kind])) markup.push([k, en]);
    }
    const arrays = [...SWATCHES.map(o => [o[2], o[1]]), ...SIZES.map(o => [o[4], o[1]]),
                    ...Object.values(EDITORS), ...Object.values(TIER_WORDS)];
    const prefixes = new Set(Object.keys(T.ru).map(k => k.split(".")[0]));
    const literals = [...src.matchAll(/"([a-z]\w*(?:\.\w+)+)"/g)].map(m => m[1])
      .filter(k => prefixes.has(k.split(".")[0])).map(k => [k, null]);
    const households = LANGS.filter(c => c !== "en" && src.includes('"add.help" + household'))
      .flatMap(c => [["add.help.household_" + c, null], ["add.placeholder.household_" + c, null]]);
    const monthKeys = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                       "October", "November", "December", "undated"].map(m => ["month." + m, null]);
    const source = [...calls, ...markup, ...arrays, ...literals, ...households];
    const lacking = source.filter(([k]) => T.ru[k] === undefined || T.ru[k] === "").map(([k]) => k);
    say(`every key in the page's source (${new Set(source.map(s => s[0])).size}) has Russian`, lacking.length === 0,
        [...new Set(lacking)].join(","));
    say("with the same placeholders as its English", parity([...calls, ...markup, ...arrays]).length === 0,
        parity([...calls, ...markup, ...arrays]).join(","));
    say("the twelve months and undated have their labels", monthKeys.every(([k]) => cyrillic(T.ru[k])),
        monthKeys.filter(([k]) => !cyrillic(T.ru[k])).map(([k]) => k).join(","));
    const used = new Set([...source, ...monthKeys].map(([k]) => k));
    const stray = Object.keys(T.ru).filter(k => !used.has(k));
    say("no Russian is kept for a key the page does not use", stray.length === 0, stray.join(","));
    LANG = "ru";
    const plural = [1, 2, 5, 11, 21, 22].map(n => t("gear.wiped.months", "{n} month{s}", { n, s: n === 1 ? "" : "s" })).join(", ");
    LANG = "en";
    say("a count takes its Russian form", plural === "1 месяц, 2 месяца, 5 месяцев, 11 месяцев, 21 месяц, 22 месяца", plural);
  } catch (e) {
    say("the driver ran to its end", false, (e && e.stack) || e);
  }
  say("no script errors", ERRORS.length === 0, ERRORS.join(" / "));
  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n").replace(/[<&]/g, c => (c === "<" ? "&lt;" : "&amp;")) + "</pre>";
})();
