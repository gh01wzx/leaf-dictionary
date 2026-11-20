from datetime import datetime, time, timedelta, timezone
import json
import unittest
from unittest.mock import patch
import test_app
import app
import helpers
from fsrs import Card, State


class ReviewFlowTests(unittest.TestCase):
    setUp = test_app.LearningTests.setUp
    tearDown = test_app.LearningTests.tearDown
    start = datetime(2026, 10, 18, 22, tzinfo=timezone.utc)

    def create(self, word='reluctant'):
        row=helpers.collect(word)
        card=Card.from_json(row['card_json']); card.due=self.start
        with app.connect() as db:
            db.execute('UPDATE cards SET card_json=?,due=? WHERE id=?',(card.to_json(),card.due.isoformat(),row['id']))
        return row['id']

    def row(self, row_id):
        return next(row for row in app.library() if row['id']==row_id)

    def answer(self, row_id, rating, at=None):
        row=self.row(row_id)
        with patch('app.now',return_value=at or datetime.fromisoformat(row['due'])):
            result=app.rate({'id':row_id,'rating':rating,'version':row['card_json']})
        return result, Card.from_json(self.row(row_id)['card_json'])

    def test_remembered_words_progress_from_learning_to_longer_intervals(self):
        row_id=self.create()
        _,first=self.answer(row_id,3)
        self.assertEqual(first.due-self.start,timedelta(minutes=10))
        _,second=self.answer(row_id,3)
        self.assertEqual(second.state,State.Review)
        second_interval=second.due-first.due
        self.assertGreaterEqual(second_interval,timedelta(days=1))
        _,third=self.answer(row_id,3)
        self.assertGreater(third.due-second.due,second_interval)

    def test_forgetting_a_review_word_returns_to_short_relearning(self):
        row_id=self.create()
        self.answer(row_id,3); _,learned=self.answer(row_id,3)
        _,forgotten=self.answer(row_id,1)
        self.assertEqual(forgotten.state,State.Relearning)
        self.assertEqual(forgotten.due-learned.due,timedelta(minutes=10))

    def test_hard_is_a_successful_recall_and_different_from_forgotten(self):
        hard_id=self.create(); forgot_id=self.create('bank')
        _,hard=self.answer(hard_id,2); _,forgot=self.answer(forgot_id,1)
        self.assertGreater(hard.stability,forgot.stability)
        self.assertGreater(hard.due,forgot.due)

    def test_schedule_and_log_use_the_identical_timestamp(self):
        row_id=self.create(); at=self.start+timedelta(hours=2)
        _,card=self.answer(row_id,3,at)
        with app.connect() as db:
            row=db.execute('SELECT created,log_json FROM reviews').fetchone()
        self.assertEqual(card.last_review,at)
        self.assertEqual(datetime.fromisoformat(row['created']),at)
        self.assertEqual(datetime.fromisoformat(json.loads(row['log_json'])['review_datetime']),at)

    def test_early_or_duplicate_rating_does_not_change_history(self):
        row_id=self.create(); original=self.row(row_id)
        self.answer(row_id,3)
        updated=self.row(row_id)
        # A stale version is always refused.
        with patch('app.now',return_value=self.start+timedelta(seconds=5)):
            with self.assertRaises(app.ReviewConflict):
                app.rate({'id':row_id,'rating':3,'version':original['card_json']})
        # Even short steps must wait. Reloading must not compress a ten-minute interval.
        with patch('app.now', return_value=self.start + timedelta(minutes=2)):
            with self.assertRaises(app.ReviewConflict):
                app.rate({'id':row_id, 'rating':3, 'version':updated['card_json']})
            self.assertIsNone(app.review_next()['card'])
            self.assertIsNone(app.review_next(focus=row_id)['card'])
        _, learned = self.answer(row_id, 3)
        self.assertEqual(learned.state, State.Review)
        updated = self.row(row_id)
        with patch('app.now', return_value=learned.last_review + timedelta(minutes=1)):
            with self.assertRaises(app.ReviewConflict):
                app.rate({'id':row_id, 'rating':3, 'version':updated['card_json']})
        with app.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0],2)
        self.assertEqual(self.row(row_id)['card_json'],updated['card_json'])

    def test_queue_waits_until_due_and_does_not_advance_when_viewed(self):
        row_id=self.create(); _,card=self.answer(row_id,3)
        before=self.row(row_id)['card_json']
        # Right after answering, the same word is not shown again early.
        with patch('app.now',return_value=card.due-timedelta(microseconds=1)):
            self.assertIsNone(app.review_next(last=row_id)['card'])
        with patch('app.now',return_value=card.due):
            self.assertEqual(app.review_next(last=row_id)['card']['id'],row_id)
        self.assertEqual(self.row(row_id)['card_json'],before)

    def test_review_uses_the_same_learner_pronunciation_as_lookup(self):
        entry=app.dictionary_explain({'query':'demagogic','save':True})
        review=app.review_next()['card']
        self.assertEqual(review['phonetic'],entry['phonetic'])
        self.assertEqual(review['explanation']['core_meaning'],entry['explanation']['core_meaning'])

    def test_daily_counts_deduplicate_words_but_keep_all_practice(self):
        first=self.create(); second=self.create('bank')
        for _ in range(47):
            with app.connect() as db:
                db.execute('INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,?,?,?)',(first,3,self.start.isoformat(),'{}'))
        with app.connect() as db:
            db.execute('INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,?,?,?)',(second,3,self.start.isoformat(),'{}'))
        with patch('app.now',return_value=self.start+timedelta(seconds=1)):
            stats=app.stats()
        self.assertEqual(stats['reviewed_today'],2)
        self.assertEqual(stats['review_attempts_today'],48)
        self.assertEqual(stats['week'][stats['today']],2)
        self.assertEqual(stats['week_attempts'][stats['today']],48)

    def test_calendar_boundaries_and_offset_timestamps(self):
        row_id=self.create()
        tz=timezone(timedelta(hours=13))
        at=datetime(2026,10,19,0,1,tzinfo=tz).astimezone(timezone.utc)
        times=[at-timedelta(minutes=2),at,at+timedelta(days=1),at-timedelta(days=8)]
        with app.connect() as db:
            for t in times:
                db.execute('INSERT INTO reviews(card_id,rating,created,log_json) VALUES(?,?,?,?)',(row_id,3,t.astimezone(tz).isoformat(),'{}'))
        with patch('app.now',return_value=at),patch('app.study_day',side_effect=lambda t:t.astimezone(tz).date()),patch('app.day_start',side_effect=lambda d:datetime.combine(d,time(0),tz).astimezone(timezone.utc)):
            stats=app.stats()
        self.assertEqual(stats['today'],'2026-10-19')
        self.assertEqual(stats['week']['2026-10-18'],1)
        self.assertEqual(stats['week']['2026-10-19'],1)
        self.assertEqual(sum(stats['week'].values()),2)
        self.assertEqual(stats['review_attempts_today'],1)
        self.assertEqual(len(stats['week']),7)

    def test_completion_excludes_paused_words_and_due_words_from_next_time(self):
        due_id=self.create(); future_id=self.create('bank')
        _,future=self.answer(future_id,3)
        with patch('app.now',return_value=self.start):
            stats=app.stats()
        self.assertEqual(stats['due'],1)
        self.assertEqual(stats['next_due'],future.due.isoformat())
        with app.connect() as db:db.execute('UPDATE cards SET paused=1 WHERE id=?',(future_id,))
        with patch('app.now',return_value=self.start):self.assertIsNone(app.stats()['next_due'])
