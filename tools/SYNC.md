# Hourly sync: Google Sheet → iPhone app

The Google Sheet **"Japan Nov 2026"** (id `1DEfa1xDX_tnHuwyS_R9OV_8LuLdtXnTj2Oz0VeofrMY`, tab `Sheet1`) is the single source of truth.
`data/trip.json` is the app's copy of it, plus things the sheet doesn't hold: place coordinates, Japanese names, map codes,
day headings, the hotel each night, and Google Maps travel modes. The scheduled routine keeps the two in step.

## Steps

1. Clone this repo. Run `python3 tools/sync.py state` and read `sheetRevision`.
2. Read the sheet's Drive `modifiedTime` (Google Drive `get_file_metadata`, `excludeContentSnippets: true`).
   If it equals `sheetRevision`, stop. Nothing changed, so do not commit.
3. Read the sheet with **exactly** this call, so the result is large enough to be saved to a file:
   Google Sheets `get_spreadsheet`, with these arguments:
   - `spreadsheetId` 1DEfa1xDX_tnHuwyS_R9OV_8LuLdtXnTj2Oz0VeofrMY
   - `includeGridData: true`
   - `ranges: ["Sheet1!A1:L200"]`
   - `fields: ["sheets.data.rowData.values.formattedValue", "sheets.data.rowData.values.userEnteredValue"]`

   The tool reports the path of the saved file. If it comes back inline instead, write that JSON to a file.
4. Run `python3 tools/sync.py auto <saved file> <modifiedTime> > /tmp/patch.json`. It matches sheet rows to stops and to-dos and writes every text change as ops. Then read its `"review"` list:
   - **NEW STOP**: fill that op's `"places"` (rules below) and add any `place.add` ops before it.
   - **REMOVED STOP**: check the row is really gone from the sheet and wasn't just renamed beyond recognition. If it was renamed, swap the delete+add for an `item.set` on the old id.
   - If a check-in row changed, add the `day.set` hotel ops.
   - Then set `"reviewed": true`. If `review` is empty, apply it as is.
5. Run `python3 tools/sync.py apply /tmp/patch.json`, then `node tools/build.js`. If `ops` was empty, still apply it, so that `sheetRevision` advances.
6. Commit `data/ index.html sw.js manifest.webmanifest` with a message listing what changed, and push to `main`.
   Pages publishes within a couple of minutes.
7. Only when ops were applied: refresh the view-only Claude-app copy.
   - Run `node tools/build.js --artifact /tmp/japan-artifact.html`.
   - Publish it with the Artifact tool to https://claude.ai/artifact/28vtak4L17FNue2WPbvhC6 . Read that URL first, then use `capabilities: {}` so it stays view-only.
   - Skip this step if the Artifact tool is unavailable.

## Sheet layout → app fields

Columns:

| Sheet column | App field |
|---|---|
| A Date (only on a day's first row) | day |
| C Time | `time` |
| D Activity | `title` |
| E Address / Transit | `how` |
| F Remarks | `notes` |
| L Payment / Action | `action` |

- Ignore the cost columns (G, H, J, K) and the booking column (I).
- Rows end at the TOTALS row. Notes rows follow it.
- The TO-DO block comes after "TO-DO / BOOKINGS":
  - column A ✔ (TRUE/FALSE) → `done`
  - B → `task`
  - E → `how`
  - F → `by`
- Copy text **verbatim**, keeping line breaks as `\n`. The app shows `how` and `notes` line by line. Times like `05:55` at the start of a notes line become a timeline.

## Rules

- Stops keep their `id`. Match sheet rows to stops by day and order, then by title.
- If a row moved to another day, use `item.move` rather than delete + add, so its place links survive.
- A **new row** needs places so its Directions and taxi buttons work:
  - Reuse an existing place id when the row is at a place already in `data/trip.json`.
  - Otherwise use `place.add` with `en`, `ja` (Japanese name), `addr` (Japanese address with 〒 if known), `tel` and `mc` (from the sheet if given).
  - Add `lat`/`lng` only if you are sure of them, for example from the official site or Google Maps.
  - With no coordinates, the app falls back to a Google Maps search on the name and address. That is acceptable; wrong coordinates are not.
- **Check-in rows**: if a new "Check in · X" row replaces a hotel, `day.set` that night's `hotel`, and the following nights' too, until the next check-in.
- **Deleted rows**: use `item.delete`. Never delete places.
- Don't touch `contacts`, `title` or `travellers`. Don't edit `index.html` by hand; `tools/build.js` writes it.
- If the patch is rejected, fix the patch rather than editing `trip.json` by hand.
- If you're unsure what a change means, apply the plain reading. Mention it in the commit message.
