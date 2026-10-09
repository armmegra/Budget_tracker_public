const LOG = [];
const say = (name, ok, detail) => LOG.push((ok ? "PASS " : "FAIL ") + name + (detail ? " :: " + detail : ""));

let SERVER = {
  periods: { "salary:58400": "12.06\n2000 grocer\n" },
  answers: { "salary:58400|2000 grocer|0": "Road fares" },
  years:   { "salary:58400": 2026 },
  config: { limits: { Food: 300 } },
  config_versions: [],
  omitted: {},
  adjusted: { "salary:58400": { "Lakeside": 17.5 } },
};
let CALLS = [];
let FAIL_PERIODS = false;
window.call = async function (body) {
  CALLS.push(body);
  if (body.action === "periods") {
    if (FAIL_PERIODS) { FAIL_PERIODS = false; throw new Error("network went away"); }
  }
  if (body.action === "periods")
    return Object.keys(SERVER.periods).map((k, i) =>
      ({ identity: k, span: "12.06..11.07", month: ["June", "July", "August"][i] || k,
         year: SERVER.years[k], days: 1 }));
  if (body.action === "backup")
    return { kind: "budget-backup", version: 1, saved: "2026-02-14T06:00:00+00:00",
             months: Object.keys(SERVER.periods).length,
             answers: Object.keys(SERVER.answers).length,
             server: JSON.parse(JSON.stringify(SERVER)), rules: RULES };
  if (body.action === "restore") {
    if (body.confirm !== "RESTORE") throw new Error("needs confirm");
    if (!body.backup || body.backup.kind !== "budget-backup") throw new Error("not a backup");
    SERVER = JSON.parse(JSON.stringify(body.backup.server));
    return { restored: { months: Object.keys(SERVER.periods).length,
                         answers: Object.keys(SERVER.answers).length },
             replaced: { months: 1, answers: 1 }, saved: body.backup.saved,
             rules: body.backup.rules === undefined ? "absent"
                  : body.backup.rules === RULES ? "same" : "different" };
  }
  throw new Error("unexpected action " + body.action);
};

const RULES = "[groups]\nFood = 1\n";

let CAPTURED = null;
window.download = (name, body, type) => { CAPTURED = { name, body, type }; };

const said = () => document.getElementById("restore-said");
const btn  = (go) => said().querySelector('[data-go=' + go + ']');
const drop = (el) => el && el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
const wait = () => new Promise(r => setTimeout(r, 40));
async function settle(was, tries = 200) {
  for (let i = 0; i < tries; i++) {
    await new Promise(r => setTimeout(r, 10));
    if (said().innerHTML !== was) return true;
  }
  return false;
}

async function armed(tries = 300) {
  for (let i = 0; i < tries; i++) {
    if (btn("yes") && !btn("yes").disabled) return true;
    await new Promise(r => setTimeout(r, 10));
  }
  return false;
}

async function chooseFile(text, name) {
  const input = document.getElementById("restore-file");
  const was = said().innerHTML;
  const dt = new DataTransfer();
  dt.items.add(new File([text], name, { type: "application/json" }));
  input.files = dt.files;
  input.dispatchEvent(new Event("change"));
  if (!await settle(was)) say("the file was read at all (" + name + ")", false);
}

(async () => {
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  initOptions(() => {});

  const swatch = document.querySelector('#swatches input[data-key="--green"]');
  swatch.value = "#123456";
  swatch.dispatchEvent(new Event("input"));
  await wait();
  say("a colour change reaches the CSS",
      getComputedStyle(document.documentElement).getPropertyValue("--green").trim() === "#123456");

  { const was = said().innerHTML; drop(document.getElementById("do-backup")); await settle(was); }
  say("download produced a file", !!CAPTURED, CAPTURED && CAPTURED.name);
  const file = JSON.parse(CAPTURED.body);
  say("the file names itself by date", CAPTURED.name === "budget-backup-2026-02-14.json", CAPTURED.name);
  say("it is JSON, not text/plain (no BOM)", CAPTURED.type === "application/json");
  say("it carries the server's half", JSON.stringify(file.server) === JSON.stringify(SERVER));
  say("it carries the browser's half", file.page.options["--green"] === "#123456",
      JSON.stringify(file.page.options));
  say("every stored field is in it",
      ["periods","answers","years","config","config_versions","omitted","adjusted"]
        .every(k => k in file.server));

  await chooseFile('{"kind":"something-else"}', "notes.json");
  say("a foreign file is named, not acted on",
      said().className === "err" && !btn("apply") && !btn("yes"), said().textContent);
  await chooseFile("this is not json at all", "photo.json");
  say("unreadable JSON is named, not acted on",
      said().className === "err" && !btn("apply"), said().textContent);

  SERVER = { periods: {}, answers: {}, years: {}, config: {}, config_versions: [],
             omitted: {}, adjusted: {} };
  document.getElementById("reset-colours").click();
  await wait();
  say("the ground is cleared for the test",
      Object.keys(SERVER.periods).length === 0 &&
      getComputedStyle(document.documentElement).getPropertyValue("--green").trim() === "#3f9d5a");

  CALLS = [];
  await chooseFile(CAPTURED.body, "budget-backup-2026-02-14.json");
  say("step 1 asks, with both answers", !!btn("apply") && !!btn("cancel"), said().textContent.trim().slice(0, 60));
  say("step 1 has not called anything", CALLS.length === 0);
  say("step 1 names the file and what it holds",
      said().textContent.includes("budget-backup-2026-02-14.json") &&
      said().textContent.includes("1 month(s)"));

  { const was = said().innerHTML; drop(btn("cancel")); await settle(was); }
  say("Cancel at step 1 puts the question away", !btn("apply") && said().textContent === "");
  say("Cancel restored nothing", Object.keys(SERVER.periods).length === 0);

  await chooseFile(CAPTURED.body, "budget-backup-2026-02-14.json");
  { const was = said().innerHTML; drop(btn("apply")); await settle(was); }
  say("step 2 is the final one, and says so", !!btn("yes") && !!btn("cancel"),
      btn("yes") && btn("yes").textContent.trim());
  say("step 2 has still called nothing", CALLS.length === 0);

  { const was = said().innerHTML; drop(btn("cancel")); await settle(was); }
  say("Cancel at step 2 puts it away too", !btn("yes") && !btn("apply"));
  say("still nothing restored", Object.keys(SERVER.periods).length === 0 && CALLS.length === 0);

  await chooseFile(CAPTURED.body, "budget-backup-2026-02-14.json");
  const spot = btn("apply").getBoundingClientRect();
  const cx = spot.left + spot.width / 2, cy = spot.top + spot.height / 2;
  { const was = said().innerHTML; drop(btn("apply")); await settle(was); }
  drop(document.elementFromPoint(cx, cy));
  await wait();
  say("a double-click on Apply restores nothing", CALLS.length === 0,
      JSON.stringify(CALLS.map(c => c.action)));
  say("the final Yes starts dead", !!btn("yes") && btn("yes").disabled);
  say("Cancel comes first at step 2, where Apply stood",
      said().querySelector("button").dataset.go === "cancel");
  say("the point Apply occupied is not the final Yes",
      document.elementFromPoint(cx, cy) !== btn("yes"));
  say("the block kept step one's height, so nothing moved",
      said().style.minHeight !== "" && btn("yes").getBoundingClientRect().top === spot.top,
      said().style.minHeight);
  say("it arms itself shortly after", await armed());
  { const was = said().innerHTML; drop(btn("cancel")); await settle(was); }

  await chooseFile(CAPTURED.body, "budget-backup-2026-02-14.json");
  { const was = said().innerHTML; drop(btn("apply")); await settle(was); }
  await armed();
  { const was = said().innerHTML; drop(btn("yes")); await settle(was); await wait(); }
  const restore = CALLS.find(c => c.action === "restore");
  say("the final Yes calls restore", !!restore);
  say("it sends the confirmation string", restore && restore.confirm === "RESTORE");
  say("the server's half is back", JSON.stringify(SERVER) === JSON.stringify(file.server));
  say("the browser's half is back",
      getComputedStyle(document.documentElement).getPropertyValue("--green").trim() === "#123456");
  say("the swatch shows it too",
      document.querySelector('#swatches input[data-key="--green"]').value === "#123456");
  say("localStorage has it",
      (JSON.parse(localStorage.getItem("options")) || {})["--green"] === "#123456");
  say("the page reloaded its periods", CALLS.filter(c => c.action === "periods").length === 1);
  say("it reports what landed", said().className === "ok" &&
      said().textContent.includes("1 month(s)"), said().textContent);
  say("the downloaded file carries the rules", file.rules === RULES);
  say("a file made with these same rules says nothing more",
      !/different rules/.test(said().textContent), said().textContent);

  const foreign = JSON.parse(CAPTURED.body);
  foreign.rules = RULES + "# another household\n";
  await chooseFile(JSON.stringify(foreign), "from-the-phone.json");
  { const was = said().innerHTML; drop(btn("apply")); await settle(was); }
  await armed();
  { const was = said().innerHTML; drop(btn("yes")); await settle(was); await wait(); }
  say("a file with other rules is still restored, and says its months read by this app's rules",
      said().className === "ok" && /different rules/.test(said().textContent)
        && /this app's own rules/.test(said().textContent), said().textContent);

  const nasty = JSON.parse(CAPTURED.body);
  nasty.page.options = {
    "--green": '#111"><img src=x onerror="window.PWNED=1">',
    "--fs-major": "30px",
    "--not-a-setting": "#abcdef",
    "--red": { evil: true },
  };
  await chooseFile(JSON.stringify(nasty), "hostile.json");
  { const was = said().innerHTML; drop(btn("apply")); await settle(was); }
  await armed();
  { const was = said().innerHTML; drop(btn("yes")); await settle(was); await wait(); }
  say("nothing from the file ran", !window.PWNED);
  say("no markup reached the panel", !document.getElementById("swatches").querySelector("img"));
  const kept = JSON.parse(localStorage.getItem("options")) || {};
  say("only what the gear itself can mean is kept",
      JSON.stringify(kept) === JSON.stringify({ "--fs-major": "30px" }), JSON.stringify(kept));
  say("the swatch fell back to its default",
      getComputedStyle(document.documentElement).getPropertyValue("--green").trim() === "#3f9d5a");

  FAIL_PERIODS = true;
  await chooseFile(CAPTURED.body, "budget-backup-2026-02-14.json");
  { const was = said().innerHTML; drop(btn("apply")); await settle(was); }
  await armed();
  { const was = said().innerHTML; drop(btn("yes")); await settle(was); await wait(); }
  say("a failed reload does not deny the restore that happened",
      said().textContent.includes("Restored 1 month(s)"), said().textContent);
  say("and it says the page is behind", said().textContent.includes("refresh"));

  SERVER.periods["salary:2"] = "12.07\n850 fuel\n";
  SERVER.years["salary:2"] = 2026;
  PERIODS = await call({ action: "periods" });
  fillPeriods();
  document.getElementById("period").value = "July";
  say("a second month can be shown", document.getElementById("period").value === "July");
  await chooseFile(CAPTURED.body, "budget-backup-2026-02-14.json");
  { const was = said().innerHTML; drop(btn("apply")); await settle(was); }
  await armed();
  { const was = said().innerHTML; drop(btn("yes")); await settle(was); await wait(); }
  const sel = document.getElementById("period");
  say("the selector lands on a month that exists",
      sel.value !== "" && sel.selectedIndex >= 0 &&
      PERIODS.some(p => p.month === sel.value),
      sel.value + " / " + sel.selectedIndex + " / " + JSON.stringify(PERIODS.map(p => p.month)));

  document.title = LOG.some(l => l.startsWith("FAIL")) ? "SOME FAILED" : "ALL PASSED";
  document.body.innerHTML = "<pre id='out'>" + LOG.join("\n") + "</pre>";
})();
