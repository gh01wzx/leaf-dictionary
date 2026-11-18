"""Deterministic dictionary presentation. Never calls a model or the internet."""
import hashlib
import re
from learner_dictionary import present

FIELD = {
    'core_meaning':'field 常见的名词用法是：种植或放牧的一块土地、进行体育活动的场地，以及某种工作或研究的领域。动词搭配 field questions 指回答、应对别人提出的问题。',
    'usage':'a wheat field · a sports field · a field of research',
    'usage_meaning':'麦田 · 运动场 · 研究领域',
    'example_en':'She works in the field of education.',
    'example_zh':'她在教育领域工作。',
    'other_uses':['专业用法：electric / magnetic field 指电场、磁场；数据库中的 field 指字段。','其他搭配：field research / in the field 指实地研究、在现场；体育动词 field 可指接住或处理来球。'],
    'reference_url':'https://dictionary.cambridge.org/dictionary/english/field',
    'reference_title':'参考 Cambridge Dictionary 的 field 条目；中文为本原型整理摘要',
}
INFORMED = {
    'core_meaning':'informed 作形容词，常指了解了相关事实、掌握情况的。inform 这个动词除了“告知”，也有“影响、塑造某事物的内容或特点”的用法，因此 be informed by 可以表示“受……影响、以……为依据”。',
    'usage':'an informed decision · keep someone informed · be informed by',
    'usage_meaning':'在充分了解情况后作出的决定 · 让某人保持知情 · 受……影响',
    'example_en':'Her decisions are informed by experience.',
    'example_zh':'她作决定时会以经验为依据。',
    'reference_url':'https://www.collinsdictionary.com/dictionary/english/inform',
    'reference_title':'本原型整理摘要；原词库 inform 的英文定义包含影响、赋予特质这一用法',
}
DEMAGOGIC = {
    'part_of_speech':'形容词 · 贬义',
    'core_meaning':'为了争取支持而刻意迎合、煽动大众情绪的，尤其指用这种方式代替讲事实、讲道理。常用来批评政治人物的言论或手法。',
    'usage':'demagogic rhetoric · a demagogic politician',
    'usage_meaning':'靠煽动情绪争取支持的言辞 · 靠迎合、煽动民众争取支持的政客',
    'example_en':'The speech was demagogic: it stirred up anger but offered no real solutions.',
    'example_zh':'这场演说靠煽动民众情绪争取支持：它激起了愤怒，却没有提出真正的解决办法。',
    'explanation':'重点不只是“有煽动性”，而是“利用大众情绪争取支持”。这个词带批评意味。',
    'word_family':'它来自 demagogue，指靠煽动、迎合民众情绪来争取支持的政客；demagogic 是对应的形容词。',
    'reference_url':'https://www.collinsdictionary.com/us/dictionary/english/demagogic',
    'reference_title':'参考 Collins COBUILD 的 demagogic 条目；中文说明与例句由本原型整理',
}
DEMAGOGUE = {
    'part_of_speech':'名词 · 贬义',
    'core_meaning':'靠迎合、煽动大众的情绪或偏见来争取支持的政治人物，而不是靠讲道理说服人。',
    'usage':'a demagogue',
    'usage_meaning':'靠煽动民众争取支持的政客',
    'reference_url':'https://www.collinsdictionary.com/dictionary/english/demagogue',
    'reference_title':'本原型整理中文说明；参考 Collins 的 demagogue 条目',
}
DEMAGOGY = {
    'part_of_speech':'名词 · 贬义',
    'core_meaning':'为了争取政治支持而迎合、煽动民众情绪的做法，侧重激起情绪，而不是提出合理的论据。',
    'reference_url':'https://www.collinsdictionary.com/dictionary/english/demagogy',
    'reference_title':'参考 Collins COBUILD 的 demagogy 条目；中文为本原型整理说明',
}
READABLE_ENTRIES = {'field':FIELD, 'inform':INFORMED, 'informed':INFORMED,
    'demagogic':DEMAGOGIC, 'demagogical':DEMAGOGIC, 'demagogue':DEMAGOGUE,
    'demagogy':DEMAGOGY, 'demagoguery':DEMAGOGY}
PRESENTATION_VERSION = 4
PHONETICS = {'demagogic':'ˌdeməˈɡɒdʒɪk'}
POS_NAMES = {'n':'名词', 'v':'动词', 'vt':'及物动词', 'vi':'不及物动词',
    'a':'形容词', 'adj':'形容词', 'adv':'副词', 'prep':'介词', 'pron':'代词',
    'conj':'连词', 'interj':'感叹词', 'art':'冠词', 'num':'数词', 'aux':'助动词', 'pl':'复数'}

def chinese_meanings(entry):
    """Keep source wording/order. This is presentation, not a frequency ranking."""
    items = []
    for meaning in entry.get('meanings', []):
        text = meaning.get('text', '').strip()
        if re.search(r'[\u3400-\u9fff]', text):
            pos = POS_NAMES.get(meaning.get('pos', ''), '')
            items.append((pos, text))
    return items

def make_result(query, context, source, entry, curated, english_definition='', learner=None):
    base_word=entry.get('word','')
    if learner:
        entry={**entry,'found':True,'word':learner['word'],
            'phonetic':next(iter(learner['phonetics']),'').strip('/')}
    result = {'found':entry.get('found',False),'query':query,'word':query,'context':context,
        'source':source,'saved_card':None,'phonetic':'',
        'dictionary_source':'本地基础词库','source_kind':'dictionary'}
    explanation = {key:'' for key in ('lemma','part_of_speech','core_meaning','context_meaning',
        'context_translation','explanation','usage','usage_meaning','example_en','example_zh','warning')}
    explanation.update(valid_word=result['found'],other_uses=[],origin='dictionary',
        presentation_version=PRESENTATION_VERSION, core_label='核心释义',
        other_uses_label='其他用法', source_note='', english_definition='')
    if not result['found']:
        explanation['warning']='本地词库未找到这个词，请检查拼写或尝试原形。'
        result['explanation']=explanation
        return result
    result['lemma']=entry['word']
    result['phonetic']=entry['phonetic'] if entry['word'].lower()==query else ''
    result['phonetic']=PHONETICS.get(query,result['phonetic'])
    explanation['lemma']=entry['word']
    special = READABLE_ENTRIES.get(query) or READABLE_ENTRIES.get(entry['word'].lower())
    if learner:
        explanation.update(present(learner))
        if base_word and base_word not in (query,learner['word']):
            explanation['related_lemma']=base_word
        result['dictionary_source']='开放学习词库 · 修订版'
        if query in ('inform','informed') and re.search(r'\binformed\s+by\b',context,re.I):
            explanation['context_meaning']='be informed by：受……影响；以……为依据'
            explanation['explanation']='这里展示 informed by 的词典搭配义；不是自动翻译整段原文。'
    elif special:
        explanation.update(special)
        result['dictionary_source']='本地整理摘要'
        if query in ('inform','informed') and re.search(r'\binformed\s+by\b',context,re.I):
            explanation['context_meaning']='be informed by：受……影响；以……为依据'
            explanation['explanation']='原句包含词典搭配 informed by；此处展示该搭配的释义，不是自动翻译整句。'
    elif curated:
        result['dictionary_source']='本地整理条目'
        if curated.get('senses'):
            senses=curated['senses']
            explanation['core_meaning']='；'.join(x['text'] for x in senses[:3])+'。'
            explanation['other_uses']=[x['text'] for x in senses[3:5]]
            example=senses[0]
        else:
            explanation['core_meaning']=curated.get('summary','')
            explanation['explanation']=curated.get('note','')
            example=curated
        explanation['example_en']=example.get('example','')
        explanation['example_zh']=example.get('translation','')
    else:
        meanings = chinese_meanings(entry)
        explanation['core_label']='中文简释'
        explanation['english_definition']=english_definition[:6000]
        explanation['source_note']='基础词库原文，尚未做常用义筛选。'
        if meanings:
            # Prefer an untagged line over explicitly tagged specialist material.
            # Do not infer commonness from source order or discard other senses.
            primary = next((i for i, (_, text) in enumerate(meanings)
                if not re.match(r'^\[[^\]]+\]', text)), 0)
            explanation['part_of_speech'], explanation['core_meaning'] = meanings[primary]
            explanation['source_meanings'] = [f'{pos}：{text}' if pos else text
                for i, (pos, text) in enumerate(meanings) if i != primary]
        else:
            explanation['core_label']='暂无中文释义'
            explanation['core_meaning']='本地词库收录了这个词，但还没有可用的中文解释。'
            explanation['warning']='可展开英文原文参考；暂时不能加入生词本。'
        explanation['reference_title']='ECDICT 基础词库'
        explanation['reference_url']='https://github.com/skywind3000/ECDICT'
    result['can_save']=bool(learner or chinese_meanings(entry) or special or curated)
    explanation['dictionary_source']=result['dictionary_source']
    result['explanation']=explanation
    result['sense_key']='dict:'+hashlib.sha256((query+'\0'+context).encode()).hexdigest()[:24]
    return result
