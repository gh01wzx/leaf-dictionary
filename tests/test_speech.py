import io
import json
import sys
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import wave
import helpers
import app
import offline_speech as speech


class SpeechTests(unittest.TestCase):
    def test_word_validation_supports_words_and_phrases_without_shell_syntax(self):
        for word in ("can't",'well-informed','put up with','café','U.S.'):
            self.assertEqual(speech.validate_word(word),word)
        for word in ('',None,[], 'a'*121,'<speak>hello</speak>','$(calc)', 'hello;exit'):
            with self.subTest(word=word),self.assertRaises(ValueError):speech.validate_word(word)

    def test_accent_and_slow_are_validated_before_synthesis(self):
        status={'available':True,'default':'en-US','accents':[{'id':'en-US','voice':'Local voice'}]}
        with patch.object(speech,'speech_status',return_value=status),patch.object(speech,'synthesize',return_value=b'wav') as synth:
            self.assertEqual(speech.pronounce({'word':'field','slow':True}),b'wav')
            synth.assert_called_once_with('field','Local voice',True)
            with self.assertRaises(speech.SpeechUnavailable):speech.pronounce({'word':'field','accent':'en-GB'})
            with self.assertRaises(ValueError):speech.pronounce({'word':'field','slow':'false'})

    def test_missing_local_voice_has_a_clear_message_and_no_cloud_fallback(self):
        with patch.object(speech,'installed_voices',return_value=()):
            status=speech.speech_status()
            self.assertFalse(status['available'])
            self.assertTrue(status['offline'])
            with self.assertRaises(speech.SpeechUnavailable):speech.pronounce({'word':'field'})

    @unittest.skipUnless(sys.platform=='win32','Windows speech engine required')
    def test_actual_local_english_audio_and_slow_rate(self):
        status=speech.speech_status()
        if not status['available']:self.skipTest(status['message'])
        duration=[]
        for slow in (False,True):
            audio=speech.pronounce({'word':'dictionary','slow':slow})
            with wave.open(io.BytesIO(audio),'rb') as reader:
                self.assertGreater(reader.getnframes(),1000)
                duration.append(reader.getnframes()/reader.getframerate())
        self.assertGreater(duration[1],duration[0])


class SpeechHTTPTests(unittest.TestCase):
    setUp=helpers.TempData.setUp
    tearDown=helpers.TempData.tearDown

    def test_audio_route_requires_csrf_and_never_collects_words(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.object(app,'pronounce',return_value=b'RIFF-test-audio') as pronounce:
                for token,status in [('wrong',403),(app.TOKEN,200)]:
                    req=urllib.request.Request(base+'/api/speech',data=b'{"word":"field"}',
                        headers={'Content-Type':'application/json','X-Leaf-Token':token})
                    if status==403:
                        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req)
                        self.assertEqual(cm.exception.code,403)
                        pronounce.assert_not_called()
                    else:
                        with urllib.request.urlopen(req) as response:
                            self.assertEqual(response.headers['Content-Type'],'audio/wav')
                            self.assertEqual(response.read(),b'RIFF-test-audio')
                            self.assertIn("media-src 'self' blob:",response.headers['Content-Security-Policy'])
                self.assertEqual(app.stats()['total'],0)
        finally:
            server.shutdown();server.server_close();thread.join()
