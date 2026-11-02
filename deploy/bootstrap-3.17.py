"""Initialize an empty shared store using upstream commands; run once before Compose."""
import json
import os
import shutil
from pathlib import Path
from scope_recall.maintenance.shared import init_shared, attach
from scope_recall.adapters.clients.remote_server import write_server_config
from scope_recall.runtime.instance_config import RuntimeInstanceConfig
from scope_recall.runtime.model_budget import initialize_auxiliary_budget_ledger

os.umask(0o077)
root = Path('/data/shared')
config = Path('/config')
if (root / 'installation.json').exists():
    raise SystemExit('Existing store: bootstrap refuses to overwrite it')
threshold = json.loads((config / 'embedding-check.json').read_text())['vector_threshold']
raw = {
    'binding': {'agent_id':'default', 'installation_id':'bootstrap', 'data_directory':str(root),
                'scope_ids':['bootstrap'], 'test_mode':False, 'installation_kind':'shared'},
    'session_id':'bootstrap', 'allowed_scope_ids':['bootstrap'], 'supervisor_enabled':False,
    'vector_threshold':threshold, 'auto_vector_threshold':max(0.55, threshold),
    'max_items':32, 'model_request_seconds':90, 'lease_seconds':120,
    'auxiliary': {
        'external_embedding':True, 'external_consolidation':True,
        'budget': {
            'batch':'scope-recall', 'period':'monthly', 'time_zone':'Asia/Shanghai',
            'cap_micro_usd':5000000, 'total_input_cap':None, 'total_output_cap':None,
            'total_call_cap':10000, 'max_request_bytes':128000,
            'default_reserve_input':32768, 'default_reserve_output':4096,
            'model_reserve_output':{'gpt-6-luna':4096, 'text-embedding-3-small':1},
            'approved_models':['gpt-6-luna','text-embedding-3-small'],
            'pricing':{
                'gpt-6-luna':{'input_usd_per_million':'0.10','output_usd_per_million':'0.50'},
                'text-embedding-3-small':{'input_usd_per_million':'0.02','output_usd_per_million':'0'}
            }
        },
        'embedding':{'credential_env':'OPENAI_API_KEY', 'model':'text-embedding-3-small',
                     'endpoint':'https://api.openai.com/v1/embeddings', 'dimensions':1536, 'dialect':'openai'},
        'consolidation':{'kind':'openai', 'credential_env':'OPENAI_API_KEY', 'model':'gpt-6-luna',
                         'endpoint':'https://api.openai.com/v1/chat/completions',
                         'output_limit_field':'max_completion_tokens', 'max_output_tokens':4096,
                         'reasoning_effort':'low', 'response_format':{'type':'json_object'}}
    }
}
space = RuntimeInstanceConfig.from_mapping(raw).embedding_space_id()
raw['vector'] = {'backend':'lancedb','storage_dir':str(root/'vectors'/space),
                 'table_name':'scope_recall', 'dimensions':1536}
RuntimeInstanceConfig.from_mapping(raw)
routes = config / 'routes.json'
routes.write_text(json.dumps(raw, indent=2)+'\n')
init_shared(root=root)
entries = json.loads((config / 'entries-public.json').read_text())
for entry in entries:
    host = entry['host']
    home = config / 'entries' / ('mac-'+host)
    options = {} if host == 'codex' else {'grants_like':('all',), 'capture_like':'mac-codex'}
    attach(host=host, instance_root=home, root=root, entry_id='mac-'+host,
           display_name='Mac '+host.capitalize(), runtime_config_from=routes,
           python_executable=Path('/usr/local/bin/python'), **options)
    write_server_config(home, host, listen=entry['listen'], port=entry['port'], token_sha256=entry['token_sha256'])
paths = [root/'runtime-config.json', *config.glob('entries/*/scope-recall/runtime-config.json')]
assert len(paths) == 3, paths
for path in paths:
    data = json.loads(path.read_text())
    data['auxiliary']['ledger_path'] = str(root/'auxiliary-budget.sqlite3')
    cfg = RuntimeInstanceConfig.from_mapping(data)
    path.write_text(json.dumps(data, indent=2)+'\n')
initialize_auxiliary_budget_ledger(cfg.auxiliary.ledger_path, cfg.auxiliary.budget)
shutil.move(root/'runtime-config.json', config/'shared-runtime.json')
print(json.dumps({'initialized':True, 'entries':len(entries), 'threshold':threshold, 'embedding_space':space}))
