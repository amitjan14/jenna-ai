import io
import json
import os
import unittest
import wave
from unittest.mock import Mock, patch
from main.src.tools import web_tools, voice


class WebTests(unittest.TestCase):
    def test_missing_key(self):
        with patch.dict(os.environ,{'TAVILY_API_KEY':''}):
            with self.assertRaises(web_tools.WebSearchError):web_tools.search_web('question')

    def test_web_response_normalization(self):
        payload={'results':[{'url':'https://example.com/policy','title':'Policy','content':'The policy allows 18 days.'},
                            {'url':'https://example.com/policy','title':'Duplicate','content':'same'},
                            {'url':'javascript:alert(1)','content':'unsafe link'}]}
        response=Mock();response.read.return_value=json.dumps(payload).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'TAVILY_API_KEY':'test-only'}),patch.object(web_tools,'urlopen',return_value=response):
            sources=web_tools.search_web('leave policy')
        self.assertEqual(len(sources),1)
        self.assertEqual(sources[0]['kind'],'web')
        self.assertEqual(sources[0]['url'],'https://example.com/policy')

    def test_bad_web_response(self):
        response=Mock();response.read.return_value=b'not json'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'TAVILY_API_KEY':'test-only'}),patch.object(web_tools,'urlopen',return_value=response):
            with self.assertRaises(web_tools.WebSearchError):web_tools.search_web('question')

    def test_advanced_search_requests_relevant_chunks(self):
        response=Mock();response.read.return_value=b'{"results": []}'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.dict(os.environ,{'TAVILY_API_KEY':'test-only'}),patch.object(web_tools,'urlopen',return_value=response) as fetch:
            web_tools.search_web('What is the capital of Japan?',search_depth='advanced')
        body=json.loads(fetch.call_args.args[0].data)
        self.assertEqual(body['search_depth'],'advanced')
        self.assertEqual(body['chunks_per_source'],3)
        self.assertFalse(body['include_answer'])


class VoiceTests(unittest.TestCase):
    def wav(self,seconds):
        data=io.BytesIO()
        with wave.open(data,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
            wav.writeframes(b'\0\0'*(16000*seconds))
        return data.getvalue()

    def test_long_audio_rejected_before_model_load(self):
        with patch.object(voice,'get_transcriber') as loader:
            with self.assertRaises(ValueError):voice.transcribe_audio(self.wav(61))
            loader.assert_not_called()

    def test_transcription_text(self):
        import threading
        transcriber=Mock();transcriber.transcribe.return_value=([Mock(text=' Hello Jenna. ')],{})
        with patch.object(voice,'get_transcriber',return_value=(transcriber,threading.Lock())):
            self.assertEqual(voice.transcribe_audio(self.wav(1)),'Hello Jenna.')


if __name__=='__main__':unittest.main()
