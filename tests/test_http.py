"""Real HTTP integration tests for the standard-library web application."""
import json
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

from run import Handler
from engine.scenarios import scenarios


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def assert_http_error(self, request, status):
        with self.assertRaises(HTTPError) as failure:
            urlopen(request).close()
        with failure.exception as response:
            self.assertEqual(response.code, status)

    def test_serve_interface(self):
        with urlopen(self.base+'/') as response:
            html=response.read().decode('utf-8')
        self.assertIn('AISLE.AI',html.replace('<span>', '').replace('</span>',''))
        self.assertIn('warehouseCanvas',html)

    def test_json_presets(self):
        with urlopen(self.base+'/api/presets') as response:
            data=json.load(response)
        self.assertEqual(set(data['presets']),set(scenarios()))

    def test_analysis_api(self):
        request=Request(self.base+'/api/analyze',data=json.dumps(scenarios()['standard']).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request) as response:
            data=json.load(response)
        self.assertIn('hill_climbing',data)
        self.assertIn('risk_aware_controller',data['mdp'])
        self.assertEqual(data['mdp']['risk_aware_controller']['trials'],60)

    def test_invalid_api_request_returns_400(self):
        raw=scenarios()['standard']
        raw['tasks']=[]
        request=Request(self.base+'/api/analyze',data=json.dumps(raw).encode(),headers={'Content-Type':'application/json'},method='POST')
        self.assert_http_error(request, 400)

    def test_malformed_json_returns_400(self):
        request=Request(self.base+'/api/analyze',data=b'{oops',
                        headers={'Content-Type':'application/json'},method='POST')
        self.assert_http_error(request, 400)

    def test_non_object_json_returns_400(self):
        request=Request(self.base+'/api/analyze',data=b'[1,2,3]',
                        headers={'Content-Type':'application/json'},method='POST')
        self.assert_http_error(request, 400)

    def test_wrong_media_type_returns_415(self):
        request=Request(self.base+'/api/analyze',data=b'hello',
                        headers={'Content-Type':'text/plain'},method='POST')
        self.assert_http_error(request, 415)

    def test_oversized_request_returns_413(self):
        request=Request(self.base+'/api/analyze',data=b' '*200001,
                        headers={'Content-Type':'application/json'},method='POST')
        self.assert_http_error(request, 413)

    def test_unknown_api_returns_404(self):
        request=Request(self.base+'/api/unknown',data=b'{}',
                        headers={'Content-Type':'application/json'},method='POST')
        self.assert_http_error(request, 404)

    def test_web_only_serves_public_web_assets(self):
        # Source code and documents outside web/ must not be served.
        for url in ['/run.py','/engine/algorithms.py','/docs/TECHNICAL_REPORT.md']:
            with self.subTest(url=url):
                self.assert_http_error(self.base + url, 404)


if __name__ == '__main__':
    unittest.main()
