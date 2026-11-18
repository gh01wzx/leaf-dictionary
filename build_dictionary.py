"""Prepare the shipped, read-only dictionary. Not needed when running the app."""
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def build():
    dest = ROOT / 'data' / 'dictionary.sqlite3'
    if dest.exists():
        raise SystemExit('Dictionary already exists; keep the existing build.')
    db = sqlite3.connect(dest)
    db.executescript('''
        CREATE TABLE words(word TEXT PRIMARY KEY COLLATE NOCASE, phonetic TEXT,
            translation TEXT, definition TEXT, exchange TEXT, rank INTEGER);
        CREATE TABLE forms(form TEXT COLLATE NOCASE, word TEXT, PRIMARY KEY(form, word));
        CREATE INDEX forms_lookup ON forms(form);
    ''')
    count = 0
    with (ROOT / 'data' / 'ecdict.csv').open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            word = row['word'].strip()
            if not word or not row['translation'].strip():
                continue
            rank = int(row['frq'] or 0) or int(row['bnc'] or 0) or 999999
            db.execute('INSERT OR IGNORE INTO words VALUES(?,?,?,?,?,?)',
                (word, row['phonetic'], row['translation'].replace('\\n', '\n'),
                 row['definition'].replace('\\n', '\n'), row['exchange'], rank))
            for group in row['exchange'].split('/'):
                if ':' not in group:
                    continue
                kind, value = group.split(':', 1)
                if kind not in ('p', 'd', 'i', '3', 's', 'r', 't'):
                    continue
                for form in value.split(','):
                    if form and form.lower() != word.lower():
                        db.execute('INSERT OR IGNORE INTO forms VALUES(?,?)', (form, word))
            count += 1
    db.commit()
    db.execute('VACUUM')
    actual = db.execute('SELECT COUNT(*) FROM words').fetchone()[0]
    db.close()
    (ROOT / 'data' / 'manifest.json').write_text(json.dumps({
        'entries': actual, 'source': 'ECDICT', 'url': 'https://github.com/skywind3000/ECDICT',
        'license': 'MIT', 'edition': '2026-10-15',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Built {actual:,} entries, {dest.stat().st_size / 1048576:.1f} MB')

if __name__ == '__main__':
    build()
