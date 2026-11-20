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
import socket
import socketserver
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

VERSION = '1.1.0'
APP_ID = 'leaf-offline-dictionary-v1'
TOKEN = secrets.token_urlsafe(32)
CURATED = json.loads(data_file('insights.json').read_text(encoding='utf-8'))
MANIFEST = json.loads(data_file('manifest.json').read_text(encoding='utf-8'))
DATA_DIR = HOME / 'user_data'
DICTIONARY_PATH = data_file('dictionary.sqlite3')

# A study day starts at 04:00 local time, so late-night reading counts toward
# the day you are still living in (the convention used by Anki and SuperMemo).
DAY_START_HOUR = 4
# Learning steps are shown only when due. Daily goals never gate the queue.
CONTINUE_BATCH_SIZE = 10
# daily_goal / daily_minimum: how many different words to review per study day
# (a habit target and the smallest amount that still counts as a "kept" day).
DEFAULT_SETTINGS = {'new_per_day':10, 'retention':0.9, 'typing':True, 'daily_goal':30, 'daily_minimum':8}
GOAL_LIMIT = 500
RETENTION_CHOICES = (0.85, 0.9, 0.95)
MASTERED_DAYS = 21          # stability at which a word is counted as mastered
# Three answers: 1 不记得, 2 费力想起, 3 记得 (FSRS Again / Hard / Good). FSRS's
# fourth grade, Easy, is omitted to keep answers quick. Older Easy reviews
# still count as successful recall.
RATINGS = {1:'不记得', 2:'费力想起', 3:'记得'}
REMEMBERED_RATING = 2       # 费力想起 and 记得 are successful recalls
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
            CREATE INDEX IF NOT EXISTS cards_recent_idx ON cards(created DESC,id DESC);
            CREATE INDEX IF NOT EXISTS cards_word_nocase_idx ON cards(word COLLATE NOCASE);
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
        db.execute('BEGIN IMMEDIATE')
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
            WHERE c.word COLLATE NOCASE>=? AND c.word COLLATE NOCASE<? ORDER BY length(c.word), c.word LIMIT 4''', (text, upper))]
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
            saved, created = collect(result, with_status=True)
            result['saved_card'] = compact_card(saved)
            result['newly_collected'] = created
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


def collect(result, *, with_status=False):
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
        saved = dict(db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone())
        return (saved, existing is None) if with_status else saved


def undo_collection(data):
    """Undo the original add only while the saved card is still untouched."""
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        removed = db.execute('''DELETE FROM cards WHERE id=:id AND created=:stamp AND updated=:stamp
            AND lookups=1 AND paused=0 AND card_json=:version
            AND NOT EXISTS(SELECT 1 FROM reviews WHERE card_id=cards.id)
            AND NOT EXISTS(SELECT 1 FROM encounters WHERE card_id=cards.id
                AND (context!=cards.context OR source!=cards.source OR created!=cards.created))''',
            {'id':int(data['id']), 'stamp':data['created'], 'version':data['version']}).rowcount
        if not removed:
            raise ReviewConflict('这个词已有其他改动，已保留在生词本中。')
    return {'ok':True}


# ------------------------------------------------------------------- review

def queue_counts(db, current, settings=None):
    stamp = current.isoformat()
    start = day_start(study_day(current))
    settings = settings or get_settings(db)
    row = db.execute(f'''SELECT COUNT(*) AS total, SUM(c.paused=0) AS active,
        SUM(c.paused=0 AND {STATE_SQL}=2 AND {STABILITY_SQL}>=:mastered) AS mastered,
        SUM(c.paused=0 AND {SEEN_SQL} AND {STATE_SQL} IN (1,3) AND c.due<=:now) AS learning_due,
        SUM(c.paused=0 AND {SEEN_SQL} AND {STATE_SQL}=2 AND c.due<=:now) AS review_due,
        SUM(c.paused=0 AND NOT {SEEN_SQL}) AS new_total,
        SUM(c.paused=0 AND {SEEN_SQL} AND c.due>:now AND c.due<:end) AS later_today,
        MIN(CASE WHEN c.paused=0 AND {SEEN_SQL} AND {STATE_SQL} IN (1,3) AND c.due>:now THEN c.due END) AS next_learning,
        MIN(CASE WHEN c.paused=0 AND {SEEN_SQL} AND c.due>:now THEN c.due END) AS next_due
        FROM cards c''', {'now':stamp, 'end':day_start(study_day(current) + timedelta(days=1)).isoformat(),
                            'mastered':MASTERED_DAYS}).fetchone()
    # Look at today's candidate words first. The time index narrows the range;
    # the offset-aware comparison also accepts records from older backups.
    activity = db.execute('''WITH today_reviews AS (
        SELECT card_id,prev_card_json FROM reviews WHERE created>=:low AND created<:high
        AND julianday(created) BETWEEN julianday(:start) AND julianday(:now))
        SELECT (SELECT COUNT(*) FROM today_reviews) AS attempts,
        COUNT(*) AS introduced FROM (SELECT DISTINCT card_id FROM today_reviews
            WHERE prev_card_json IS NULL OR json_extract(prev_card_json,'$.last_review') IS NULL) AS t
        WHERE NOT EXISTS (SELECT 1 FROM reviews old WHERE old.card_id=t.card_id
            AND old.created<:prior_high AND julianday(old.created)<julianday(:start))''',
        {'low':(start - timedelta(days=1)).isoformat(), 'high':(current + timedelta(days=1)).isoformat(),
         'start':start.isoformat(), 'now':stamp, 'prior_high':(start + timedelta(days=1)).isoformat()}).fetchone()
    new_today, attempts_today = activity['introduced'], activity['attempts']
    extra = extra_new_today(db, current)
    new_left = min(row['new_total'] or 0, max(0, settings['new_per_day'] + extra - new_today))
    learning_due, review_due = row['learning_due'] or 0, row['review_due'] or 0
    return {'total':row['total'], 'active':row['active'] or 0, 'mastered':row['mastered'] or 0,
        'learning_due':learning_due, 'review_due':review_due, 'new_left':new_left,
        'new_total':row['new_total'] or 0, 'new_today':new_today, 'new_per_day':settings['new_per_day'], 'extra_new':extra,
        'attempts_today':attempts_today, 'due':learning_due + review_due + new_left,
        'review_ready':learning_due + review_due, 'ready':learning_due + review_due + new_left,
        'later_today':row['later_today'] or 0,
        'can_add_new':max(0, (row['new_total'] or 0) - new_left),
        'continue_batch':min(CONTINUE_BATCH_SIZE, max(0, (row['new_total'] or 0) - new_left)),
        'next_learning':row['next_learning'], 'next_due':row['next_due']}


def extra_new_today(db, current):
    """New words added on top of the daily cap for the current study day only."""
    row = db.execute("SELECT value FROM settings WHERE key='extra_new'").fetchone()
    if not row:
        return 0
    value = json.loads(row['value'])
    return value.get('count', 0) if value.get('day') == str(study_day(current)) else 0


def add_new_today(data):
    """Add a bounded new-word batch, independent of goal progress; retries are idempotent."""
    count = data.get('count')
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= GOAL_LIMIT:
        raise ValueError('请填写要加学的新词数量。')
    request_id = text_field(data, 'request_id', 100)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        current = now()
        day = str(study_day(current))
        if data.get('day', day) != day:
            raise ReviewConflict('已经进入新的学习日，已更新今天的安排。')
        previous = db.execute("SELECT value FROM settings WHERE key='extra_new'").fetchone()
        previous = json.loads(previous[0]) if previous else {}
        requests = previous.get('requests', []) if previous.get('day') == day else []
        if request_id and request_id in requests:
            return stats(db, current)
        queue = queue_counts(db, current)
        added = min(count, queue['can_add_new'])
        total = added + extra_new_today(db, current)
        if request_id:
            requests.append(request_id)
        db.execute("INSERT INTO settings(key,value) VALUES('extra_new',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps({'day':day, 'count':total, 'requests':requests}),))
    return stats()


def pick_next(db, current, last=None, focus=None, counts=None):
    """One queue for due retrievals followed by the planned first encounters."""
    counts = counts or queue_counts(db, current)
    params = {'now':current.isoformat(), 'new_left':counts['new_left'], 'focus':focus}
    if focus:
        row = db.execute(f'''SELECT c.* FROM cards c WHERE c.id=:focus AND c.paused=0
            AND (({SEEN_SQL} AND c.due<=:now) OR (NOT {SEEN_SQL} AND :new_left>0))''', params).fetchone()
        if row:
            return row, False
    row = db.execute(f'''SELECT c.* FROM cards c WHERE c.paused=0 AND {SEEN_SQL} AND c.due<=:now
        ORDER BY CASE WHEN {STATE_SQL} IN (1,3) THEN 0 ELSE 1 END, c.due, c.id LIMIT 1''', params).fetchone()
    if row:
        return row, False
    if counts['new_left']:
        row = db.execute(f'''SELECT c.* FROM cards c WHERE c.paused=0 AND NOT {SEEN_SQL}
            ORDER BY c.created DESC,c.id DESC LIMIT 1''').fetchone()
        return row, False
    return None, False


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
    if settings['typing'] and fs.state == State.Review and (fs.stability or 0) >= 3 and len(history) % 2 == 1:
        cloze = build_cloze(card['word'], word_forms(card['word'], explanation.get('lemma', '')),
            example_pool(card, encounters, explanation), len(history) // 2)
        if cloze:
            mode = 'cloze'
            cloze['hint'] = cloze['gloss'] or explanation.get('core_meaning', '')
    card['mode'], card['cloze'], card['typing'] = mode, cloze, settings['typing']
    return card


def review_next(last=None, focus=None):
    with connect() as db:
        db.execute('BEGIN')
        current = now()
        summary = stats(db, current)
        row, ahead = pick_next(db, current, last, focus, summary['queue'])
    return {'card':review_payload(row, ahead) if row else None, 'stats':summary}


class ReviewConflict(ValueError):
    """The displayed card can no longer be rated; load the current queue."""


def rate(data):
    card_id = int(data['id'])
    if not isinstance(data.get('rating'), int) or isinstance(data.get('rating'), bool) or data['rating'] not in RATINGS:
        raise ValueError('请选择：不记得、费力想起或记得。')
    rating = Rating(data['rating'])
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
        if previous.last_review is None and queue_counts(db, reviewed_at)['new_left'] == 0:
            raise ReviewConflict('今天的新词名额已经用完，已更新复习列表。')
        if previous.last_review is not None and datetime.fromisoformat(row['due']) > reviewed_at:
            raise ReviewConflict('这个词还没到复习时间，系统会在到期后安排。')
        retention = get_settings(db)['retention']
        card, log = scheduler(retention).review_card(previous, rating, review_datetime=reviewed_at, review_duration=duration)
        stamp = reviewed_at.isoformat()
        db.execute('UPDATE cards SET card_json=?,due=?,updated=? WHERE id=?', (card.to_json(), card.due.isoformat(), stamp, card_id))
        review_id = db.execute('''INSERT INTO reviews(card_id,rating,created,log_json,prev_card_json,prev_due,mode,duration_ms)
            VALUES(?,?,?,?,?,?,?,?)''', (card_id, int(rating), stamp, log.to_json(), row['card_json'], row['due'], mode, duration)).lastrowid
    result = {'due':card.due.isoformat(), 'review_id':review_id, 'card_id':card_id, 'review_version':card.to_json()}
    if data.get('include_next') is True:
        result.update(review_next(last=card_id))
    else:
        result['stats'] = stats()
    return result


def undo_review(data):
    review_id = int(data['review_id'])
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM reviews WHERE id=(SELECT MAX(id) FROM reviews)').fetchone()
        if not row or row['id'] != review_id or not row['prev_card_json']:
            raise ReviewConflict('只能撤销刚才的最后一次评分。')
        current = db.execute('SELECT card_json FROM cards WHERE id=?', (row['card_id'],)).fetchone()
        if ('card_id' in data and int(data['card_id']) != row['card_id']) or (
                'version' in data and data['version'] != current['card_json']):
            raise ReviewConflict('这次评分已发生变化，请刷新后查看当前记录。')
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

def daily_outcomes(rows, since=None, through=None):
    """Per study day: each word's latest rating that day, and the number of attempts.

    A word counts as remembered on a day when its last answer that day was a
    successful recall (费力想起 or 记得). Forgetting it later the same day takes it
    back out; recalling it after relearning puts it back in.
    """
    latest, attempts, last_at = {}, {}, {}
    for card_id, created, rating in rows:
        instant = datetime.fromisoformat(created)
        if (since is not None and instant < since) or (through is not None and instant > through):
            continue
        day = str(study_day(instant))
        key = (day, card_id)
        if key not in last_at or instant >= last_at[key]:
            latest.setdefault(day, {})[card_id] = rating
            last_at[key] = instant
        attempts[day] = attempts.get(day, 0) + 1
    return latest, attempts


def remembered(ratings):
    return sum(1 for rating in ratings.values() if rating >= REMEMBERED_RATING)


def outcomes_between(db, since, through):
    # ISO strings from older clients can carry a local offset. Widen the
    # indexed search by one day, then compare the exact instants in Python.
    rows = db.execute('''SELECT card_id,created,rating FROM reviews
        WHERE created>=? AND created<? ORDER BY id''',
        ((since - timedelta(days=1)).isoformat(), (through + timedelta(days=1)).isoformat()))
    return daily_outcomes(rows, since, through)


def stats(db=None, current=None):
    if db is None:
        with connect() as conn:
            conn.execute('BEGIN')
            return stats(conn, now())
    current = current or now()
    stamp = current.isoformat()
    today = study_day(current)
    days = [str(today - timedelta(days=i)) for i in reversed(range(7))]
    settings = get_settings(db)
    counts = queue_counts(db, current, settings)
    first_day = today - timedelta(days=6)
    latest, attempts = outcomes_between(db, day_start(first_day), current)
    # Use the first delayed retrieval for each word/day. Immediate repeats and
    # spelling exercises measure different things from delayed meaning recall.
    mature = {}
    since = current - timedelta(days=30)
    rows = db.execute('''SELECT card_id,rating,created,prev_card_json,mode FROM reviews
        WHERE created>=? AND created<? AND prev_card_json IS NOT NULL
        AND json_extract(prev_card_json,'$.state')=2 ORDER BY id''',
        ((since - timedelta(days=1)).isoformat(), (current + timedelta(days=1)).isoformat()))
    for r in rows:
        moment = datetime.fromisoformat(r['created'])
        prior = json.loads(r['prev_card_json'])
        last_review = prior.get('last_review')
        if not since <= moment <= current or r['mode'] == 'cloze' or not last_review:
            continue
        if moment - datetime.fromisoformat(last_review) < timedelta(days=1):
            continue
        key = (r['card_id'], study_day(moment))
        if key not in mature or moment < mature[key][0]:
            mature[key] = (moment, r['rating'])
    forecast_rows = [r[0] for r in db.execute(f'''SELECT c.due FROM cards c WHERE c.paused=0 AND {SEEN_SQL}
        AND c.due>? AND c.due<?''', (stamp, day_start(today + timedelta(days=8)).isoformat()))]
    recent = [dict(r) for r in db.execute('''SELECT c.id,c.word,COALESCE(d.meaning,c.meaning) AS meaning,
        c.context,c.source,c.lookups,c.updated FROM cards c LEFT JOIN definition_overrides d ON d.word=c.word
        ORDER BY c.created DESC,c.id DESC LIMIT 6''')]
    week = {day:len(latest.get(day, {})) for day in days}
    week_recalled = {day:remembered(latest.get(day, {})) for day in days}
    week_reviewed = {day:len(latest.get(day, {})) for day in days}
    week_attempts = {day:attempts.get(day, 0) for day in days}
    # Habit progress counts distinct words practised, independent of recall success.
    minimum, target = settings['daily_minimum'], settings['daily_goal']
    cursor = today if week[str(today)] >= minimum else today - timedelta(days=1)
    streak, period = 0, latest
    while True:
        if cursor < first_day:
            end = day_start(first_day) - timedelta(microseconds=1)
            first_day -= timedelta(days=28)
            period, _ = outcomes_between(db, day_start(first_day), end)
        if len(period.get(str(cursor), {})) < minimum:
            break
        streak += 1
        cursor -= timedelta(days=1)
    forecast = {str(today + timedelta(days=i)):0 for i in range(1, 8)}
    for due in forecast_rows:
        day = str(study_day(datetime.fromisoformat(due)))
        if day in forecast:
            forecast[day] += 1
    todays = latest.get(str(today), {})
    done = len(todays)
    due_by_tonight = db.execute(f'''SELECT c.id FROM cards c WHERE c.paused=0 AND {SEEN_SQL} AND c.due<?''',
        (day_start(today + timedelta(days=1)).isoformat(),))
    reachable = done + counts['new_left'] + sum(r[0] not in todays for r in due_by_tonight)
    breakdown = {'forgot':sum(r == 1 for r in todays.values()), 'hard':sum(r == 2 for r in todays.values()),
        'good':sum(r >= 3 for r in todays.values())}
    goal = {'target':target, 'minimum':minimum, 'done':done, 'reviewed':done,
        'recalled':remembered(todays), 'new_today':counts['new_today'],
        'old_today':max(0, done - counts['new_today']), **breakdown,
        'met_minimum':done >= minimum, 'met_goal':done >= target,
        'remaining':max(0, target - done), 'to_minimum':max(0, minimum - done),
        'reachable':reachable,
        'new_available':max(0, counts['new_total'] - counts['new_left'])}
    return {'goal':goal, 'total':counts['total'], 'active':counts['active'], 'mastered':counts['mastered'],
        'due':counts['due'], 'queue':counts, 'reviewed_today':done, 'remembered_today':remembered(todays),
        'review_attempts_today':week_attempts[str(today)], 'week':week, 'week_reviewed':week_reviewed,
        'week_attempts':week_attempts, 'week_recalled':week_recalled, 'today':str(today), 'as_of':stamp, 'recent':recent,
        'day_ends_at':day_start(today + timedelta(days=1)).isoformat(),
        'next_due':counts['next_due'], 'streak':streak, 'forecast':forecast,
        'retention':{'target':settings['retention'], 'reviews':len(mature), 'rate':round(sum(rating > 1 for _, rating in mature.values()) / len(mature), 3) if mature else None}}


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
LIBRARY_ORDERS = {
    'recent':(('created', 'id'), 'DESC'), 'alpha':(('word', 'id'), 'ASC'),
    'due':(('paused', 'due', 'id'), 'ASC'), 'updated':(('updated', 'id'), 'DESC'),
}


def library(q='', status='all', *, brief=False, sort='recent', limit=2000):
    return _read_library(q, status, brief, sort, limit, paged=False)['cards']


def library_page(q='', status='all', *, sort='recent', limit=40, cursor=''):
    if not 1 <= limit <= 100:
        raise ValueError('每次可以读取 1 到 100 个词。')
    return _read_library(q, status, True, sort, limit, paged=True, cursor=cursor)


def _read_library(q, status, brief, sort, limit, *, paged, cursor=''):
    current = now()
    params = {'now':current.isoformat(), 'limit':limit + int(paged)}
    where = [LIBRARY_FILTERS.get(status, '1')]
    if q:
        params['q'] = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        where.append("(c.word LIKE :q ESCAPE '\\' OR COALESCE(d.meaning,c.meaning) LIKE :q ESCAPE '\\' OR c.source LIKE :q ESCAPE '\\')")
    table = ' FROM cards c'
    joined = table + ' LEFT JOIN definition_overrides d ON d.word=c.word'
    count_sql = 'SELECT COUNT(*)' + (joined if q else table) + ' WHERE ' + ' AND '.join(where)
    keys, direction = LIBRARY_ORDERS.get(sort, LIBRARY_ORDERS['recent'])
    order = ['c.word COLLATE NOCASE' if k == 'word' else 'c.' + k for k in keys]
    if cursor:
        values = json.loads(cursor)
        if not isinstance(values, list) or len(values) != len(keys):
            raise ValueError('翻页位置无效，请刷新生词本。')
        for key, value in zip(keys, values):
            if key in ('id', 'paused'):
                if type(value) is not int or not 0 <= value < 2**63:
                    raise ValueError('翻页位置无效。')
            elif not isinstance(value, str) or len(value) > 200:
                raise ValueError('翻页位置无效。')
            params['after_' + key] = value
        after = ','.join(':after_' + key for key in keys)
        where.append(f"({','.join(order)}) {'>' if direction == 'ASC' else '<'} ({after})")
    if paged:
        fields = ['id', 'word', 'meaning', 'due', 'paused', 'card_json', *keys]
    else:
        fields = ['id', 'word', 'meaning', 'context', 'source', 'due', 'paused', 'created', 'updated', 'lookups', 'card_json']
    columns = ','.join('c.' + k for k in dict.fromkeys(fields)) if brief else 'c.*'
    counts = '' if paged else ', (SELECT COUNT(*) FROM reviews r WHERE r.card_id=c.id) AS reviews'
    sql = (f'''SELECT {columns}, d.meaning AS personal_meaning,
        (SELECT COUNT(*) FROM reviews r WHERE r.card_id=c.id AND r.rating=1) AS failures {counts}
        {joined} WHERE {' AND '.join(where)}
        ORDER BY {', '.join(expr + ' ' + direction for expr in order)} LIMIT :limit''')
    with connect() as db:
        db.execute('BEGIN')
        total = db.execute(count_sql, params).fetchone()[0] if paged else None
        rows = [dict(r) for r in db.execute(sql, params)]
        retention = get_settings(db)['retention']
    next_cursor = None
    if paged and len(rows) > limit:
        rows.pop()
        next_cursor = json.dumps([rows[-1][k] for k in keys], ensure_ascii=False)
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
    return {'cards':rows, 'total':total, 'next_cursor':next_cursor}


def card_detail(card_id, include_explanation=False):
    with connect() as db:
        row = db.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
        if not row:
            return {'card':None, 'encounters':[], 'history':[]}
        encounters = [dict(r) for r in db.execute('SELECT * FROM encounters WHERE card_id=? ORDER BY created DESC,id DESC', (card_id,))]
        history = [dict(r) for r in db.execute('SELECT rating,created,mode FROM reviews WHERE card_id=? ORDER BY id', (card_id,))]
        retention = get_settings(db)['retention']
    card = compact_card(row)
    card['progress'] = card_progress(Card.from_json(card['card_json']), history, now(), retention)
    detail = {'card':card, 'encounters':encounters, 'history':history}
    if include_explanation:
        detail['result'] = dictionary_explain({'query':card['word'], 'context':card['context'], 'source':card['source']})
    return detail


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
                return self.send(card_detail(int(arg('id', '0')), include_explanation=arg('explain') == '1'))
            if path == '/api/stats':
                return self.send(stats())
            if path == '/api/library':
                if 'limit' in qs:
                    return self.send(library_page(arg('q')[:200], arg('status', 'all'), sort=arg('sort', 'recent'),
                        limit=int(arg('limit')), cursor=arg('cursor')))
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
        except (ValueError, TypeError):
            self.send({'error':'查询条件无效，请重新选择。'}, 400)
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
                '/api/explain':dictionary_explain, '/api/definition':edit_definition, '/api/undo-collection':undo_collection,
                '/api/rate':rate, '/api/undo':undo_review, '/api/sentence':add_sentence,
                '/api/settings':update_settings, '/api/import':import_backup, '/api/extra-new':add_new_today,
            }
            if path in routes:
                return self.send(routes[path](data))
            if path == '/api/speech':
                return self.send(pronounce(data), mime='audio/wav')
            if path == '/api/toggle':
                with connect() as db:
                    card_id = int(data['id'])
                    if not db.execute('UPDATE cards SET paused=1-paused WHERE id=?', (card_id,)).rowcount:
                        raise ReviewConflict('这个词已被移除。')
                    paused = bool(db.execute('SELECT paused FROM cards WHERE id=?', (card_id,)).fetchone()[0])
                return self.send({'ok':True, 'paused':paused, 'stats':stats()})
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
    # HTTPServer enables SO_REUSEADDR, which on Windows lets a second Leaf bind
    # the same port instead of failing, leaving idle duplicate servers behind.
    # Claim the port exclusively so a second launch hands over to the first.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # Skip HTTPServer's reverse DNS lookup (socket.getfqdn), which can stall startup.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


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
