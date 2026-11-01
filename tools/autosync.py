#!/usr/bin/env python3
"""Unattended sheet → app sync, run by .github/workflows/sync.yml.

  python3 tools/autosync.py data/sheet.json      apply the sheet snapshot to data/trip.json; prints a commit summary

data/sheet.json is written by the Apps Script in the Google Sheet (tools/sheet-push.gs):
  {"revision": "<ISO time of the push>", "values": [[cell, ...], ...]}   (columns A–F and L only)

It runs `sync.py auto`, then settles the review points that sync.py leaves for a person, without judgement calls:
  - new stop: link an existing place with the same name, else add a place from the row (name + first address
    line, no coordinates, so the app's buttons fall back to a Google Maps search)
  - renamed stop: keep the places whose name is still in the row, else the same as a new stop
  - new check-in row: that night's hotel (and "(n nt)" nights) point at it
  - removed stops: applied, unless an implausible number go at once (then nothing is applied; exit 3)
Anything a person may want to tidy (coordinates, Japanese names) is listed under "review" in data/sync-state.json.
A snapshot whose revision is already in sync-state.json is skipped, so pushes of other files can't roll the app back.
Exit 0 = applied or nothing to do, 2 = sheet unreadable, 3 = refused (too many deletions).
"""
import json, os, re, sys, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync

MAX_DELETES = 8


def place_name(title):
    name = title.split(' · ')[-1] if ' · ' in title else title
    return re.sub(r'\s*\((\d+\s*nts?|if [^)]*)\)\s*$', '', name).strip()


def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')[:24] or 'place'


def same(a, b):
    a, b = sync.norm(a), sync.norm(b)
    return a == b or (min(len(a), len(b)) >= 6 and (a in b or b in a))


def auto_place(d, fields, new_places, ops_out):
    """Return a place id for a row, reusing or adding one. None for travel rows or rows with no usable name."""
    title, how = fields.get('title', ''), fields.get('how', '')
    if sync.kind(title) == 'travel': return None
    name = place_name(title)
    if not name: return None
    for pid, p in list(d['places'].items()) + list(new_places.items()):
        if same(p.get('en', ''), name): return pid
    first = how.split('\n')[0].strip()
    addr = '' if ('→' in first or first.lower().startswith(('walk', 'drive', 'taxi', 'train', 'bus'))) else first
    pid, k = slug(name), 2
    while pid in d['places'] or pid in new_places: pid, k = '%s_%d' % (slug(name), k), k + 1
    f = {'en': name, 'addr': addr}
    new_places[pid] = f
    ops_out.append({'op': 'place.add', 'id': pid, 'fields': f})
    return pid


def describe(d, ops):
    titles = {it['id']: it['title'] for day in d['days'] for it in day['items']}
    dates = {it['id']: day['date'] for day in d['days'] for it in day['items']}
    tasks = {t['id']: t['task'] for t in d['todo']}
    dd = lambda s: '%d Nov' % int(s[-2:]) if s else ''
    out = []
    for o in ops:
        f = o.get('fields', {})
        if o['op'] == 'item.set':
            out.append('%s %s: %s' % (dd(dates.get(o['id'], '')), f.get('title') or titles.get(o['id'], o['id']), ', '.join(k for k in f if k != 'places')))
        elif o['op'] == 'item.add': out.append('%s added: %s' % (dd(o['date']), f.get('title')))
        elif o['op'] == 'item.delete': out.append('%s removed: %s' % (dd(dates.get(o['id'], '')), titles.get(o['id'])))
        elif o['op'] == 'item.move': out.append('moved to %s: %s' % (dd(o['date']), titles.get(o['id'])))
        elif o['op'] == 'todo.set': out.append('to-do %s: %s' % ('done' if f.get('done') else 'edited', f.get('task') or tasks.get(o['id'])))
        elif o['op'] == 'todo.add': out.append('to-do added: %s' % f.get('task'))
        elif o['op'] == 'todo.delete': out.append('to-do removed: %s' % tasks.get(o['id']))
        elif o['op'] == 'day.set': out.append('%s hotel → %s' % (dd(o['date']), f.get('hotel')))
    return out


def main():
    src = sys.argv[1]
    snap = json.load(open(src, encoding='utf-8'))
    rev = snap.get('revision', '')
    state = json.load(open(sync.STATE)) if os.path.exists(sync.STATE) else {}
    if rev and rev == state.get('sheetRevision'):
        print('no app-visible changes'); return  # snapshot already applied; never re-apply an old one over newer edits
    d = json.load(open(sync.DATA, encoding='utf-8'))
    patch = sync.auto(d, src, rev)
    if any(r.startswith('could not read any stops') for r in patch['review']):
        print('Sheet snapshot has no stops; nothing applied'); sys.exit(2)
    ops, notes, new_places, pre = patch['ops'], [], {}, []
    dels = [o for o in ops if o['op'] == 'item.delete']
    if len(dels) > MAX_DELETES:
        print('Refused: the snapshot would remove %d stops at once (limit %d); nothing applied' % (len(dels), MAX_DELETES)); sys.exit(3)
    items = {it['id']: it for day in d['days'] for it in day['items']}
    hotel_days = []
    for o in ops:
        f = o.get('fields', {})
        if o['op'] == 'item.add':
            pid = auto_place(d, f, new_places, pre)
            f['places'] = [pid] if pid else []
            if pid and pid in new_places: notes.append('place %s ("%s") added without coordinates' % (pid, new_places[pid]['en']))
            if f['title'].lower().startswith('check in') and pid: hotel_days.append((o['date'], f['title'], pid))
        elif o['op'] == 'item.set' and 'title' in f:
            it = items[o['id']]
            if sync.difflib.SequenceMatcher(None, sync.norm(it['title']), sync.norm(f['title'])).ratio() >= 0.8: continue
            text = f['title'] + ' ' + f.get('how', it.get('how', ''))
            keep = [p for p in it.get('places', []) if same(d['places'][p].get('en', ''), place_name(f['title'])) or sync.norm(d['places'][p].get('en', '')) in sync.norm(text)]
            if not keep:
                pid = auto_place(d, f | {'how': f.get('how', it.get('how', ''))}, new_places, pre)
                keep = [pid] if pid else []
                if pid and pid in new_places: notes.append('place %s ("%s") added without coordinates' % (pid, new_places[pid]['en']))
            if keep != it.get('places', []): f['places'] = keep
            if f['title'].lower().startswith('check in') and keep: hotel_days.append((dates_of(d, o['id']), f['title'], keep[0]))
    dates = [day['date'] for day in d['days']]
    hotel_ops = []
    for date, title, pid in hotel_days:
        m = re.search(r'\((\d+)\s*nts?\)', title)
        n = int(m.group(1)) if m else 1
        i = dates.index(date)
        for dt in dates[i:i + n]: hotel_ops.append({'op': 'day.set', 'date': dt, 'fields': {'hotel': pid}})
    notes += [r for r in patch['review'] if r.startswith('sheet has a day')]
    patch['ops'] = pre + ops + hotel_ops
    patch['reviewed'] = True
    summary = describe(d, ops + hotel_ops)
    if patch['ops']:  # with no ops, leave trip.json (and its "updated" date) alone
        sync.apply(d, patch)
        json.dump(d, open(sync.DATA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    now = sync.datetime.datetime.now(sync.datetime.timezone.utc)
    st = {'sheetRevision': rev, 'syncedAt': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'ops': len(patch['ops'])}
    if notes or state.get('review'): st['review'] = state.get('review', []) + notes
    json.dump(st, open(sync.STATE, 'w'), indent=1, ensure_ascii=False)
    print('\n'.join(summary) if summary else 'no app-visible changes')


def dates_of(d, iid):
    for day in d['days']:
        if any(it['id'] == iid for it in day['items']): return day['date']


if __name__ == '__main__':
    main()
