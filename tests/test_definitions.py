"""Personal definitions must outlive lookups and upgrades without touching FSRS."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
import helpers


class DefinitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=app.DATA_DIR
        app.DATA_DIR=Path(self.temp.name)
        app.initialize()

    def tearDown(self):
        app.DATA_DIR=self.original
        self.temp.cleanup()

    def edit(self, word='canonical', meaning='某个领域公认、正式采用的标准。', expected=''):
        return app.edit_definition({'word':word,'meaning':meaning,'expected':expected})

    def export(self):
        with app.connect() as db:
            return {'app':app.APP_ID,'version':1,**{table:[dict(r) for r in db.execute('SELECT * FROM '+table)]
                for table in ('cards','encounters','reviews','definition_overrides')}}

    def test_edit_unsaved_word_persists_without_collecting_and_does_not_affect_lemma(self):
        original=app.dictionary_explain({'query':'informed'})['explanation']['core_meaning']
        self.edit(' INFORMED! ','我理解的释义\n第二行。')
        app.initialize()
        result=app.dictionary_explain({'query':'informed'})
        self.assertEqual(result['explanation']['core_meaning'],'我理解的释义\n第二行。')
        self.assertEqual(result['explanation']['dictionary_core_meaning'],original)
        self.assertTrue(result['explanation']['custom_definition'])
        self.assertFalse(app.dictionary_explain({'query':'inform'})['explanation']['custom_definition'])
        self.assertEqual(app.stats()['total'],0)

    def test_existing_card_review_list_recent_and_search_all_use_personal_text(self):
        saved=app.dictionary_explain({'query':'canonical','save':True})['saved_card']
        before=self.export()
        custom=self.edit()
        for _ in range(2):
            card=app.review_next()['card']
            self.assertEqual(card['id'],saved['id'])
            self.assertEqual(card['meaning'],custom['meaning'])
            self.assertEqual(card['explanation']['core_meaning'],custom['meaning'])
            self.assertEqual(card['card_json'],saved['card_json'])
        self.assertEqual(app.library()[0]['meaning'],custom['meaning'])
        self.assertEqual(app.library(brief=True)[0]['meaning'],custom['meaning'])
        self.assertEqual(len(app.library(q='正式采用')),1)
        self.assertEqual(app.stats()['recent'][0]['meaning'],custom['meaning'])
        after=self.export()
        for table in ('cards','encounters','reviews'):
            self.assertEqual(before[table],after[table])

    def test_restore_and_repeat_collection_never_bake_custom_text_into_dictionary(self):
        original=app.dictionary_explain({'query':'canonical'})['explanation']['core_meaning']
        custom=self.edit()
        saved=app.dictionary_explain({'query':'canonical','save':True})['saved_card']
        self.assertEqual(saved['meaning'],custom['meaning'])
        raw=self.export()['cards'][0]
        self.assertEqual(json.loads(raw['explanation_json'])['core_meaning'],original)
        self.edit(meaning=None,expected=custom['updated'])
        self.assertEqual(app.dictionary_explain({'query':'canonical'})['explanation']['core_meaning'],original)
        self.assertEqual(app.review_next()['card']['explanation']['core_meaning'],original)
        self.assertEqual(app.library()[0]['meaning'],raw['meaning'])
        self.assertEqual(app.stats()['total'],1)

    def test_dictionary_presentation_upgrade_preserves_edit_and_learning_schedule(self):
        saved=app.dictionary_explain({'query':'canonical','save':True})['saved_card']
        app.rate({'id':saved['id'],'rating':3,'version':saved['card_json']})
        before=app.library()[0]
        custom=self.edit()
        with patch.object(app,'PRESENTATION_VERSION',999):
            app.initialize()
        self.assertEqual(app.dictionary_explain({'query':'canonical'})['explanation']['core_meaning'],custom['meaning'])
        after=app.library()[0]
        self.assertEqual(after['card_json'],before['card_json'])
        self.assertEqual(after['due'],before['due'])
        self.assertEqual(len(self.export()['reviews']),1)

    def test_legacy_cards_are_editable_without_destroying_old_meaning(self):
        saved=helpers.collect('bank')
        custom=self.edit('bank','水边的陆地。')
        card=app.review_next()['card']
        self.assertEqual(card['explanation']['core_meaning'],'水边的陆地。')
        self.assertEqual(card['meaning'],'水边的陆地。')
        self.assertEqual(card['explanation']['dictionary_core_meaning'],saved['meaning'])
        self.edit('bank',None,custom['updated'])
        self.assertEqual(app.review_next()['card']['meaning'],saved['meaning'])

    def test_backup_carries_edits_for_unsaved_words_and_keeps_local_edits_on_merge(self):
        self.edit()
        self.edit('credo','指引行动的一套信念。')
        payload=self.export()
        with tempfile.TemporaryDirectory() as other:
            app.DATA_DIR=Path(other);app.initialize()
            self.assertEqual(app.import_backup(payload)['imported'],0)
            result=app.dictionary_explain({'query':'canonical'})['explanation']
            self.assertIn('正式采用',result['core_meaning'])
            self.edit(meaning='本机的新释义。',expected=result['custom_updated'])
            app.import_backup(payload)
            self.assertEqual(app.dictionary_explain({'query':'canonical'})['explanation']['core_meaning'],'本机的新释义。')
            self.assertEqual(app.stats()['total'],0)
        app.DATA_DIR=Path(self.temp.name)

    def test_invalid_import_is_atomic_and_old_backups_still_work(self):
        payload=self.export()
        payload['definition_overrides']=[{'word':'canonical','meaning':'有效。','updated':app.now().isoformat()},
            {'word':'credo','meaning':'','updated':app.now().isoformat()}]
        with self.assertRaises(ValueError):app.import_backup(payload)
        self.assertEqual(self.export()['definition_overrides'],[])
        payload.pop('definition_overrides')
        self.assertEqual(app.import_backup(payload)['imported'],0)

    def test_empty_overlong_invalid_and_concurrent_edits_cannot_overwrite_saved_text(self):
        for text in ('   ','a'*3001,123):
            with self.assertRaises(ValueError):self.edit(meaning=text)
        with self.assertRaises(ValueError):self.edit('zznotarealwordzz','内容。')
        custom=self.edit()
        with self.assertRaises(app.DefinitionConflict):self.edit(meaning='旧窗口覆盖。')
        with self.assertRaises(app.DefinitionConflict):self.edit(meaning=None)
        self.assertEqual(app.dictionary_explain({'query':'canonical'})['explanation']['core_meaning'],custom['meaning'])

    def test_imported_phrase_outside_lexicon_is_searchable_editable_and_reviewable(self):
        word='with bearing of'
        self.assertFalse(app.dictionary_explain({'query':word})['found'])
        card=app.Card()
        stamp=app.now().isoformat()
        original='带着某种仪态、风度，通常见于 with the bearing of。'
        with app.connect() as db:
            card_id=db.execute('''INSERT INTO cards(word,sense_key,meaning,card_json,due,created,updated)
                VALUES(?,?,?,?,?,?,?)''',(word,'personal:import',original,card.to_json(),card.due.isoformat(),stamp,stamp)).lastrowid
        change=self.edit(word,'带着……的仪态。')
        result=app.dictionary_explain({'query':word})
        self.assertTrue(result['found'])
        self.assertTrue(result['can_save'])
        self.assertEqual(result['explanation']['origin'],'personal')
        self.assertEqual(result['explanation']['core_meaning'],change['meaning'])
        self.assertEqual(result['explanation']['dictionary_core_meaning'],original)
        self.assertEqual(app.review_next()['card']['meaning'],change['meaning'])
        saved=app.dictionary_explain({'query':word,'save':True})['saved_card']
        self.assertEqual(saved['id'],card_id)
        self.assertEqual(saved['card_json'],card.to_json())
        self.edit(word,None,change['updated'])
        self.assertEqual(app.dictionary_explain({'query':word})['explanation']['core_meaning'],original)

    def test_personal_only_backup_entry_can_be_queried_without_collecting(self):
        word='a newly imported phrase'
        with app.connect() as db:
            db.execute('INSERT INTO definition_overrides VALUES(?,?,?)',(word,'这是一条个人整理的短语解释。',app.now().isoformat()))
        result=app.dictionary_explain({'query':word})
        self.assertTrue(result['found'])
        self.assertEqual(result['explanation']['core_meaning'],'这是一条个人整理的短语解释。')
        self.assertEqual(app.stats()['total'],0)

    def test_personal_entry_replaces_english_only_placeholder_without_warning(self):
        word='beakish'
        with app.connect() as db:
            db.execute('INSERT INTO definition_overrides VALUES(?,?,?)',(word,'形状像鸟喙的，常用于鼻子。',app.now().isoformat()))
        entry={'found':True,'word':word,'phonetic':'','meanings':[{'pos':'adj','text':'resembling a beak'}]}
        with patch.object(app,'lookup',return_value=entry),patch.object(app,'learner_entry',return_value=None):
            result=app.dictionary_explain({'query':word})
        self.assertTrue(result['can_save'])
        self.assertEqual(result['dictionary_source'],'我的整理词条')
        self.assertEqual(result['explanation']['warning'],'')


if __name__=='__main__':unittest.main()
