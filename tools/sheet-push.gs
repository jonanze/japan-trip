/**
 * Japan trip: push the itinerary sheet to the iPhone app.
 * Paste into the sheet's Extensions → Apps Script (Code.gs), save, reload the sheet, then use the "Trip app" menu.
 * Every edit (and every minute, to catch edits made through the API) it writes columns A–F and L to
 * data/sheet.json in github.com/jonanze/japan-trip; a GitHub Action there rebuilds and publishes the app.
 * Cost columns (G–K) and the notes block under TOTALS never leave the sheet.
 * @OnlyCurrentDoc
 */
var REPO = 'jonanze/japan-trip', FILE = 'data/sheet.json', TAB = 'Sheet1', KEEP = [0, 1, 2, 3, 4, 5, 11];

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Trip app')
    .addItem('Set GitHub token…', 'setToken')
    .addItem('Turn on auto-push', 'turnOn')
    .addItem('Push to app now', 'pushNow')
    .addItem('Status', 'status')
    .addItem('Turn off auto-push', 'turnOff')
    .addToUi();
}

function setToken() {
  var ui = SpreadsheetApp.getUi();
  var r = ui.prompt('GitHub token', 'Paste the fine-grained token for jonanze/japan-trip', ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK || !r.getResponseText().trim()) return;
  PropertiesService.getUserProperties().setProperty('GITHUB_TOKEN', r.getResponseText().trim());
  ui.alert('Token saved. Now choose Trip app → Turn on auto-push.');
}

function turnOn() {
  removeTriggers_();
  ScriptApp.newTrigger('onSheetChange').forSpreadsheet(SpreadsheetApp.getActive()).onChange().create();
  ScriptApp.newTrigger('everyMinute').timeBased().everyMinutes(1).create();
  SpreadsheetApp.getUi().alert('Auto-push on. ' + run_(true));
}

function turnOff() {
  removeTriggers_();
  SpreadsheetApp.getUi().alert('Auto-push off.');
}

function pushNow() { SpreadsheetApp.getUi().alert(run_(true)); }

function status() {
  var p = PropertiesService.getScriptProperties();
  var n = ScriptApp.getProjectTriggers().length;
  SpreadsheetApp.getUi().alert('Auto-push ' + (n ? 'on' : 'off') + '\nLast push: ' + (p.getProperty('lastPush') || 'never') +
    '\nLast result: ' + (p.getProperty('lastResult') || '-'));
}

function onSheetChange() { run_(false); }
function everyMinute() { run_(false); }

function removeTriggers_() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
}

/** Columns A–F and L, itinerary and to-do rows only; the notes block under TOTALS is blanked. */
function snapshot_(values) {
  var out = [], zone = 'trip';
  values.forEach(function (r) {
    r = r.map(function (c) { return String(c); });
    if (zone === 'trip' && r[2] === 'TOTALS') { zone = 'notes'; out.push(['', '', 'TOTALS']); return; }
    if (zone === 'notes') {
      if (r[0].indexOf('TO-DO') === 0) { zone = 'todo'; out.push(['TO-DO']); } else out.push([]);
      return;
    }
    var row = r.map(function (c, i) { return KEEP.indexOf(i) >= 0 ? c : ''; });
    while (row.length && row[row.length - 1] === '') row.pop();
    out.push(row);
  });
  while (out.length && !out[out.length - 1].length) out.pop();
  return out;
}

function run_(force) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(force ? 20000 : 2000)) return 'Busy, try again.';
  var props = PropertiesService.getScriptProperties();
  try {
    var token = PropertiesService.getUserProperties().getProperty('GITHUB_TOKEN');
    if (!token) return 'No GitHub token: choose Trip app → Set GitHub token… first.';
    var sh = SpreadsheetApp.getActive().getSheetByName(TAB);
    var values = snapshot_(sh.getRange(1, 1, Math.max(sh.getLastRow(), 1), 12).getDisplayValues());
    var body = JSON.stringify(values);
    var hash = Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, body, Utilities.Charset.UTF_8));
    if (!force && hash === props.getProperty('lastHash')) return 'No change since the last push.';
    var rev = new Date().toISOString();
    var json = '{"revision":' + JSON.stringify(rev) + ',\n"values":[\n' +
      values.map(function (r) { return JSON.stringify(r); }).join(',\n') + '\n]}\n';
    var res = put_(token, json, 'Sheet edit ' + Utilities.formatDate(new Date(), 'Asia/Singapore', 'd MMM HH:mm') + ' SGT');
    if (res === 409 || res === 422) res = put_(token, json, 'Sheet edit (retry)');
    var msg = res === 200 || res === 201 ? 'Pushed to the app; live in ~2 min.' :
      res === 401 || res === 403 ? 'GitHub refused the token (' + res + '): make a new one and use Set GitHub token…' :
      'GitHub error ' + res + '; will retry on the next edit or minute.';
    props.setProperty('lastResult', msg);
    if (res === 200 || res === 201) {
      props.setProperty('lastHash', hash);
      props.setProperty('lastPush', Utilities.formatDate(new Date(), 'Asia/Singapore', 'd MMM yyyy HH:mm:ss') + ' SGT');
    } else if (!force) {
      throw new Error(msg); // Google emails the sheet owner a failure summary
    }
    return msg;
  } finally {
    lock.releaseLock();
  }
}

function put_(token, json, message) {
  var url = 'https://api.github.com/repos/' + REPO + '/contents/' + FILE;
  var h = { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' };
  var cur = UrlFetchApp.fetch(url + '?ref=main', { headers: h, muteHttpExceptions: true });
  var payload = { message: message, branch: 'main', content: Utilities.base64Encode(json, Utilities.Charset.UTF_8) };
  if (cur.getResponseCode() === 200) payload.sha = JSON.parse(cur.getContentText()).sha;
  else if (cur.getResponseCode() !== 404) return cur.getResponseCode();
  return UrlFetchApp.fetch(url, { method: 'put', headers: h, contentType: 'application/json',
    payload: JSON.stringify(payload), muteHttpExceptions: true }).getResponseCode();
}
