import json
import unittest
import helpers
import app
from learner_dictionary import get_entry, info

class LearnerTests(unittest.TestCase):
    setUp=helpers.TempData.setUp
    tearDown=helpers.TempData.tearDown

    def explain(self,word,**extra):
        return app.dictionary_explain({'query':word,**extra})['explanation']

    def test_corpus_installed_and_generated_rules_not_published(self):
        meta=info()
        self.assertGreater(meta['entries'],84212)
        self.assertEqual(meta['audit']['source_senses'],241427)
        for word in ('run','subtle','crystalline','ubiquitous'):
            doc=get_entry(word)
            self.assertTrue(doc)
            for sense in doc['senses']:
                if sense['usage']:self.assertTrue(sense['verified_usage'])

    def test_field_domain_is_not_just_in_the_summary(self):
        result=self.explain('field')
        self.assertTrue(any('领域' in s['gloss'] and '研究' in s['definition'] for s in result['learner_senses']))
        self.assertFalse(any('电场' in str(s) for s in result['learner_senses']))

    def test_run_distance_rule_corrected(self):
        doc=get_entry('run')
        sense=next(s for s in doc['senses'] if s['pos']=='verb' and s['etymology']=='et1' and s['sid']=='s1')
        self.assertIn('run a mile',sense['usage'])
        self.assertIn('可以直接接距离',sense['usage'])
        self.assertNotIn('不能在这个意义下',sense['usage'])

    def test_bank_no_forced_single_origin_story_in_main_definition(self):
        result=self.explain('bank')
        self.assertNotIn('隆起',result['core_meaning'])
        for sense in result['learner_senses']:self.assertNotIn('隆起',sense['definition'])

    def test_legacy_and_names_do_not_displace_modern_definitions(self):
        for word in ('informed','inform','act','subtle'):
            result=self.explain(word)
            self.assertTrue(all(s['section']=='main' for s in result['learner_senses']))
            self.assertFalse(any(set(s['labels'])&{'obsolete','archaic','dated','rare'} for s in result['learner_senses']))
        self.assertNotIn('入学考试',self.explain('act')['core_meaning'])

    def test_missing_conjunction_part_of_speech_restored(self):
        for word in ('and','or','if','unless','although','because','whereas','albeit'):
            result=self.explain(word)
            self.assertTrue(any(s['pos']=='conj' for s in result['learner_senses']),word)

    def test_spelling_and_inflection_recovery_keep_query_identity(self):
        for word in ('summarise','catalog','cozy','fascinate','entitle','underlie'):
            result=app.dictionary_explain({'query':word})
            self.assertEqual(result['word'],word)
            self.assertTrue(result['explanation']['learner_senses'])
        # A verb cannot be substituted by its adjective merely to fill a gap.
        self.assertEqual(get_entry('fascinate')['word'],'fascinate')
        self.assertEqual(get_entry('fascinated')['word'],'fascinated')

    def test_large_word_entry_backup_and_review_round_trip(self):
        result=app.dictionary_explain({'query':'run','save':True})
        card=helpers.full_row(result['saved_card']['id'])
        parsed=json.loads(card['explanation_json'])
        self.assertEqual(parsed['learner_word'],'run')
        self.assertLess(len(card['explanation_json']),30000)
        self.assertTrue(app.review_next()['card']['explanation']['learner_senses'])
        payload={'app':app.APP_ID,'version':1,'cards':[card]}
        with app.connect() as db:db.execute('DELETE FROM cards')
        self.assertEqual(app.import_backup(payload)['imported'],1)
        self.assertEqual(app.library()[0]['card_json'],card['card_json'])
        self.assertTrue(app.review_next()['card']['explanation']['learner_senses'])
