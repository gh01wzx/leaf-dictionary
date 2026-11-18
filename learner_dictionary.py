"""Read the corrected, fixed offline learner corpus. Never generates text."""
from functools import lru_cache
import json
import sqlite3
import threading
import zlib

from paths import data_file

PATH = data_file('learner.sqlite3')
POS = {'noun':'名词','verb':'动词','adj':'形容词','adv':'副词','name':'专有名词',
    'conj':'连词','prep':'介词','pron':'代词','det':'限定词','intj':'感叹词',
    'phrase':'短语','proverb':'谚语','suffix':'后缀','prefix':'前缀','num':'数词'}
_local = threading.local()


def connect():
    """One read-only connection per server thread; the corpus never changes."""
    db = getattr(_local, 'db', None)
    if db is None:
        db = _local.db = sqlite3.connect(PATH.as_uri() + '?mode=ro', uri=True, check_same_thread=False)
    return db


@lru_cache(maxsize=512)
def get_entry(query, base=''):
    if not PATH.exists():
        return None
    db = connect()
    # Exact headword precedes spelling aliases, then attested base forms.
    row = db.execute('SELECT document FROM entries WHERE word=?', (query,)).fetchone()
    if not row:
        row = db.execute('SELECT e.document FROM aliases a JOIN entries e ON e.word=a.word WHERE a.alias=?', (query,)).fetchone()
    if not row and base and base != query:
        row = db.execute('SELECT document FROM entries WHERE word=?', (base,)).fetchone()
    if not row:
        # Ambiguous forms need a source-attested lemma or a user-visible
        # choice; never silently pick a name/adjective by alphabetical order.
        options = db.execute('SELECT word FROM forms WHERE form=? LIMIT 2', (query,)).fetchall()
        if len(options) == 1:
            row = db.execute('SELECT document FROM entries WHERE word=?', options[0]).fetchone()
    return json.loads(zlib.decompress(row[0])) if row else None


@lru_cache(maxsize=1)
def info():
    if not PATH.exists():
        return {'installed':False, 'entries':0}
    metadata = {key:json.loads(value) for key, value in connect().execute('SELECT key,value FROM metadata')}
    return {'installed':True, 'entries':metadata['counts']['compiled_entries'],
        'edition':metadata['edition'], 'license':metadata['license'],
        'source_url':metadata['source_url'], 'audit':metadata['counts']}


def forms(doc):
    """Inflected spellings the corpus attests for a headword."""
    if not doc:
        return []
    return [form for form in dict.fromkeys([doc['word'], *doc.get('forms', [])])
        if form and form != '-' and any(c.isalpha() for c in form)]


def present(doc):
    senses = doc['senses']
    main = [m for m in senses if m['section'] == 'main']
    # A genuinely rare/technical word must still receive a useful answer.
    visible = main or senses
    core = [m for m in visible if m['priority'] == 'core'] or visible
    overview = doc['overview']
    if not overview:
        pieces = []
        for m in core:
            first = m['definition'].split('。')[0] + '。'
            if first not in pieces:
                pieces.append(first)
            if len(pieces) == 3:
                break
        overview = ''.join(pieces)
    primary, seen = [], set()
    for key in doc.get('primary_keys', []):
        matched = next((m for m in visible if (m['pos'], m['etymology'], m['sid']) == tuple(key)), None)
        if matched:
            primary.append(matched)
            seen.add(tuple(key))
    for m in core + visible:
        if len(primary) == 3:
            break
        key = (m['pos'], m['etymology'], m['sid'])
        if key not in seen:
            primary.append(m)
            seen.add(key)
    other_main = [m for m in main if m not in primary]
    supplementary = [m for m in senses if m not in primary and m not in other_main]

    def for_return(m):
        return {**m, 'pos_label':POS.get(m['pos'], m['pos']) + (' · 贬义' if 'disapproving' in m['labels'] else ''),
            'section_label':{'rare':'少见或旧用法', 'specialist':'专业用法', 'proper':'专名用法', 'main':''}[m['section']]}

    return dict(core_meaning=overview, core_label='核心释义', lemma=doc['word'],
        part_of_speech=' · '.join(dict.fromkeys(POS.get(m['pos'], m['pos']) for m in primary))
            + (' · 贬义' if any('disapproving' in m['labels'] for m in primary) else ''),
        learner_word=doc['word'], learner_senses=[for_return(m) for m in primary],
        more_main_senses=[for_return(m) for m in other_main],
        supplementary_senses=[for_return(m) for m in supplementary],
        word_family=doc.get('word_family', ''), other_uses=[],
        example_en='', example_zh='', usage='', usage_meaning='',
        reference_url='https://github.com/ahpxex/open-dictionary/releases/tag/v2.0',
        reference_title='Open Dictionary / Wiktionary · CC BY-SA 4.0 · 本地修订版',
        editorial_references=doc['references'],
        source_note='固定中文词条，含上游预先生成内容。本版做过整库结构检查和部分词义修订，未逐条人工核对。未核实的用法规则与记忆联想不作为释义展示。')


def stored_explanation(explanation):
    """Keep compact snapshots; live details are hydrated from the fixed corpus."""
    return {key:value for key, value in explanation.items()
        if key not in ('learner_senses', 'more_main_senses', 'supplementary_senses')}
