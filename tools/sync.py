#!/usr/bin/env python3
"""Sheet → app sync helper (used by the scheduled Claude routine; see tools/SYNC.md).

  python3 tools/sync.py rows             print the app's stops and to-dos laid out like the sheet's columns
  python3 tools/sync.py apply PATCH.json apply a patch (ops below), validate, rewrite data/trip.json
  python3 tools/sync.py state            print the last synced sheet revision

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
    if t.startswith(('lunch', 'dinner', 'late lunch', 'last dinner', 'onsen + ')): return 'food'
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


def main():
    d = json.load(open(DATA, encoding='utf-8'))
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'rows'
    if cmd == 'rows': rows(d)
    elif cmd == 'state': print(open(STATE).read() if os.path.exists(STATE) else '{}')
    elif cmd == 'apply':
        patch = json.load(open(sys.argv[2], encoding='utf-8'))
        apply(d, patch)
        json.dump(d, open(DATA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        st = {'sheetRevision': patch.get('sheetRevision', ''), 'syncedAt': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), 'ops': len(patch.get('ops', []))}
        json.dump(st, open(STATE, 'w'), indent=1)
        print('applied %d ops' % len(patch.get('ops', [])))
    else: sys.exit(__doc__)


if __name__ == '__main__':
    main()
