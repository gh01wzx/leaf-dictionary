import unittest
import json
from unittest.mock import patch
import helpers
import app
from dictionary_engine import make_result

class DictionaryTests(unittest.TestCase):
    setUp=helpers.TempData.setUp
    tearDown=helpers.TempData.tearDown
    def test_dictionary_has_no_model_path(self):
        self.assertFalse(hasattr(app,'MODEL'))
        self.assertFalse(hasattr(app,'ai_explain'))
        result=app.dictionary_explain({'query':'field','save':True})
        self.assertTrue(result['found'])
        self.assertNotIn('model',result)
        self.assertEqual(result['explanation']['origin'],'dictionary')
        self.assertEqual(app.stats()['total'],1)

    def test_field_common_and_specialist_meanings_are_separate(self):
        result=app.dictionary_explain({'query':'field'})
        self.assertIn('领域',result['explanation']['core_meaning'])
        self.assertNotIn('电场',result['explanation']['core_meaning'])
        self.assertTrue(any('电场' in str(x) for x in result['explanation']['supplementary_senses']))
        self.assertNotIn('COBUILD',result['dictionary_source'])

    def test_informed_does_not_lose_requested_form(self):
        result=app.dictionary_explain({'query':'informed','context':'Values are informed by experience.','save':True})
        self.assertEqual(result['word'],'informed')
        self.assertIn('影响',result['explanation']['context_meaning'])
        self.assertEqual(result['saved_card']['word'],'informed')

    def test_unedited_entries_do_not_claim_premium_source(self):
        result=app.dictionary_explain({'query':'bicycle'})
        self.assertIn('自行车',result['explanation']['core_meaning'])
        self.assertNotIn('COBUILD',result['dictionary_source'])
        self.assertTrue(result['explanation']['learner_senses'])

    def test_queries_do_not_save_without_explicit_request(self):
        for word in ('demagogic','ubiquitous','bicycle'):
            for _ in range(2):
                app.dictionary_explain({'query':word})
        self.assertEqual(app.stats()['total'],0)

    def test_compact_library_omits_heavy_payloads_and_preserves_saved_record(self):
        card=app.dictionary_explain({'query':'field','save':True})['saved_card']
        brief=app.library(brief=True)[0]
        self.assertEqual(brief['id'],card['id'])
        self.assertEqual(brief['meaning'],card['meaning'])
        self.assertNotIn('explanation_json',brief)
        self.assertNotIn('card_json',brief)
        self.assertEqual(app.library()[0]['card_json'],card['card_json'])
        self.assertEqual(app.library(q='field',brief=True)[0]['id'],card['id'])
        self.assertEqual(app.library(status='paused',brief=True),[])

    def test_demagogic_explains_purpose_and_tone_in_chinese(self):
        result=app.dictionary_explain({'query':'demagogic'})['explanation']
        self.assertIn('争取支持',result['core_meaning'])
        self.assertIn('情绪',result['core_meaning'])
        self.assertIn('贬义',result['part_of_speech'])
        self.assertNotIn('demagogue',result['core_meaning'])
        self.assertIn('demagogue',result['word_family'])
        self.assertIn('CC BY-SA',result['reference_title'])

    def test_unedited_words_never_promote_english_to_primary_definition(self):
        for word in ('crystalline','sanguine','xylophagous','quark','bicycle'):
            with self.subTest(word=word):
                result=app.dictionary_explain({'query':word})
                self.assertRegex(result['explanation']['core_meaning'],r'[\u3400-\u9fff]')
                self.assertIn(result['explanation']['core_label'],('中文简释','核心释义'))

    def test_no_chinese_translation_does_not_create_placeholder_card(self):
        entry={'found':True,'word':'test','phonetic':'','meanings':[{'pos':'n','text':'an English definition'}]}
        with patch.object(app,'lookup',return_value=entry), patch.object(app,'learner_entry',return_value=None):
            result=app.dictionary_explain({'query':'test','save':True})
        self.assertFalse(result['can_save'])
        self.assertEqual(result['explanation']['core_label'],'暂无中文释义')
        self.assertEqual(app.stats()['total'],0)

    def test_manual_add_deduplicates_case_and_context_without_resetting_schedule(self):
        first=app.dictionary_explain({'query':'demagogic','context':'A first sentence.','save':True})['saved_card']
        app.rate({'id':first['id'],'rating':3,'version':first['card_json']})
        progress=app.library()[0]
        second=app.dictionary_explain({'query':' DEMAGOGIC! ','context':'A second sentence.','save':True})['saved_card']
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(second['card_json'],progress['card_json'])
        self.assertEqual(second['due'],progress['due'])
        self.assertEqual(app.stats()['total'],1)
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM encounters').fetchone()[0],2)

    def test_upgrade_merges_existing_duplicates_preserving_history_and_progress(self):
        first=app.dictionary_explain({'query':'demagogic','context':'First context.','save':True})['saved_card']
        first=helpers.full_row(first['id'])
        app.rate({'id':first['id'],'rating':1,'version':first['card_json']})
        progress=app.library()[0]
        with app.connect() as db:
            db.execute('DROP INDEX one_card_per_word')
            db.execute('''INSERT INTO cards(word,sense_key,meaning,context,source,card_json,due,created,updated)
                VALUES(?,?,?,?,?,?,?,?,?)''',('DEMAGOGIC','old-sense','old meaning','Second context.','Book',first['card_json'],first['due'],first['created'],first['updated']))
            old=json.loads(first['explanation_json'])
            old.pop('presentation_version')
            old['core_meaning']='characteristic of or resembling a demagogue'
            db.execute('UPDATE cards SET meaning=?,explanation_json=? WHERE id=?',
                (old['core_meaning'],json.dumps(old),first['id']))
        app.initialize()
        self.assertEqual(app.stats()['total'],1)
        updated=app.library()[0]
        self.assertEqual(updated['id'],first['id'])
        self.assertEqual(updated['card_json'],progress['card_json'])
        self.assertEqual(updated['due'],progress['due'])
        self.assertIn('争取支持',updated['meaning'])
        self.assertEqual(app.stats()['reviewed_today'],1)
        with app.connect() as db:
            contexts={r[0] for r in db.execute('SELECT context FROM encounters')}
        self.assertEqual(contexts,{'First context.','Second context.'})
        self.assertTrue(list((app.DATA_DIR/'backups').glob('*.sqlite3')))

    def test_backup_import_deduplicates_words_and_merges_history_idempotently(self):
        first=app.dictionary_explain({'query':'demagogic','context':'Original context.','save':True})['saved_card']
        app.rate({'id':first['id'],'rating':1,'version':first['card_json']})
        local=app.library()[0]
        duplicate={**local,'id':123,'word':'DEMAGOGIC','sense_key':'old-key','context':'Imported context.'}
        with app.connect() as db:
            reviews=[{**dict(row),'card_id':123} for row in db.execute('SELECT * FROM reviews')]
        payload={'app':app.APP_ID,'version':1,'cards':[duplicate],'reviews':reviews}
        for _ in range(2):
            self.assertEqual(app.import_backup(payload)['imported'],0)
        self.assertEqual(app.stats()['total'],1)
        self.assertEqual(app.stats()['reviewed_today'],1)
        self.assertEqual(app.library()[0]['card_json'],local['card_json'])
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM encounters').fetchone()[0],2)

    def test_not_found_not_saved(self):
        result=app.dictionary_explain({'query':'zznotawordzz','save':True})
        self.assertFalse(result['found'])
        self.assertEqual(app.stats()['total'],0)
