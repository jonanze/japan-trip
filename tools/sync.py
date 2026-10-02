#!/usr/bin/env python3
"""Sheet → app sync helper (used by the scheduled Claude routine; see tools/SYNC.md).

  python3 tools/sync.py rows             print the app's stops and to-dos laid out like the sheet's columns
  python3 tools/sync.py apply PATCH.json apply a patch (ops below), validate, rewrite data/trip.json
  python3 tools/sync.py state            print the last synced sheet revision
  python3 tools/sync.py auto SHEET.json REVISION   compare a saved sheet read with the app and write the patch to
                                         stdout (SHEET.json = saved get_spreadsheet grid data or get_values output)

Patch: {"sheetRevision": "...", "ops": [ ... ]}
  {"op":"item.set",    "id":"i45", "fields":{"time","title","how","notes","action","mode","places"}}
  {"op":"item.add",    "date":"2026-11-16", "after":"i45" | null, "fields":{...same...}}
  {"op":"item.delete", "id":"i46"}
  {"op":"item.move",   "id":"i46", "date":"2026-11-17", "after":"i47" | null}
  {"op":"day.set",     "date":"2026-11-16", "fields":{"sub","hotel","en","ja","mode"}}
  {"op":"place.add",   "id":"new_id", "fields":{"en","ja","addr","lat","lng","mc","tel"}}
  {"op":"place.set",   "id":"marui", "fields":{...}}
  {"op":"todo.set",    "id":"t03", "fields":{"task","how","by","done"}}
  {"op":"todo.add",    "after":"t02" | null, "fields":{...}}
  {"op":"todo.delete", "id":"t03"}
An empty "action" removes it. "after": null puts the stop first in its day.
"""
import json, sys, os, datetime

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
DATA = os.path.join(ROOT, 'data', 'trip.json')
STATE = os.path.join(ROOT, 'data', 'sync-state.json')
ITEM_F = {'time', 'title', 'how', 'notes', 'action', 'mode', 'places'}
DAY_F = {'sub', 'hotel', 'en', 'ja', 'mode'}
PLACE_F = {'en', 'ja', 'addr', 'lat', 'lng', 'mc', 'tel'}
TODO_F = {'task', 'how', 'by', 'done'}
MODES = {'transit', 'walking', 'driving'}


def kind(title):  # same rules the app was first built with
    t = title.lower()
    if t.startswith(('check in', 'drop bags')): return 'stay'
    if t.startswith(('lunch', 'dinner', 'late lunch', 'last dinner', 'onsen + ', 'crab', 'café', 'cafe', 'breakfast')): return 'food'
    if t.startswith(('transit', 'shuttle', 'depart', 'arrive', 'leave', 'return', 'check out', 'day trip')): return 'travel'
    if t.startswith(('relax', 'free afternoon')): return 'rest'
    return 'visit'


def fail(msg):
    sys.exit('PATCH REJECTED: ' + msg)


def find_item(d, iid):
    for day in d['days']:
        for k, it in enumerate(day['items']):
            if it['id'] == iid: return day, k
    fail('no stop with id %s' % iid)


def find_day(d, date):
    for day in d['days']:
        if day['date'] == date: return day
    fail('no day %s' % date)


def check_fields(f, allowed, what):
    bad = set(f) - allowed
    if bad: fail('%s: unknown fields %s' % (what, sorted(bad)))


def set_item_fields(d, it, f):
    check_fields(f, ITEM_F, 'stop ' + it.get('id', 'new'))
    for k, v in f.items():
        if k == 'places':
            if not isinstance(v, list) or any(p not in d['places'] for p in v): fail('stop %s: unknown place in %s' % (it.get('id'), v))
            it['places'] = v
        elif k == 'mode':
            if v and v not in MODES: fail('bad mode %s' % v)
            if v: it['mode'] = v
            else: it.pop('mode', None)
        elif k == 'action':
            if v: it['action'] = str(v)
            else: it.pop('action', None)
        else:
            it[k] = str(v)
    it['kind'] = kind(it.get('title', ''))


def next_id(existing, prefix):
    n = max([int(x[1:]) for x in existing if x[1:].isdigit()] + [0]) + 1
    return '%s%02d' % (prefix, n)


def insert_after(lst, obj, after, what):
    if after is None: lst.insert(0, obj); return
    for k, x in enumerate(lst):
        if x['id'] == after: lst.insert(k + 1, obj); return
    fail('%s: "after" id %s is not in that list' % (what, after))


def apply(d, patch):
    for op in patch.get('ops', []):
        o, f = op.get('op'), op.get('fields', {})
        if o == 'item.set':
            day, k = find_item(d, op['id']); set_item_fields(d, day['items'][k], f)
        elif o == 'item.add':
            day = find_day(d, op['date'])
            if not f.get('title'): fail('item.add needs a title')
            ids = [it['id'] for dd in d['days'] for it in dd['items']]
            it = {'id': next_id(ids, 'i'), 'time': '', 'title': '', 'kind': 'visit', 'how': '', 'notes': '', 'places': []}
            set_item_fields(d, it, f)
            insert_after(day['items'], it, op.get('after'), 'item.add')
        elif o == 'item.delete':
            day, k = find_item(d, op['id']); day['items'].pop(k)
        elif o == 'item.move':
            day, k = find_item(d, op['id']); it = day['items'].pop(k)
            insert_after(find_day(d, op['date'])['items'], it, op.get('after'), 'item.move')
        elif o == 'day.set':
            day = find_day(d, op['date']); check_fields(f, DAY_F, 'day ' + op['date'])
            if 'hotel' in f and f['hotel'] and f['hotel'] not in d['places']: fail('unknown hotel place %s' % f['hotel'])
            if 'mode' in f and f['mode'] not in MODES: fail('bad mode')
            day.update({k: str(v) for k, v in f.items()})
        elif o in ('place.add', 'place.set'):
            pid = op['id']; check_fields(f, PLACE_F, 'place ' + pid)
            if o == 'place.add':
                if pid in d['places']: fail('place %s already exists' % pid)
                d['places'][pid] = {'en': '', 'ja': '', 'addr': '', 'lat': '', 'lng': '', 'mc': '', 'tel': ''}
            elif pid not in d['places']: fail('no place %s' % pid)
            p = d['places'][pid]
            for k, v in f.items():
                if k in ('lat', 'lng'):
                    if v in ('', None): p[k] = ''
                    else:
                        v = float(v)
                        if not (20 < v < 50 if k == 'lat' else 100 < v < 150): fail('place %s: %s %s outside Japan/Singapore' % (pid, k, v))
                        p[k] = v
                else: p[k] = str(v)
            if not (p['en'] or p['ja']): fail('place %s needs a name' % pid)
        elif o == 'todo.set':
            t = next((t for t in d['todo'] if t['id'] == op['id']), None)
            if not t: fail('no to-do %s' % op['id'])
            check_fields(f, TODO_F, 'to-do'); t.update({k: (bool(v) if k == 'done' else str(v)) for k, v in f.items()})
        elif o == 'todo.add':
            check_fields(f, TODO_F, 'to-do')
            t = {'id': next_id([t['id'] for t in d['todo']], 't'), 'task': '', 'how': '', 'by': '', 'done': False}
            t.update({k: (bool(v) if k == 'done' else str(v)) for k, v in f.items()})
            insert_after(d['todo'], t, op.get('after'), 'todo.add')
        elif o == 'todo.delete':
            n = len(d['todo']); d['todo'] = [t for t in d['todo'] if t['id'] != op['id']]
            if len(d['todo']) == n: fail('no to-do %s' % op['id'])
        else:
            fail('unknown op %r' % o)
    # integrity: every stop has a title, every place link and hotel resolves
    for day in d['days']:
        for it in day['items']:
            if not it.get('title'): fail('stop %s has no title' % it['id'])
            for p in it.get('places', []):
                if p not in d['places']: fail('stop %s links missing place %s' % (it['id'], p))
    d['updated'] = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime('%-d %b %Y')


def rows(d):
    esc = lambda s: str(s).replace('\n', ' ⏎ ')
    for day in d['days']:
        print('=== %s (%s) · %s · hotel=%s · mode=%s' % (day['label'], day['date'], day['sub'], day.get('hotel') or '-', day['mode']))
        for it in day['items']:
            print('%s | %s | %s' % (it['id'], esc(it['time']), esc(it['title'])))
            print('    how: %s' % esc(it['how']))
            print('    notes: %s' % esc(it['notes']))
            if it.get('action'): print('    action: %s' % esc(it['action']))
            print('    places: %s%s' % (', '.join(it['places']) or '-', ('  mode=' + it['mode']) if it.get('mode') else ''))
    print('=== TO-DO')
    for t in d['todo']:
        print('%s | %s | %s | how: %s | by: %s' % (t['id'], 'DONE' if t['done'] else 'open', esc(t['task']), esc(t['how']), esc(t['by'])))


# ---------- automatic sheet comparison ----------
import difflib, re

MONTHS = {'Nov': '11', 'Oct': '10', 'Dec': '12'}


def sheet_matrix(path):
    j = json.load(open(path, encoding='utf-8'))
    if 'values' in j and isinstance(j['values'], list):
        return [[str(c) for c in r] for r in j['values']]
    out = []
    for r in j['sheets'][0]['data'][0].get('rowData', []):
        out.append([c.get('formattedValue', '') if isinstance(c, dict) else '' for c in r.get('values', [])])
    return out


def cell(r, i):
    return r[i].strip() if i < len(r) and r[i] is not None else ''


def parse_sheet(m, year):
    days, todo, cur, mode = {}, [], None, 'trip'
    for r in m[2:]:
        a = cell(r, 0)
        if mode == 'trip':
            if cell(r, 2) == 'TOTALS': mode = 'notes'; continue
            mm = re.match(r'^(\d{1,2}) (\w{3})$', a)
            if mm and mm.group(2) in MONTHS:
                cur = '%s-%s-%02d' % (year, MONTHS[mm.group(2)], int(mm.group(1)))
            if not cell(r, 3) or not cur: continue
            days.setdefault(cur, []).append({'time': cell(r, 2), 'title': cell(r, 3), 'how': cell(r, 4), 'notes': cell(r, 5), 'action': cell(r, 11)})
        elif mode == 'notes':
            if a.startswith('TO-DO'): mode = 'todohead'
        elif mode == 'todohead':
            mode = 'todo'
        else:
            if not cell(r, 1): continue
            todo.append({'task': cell(r, 1), 'how': cell(r, 4), 'by': cell(r, 5), 'done': a.upper() in ('TRUE', '✔', 'YES', 'DONE')})
    return days, todo


def norm(t):
    return re.sub(r'\W+', ' ', t.lower()).strip()


def pair(old, new, key):
    """Order-preserving match of two lists by title similarity: list of (old_idx|None, new_idx|None)."""
    sm = difflib.SequenceMatcher(None, [norm(key(x)) for x in old], [norm(key(x)) for x in new], autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
            out += list(zip(range(i1, i2), range(j1, j2)))
        else:  # unequal block: pair the most similar titles, rest become delete / add
            olds, news, used = list(range(i1, i2)), list(range(j1, j2)), set()
            for i in olds:
                best = max(news, key=lambda j: difflib.SequenceMatcher(None, norm(key(old[i])), norm(key(new[j]))).ratio(), default=None)
                if best is not None and best not in used and difflib.SequenceMatcher(None, norm(key(old[i])), norm(key(new[best]))).ratio() >= 0.6:
                    used.add(best); out.append((i, best))
                else: out.append((i, None))
            out += [(None, j) for j in news if j not in used]
    return out


def auto(d, path, revision):
    days, todo = parse_sheet(sheet_matrix(path), d['days'][0]['date'][:4])
    ops, review, adds, dels = [], [], [], []
    for day in d['days']:
        rows_ = days.get(day['date'], [])
        prev = None
        for oi, ni in pair(day['items'], rows_, lambda x: x['title']):
            if oi is not None and ni is not None:
                it, row = day['items'][oi], rows_[ni]
                f = {k: row[k] for k in ('time', 'title', 'how', 'notes') if row[k] != it.get(k, '')}
                if row['action'] != it.get('action', ''): f['action'] = row['action']
                if f: ops.append({'op': 'item.set', 'id': it['id'], 'fields': f})
                if 'title' in f and difflib.SequenceMatcher(None, norm(it['title']), norm(row['title'])).ratio() < 0.8:
                    review.append('RENAMED STOP %s (%s) "%s" -> "%s": check its "places" (now %s) still fit' % (day['date'], it['id'], it['title'], row['title'], it['places']))
            elif oi is not None:
                dels.append((day['date'], day['items'][oi]))
            else:
                after = None
                for o2, n2 in pair(day['items'], rows_, lambda x: x['title']):
                    if n2 is not None and n2 < ni and o2 is not None: after = day['items'][o2]['id']
                adds.append((day['date'], after, rows_[ni]))
    for date in days:
        if date not in [x['date'] for x in d['days']]: review.append('sheet has a day %s that the app does not; add it by hand' % date)
    # a stop deleted on one day and added with the same title on another = a move
    for date, after, row in adds:
        mv = next((x for x in dels if norm(x[1]['title']) == norm(row['title'])), None)
        if mv:
            dels.remove(mv); it = mv[1]
            ops.append({'op': 'item.move', 'id': it['id'], 'date': date, 'after': after})
            f = {k: row[k] for k in ('time', 'title', 'how', 'notes') if row[k] != it.get(k, '')}
            if row['action'] != it.get('action', ''): f['action'] = row['action']
            if f: ops.append({'op': 'item.set', 'id': it['id'], 'fields': f})
        else:
            f = {k: row[k] for k in ('time', 'title', 'how', 'notes', 'action') if row[k]}
            f['places'] = []
            ops.append({'op': 'item.add', 'date': date, 'after': after, 'fields': f})
            review.append('NEW STOP %s "%s": set "places" (existing place id, or place.add first)' % (date, row['title']))
    for date, it in dels:
        ops.append({'op': 'item.delete', 'id': it['id']})
        review.append('REMOVED STOP %s "%s" (%s): check it really left the sheet' % (date, it['title'], it['id']))
    tpairs = pair(d['todo'], todo, lambda x: x['task'])
    new_to_old = {ni: oi for oi, ni in tpairs if oi is not None and ni is not None}
    for oi, ni in tpairs:
        if oi is not None and ni is not None:
            t, row = d['todo'][oi], todo[ni]
            f = {k: row[k] for k in ('task', 'how', 'by', 'done') if row[k] != t.get(k)}
            if f: ops.append({'op': 'todo.set', 'id': t['id'], 'fields': f})
        elif oi is not None: ops.append({'op': 'todo.delete', 'id': d['todo'][oi]['id']})
    for oi, ni in tpairs:
        if oi is None:
            prev = [new_to_old[k] for k in range(ni) if k in new_to_old]
            ops.append({'op': 'todo.add', 'after': d['todo'][prev[-1]]['id'] if prev else None, 'fields': todo[ni]})
    if not sum(len(v) for v in days.values()): review.append('could not read any stops from the sheet; do not apply')
    return {'sheetRevision': revision, 'ops': ops, 'review': review}


def main():
    d = json.load(open(DATA, encoding='utf-8'))
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'rows'
    if cmd == 'rows': rows(d)
    elif cmd == 'state': print(open(STATE).read() if os.path.exists(STATE) else '{}')
    elif cmd == 'auto':
        print(json.dumps(auto(d, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ''), ensure_ascii=False, indent=1))
    elif cmd == 'apply':
        patch = json.load(open(sys.argv[2], encoding='utf-8'))
        if patch.get('review') and not patch.get('reviewed'):
            fail('the patch has a "review" list; resolve each point, then set "reviewed": true')
        apply(d, patch)
        json.dump(d, open(DATA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        st = {'sheetRevision': patch.get('sheetRevision', ''), 'syncedAt': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'ops': len(patch.get('ops', []))}
        json.dump(st, open(STATE, 'w'), indent=1)
        print('applied %d ops' % len(patch.get('ops', [])))
    else: sys.exit(__doc__)


if __name__ == '__main__':
    main()
