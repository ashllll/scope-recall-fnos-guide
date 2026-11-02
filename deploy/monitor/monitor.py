"""Read-only Scope Recall telemetry and persistent ServerChan incident notifications."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zoneinfo import ZoneInfo


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.chmod(0o600)
    os.replace(temporary, path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def request_json(url, body=None, headers=None, timeout=12):
    request = urllib.request.Request(url, data=body, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('response too large')
    text = raw.decode('utf-8')
    if text.startswith(('event:', 'data:')):
        messages = [json.loads(line[5:]) for line in text.splitlines() if line.startswith('data:')]
        return messages[-1]
    return json.loads(text)


def notify(config, title, body):
    """Never expose exception text: HTTP exceptions can contain the SendKey URL."""
    try:
        key = Path(config['sendkey_file']).read_text().strip()
        if not re.fullmatch(r'SCT[0-9A-Za-z-]+', key):
            return {'ok': False, 'error': 'invalid_sendkey_format'}
        data = urllib.parse.urlencode({'title': title[:32], 'desp': body, 'noip': '1'}).encode()
        result = request_json('https://sctapi.ftqq.com/' + key + '.send', data,
                              {'Content-Type': 'application/x-www-form-urlencoded'}, 15)
        code = result.get('code')
        return {'ok': type(code) is int and code == 0, 'code': code if type(code) is int else None}
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'error': 'http_error', 'code': exc.code}
    except Exception as exc:
        return {'ok': False, 'error': type(exc).__name__}


class Alerts:
    def __init__(self, path, config, sender):
        self.path, self.config, self.sender = Path(path), config, sender
        self.state = read_json(path) if self.path.exists() else {}

    def observe(self, issues, now):
        issues = sorted(set(issues))
        state = self.state
        observed = state.get('observed', {})
        clearing = state.get('clearing', {})
        notified = set(state.get('notified', []))
        state['observed'] = {issue: observed.get(issue, now) for issue in issues}
        state['clearing'] = {issue: clearing.get(issue, now) for issue in notified - set(issues)}
        stable = notified.copy()
        stable.update(issue for issue, since in state['observed'].items()
                      if now - since >= self.config.get('alert_after_seconds', 120))
        stable.difference_update(issue for issue, since in state['clearing'].items()
                                 if now - since >= self.config.get('recovery_after_seconds', 60))
        issues_to_send = sorted(stable)
        state['candidate'] = issues
        changed = stable != notified
        retry = now - state.get('attempt_at', 0) >= self.config.get('notify_retry_seconds', 900)
        # A successful delivery must not delay a different incident or recovery.
        if changed and (state.get('delivery', {}).get('ok', True) or retry):
            title = 'Scope Recall 异常告警' if stable else 'Scope Recall 已恢复'
            label = self.config.get('label', 'NAS 内部监控')
            when = dt.datetime.fromtimestamp(now, ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
            body = f'{label} · {when}\n\n' + '\n'.join('- ' + item for item in (issues_to_send or ['已通知的异常均已恢复']))
            state['delivery'] = self.sender(title, body)
            state['attempt_at'] = now
            if state['delivery'].get('ok'):
                state['notified'] = issues_to_send
                state['delivered_at'] = now
                state['events'] = (state.get('events', []) + [{'at': now, 'title': title, 'issues': issues_to_send}])[-30:]
        atomic_json(self.path, state)
        return state


def entry_status(entry):
    token = Path(entry['token_file']).read_text().strip()
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
               'Accept': 'application/json, text/event-stream'}
    base = entry['url'].rstrip('/')
    health = request_json(base + '/health', headers=headers)
    body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'status', 'arguments': {'protocol_version': '1.1'}}}
    reply = request_json(base + '/mcp', json.dumps(body).encode(), headers)
    result = reply['result']
    if result.get('isError'):
        raise ValueError('MCP status refused')
    structured = result.get('structuredContent')
    if structured is None:
        structured = json.loads(result['content'][0]['text'])
    status = structured['result']['status']
    fields = ('sources', 'pending_work', 'failed_work', 'leased_work', 'terminal_failed_work', 'oldest_pending_at')
    return {'name': entry['name'], 'ok': True, 'version': health['version'],
            'queue': {key: status[key] for key in fields}}


def local_metrics(config, now):
    root = Path(config['store_root'])
    result = {}
    # These aggregate-only queries follow the documented deployment baseline (3.17).
    # Schema drift is reported as unavailable; no migration or repair runs here.
    con = sqlite3.connect(f'file:{root / "memory.sqlite3"}?mode=ro', uri=True, timeout=3)
    try:
        row = con.execute('SELECT persisted_at FROM source_events ORDER BY rowid DESC LIMIT 1').fetchone()
        result['last_capture_at'] = timestamp(row[0]) if row else None
    finally:
        con.close()
    runtime = read_json(config['runtime_file'])
    budget = runtime['auxiliary']['budget']
    current = dt.datetime.fromtimestamp(now, ZoneInfo(budget['time_zone']))
    start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    con = sqlite3.connect(f'file:{root / "auxiliary-budget.sqlite3"}?mode=ro', uri=True, timeout=3)
    try:
        calls, cost = con.execute('SELECT count(*), coalesce(sum(charge_micro_usd),0) FROM requests WHERE started_ns >= ? AND batch = ?',
                                 (int(start * 1e9), budget['batch'])).fetchone()
    finally:
        con.close()
    result['budget'] = {'calls': calls, 'call_cap': budget['total_call_cap'], 'usd': cost / 1e6,
                        'usd_cap': budget['cap_micro_usd'] / 1e6, 'period': current.strftime('%Y-%m')}
    return result


def api_check(config, now):
    try:
        values = {}
        for line in Path(config['model_env_file']).read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                name, value = line.split('=', 1)
                parsed = shlex.split(value)
                values[name.strip()] = parsed[0] if parsed else ''
        request_json('https://api.openai.com/v1/models', headers={'Authorization': 'Bearer ' + values['OPENAI_API_KEY']})
        return {'ok': True, 'checked_at': now, 'http_status': 200}
    except urllib.error.HTTPError as exc:
        return {'ok': False, 'checked_at': now, 'http_status': exc.code}
    except Exception as exc:
        return {'ok': False, 'checked_at': now, 'error': type(exc).__name__}


def collect(config, previous=None, now=None):
    now = time.time() if now is None else now
    previous = previous or {}
    issues, entries = [], []
    for entry in config['entries']:
        try:
            value = entry_status(entry)
            queue = value['queue']
            if queue['failed_work'] or queue['terminal_failed_work']:
                issues.append(entry['name'] + ' 有失败任务')
            if queue['pending_work'] and queue['oldest_pending_at'] and now - timestamp(queue['oldest_pending_at']) > config.get('queue_age_seconds', 900):
                issues.append(entry['name'] + ' 任务积压超过阈值')
        except Exception as exc:
            value = {'name': entry['name'], 'ok': False, 'error': type(exc).__name__}
            issues.append(entry['name'] + ' 入口或状态查询异常')
        entries.append(value)
    try:
        raw = read_json(Path(config['store_root']) / 'runtime-worker-status.json')
        age = now - timestamp(raw['finished_at'])
        degraded = raw['status'] == 'degraded'
        worker = {'ok': age < config.get('worker_stale_seconds', 600) and raw['exit_code'] == 0 and not degraded,
                  'finished_at': timestamp(raw['finished_at']), 'status': raw['status'], 'exit_code': raw['exit_code']}
        if degraded:
            issues.append('后台处理降级')
        elif not worker['ok']:
            issues.append('后台处理失败或心跳过期')
    except Exception as exc:
        worker = {'ok': False, 'error': type(exc).__name__}
        issues.append('后台处理心跳不可读')
    try:
        metrics = local_metrics(config, now)
        budget = metrics['budget']
        if budget['usd'] >= budget['usd_cap'] * .9 or budget['calls'] >= budget['call_cap'] * .9:
            issues.append('应用模型预算已用到 90%')
    except Exception as exc:
        metrics = {'error': type(exc).__name__}
        issues.append('记忆写入时间或用量账本不可读')
    storage = []
    for name, path in config['storage_paths'].items():
        try:
            total, used, free = shutil.disk_usage(path)
            storage.append({'name': name, 'total': total, 'used': used, 'free': free})
            if free / total < config.get('disk_free_ratio', .1):
                issues.append(name + ' 剩余容量不足 10%')
        except OSError:
            issues.append(name + ' 存储不可读')
    try:
        backups = list(Path(config['backup_dir']).glob('*.zip'))
        latest = max((p.stat().st_mtime for p in backups), default=None)
        backup = {'latest_file_at': latest, 'count': len(backups), 'scheduled': False}
        if latest is None or now - latest > config.get('backup_age_seconds', 7 * 86400):
            issues.append('备份文件缺失或超过 7 天')
    except OSError:
        backup = {'error': 'unreadable'}
        issues.append('备份目录不可读')
    api = previous.get('api', {})
    if now - api.get('checked_at', 0) >= config.get('api_interval_seconds', 900):
        api = api_check(config, now)
    if not api.get('ok'):
        issues.append('OpenAI 鉴权或连通性检查失败')
    queue = next((e['queue'] for e in entries if e['ok']), None)
    return {'checked_at': now, 'issues': sorted(set(issues)), 'entries': entries, 'queue': queue,
            'worker': worker, 'metrics': metrics, 'storage': storage, 'backup': backup, 'api': api}


def probe(config, now=None):
    now = time.time() if now is None else now
    try:
        result = request_json(config['probe_url'])
        ok = result['ok'] is True and now - result['checked_at'] < config.get('stale_seconds', 240)
    except Exception:
        ok = False
    return [] if ok else ['NAS 状态面板不可达或采集已停滞']


class Monitor:
    def __init__(self, config):
        self.config = config
        self.state_dir = Path(config['state_dir'])
        self.alerts = Alerts(self.state_dir / 'alerts.json', config, lambda title, body: notify(config, title, body))
        self.snapshot = {}
        self.lock = threading.Lock()

    def tick(self):
        now = time.time()
        if self.config.get('mode') == 'probe':
            self.alerts.observe(probe(self.config, now), now)
            return
        try:
            data = collect(self.config, self.snapshot, now)
        except Exception as exc:
            data = {'checked_at': now, 'issues': ['采集器内部异常'], 'error': type(exc).__name__}
        state = self.alerts.observe(data['issues'], now)
        data['notifications'] = {k: state.get(k) for k in ('delivered_at', 'attempt_at', 'delivery', 'events')}
        history = self.snapshot.get('history', [])
        q = data.get('queue') or {}
        data['history'] = (history + [{'at': now, 'pending': q.get('pending_work'), 'failed': q.get('failed_work')}])[-120:]
        data['poll_seconds'] = self.config.get('poll_seconds', 60)
        atomic_json(self.state_dir / 'status.json', data)
        with self.lock:
            self.snapshot = data

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as exc:
                # Leave the previous timestamp stale so the external probe notices.
                print(json.dumps({'monitor_error': type(exc).__name__}), flush=True)
            time.sleep(self.config.get('poll_seconds', 60))


def server(monitor, address):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            host = urllib.parse.urlsplit('//' + self.headers.get('Host', '')).hostname
            if host not in monitor.config['allowed_hosts']:
                self.send_error(421)
                return
            path = urllib.parse.urlsplit(self.path).path
            with monitor.lock:
                data = dict(monitor.snapshot)
            fresh = bool(data) and time.time() - data.get('checked_at', 0) < monitor.config.get('stale_seconds', 240)
            status = 200
            if path == '/healthz':
                body = json.dumps({'ok': fresh, 'checked_at': data.get('checked_at')}).encode()
                status = 200 if fresh else 503
                mime = 'application/json'
            elif path == '/api/status':
                data['fresh'] = fresh
                body, mime = json.dumps(data, ensure_ascii=False).encode(), 'application/json'
            elif path == '/':
                body, mime = Path(__file__).with_name('index.html').read_bytes(), 'text/html'
            else:
                self.send_error(404)
                return
            self.send_response(status)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--test-notification', action='store_true')
    args = parser.parse_args()
    config = read_json(args.config)
    if args.test_notification:
        result = notify(config, 'Scope Recall 通知测试', '状态面板通知链路测试；这不是故障。收到后表示 Server酱 → Bark 已送达。')
        print(json.dumps(result))
        raise SystemExit(0 if result['ok'] else 1)
    monitor = Monitor(config)
    if args.once:
        monitor.tick()
        return
    if config.get('mode') == 'probe':
        monitor.run()
    else:
        threading.Thread(target=monitor.run, daemon=True).start()
        server(monitor, (config.get('listen', '0.0.0.0'), config.get('port', 8080))).serve_forever()


if __name__ == '__main__':
    main()
