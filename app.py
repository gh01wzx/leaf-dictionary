"""Leaf: a strictly local reading dictionary with science-based vocabulary review.

Review design (see README "复习是怎样安排的"):
* Retrieval practice: every review asks you to recall before showing anything.
* Spacing: FSRS-6 schedules each word at the moment recall probability falls to
  the target retention (default 90%).
* Receptive -> productive: new words are reviewed as "see the word, recall the
  meaning". Once a word is stable, reviews alternate with "see a sentence and the
  meaning, produce the word" (cloze), which trains use, not only recognition.
* Varied contexts: cloze sentences rotate through your own reading, your own
  sentences and dictionary examples.
* Manageable load: a daily cap on new words; reviews are never capped so no
  backlog builds up silently.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import urllib.request
from urllib.parse import parse_qs, urlsplit
import webbrowser

from paths import BUNDLE, FROZEN, HOME, data_file

sys.path.insert(0, str(BUNDLE / 'vendor'))
from fsrs import Card, Rating, Scheduler, State  # noqa: E402

from dictionary_engine import PRESENTATION_VERSION, make_result  # noqa: E402
from learner_dictionary import forms as learner_forms  # noqa: E402
from learner_dictionary import get_entry as learner_entry  # noqa: E402
from learner_dictionary import info as learner_info  # noqa: E402
from learner_dictionary import stored_explanation  # noqa: E402
from offline_speech import SpeechUnavailable, pronounce, speech_status  # noqa: E402

VERSION = '1.0.0'
APP_ID = 'leaf-offline-dictionary-v1'
TOKEN = secrets.token_urlsafe(32)
CURATED = json.loads(data_file('insights.json').read_text(encoding='utf-8'))
MANIFEST = json.loads(data_file('manifest.json').read_text(encoding='utf-8'))
DATA_DIR = HOME / 'user_data'
DICTIONARY_PATH = data_file('dictionary.sqlite3')

# A study day starts at 04:00 local time, so late-night reading counts toward
# the day you are still living in (the convention used by Anki and SuperMemo).
DAY_START_HOUR = 4
# Short learning steps may be taken a little early when nothing else is waiting.
LEARN_AHEAD = timedelta(minutes=20)
# daily_goal / daily_minimum: how many different words to review per study day
# (a habit target and the smallest amount that still counts as a "kept" day).
DEFAULT_SETTINGS = {'new_per_day':10, 'retention':0.9, 'typing':True, 'daily_goal':30, 'daily_minimum':8}
GOAL_LIMIT = 500
RETENTION_CHOICES = (0.85, 0.9, 0.95)
MASTERED_DAYS = 21          # stability at which a word is counted as mastered
LEECH_FAILURES = 5          # repeated forgetting suggests rewriting the definition
OWN_SENTENCE = '我的造句'

STATE_SQL = "json_extract(c.card_json,'$.state')"
SEEN_SQL = "json_extract(c.card_json,'$.last_review') IS NOT NULL"
STABILITY_SQL = "json_extract(c.card_json,'$.stability')"
STATE_NAMES = {State.Learning:'learning', State.Review:'review', State.Relearning:'relearning'}


def now():
    return datetime.now(timezone.utc)


def study_day(value):
    """The local study day a moment belongs to."""
    return (value.astimezone() - timedelta(hours=DAY_START_HOUR)).date()


def day_start(day):
    """UTC instant at which a local study day begins."""
    return datetime.combine(day, time(DAY_START_HOUR)).astimezone().astimezone(timezone.utc)


@lru_cache(maxsize=8)
def scheduler(retention):
    # Fuzzing spreads words collected together over neighbouring days, which
    # avoids review spikes without changing the expected retention.
    return Scheduler(desired_retention=retention, enable_fuzzing=True)


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect():
    db = sqlite3.connect(DATA_DIR / 'learning.sqlite3', timeout=20, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


_lexicon_local = threading.local()


def lexicon():
    """Read-only ECDICT connection reused per thread."""
    db = getattr(_lexicon_local, 'db', None)
    if db is None:
        db = sqlite3.connect(DICTIONARY_PATH.as_uri() + '?mode=ro', uri=True, check_same_thread=False)
        db.row_factory = sqlite3.Row
        _lexicon_local.db = db
    return db


def initialize():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    database = DATA_DIR / 'learning.sqlite3'
    if database.exists():
        with connect() as db:
            upgrading = 'mode' not in {row[1] for row in db.execute('PRAGMA table_info(reviews)')}
        if upgrading:
            # First launch of 1.0: keep an untouched copy before adding columns.
            backup_learning_database('before-1.0-upgrade')
    with connect() as db:
        db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cards(
                id INTEGER PRIMARY KEY, word TEXT NOT NULL, sense_key TEXT NOT NULL,
                meaning TEXT NOT NULL, context TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',
                card_json TEXT NOT NULL, due TEXT NOT NULL, paused INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL, updated TEXT NOT NULL, lookups INTEGER NOT NULL DEFAULT 1,
                UNIQUE(word,sense_key));
            CREATE TABLE IF NOT EXISTS encounters(
                id INTEGER PRIMARY KEY, card_id INTEGER REFERENCES cards(id) ON DELETE CASCADE,
                context TEXT NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews(
                id INTEGER PRIMARY KEY, card_id INTEGER REFERENCES cards(id) ON DELETE CASCADE,
                rating INTEGER NOT NULL, created TEXT NOT NULL, log_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS definition_overrides(
                word TEXT PRIMARY KEY, meaning TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS reviews_created_idx ON reviews(created);
            CREATE INDEX IF NOT EXISTS reviews_card_idx ON reviews(card_id,created);
            CREATE INDEX IF NOT EXISTS encounters_card_idx ON encounters(card_id);
            CREATE INDEX IF NOT EXISTS cards_due_idx ON cards(paused,due);
        ''')
        columns = {row[1] for row in db.execute('PRAGMA table_info(cards)')}
        if 'explanation_json' not in columns:
            db.execute("ALTER TABLE cards ADD COLUMN explanation_json TEXT NOT NULL DEFAULT ''")
        review_columns = {row[1] for row in db.execute('PRAGMA table_info(reviews)')}
        for name, kind in (('prev_card_json', 'TEXT'), ('prev_due', 'TEXT'), ('mode', 'TEXT'), ('duration_ms', 'INTEGER')):
            if name not in review_columns:
                db.execute(f'ALTER TABLE reviews ADD COLUMN {name} {kind}')
    deduplicate_cards()
    refresh_dictionary_cards()


def backup_learning_database(prefix):
    backup_dir = DATA_DIR / 'backups'
    backup_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / (prefix + '-' + now().strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    with connect() as original:
        snapshot = sqlite3.connect(backup_path)
        try:
            original.backup(snapshot)
        finally:
            snapshot.close()


# ----------------------------------------------------------------- settings

def get_settings(db=None):
    def read(conn):
        stored = {row['key']:json.loads(row['value']) for row in conn.execute('SELECT key,value FROM settings')}
        return {**DEFAULT_SETTINGS, **{k:v for k, v in stored.items() if k in DEFAULT_SETTINGS}}
    if db is not None:
        return read(db)
    with connect() as conn:
        return read(conn)


def update_settings(data):
    changes = {}
    if 'new_per_day' in data:
        value = data['new_per_day']
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            raise ValueError('每日新词数请填写 0 到 100 之间的整数。')
        changes['new_per_day'] = value
    if 'retention' in data:
        value = data['retention']
        if not isinstance(value, (int, float)) or round(float(value), 2) not in RETENTION_CHOICES:
            raise ValueError('目标记住率只能选择 85%、90% 或 95%。')
        changes['retention'] = round(float(value), 2)
    if 'typing' in data:
        if not isinstance(data['typing'], bool):
            raise ValueError('拼写练习选项格式不正确。')
        changes['typing'] = data['typing']
    for key, label in (('daily_goal', '每日目标'), ('daily_minimum', '最低目标')):
        if key in data:
            value = data[key]
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= GOAL_LIMIT:
                raise ValueError(f'{label}请填写 1 到 {GOAL_LIMIT} 之间的整数。')
            changes[key] = value
    with connect() as db:
        merged = {**get_settings(db), **changes}
        if merged['daily_minimum'] > merged['daily_goal']:
            raise ValueError('最低目标不能高于每日目标。')
        db.executemany('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            [(key, json.dumps(value)) for key, value in changes.items()])
        return get_settings(db)


# --------------------------------------------------------------- dictionary

def remember_encounter(db, card_id, context, source, created=None):
    if (context or source) and not db.execute(
            'SELECT 1 FROM encounters WHERE card_id=? AND context=? AND source=?',
            (card_id, context, source)).fetchone():
        db.execute('INSERT INTO encounters(card_id,context,source,created) VALUES(?,?,?,?)',
            (card_id, context, source, created or now().isoformat()))


def deduplicate_cards():
    """One normalized spelling per card; retain the most established schedule."""
    with connect() as db:
        rows = [dict(row) for row in db.execute('''SELECT c.*,
            (SELECT COUNT(*) FROM reviews r WHERE r.card_id=c.id) AS review_count,
            (SELECT MAX(created) FROM reviews r WHERE r.card_id=c.id) AS last_review
            FROM cards c''')]
    groups = {}
    for row in rows:
        groups.setdefault(normalize(row['word']), []).append(row)
    if any(len(group) > 1 or group[0]['word'] != word for word, group in groups.items()):
        backup_learning_database('before-word-deduplication')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for word, group in groups.items():
                keeper = max(group, key=lambda row: (row['review_count'], row['last_review'] or '', row['updated'], -row['id']))
                for row in group:
                    remember_encounter(db, keeper['id'], row['context'], row['source'], row['created'])
                    if row['id'] == keeper['id']:
                        continue
                    for encounter in db.execute('SELECT * FROM encounters WHERE card_id=?', (row['id'],)).fetchall():
                        remember_encounter(db, keeper['id'], encounter['context'], encounter['source'], encounter['created'])
                    db.execute('UPDATE reviews SET card_id=? WHERE card_id=?', (keeper['id'], row['id']))
                    db.execute('DELETE FROM cards WHERE id=?', (row['id'],))
                db.execute('UPDATE cards SET word=?,lookups=?,created=? WHERE id=?',
                    (word, sum(row['lookups'] for row in group), min(row['created'] for row in group), keeper['id']))
    with connect() as db:
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_card_per_word ON cards(lower(trim(word)))')


def normalize(value):
    if not isinstance(value, str):
        raise ValueError('请输入英文单词或短语。')
    return re.sub(r'\s+', ' ', value.strip().replace('’', "'")).strip(' .,;:!?“”"()[]').lower()


def lookup(query):
    """Find the ECDICT entry for a query; inflections resolve to their lemma."""
    word = normalize(query)
    if not word or len(word) > 120 or not re.search('[a-z]', word):
        raise ValueError('请输入英文单词或短语；长句请放入「阅读原句」。')
    db = lexicon()
    row = db.execute('SELECT * FROM words WHERE word=?', (word,)).fetchone()
    resolved = None
    if not row:
        row = db.execute('SELECT w.* FROM forms f JOIN words w ON w.word=f.word WHERE f.form=? ORDER BY w.rank LIMIT 1', (word,)).fetchone()
        if row:
            resolved = word
    if not row and word in CURATED:
        entry = CURATED[word]
        row = {'word':word, 'phonetic':'', 'translation':entry.get('summary', ''), 'definition':'', 'exchange':'', 'rank':999999}
    if not row:
        return {'found':False, 'query':word}
    item = dict(row)
    # ECDICT sometimes contains conjugations as full entries; prefer the base lemma
    # when a source entry explicitly identifies it using exchange type 0.
    for group in item['exchange'].split('/'):
        if group.startswith('0:'):
            base = db.execute('SELECT * FROM words WHERE word=?', (group[2:],)).fetchone()
            if base:
                resolved, item = word, dict(base)
            break
    meanings = []
    for line in item['translation'].splitlines():
        match = re.match(r'^(n|v|vt|vi|a|adj|adv|prep|pron|conj|interj|art|num|aux|pl)\.\s*(.*)', line.strip())
        pos, text = (match.group(1), match.group(2)) if match else ('', line.strip())
        if text:
            meanings.append({'key':str(len(meanings)), 'pos':pos, 'text':text})
    if not meanings:
        meanings = [{'key':'0', 'pos':'', 'text':item['translation']}]
    insight = CURATED.get(item['word'].lower())
    if insight and insight.get('senses'):
        meanings = [{'key':str(i), **sense} for i, sense in enumerate(insight['senses'])]
    elif insight and insight.get('summary'):
        meanings = [{'key':'0', 'pos':meanings[0]['pos'], 'text':insight['summary']}]
    return {'found':True, 'word':item['word'], 'phonetic':item['phonetic'],
            'meanings':meanings, 'insight':insight, 'resolved_from':resolved,
            'definition':item['definition'], 'exchange':item['exchange']}


def suggest(prefix):
    """Type-ahead: your own words first, then common dictionary words."""
    try:
        text = normalize(prefix)
    except ValueError:
        return []
    if not text or len(text) > 60 or not re.search('[a-z]', text):
        return []
    upper = text + '\uffff'
    with connect() as db:
        own = [dict(r) for r in db.execute('''SELECT c.word, COALESCE(d.meaning,c.meaning) AS gloss FROM cards c
            LEFT JOIN definition_overrides d ON d.word=c.word
            WHERE lower(c.word)>=? AND lower(c.word)<? ORDER BY length(c.word), c.word LIMIT 4''', (text, upper))]
    seen = {row['word'] for row in own}
    rows = lexicon().execute('''SELECT word, translation FROM words WHERE word>=? AND word<?
        ORDER BY (word=?) DESC, rank LIMIT 12''', (text, upper, text)).fetchall() if len(text) >= 2 else \
        lexicon().execute('SELECT word, translation FROM words WHERE word=?', (text,)).fetchall()
    found = [{'word':row['word'], 'gloss':row['gloss'], 'own':True} for row in own]
    for row in rows:
        if row['word'] in seen or not re.fullmatch(r"[a-z][a-z' .-]*", row['word']):
            continue
        line = re.sub(r'^(?:[a-z]+\.\s*)', '', (row['translation'] or '').split('\n')[0].strip())
        found.append({'word':row['word'], 'gloss':line, 'own':False})
        seen.add(row['word'])
        if len(found) >= 8:
            break
    for item in found:
        item['gloss'] = item['gloss'][:40]
    return found


def text_field(data, key, limit):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('输入内容太长或格式不正确。')
    return value.strip()


def dictionary_explain(data):
    query = normalize(text_field(data, 'query', 120))
    context = text_field(data, 'context', 6000)
    source = text_field(data, 'source', 200)
    entry = lookup(query)
    learned = learner_entry(query, entry.get('word', ''))
    result = make_result(query, context, source, entry, CURATED.get(entry.get('word', '').lower()), entry.get('definition', ''), learned)
    with connect() as db:
        existing = db.execute('SELECT * FROM cards WHERE word=? COLLATE NOCASE', (query,)).fetchone()
        custom = db.execute('SELECT * FROM definition_overrides WHERE word=?', (query,)).fetchone()
    # Imported notes and personal entries can be useful even when neither bundled
    # dictionary contains the exact phrase. Do not silently drop these cards.
    if (not result['found'] or not result.get('can_save')) and (existing or custom):
        original = {}
        if existing and existing['explanation_json']:
            try:
                original = json.loads(existing['explanation_json'])
            except (ValueError, TypeError):
                pass
        base = result['explanation']
        base.update(original)
        base.update(valid_word=True, origin='personal', core_label='核心释义', warning='', lemma=query)
        base['core_meaning'] = original.get('dictionary_core_meaning') or original.get('core_meaning') or (
            existing['meaning'] if existing else custom['meaning'])
        result.update(found=True, can_save=True, explanation=base, lemma=query,
            dictionary_source='我的整理词条', source_kind='personal',
            sense_key='personal:' + hashlib.sha256(query.encode()).hexdigest()[:24])
    if result['found']:
        result['saved_card'] = compact_card(existing) if existing else None
        if data.get('save') is True and result.get('can_save'):
            result['saved_card'] = compact_card(collect(result))
            with connect() as db:
                custom = db.execute('SELECT * FROM definition_overrides WHERE word=?', (query,)).fetchone()
        apply_core_definition(result['explanation'], custom)
        if result.get('saved_card') and custom:
            result['saved_card']['meaning'] = custom['meaning']
    return result


def compact_card(row):
    card = dict(row)
    card.pop('explanation_json', None)
    return card


def apply_core_definition(explanation, custom):
    """Overlay personal text at read time; keep the source and cards untouched."""
    original = explanation.get('dictionary_core_meaning', explanation.get('core_meaning', ''))
    explanation.update(dictionary_core_meaning=original,
        core_meaning=custom['meaning'] if custom else original,
        custom_definition=bool(custom), custom_updated=custom['updated'] if custom else '')


class DefinitionConflict(ValueError):
    """A second window edited the same definition while this editor was open."""


def edit_definition(data):
    word = normalize(text_field(data, 'word', 120))
    if not word or not re.search('[a-z]', word):
        raise ValueError('请输入有效的英文单词或短语。')
    if 'meaning' not in data:
        raise ValueError('请提供要保存的释义。')
    meaning = None if data['meaning'] is None else text_field(data, 'meaning', 3000)
    if meaning == '':
        raise ValueError('请先写下释义，再保存。')
    expected = text_field(data, 'expected', 100)
    result = dictionary_explain({'query':word})
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not result['found'] and not db.execute('SELECT 1 FROM cards WHERE word=?', (word,)).fetchone():
            raise ValueError('请先查询一个词，或从生词本中打开已有词汇。')
        previous = db.execute('SELECT * FROM definition_overrides WHERE word=?', (word,)).fetchone()
        if expected != (previous['updated'] if previous else ''):
            raise DefinitionConflict('其他窗口已修改这个词。你的输入仍在，请先复制，关闭后重新编辑。')
        stamp = now().isoformat()
        if meaning is None:
            db.execute('DELETE FROM definition_overrides WHERE word=?', (word,))
        else:
            db.execute('INSERT INTO definition_overrides(word,meaning,updated) VALUES(?,?,?) '
                'ON CONFLICT(word) DO UPDATE SET meaning=excluded.meaning,updated=excluded.updated',
                (word, meaning, stamp))
    return {'word':word, 'meaning':meaning, 'updated':stamp if meaning is not None else ''}


def refresh_dictionary_cards():
    """Upgrade dictionary text only; retain every scheduling and history field."""
    with connect() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM cards WHERE sense_key LIKE 'dict:%'")]
    updates = []
    for row in rows:
        try:
            previous = json.loads(row['explanation_json'])
        except (ValueError, TypeError):
            continue
        if previous.get('origin') != 'dictionary' or previous.get('presentation_version') == PRESENTATION_VERSION:
            continue
        entry = lookup(row['word'])
        learned = learner_entry(row['word'], entry.get('word', ''))
        if not entry['found'] and not learned:
            continue
        result = make_result(row['word'], row['context'], row['source'], entry,
            CURATED.get(entry.get('word', '').lower()), entry.get('definition', ''), learned)
        if not result.get('can_save'):
            continue
        explanation = result['explanation']
        meaning = explanation['context_meaning'] or explanation['core_meaning']
        updates.append((meaning, json.dumps(stored_explanation(explanation), ensure_ascii=False), row['id']))
    if updates:
        backup_learning_database('before-chinese-definitions')
        with connect() as db:
            db.executemany('UPDATE cards SET meaning=?,explanation_json=? WHERE id=?', updates)


def collect(result):
    """Add a looked-up word to the collection, or record another reading context."""
    explanation = result['explanation']
    meaning = (explanation['context_meaning'] if result['context'] else '') or explanation['core_meaning']
    stamp = now().isoformat()
    rich_json = json.dumps(stored_explanation(explanation), ensure_ascii=False)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT * FROM cards WHERE word=? COLLATE NOCASE', (result['query'],)).fetchone()
        if existing:
            card_id = existing['id']
            remember_encounter(db, card_id, existing['context'], existing['source'], existing['created'])
            db.execute('UPDATE cards SET sense_key=?,meaning=?,context=?,source=?,explanation_json=?,lookups=lookups+1,updated=? WHERE id=?',
                (result['sense_key'], meaning, result['context'], result['source'], rich_json, stamp, card_id))
        else:
            card = Card()
            card_id = db.execute('INSERT INTO cards(word,sense_key,meaning,context,source,card_json,due,created,updated,explanation_json) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (result['query'], result['sense_key'], meaning, result['context'], result['source'], card.to_json(), card.due.isoformat(), stamp, stamp, rich_json)).lastrowid
        remember_encounter(db, card_id, result['context'], result['source'], stamp)
        return dict(db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone())


# ------------------------------------------------------------------- review

def queue_counts(db, current):
    stamp = current.isoformat()
    start = day_start(study_day(current)).isoformat()
    settings = get_settings(db)
    row = db.execute(f'''SELECT
        SUM(c.paused=0 AND {SEEN_SQL} AND {STATE_SQL} IN (1,3) AND c.due<=:now) AS learning_due,
        SUM(c.paused=0 AND {SEEN_SQL} AND {STATE_SQL}=2 AND c.due<=:now) AS review_due,
        SUM(c.paused=0 AND NOT {SEEN_SQL}) AS new_total,
        MIN(CASE WHEN c.paused=0 AND {SEEN_SQL} AND {STATE_SQL} IN (1,3) AND c.due>:now THEN c.due END) AS next_learning,
        MIN(CASE WHEN c.paused=0 AND {SEEN_SQL} AND c.due>:now THEN c.due END) AS next_due
        FROM cards c''', {'now':stamp}).fetchone()
    new_today = db.execute('''SELECT COUNT(*) FROM (SELECT MIN(created) AS first FROM reviews
        GROUP BY card_id HAVING first>=?)''', (start,)).fetchone()[0]
    attempts_today = db.execute('SELECT COUNT(*) FROM reviews WHERE created>=?', (start,)).fetchone()[0]
    extra = extra_new_today(db, current)
    new_left = min(row['new_total'] or 0, max(0, settings['new_per_day'] + extra - new_today))
    learning_due, review_due = row['learning_due'] or 0, row['review_due'] or 0
    return {'learning_due':learning_due, 'review_due':review_due, 'new_left':new_left,
        'new_total':row['new_total'] or 0, 'new_today':new_today, 'new_per_day':settings['new_per_day'], 'extra_new':extra,
        'attempts_today':attempts_today, 'due':learning_due + review_due + new_left,
        'next_learning':row['next_learning'], 'next_due':row['next_due']}


def extra_new_today(db, current):
    """New words added on top of the daily cap for the current study day only."""
    row = db.execute("SELECT value FROM settings WHERE key='extra_new'").fetchone()
    if not row:
        return 0
    value = json.loads(row['value'])
    return value.get('count', 0) if value.get('day') == str(study_day(current)) else 0


def add_new_today(data):
    """Top up today's new words, e.g. to reach the daily goal when the due list is done."""
    count = data.get('count')
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= GOAL_LIMIT:
        raise ValueError('请填写要加学的新词数量。')
    current = now()
    with connect() as db:
        total = count + extra_new_today(db, current)
        db.execute("INSERT INTO settings(key,value) VALUES('extra_new',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps({'day':str(study_day(current)), 'count':total}),))
    return stats()


def pick_next(db, current, last=None, focus=None):
    """Choose the next card. Returns (row, learned_ahead)."""
    stamp = current.isoformat()
    ahead = (current + LEARN_AHEAD).isoformat()
    if focus:
        row = db.execute('SELECT c.* FROM cards c WHERE c.id=? AND c.paused=0 AND c.due<=?', (focus, ahead)).fetchone()
        if row:
            return row, row['due'] > stamp
    # 1. Short learning steps are time-critical.
    row = db.execute(f'''SELECT c.* FROM cards c WHERE c.paused=0 AND {SEEN_SQL} AND {STATE_SQL} IN (1,3)
        AND c.due<=? ORDER BY c.due, c.id LIMIT 1''', (stamp,)).fetchone()
    if row:
        return row, False
    counts = queue_counts(db, current)
    review = db.execute(f'''SELECT c.* FROM cards c WHERE c.paused=0 AND {SEEN_SQL} AND {STATE_SQL}=2
        AND c.due<=? ORDER BY c.due, c.id LIMIT 1''', (stamp,)).fetchone()
    new = db.execute(f'''SELECT c.* FROM cards c WHERE c.paused=0 AND NOT {SEEN_SQL}
        ORDER BY c.created DESC, c.id DESC LIMIT 1''').fetchone() if counts['new_left'] > 0 else None
    # 2. Interleave: about one new word for every three reviews.
    if review and new:
        return (new if counts['attempts_today'] % 4 == 3 else review), False
    if review or new:
        return review or new, False
    # 3. Nothing else waiting: take a learning step a little early, but never
    #    the card just answered (that would remove the spacing entirely).
    row = db.execute(f'''SELECT c.* FROM cards c WHERE c.paused=0 AND {SEEN_SQL} AND {STATE_SQL} IN (1,3)
        AND c.due<=? AND c.id IS NOT ? ORDER BY c.due LIMIT 1''', (ahead, last)).fetchone()
    return (row, True) if row else (None, False)


def word_forms(word, lemma=''):
    """Spellings to recognise a word in a sentence: corpus forms and ECDICT inflections."""
    found = [word]
    doc = learner_entry(word, lemma)
    found += learner_forms(doc)
    for target in dict.fromkeys([word, lemma, doc['word'] if doc else '']):
        if not target:
            continue
        row = lexicon().execute('SELECT exchange FROM words WHERE word=?', (target,)).fetchone()
        if row and row['exchange']:
            # ECDICT exchange codes: p past, d participle, i -ing, 3 third person,
            # s plural, r/t comparative/superlative. Other codes are not spellings.
            found += [part[2:] for part in row['exchange'].split('/')
                if part[:2] in ('p:', 'd:', 'i:', '3:', 's:', 'r:', 't:') and len(part) > 4]
    return [form for form in dict.fromkeys(f.strip() for f in found) if form and re.search('[A-Za-z]', form)]


def sentence_around(text, start, end):
    """The sentence of a longer passage that contains a match."""
    left = max(text.rfind(mark, 0, start) for mark in ('. ', '! ', '? ', '。', '\n'))
    right_candidates = [i for i in (text.find(mark, end) for mark in ('. ', '! ', '? ', '。', '\n')) if i != -1]
    left = 0 if left == -1 else left + 1
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return left, right


def build_cloze(word, forms, pool, rotation):
    """Blank the word in one of several sentences; rotate sentences across reviews."""
    if not forms:
        return None
    pattern = re.compile(r"(?<![A-Za-z])(" + '|'.join(re.escape(f) for f in sorted(forms, key=len, reverse=True)) + r")(?![A-Za-z])", re.I)
    candidates = []
    for example in pool:
        text = ' '.join(example['text'].split())
        match = pattern.search(text)
        if not match:
            continue
        left, right = sentence_around(text, match.start(), match.end())
        if right - left > 320:
            left, right = max(0, match.start() - 150), min(len(text), match.end() + 150)
        sentence = text[left:right].strip()
        parts = pattern.split(sentence)
        # parts alternates text / matched form; keep the first match as the answer.
        segments = [{'text':part, 'blank':i % 2 == 1} for i, part in enumerate(parts) if part or i % 2 == 1]
        answer = next(seg['text'] for seg in segments if seg['blank'])
        candidates.append({'segments':segments, 'answer':answer, 'gloss':example.get('gloss', ''),
            'translation':example.get('translation', '') if right - left == len(text) else '',
            'source':example.get('source', ''), 'own':example.get('own', False)})
    if not candidates:
        return None
    choice = candidates[rotation % len(candidates)]
    # Any attested form of the word counts as "right word, other form".
    choice['accept'] = list(dict.fromkeys([choice['answer'], word, *forms]))
    return choice


def example_pool(card, encounters, explanation):
    pool = []
    for row in encounters:
        if row['context']:
            pool.append({'text':row['context'], 'source':row['source'] or '你的阅读', 'own':True})
    if card['context'] and not any(p['text'] == card['context'] for p in pool):
        pool.append({'text':card['context'], 'source':card['source'] or '你的阅读', 'own':True})
    if explanation:
        for sense in (explanation.get('learner_senses') or []) + (explanation.get('more_main_senses') or [])[:3]:
            for example in sense.get('examples', [])[:2]:
                if example.get('text'):
                    pool.append({'text':example['text'], 'translation':example.get('translation', ''), 'gloss':sense.get('gloss', ''), 'source':'词典例句'})
        if explanation.get('example_en'):
            pool.append({'text':explanation['example_en'], 'translation':explanation.get('example_zh', ''), 'source':'词典例句'})
    return pool


def card_progress(fs, history, current, retention):
    failures = sum(1 for r in history if r['rating'] == 1)
    seen = fs.last_review is not None
    return {'is_new':not seen, 'state':STATE_NAMES.get(fs.state, 'learning') if seen else 'new',
        'reviews':len(history), 'failures':failures,
        'stability':round(fs.stability, 1) if fs.stability else None,
        'retrievability':round(scheduler(retention).get_card_retrievability(fs, current), 3) if seen else None,
        'leech':failures >= LEECH_FAILURES}


def review_payload(row, learned_ahead):
    current = now()
    card = dict(row)
    with connect() as db:
        history = [dict(r) for r in db.execute('SELECT rating,created,mode FROM reviews WHERE card_id=? ORDER BY id', (card['id'],))]
        encounters = [dict(r) for r in db.execute('SELECT context,source,created FROM encounters WHERE card_id=? ORDER BY created DESC,id DESC', (card['id'],))]
        custom = db.execute('SELECT * FROM definition_overrides WHERE word=?', (card['word'],)).fetchone()
        settings = get_settings(db)
    stored = None
    if card.get('explanation_json'):
        try:
            stored = json.loads(card['explanation_json'])
        except ValueError:
            stored = None
    explanation, phonetic = None, ''
    try:
        live = dictionary_explain({'query':card['word'], 'context':card['context'], 'source':card['source']})
        if live['found']:
            explanation, phonetic = live['explanation'], live.get('phonetic', '')
    except ValueError:
        pass
    if explanation is None and stored:
        explanation = stored
        apply_core_definition(explanation, custom)
    if explanation is None:
        explanation = {'core_meaning':card['meaning'], 'core_label':'当时记录的词义'}
        apply_core_definition(explanation, custom)
    if not phonetic:
        found = lexicon().execute('SELECT phonetic FROM words WHERE word=?', (card['word'],)).fetchone()
        phonetic = found[0] if found else ''
    card.pop('explanation_json', None)
    card['meaning'] = explanation.get('core_meaning') or card['meaning']
    card.update(explanation=explanation, phonetic=phonetic, encounters=[e for e in encounters if e['context']],
        learned_ahead=learned_ahead)
    fs = Card.from_json(card['card_json'])
    card['progress'] = card_progress(fs, history, current, settings['retention'])
    # Receptive first, productive once the word is established.
    mode, cloze = 'recognize', None
    if fs.state == State.Review and (fs.stability or 0) >= 3 and len(history) % 2 == 1:
        cloze = build_cloze(card['word'], word_forms(card['word'], explanation.get('lemma', '')),
            example_pool(card, encounters, explanation), len(history) // 2)
        if cloze:
            mode = 'cloze'
            cloze['hint'] = cloze['gloss'] or explanation.get('core_meaning', '')
    card['mode'], card['cloze'], card['typing'] = mode, cloze, settings['typing']
    return card


def review_next(last=None, focus=None):
    current = now()
    with connect() as db:
        row, learned_ahead = pick_next(db, current, last, focus)
    if not row:
        return {'card':None, 'stats':stats()}
    return {'card':review_payload(row, learned_ahead), 'stats':stats()}


class ReviewConflict(ValueError):
    """The displayed card can no longer be rated; load the current queue."""


def rate(data):
    card_id, rating = int(data['id']), Rating(int(data['rating']))
    mode = data.get('mode') if data.get('mode') in ('recognize', 'cloze') else 'recognize'
    duration = data.get('duration_ms')
    duration = max(0, min(int(duration), 3_600_000)) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM cards WHERE id=? AND paused=0', (card_id,)).fetchone()
        if not row:
            raise ReviewConflict('这个词已暂停或移除，已为你更新复习列表。')
        if data.get('version') != row['card_json']:
            raise ReviewConflict('这个词已经记录过本次回答，已为你更新复习列表。')
        reviewed_at = now()
        previous = Card.from_json(row['card_json'])
        early = datetime.fromisoformat(row['due']) > reviewed_at
        learning = previous.last_review is not None and previous.state in (State.Learning, State.Relearning)
        if early and not (learning and datetime.fromisoformat(row['due']) <= reviewed_at + LEARN_AHEAD):
            raise ReviewConflict('这个词还没到复习时间，系统会在到期后安排。')
        retention = get_settings(db)['retention']
        card, log = scheduler(retention).review_card(previous, rating, review_datetime=reviewed_at, review_duration=duration)
        stamp = reviewed_at.isoformat()
        db.execute('UPDATE cards SET card_json=?,due=?,updated=? WHERE id=?', (card.to_json(), card.due.isoformat(), stamp, card_id))
        review_id = db.execute('''INSERT INTO reviews(card_id,rating,created,log_json,prev_card_json,prev_due,mode,duration_ms)
            VALUES(?,?,?,?,?,?,?,?)''', (card_id, int(rating), stamp, log.to_json(), row['card_json'], row['due'], mode, duration)).lastrowid
    return {'due':card.due.isoformat(), 'review_id':review_id, 'card_id':card_id, 'stats':stats()}


def undo_review(data):
    review_id = int(data['review_id'])
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM reviews WHERE id=(SELECT MAX(id) FROM reviews)').fetchone()
        if not row or row['id'] != review_id or not row['prev_card_json']:
            raise ReviewConflict('只能撤销刚才的最后一次评分。')
        db.execute('UPDATE cards SET card_json=?,due=?,updated=? WHERE id=?',
            (row['prev_card_json'], row['prev_due'], now().isoformat(), row['card_id']))
        db.execute('DELETE FROM reviews WHERE id=?', (review_id,))
    return {'card_id':row['card_id'], 'stats':stats()}


def add_sentence(data):
    """Writing your own sentence is generative practice; it also feeds future cloze reviews."""
    card_id = int(data['id'])
    text = text_field(data, 'text', 500)
    if len(text) < 3 or not re.search('[A-Za-z]', text):
        raise ValueError('请用英文写一个包含这个词的句子。')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        card = db.execute('SELECT word FROM cards WHERE id=?', (card_id,)).fetchone()
        if not card:
            raise ReviewConflict('这个词已移除。')
        remember_encounter(db, card_id, text, OWN_SENTENCE)
        encounters = [dict(r) for r in db.execute('SELECT context,source,created FROM encounters WHERE card_id=? ORDER BY created DESC,id DESC', (card_id,))]
    forms = word_forms(card['word'])
    contains = bool(build_cloze(card['word'], forms, [{'text':text}], 0))
    return {'encounters':encounters, 'contains_word':contains}


# -------------------------------------------------------------- statistics

def stats():
    current = now()
    stamp = current.isoformat()
    today = study_day(current)
    days = [today - timedelta(days=i) for i in reversed(range(7))]
    words_by_day = {str(day):set() for day in days}
    attempts_by_day = dict.fromkeys(words_by_day, 0)
    with connect() as db:
        db.execute('BEGIN')
        counts = queue_counts(db, current)
        totals = db.execute(f'''SELECT COUNT(*) AS total, SUM(paused=0) AS active,
            SUM(paused=0 AND {STATE_SQL}=2 AND {STABILITY_SQL}>=?) AS mastered FROM cards c''', (MASTERED_DAYS,)).fetchone()
        # One spare day covers timestamps stored with a non-UTC offset.
        for row in db.execute('SELECT card_id,created FROM reviews WHERE created>=?', ((day_start(days[0]) - timedelta(days=1)).isoformat(),)):
            reviewed_at = datetime.fromisoformat(row['created'])
            if reviewed_at > current:
                continue
            day = str(study_day(reviewed_at))
            if day in words_by_day:
                words_by_day[day].add(row['card_id'])
                attempts_by_day[day] += 1
        settings = get_settings(db)
        words_per_day = {}
        for card_id, created in db.execute('SELECT card_id,created FROM reviews WHERE created>=?',
                ((current - timedelta(days=400)).isoformat(),)):
            words_per_day.setdefault(str(study_day(datetime.fromisoformat(created))), set()).add(card_id)
        mature = [r[0] for r in db.execute('''SELECT rating FROM reviews WHERE created>=? AND prev_card_json IS NOT NULL
            AND json_extract(prev_card_json,'$.state')=2''', ((current - timedelta(days=30)).isoformat(),))]
        forecast_rows = [r[0] for r in db.execute(f'''SELECT c.due FROM cards c WHERE c.paused=0 AND {SEEN_SQL}
            AND c.due>? AND c.due<?''', (stamp, day_start(today + timedelta(days=8)).isoformat()))]
        recent = [dict(r) for r in db.execute('''SELECT c.id,c.word,COALESCE(d.meaning,c.meaning) AS meaning,
            c.context,c.source,c.lookups,c.updated FROM cards c LEFT JOIN definition_overrides d ON d.word=c.word
            ORDER BY c.created DESC,c.id DESC LIMIT 6''')]
    # A day counts toward the streak once the minimum is reached. Today only
    # joins the streak after its minimum is met, so an unfinished day never breaks it.
    minimum, target = settings['daily_minimum'], settings['daily_goal']
    kept = {day for day, words in words_per_day.items() if len(words) >= minimum}
    streak, cursor = 0, today if str(today) in kept else today - timedelta(days=1)
    while str(cursor) in kept:
        streak += 1
        cursor -= timedelta(days=1)
    forecast = {str(today + timedelta(days=i)):0 for i in range(1, 8)}
    for due in forecast_rows:
        day = str(study_day(datetime.fromisoformat(due)))
        if day in forecast:
            forecast[day] += 1
    week = {day:len(words) for day, words in words_by_day.items()}
    done = week[str(today)]
    goal = {'target':target, 'minimum':minimum, 'done':done,
        'met_minimum':done >= minimum, 'met_goal':done >= target,
        'remaining':max(0, target - done), 'to_minimum':max(0, minimum - done),
        # Words still reachable today: what is due now plus new words not yet added.
        'reachable':done + counts['due'], 'new_available':max(0, counts['new_total'] - counts['new_left'])}
    return {'goal':goal, 'total':totals['total'], 'active':totals['active'] or 0, 'mastered':totals['mastered'] or 0,
        'due':counts['due'], 'queue':counts, 'reviewed_today':week[str(today)],
        'review_attempts_today':attempts_by_day[str(today)], 'week':week, 'week_attempts':attempts_by_day,
        'today':str(today), 'as_of':stamp, 'recent':recent, 'next_due':counts['next_due'],
        'streak':streak, 'forecast':forecast,
        'retention':{'reviews':len(mature), 'rate':round(sum(r > 1 for r in mature) / len(mature), 3) if mature else None}}


# ------------------------------------------------------------------ library

LIBRARY_FILTERS = {
    'all':'1',
    'due':f'c.paused=0 AND {SEEN_SQL} AND c.due<=:now',
    'new':f'c.paused=0 AND NOT {SEEN_SQL}',
    'learning':f'c.paused=0 AND {SEEN_SQL} AND {STATE_SQL} IN (1,3)',
    'mastered':f'c.paused=0 AND {STATE_SQL}=2 AND {STABILITY_SQL}>={MASTERED_DAYS}',
    'struggling':f'(SELECT COUNT(*) FROM reviews r WHERE r.card_id=c.id AND r.rating=1)>=3',
    'paused':'c.paused=1',
    'active':'c.paused=0',
}
LIBRARY_SORTS = {'recent':'c.created DESC, c.id DESC', 'alpha':'lower(c.word), c.id',
    'due':'c.paused, c.due, c.id', 'updated':'c.updated DESC, c.id DESC'}


def library(q='', status='all', *, brief=False, sort='recent', limit=2000):
    params = {'now':now().isoformat()}
    where = [LIBRARY_FILTERS.get(status, '1')]
    if q:
        params['q'] = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        where.append("(c.word LIKE :q ESCAPE '\\' OR COALESCE(d.meaning,c.meaning) LIKE :q ESCAPE '\\' OR c.source LIKE :q ESCAPE '\\')")
    keys = ('id', 'word', 'meaning', 'context', 'source', 'due', 'paused', 'created', 'updated', 'lookups', 'card_json')
    columns = ','.join('c.' + key for key in keys) if brief else 'c.*'
    sql = (f'''SELECT {columns}, d.meaning AS personal_meaning,
        (SELECT COUNT(*) FROM reviews r WHERE r.card_id=c.id) AS reviews,
        (SELECT COUNT(*) FROM reviews r WHERE r.card_id=c.id AND r.rating=1) AS failures
        FROM cards c LEFT JOIN definition_overrides d ON d.word=c.word
        WHERE {' AND '.join(where)} ORDER BY {LIBRARY_SORTS.get(sort, LIBRARY_SORTS['recent'])} LIMIT :limit''')
    params['limit'] = limit
    with connect() as db:
        rows = [dict(r) for r in db.execute(sql, params)]
        retention = get_settings(db)['retention']
    current = now()
    for row in rows:
        custom = row.pop('personal_meaning')
        if custom is not None:
            row['meaning'] = custom
        fs = Card.from_json(row['card_json'])
        seen = fs.last_review is not None
        row['state'] = STATE_NAMES.get(fs.state, 'learning') if seen else 'new'
        row['stability'] = round(fs.stability, 1) if fs.stability else None
        row['retrievability'] = round(scheduler(retention).get_card_retrievability(fs, current), 3) if seen else None
        if brief:
            del row['card_json']
    return rows


def card_detail(card_id):
    with connect() as db:
        row = db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
        if not row:
            return {'card':None, 'encounters':[], 'history':[]}
        encounters = [dict(r) for r in db.execute('SELECT * FROM encounters WHERE card_id=? ORDER BY created DESC,id DESC', (card_id,))]
        history = [dict(r) for r in db.execute('SELECT rating,created,mode FROM reviews WHERE card_id=? ORDER BY id', (card_id,))]
        retention = get_settings(db)['retention']
    card = compact_card(row)
    card['progress'] = card_progress(Card.from_json(card['card_json']), history, now(), retention)
    return {'card':card, 'encounters':encounters, 'history':history}


# ------------------------------------------------------------------ backups

def export_backup():
    with connect() as db:
        payload = {'app':APP_ID, 'version':1, 'exported':now().isoformat(), 'settings':get_settings(db)}
        for table in ('cards', 'encounters', 'reviews', 'definition_overrides'):
            payload[table] = [dict(r) for r in db.execute('SELECT * FROM ' + table)]
    return payload


def import_backup(data):
    if data.get('app') != APP_ID or data.get('version') != 1:
        raise ValueError('请选择从 Leaf 导出的备份文件。')
    cards, encounters, reviews = data.get('cards'), data.get('encounters', []), data.get('reviews', [])
    definitions = data.get('definition_overrides', [])
    if not isinstance(cards, list) or len(cards) > 20000 or not isinstance(encounters, list) or not isinstance(reviews, list) or not isinstance(definitions, list) or len(definitions) > 20000:
        raise ValueError('备份格式不正确或卡片过多。')
    imported, mapping = 0, {}
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in cards:
            word, sense = normalize(text_field(row, 'word', 120)), text_field(row, 'sense_key', 60)
            if not word:
                raise ValueError('备份包含空单词。')
            existing = db.execute('SELECT id FROM cards WHERE word=? COLLATE NOCASE', (word,)).fetchone()
            # Merge without overwriting any local learning progress.
            if existing:
                mapping[row['id']] = existing['id']
                remember_encounter(db, existing['id'], text_field(row, 'context', 6000), text_field(row, 'source', 200), row.get('created'))
                continue
            card = Card.from_json(row['card_json'])
            created = datetime.fromisoformat(row['created']).astimezone(timezone.utc).isoformat()
            updated = datetime.fromisoformat(row['updated']).astimezone(timezone.utc).isoformat()
            rich = text_field(row, 'explanation_json', 30000)
            if rich and not isinstance(json.loads(rich), dict):
                raise ValueError('备份中的释义格式不正确。')
            new_id = db.execute('INSERT INTO cards(word,sense_key,meaning,context,source,card_json,due,paused,created,updated,lookups,explanation_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (word, sense, text_field(row, 'meaning', 8000), text_field(row, 'context', 6000), text_field(row, 'source', 200), card.to_json(), card.due.isoformat(), int(bool(row.get('paused'))), created, updated, max(1, int(row.get('lookups', 1))), rich)).lastrowid
            mapping[row['id']] = new_id
            remember_encounter(db, new_id, text_field(row, 'context', 6000), text_field(row, 'source', 200), created)
            imported += 1
        for row in encounters:
            if row.get('card_id') in mapping:
                remember_encounter(db, mapping[row['card_id']], text_field(row, 'context', 6000), text_field(row, 'source', 200), datetime.fromisoformat(row['created']).isoformat())
        for row in reviews:
            if row.get('card_id') in mapping:
                Rating(int(row['rating']))
                json.loads(row['log_json'])
                values = (mapping[row['card_id']], int(row['rating']), datetime.fromisoformat(row['created']).astimezone(timezone.utc).isoformat(), row['log_json'])
                if not db.execute('SELECT 1 FROM reviews WHERE card_id=? AND rating=? AND created=? AND log_json=?', values).fetchone():
                    db.execute('INSERT INTO reviews(card_id,rating,created,log_json,mode,duration_ms) VALUES(?,?,?,?,?,?)',
                        values + (row.get('mode') if row.get('mode') in ('recognize', 'cloze') else None,
                                  row.get('duration_ms') if isinstance(row.get('duration_ms'), int) else None))
        for row in definitions:
            word = normalize(text_field(row, 'word', 120))
            meaning = text_field(row, 'meaning', 3000)
            if not word or not re.search('[a-z]', word) or not meaning:
                raise ValueError('备份包含无效的个人释义。')
            stamp = datetime.fromisoformat(row['updated']).astimezone(timezone.utc).isoformat()
            # Explicit local edits take precedence when merging a backup.
            db.execute('INSERT OR IGNORE INTO definition_overrides(word,meaning,updated) VALUES(?,?,?)', (word, meaning, stamp))
    return {'imported':imported}


# --------------------------------------------------------------------- HTTP

ASSETS = {'/':('index.html', 'text/html; charset=utf-8'), '/app.js':('app.js', 'text/javascript; charset=utf-8'),
    '/requests.js':('requests.js', 'text/javascript; charset=utf-8'), '/speech.js':('speech.js', 'text/javascript; charset=utf-8'),
    '/study.js':('study.js', 'text/javascript; charset=utf-8'), '/style.css':('style.css', 'text/css; charset=utf-8'),
    '/favicon.svg':('favicon.svg', 'image/svg+xml')}


@lru_cache(maxsize=16)
def asset(name):
    raw = (BUNDLE / 'web' / name).read_bytes()
    return raw.replace(b'__CSRF_TOKEN__', TOKEN.encode()).replace(b'__VERSION__', VERSION.encode()) if name == 'index.html' else raw


def app_info():
    return {'entries':MANIFEST['entries'], 'data_dir':str(DATA_DIR), 'version':VERSION,
        'algorithm':'FSRS-6', 'offline':True, 'settings':get_settings(),
        'dictionary':{'current':'开放学习词库修订版 + ECDICT 中文补充', 'learner':learner_info()}}


class Handler(BaseHTTPRequestHandler):
    server_version = 'Leaf/' + VERSION

    def log_message(self, *args):
        pass

    def send(self, payload, status=200, mime='application/json; charset=utf-8', attachment=False, cache=False):
        raw = json.dumps(payload, ensure_ascii=False).encode() if mime.startswith('application/json') else payload
        self.send_response(status)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-cache' if cache else 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        if attachment:
            self.send_header('Content-Disposition', 'attachment; filename="leaf-backup-%s.json"' % now().strftime('%Y%m%d'))
        self.end_headers()
        self.wfile.write(raw)

    def trusted_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.trusted_host():
            return self.send({'error':'Invalid host'}, 403)
        parsed = urlsplit(self.path)
        qs = parse_qs(parsed.query)
        arg = lambda key, default='': qs.get(key, [default])[0]  # noqa: E731
        path = parsed.path
        try:
            if path == '/api/health':
                return self.send({'app':APP_ID})
            if path == '/api/info':
                return self.send(app_info())
            if path == '/api/settings':
                return self.send(get_settings())
            if path == '/api/speech':
                return self.send(speech_status())
            if path == '/api/suggest':
                return self.send({'items':suggest(arg('q')[:60])})
            if path == '/api/card':
                return self.send(card_detail(int(arg('id', '0'))))
            if path == '/api/stats':
                return self.send(stats())
            if path == '/api/library':
                return self.send({'cards':library(arg('q')[:200], arg('status', 'all'), brief=True, sort=arg('sort', 'recent'))})
            if path == '/api/review':
                last, focus = arg('last'), arg('focus')
                return self.send(review_next(int(last) if last.isdigit() else None, int(focus) if focus.isdigit() else None))
            if path == '/api/export':
                return self.send(export_backup(), attachment=True)
            if path not in ASSETS:
                return self.send({'error':'Not found'}, 404)
            name, mime = ASSETS[path]
            self.send(asset(name), mime=mime, cache=name != 'index.html')
        except Exception:
            self.send({'error':'读取失败，请重新打开应用。'}, 500)

    def do_POST(self):
        if not self.trusted_host() or self.headers.get('X-Leaf-Token') != TOKEN:
            return self.send({'error':'页面已过期，请刷新。'}, 403)
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'):
            return self.send({'error':'Invalid origin'}, 403)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 16_000_000:
                raise ValueError('文件或输入内容过大。')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('数据格式不正确。')
            path = urlsplit(self.path).path
            routes = {
                '/api/explain':dictionary_explain, '/api/definition':edit_definition,
                '/api/rate':rate, '/api/undo':undo_review, '/api/sentence':add_sentence,
                '/api/settings':update_settings, '/api/import':import_backup, '/api/extra-new':add_new_today,
            }
            if path in routes:
                return self.send(routes[path](data))
            if path == '/api/speech':
                return self.send(pronounce(data), mime='audio/wav')
            if path == '/api/toggle':
                with connect() as db:
                    db.execute('UPDATE cards SET paused=1-paused WHERE id=?', (int(data['id']),))
                return self.send({'ok':True, 'stats':stats()})
            if path == '/api/delete':
                with connect() as db:
                    db.execute('DELETE FROM cards WHERE id=?', (int(data['id']),))
                return self.send({'ok':True, 'stats':stats()})
            if path == '/api/quit':
                self.send({'ok':True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self.send({'error':'Not found'}, 404)
        except SpeechUnavailable as e:
            self.send({'error':str(e)}, 503)
        except (ReviewConflict, DefinitionConflict) as e:
            self.send({'error':str(e)}, 409)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            self.send({'error':str(e) if str(e) else '输入格式不正确。'}, 400)
        except Exception:
            self.send({'error':'操作没有完成，数据已保留。请重试。'}, 500)


class Server(ThreadingHTTPServer):
    daemon_threads = True


def open_app(url):
    edges = [Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'), Path('C:/Program Files/Microsoft/Edge/Application/msedge.exe')]
    for edge in edges:
        if edge.exists():
            subprocess.Popen([str(edge), '--app=' + url, '--window-size=1280,880', '--no-first-run'])
            return
    webbrowser.open(url)


def main():
    global DATA_DIR
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=49183)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--data-dir')
    args = parser.parse_args()
    if args.data_dir:
        DATA_DIR = Path(args.data_dir).resolve()
    url = f'http://127.0.0.1:{args.port}'
    try:
        server = Server(('127.0.0.1', args.port), Handler)
    except OSError:
        try:
            # This loopback probe only checks an existing local instance.
            with urllib.request.urlopen(url + '/api/health', timeout=2) as response:
                if json.load(response).get('app') == APP_ID:
                    if not args.no_browser:
                        open_app(url)
                    return
        except Exception:
            pass
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f'本地端口被其他程序占用。请关闭占用 {args.port} 端口的程序后重试。', 'Leaf 词典', 0x10)
        raise SystemExit(1)
    initialize()
    if not args.no_browser:
        threading.Timer(0.2, open_app, (url,)).start()
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        error_path = HOME / 'leaf-error.log'
        try:
            error_path.write_text(traceback.format_exc(), encoding='utf-8')
        except OSError:
            pass
        if FROZEN and sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, '启动失败。请确认程序所在文件夹可以写入。错误详情保存在 leaf-error.log。', 'Leaf 词典', 0x10)
        else:
            raise
