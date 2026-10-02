# Hourly sync: Google Sheet → iPhone app

The Google Sheet **"Japan Nov 2026"** (id `1DEfa1xDX_tnHuwyS_R9OV_8LuLdtXnTj2Oz0VeofrMY`, tab `Sheet1`) is the single source of truth.
`data/trip.json` is the app's copy of it, plus things the sheet doesn't hold: place coordinates, Japanese names, map codes,
day headings, the hotel each night, and Google Maps travel modes. The scheduled routine keeps the two in step.

## Steps

1. Clone this repo. Run `python3 tools/sync.py state` and read `sheetRevision`.
2. Read the sheet's Drive `modifiedTime` (Google Drive `get_file_metadata`, `excludeContentSnippets: true`).
   If it equals `sheetRevision`, stop. Nothing changed, so do not commit.
3. Read the sheet: `get_values` on `Sheet1!A1:L200`. Run `python3 tools/sync.py rows` for the app's current version.
4. Compare row by row and field by field. Changes are usually small (a time, a word, a phone number), so check every field;
   don't skim.
5. Write `/tmp/patch.json` with ops (see the header of `tools/sync.py`) and `"sheetRevision": <modifiedTime>`.
   Run `python3 tools/sync.py apply /tmp/patch.json`, then `node tools/build.js`.
   Re-run `python3 tools/sync.py rows` and confirm the changed rows now match the sheet exactly.
6. Commit `data/ index.html sw.js manifest.webmanifest` with a message listing what changed, and push to `main`.
   Pages publishes within a couple of minutes.
   If the comparison found no app-visible change (formatting or cost cells only), still apply an empty patch so that
   `sheetRevision` advances, then commit.

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
