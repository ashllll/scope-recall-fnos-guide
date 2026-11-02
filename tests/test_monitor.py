"""Monitor contracts: stable incidents, persistent deduplication, safe recovery."""
import sys
import json
import threading
import tempfile
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy/monitor'))
from monitor import Alerts, entry_status, probe, server, collect


class AlertTests(unittest.TestCase):
    def test_unrelated_flapping_does_not_hide_a_persistent_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            sent = []
            alerts = Alerts(Path(directory) / 'state.json', {},
                            lambda title, body: sent.append(body) or {'ok': True})
            for offset in range(0, 601, 60):
                alerts.observe(['持续故障'] + (['短暂抖动'] if offset % 120 else []), 1000 + offset)
            self.assertEqual(len(sent), 1)
            self.assertIn('持续故障', sent[0])

    def test_transient_failure_is_silent_and_stable_incident_recovers_once(self):
        with tempfile.TemporaryDirectory() as directory:
            sent = []
            send = lambda title, body: sent.append((title, body)) or {"ok": True}
            path = Path(directory) / 'state.json'
            config = {"alert_after_seconds": 120, "recovery_after_seconds": 60}
            alerts = Alerts(path, config, send)
            alerts.observe(['Codex 入口不可达'], 1000)
            alerts.observe([], 1060)
            self.assertEqual(sent, [])
            alerts.observe(['Codex 入口不可达'], 1120)
            alerts.observe(['Codex 入口不可达'], 1240)
            self.assertEqual(len(sent), 1)
            restarted = Alerts(path, config, send)
            restarted.observe(['Codex 入口不可达'], 1400)
            self.assertEqual(len(sent), 1)
            restarted.observe([], 1460)
            restarted.observe([], 1520)
            restarted.observe([], 1600)
            self.assertEqual(len(sent), 2)
            self.assertIn('恢复', sent[-1][0])

    def test_delivery_failure_retries_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            delivered = []
            outcomes = iter([{'ok': False, 'code': 500}, {'ok': True}, {'ok': True}])
            def send(title, body):
                delivered.append(title)
                return next(outcomes)
            alerts = Alerts(Path(directory) / 'state.json', {'notify_retry_seconds': 900}, send)
            alerts.observe(['故障'], 1000)
            state = alerts.observe(['故障'], 1120)
            self.assertFalse(state['delivery']['ok'])
            self.assertNotIn('notified', state)
            alerts.observe(['故障'], 1180)
            self.assertEqual(len(delivered), 1)
            state = alerts.observe(['故障'], 2020)
            self.assertEqual(state['notified'], ['故障'])
            alerts.observe([], 2080)
            alerts.observe([], 2140)
            self.assertEqual(len(delivered), 3)

    def test_unsent_incident_does_not_send_false_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            sent = []
            def send(title, body):
                sent.append(title)
                return {'ok': False}
            alerts = Alerts(Path(directory) / 'state.json', {}, send)
            alerts.observe(['故障'], 1000)
            alerts.observe(['故障'], 1120)
            alerts.observe([], 1180)
            alerts.observe([], 2300)
            self.assertEqual(len(sent), 1)


class EndpointTests(unittest.TestCase):
    def test_fresh_degraded_worker_is_not_healthy_even_with_zero_exit(self):
        import datetime
        import sqlite3
        import time
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); now = time.time()
            worker = {'finished_at': datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat(),
                      'exit_code': 0, 'status': 'degraded', 'source_only': 1}
            (root/'runtime-worker-status.json').write_text(json.dumps(worker))
            with sqlite3.connect(root/'memory.sqlite3') as con:
                con.execute('CREATE TABLE source_events(persisted_at TEXT)')
            with sqlite3.connect(root/'auxiliary-budget.sqlite3') as con:
                con.execute('CREATE TABLE requests(started_ns INTEGER,batch TEXT,charge_micro_usd INTEGER)')
            runtime = {'auxiliary': {'budget': {'time_zone': 'Asia/Shanghai', 'batch':'scope-recall',
                                               'cap_micro_usd':5000000,'total_call_cap':10000}}}
            (root/'runtime.json').write_text(json.dumps(runtime)); (root/'backup.zip').touch()
            config = {'entries':[], 'store_root':str(root), 'runtime_file':str(root/'runtime.json'),
                      'backup_dir':str(root), 'storage_paths':{'test':str(root)}}
            value = collect(config, {'api':{'ok':True,'checked_at':now}}, now)
            self.assertFalse(value['worker']['ok'])
            self.assertIn('后台处理降级', value['issues'])

    def test_authenticated_status_over_http_and_sse(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200 if self.headers.get('Authorization') == 'Bearer test-token' else 401)
                self.end_headers()
                self.wfile.write(b'{"version":"3.17.0"}')
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert body['params']['name'] == 'status'
                queue = dict(sources=52, pending_work=0, failed_work=0, leased_work=0,
                             terminal_failed_work=0, oldest_pending_at=None)
                data = {'result': {'structuredContent': {'result': {'status': queue}}}}
                self.send_response(200); self.end_headers()
                self.wfile.write(('event: message\ndata: '+json.dumps(data)+'\n\n').encode())
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                token = Path(directory) / 'token'; token.write_text('test-token')
                value = entry_status({'name': 'Codex', 'url': f'http://127.0.0.1:{http.server_port}', 'token_file': str(token)})
                self.assertEqual(value['queue']['sources'], 52)
                self.assertTrue(value['ok'])
                self.assertNotIn('test-token', json.dumps(value))
        finally:
            http.shutdown(); http.server_close()

    def test_external_probe_rejects_stale_collector_and_web_is_read_only(self):
        import time
        import urllib.request
        from types import SimpleNamespace
        monitor = SimpleNamespace(config={'allowed_hosts': ['127.0.0.1'], 'stale_seconds': 240},
                                  snapshot={'checked_at': time.time() - 1000}, lock=threading.Lock())
        http = server(monitor, ('127.0.0.1', 0))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{http.server_port}'
        try:
            self.assertTrue(probe({'probe_url': base + '/healthz'}))
            monitor.snapshot['checked_at'] = time.time()
            self.assertEqual(probe({'probe_url': base + '/healthz'}), [])
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(base + '/api/status', data=b'{}'))
            self.assertEqual(error.exception.code, 501)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(base + '/api/status', headers={'Host':'attacker.example'}))
            self.assertEqual(error.exception.code, 421)
        finally:
            http.shutdown(); http.server_close()


if __name__ == '__main__':
    unittest.main()
