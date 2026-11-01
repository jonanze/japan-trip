# Sheet → app sync

The Google Sheet **"Japan Nov 2026"** (id `1DEfa1xDX_tnHuwyS_R9OV_8LuLdtXnTj2Oz0VeofrMY`, tab `Sheet1`) is the single source of truth.
`data/trip.json` is the app's copy of it, plus things the sheet doesn't hold: place coordinates, Japanese names, map codes,
day headings, the hotel each night, and Google Maps travel modes.

## How it runs (automatic, since 1 Nov 2026)

1. **Apps Script in the sheet** (`tools/sheet-push.gs`, pasted into Extensions → Apps Script, "Trip app" menu).
   On every edit in the sheet, and every minute to catch edits made through the Sheets API, it reads columns A–F and L
   (cost columns and the notes block under TOTALS are left out) and, if they changed, writes `data/sheet.json` to `main`
   with the GitHub Contents API. Token: a fine-grained PAT (Contents read/write on this repo only) kept in the script's
   user properties, never in the code or the repo.
2. **GitHub Action** `.github/workflows/sync.yml` runs on that push:
   `python3 tools/autosync.py data/sheet.json` → `node tools/build.js` → commit `data/ index.html sw.js manifest` → push
   (the push itself starts the Pages deploy). The phone app updates ~1–2 min after the edit (when the phone is online and the app reopens).
3. `tools/autosync.py` wraps `sync.py auto` and settles its review points without judgement:
   - new or renamed stops get an existing place with the same name, else a new place from the row's name and first
     address line, with no coordinates (the app falls back to a Google Maps search);
   - a new check-in row sets that night's hotel (and "(n nt)" nights);
   - more than 8 stops removed at once is refused (workflow fails, GitHub emails Jonan, nothing applied);
   - a snapshot whose revision is already in `data/sync-state.json` is skipped, so a push of other files never rolls the app back.
   Places it adds are listed under `"review"` in `data/sync-state.json` for a person to tidy.

## The Claude-app copy (artifact)

GitHub can't publish the Artifact https://claude.ai/artifact/28vtak4L17FNue2WPbvhC6 . The hourly Claude routine
refreshes it: `git pull`, `node tools/build.js --artifact /tmp/japan-artifact.html`, read the artifact, compare its
trip-data with `data/trip.json`, and publish with `capabilities: {}` only if they differ.

## Tidying `review` items (Claude, when asked or in the routine)

For each place under `"review"` in `data/sync-state.json`, add `ja`, `addr` (Japanese, with 〒), `tel`, `mc`, and
`lat`/`lng` only if sure (official site or Google Maps), with a `place.set` patch via `python3 tools/sync.py apply`.
Wrong coordinates are worse than none. Then remove the item from `"review"`, `node tools/build.js`, commit and push.

## Rules for hand edits

- Change the itinerary in the sheet, not in `data/trip.json`. The app follows within minutes.
- Don't hand-sync with `sync.py auto` any more; if the app looks stale, use the sheet's **Trip app → Push to app now**.
- `sync.py apply` is still the only way to edit `data/trip.json` (places, modes, day headings). Never edit `index.html` by hand.
- Don't touch `contacts`, `title` or `travellers`. Never delete places.

## Sheet layout → app fields

| Sheet column | App field |
|---|---|
| A Date (only on a day's first row) | day |
| C Time | `time` |
| D Activity | `title` |
| E Address / Transit | `how` |
| F Remarks | `notes` |
| L Payment / Action | `action` |

Rows end at the TOTALS row. The TO-DO block comes after "TO-DO / BOOKINGS": A ✔ (TRUE/FALSE) → `done`, B → `task`,
E → `how`, F → `by`. Text is copied verbatim; line breaks become `\n`, and times at the start of a notes line become a timeline.
