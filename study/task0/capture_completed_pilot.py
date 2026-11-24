#!/usr/bin/env python3
"""Copy a root-confirmed completed pilot's existing evidence; never call a model.

The native JSONL export must already exist. Original evidence is never overwritten
with changed bytes. Synced sessions are selected by chat.json.session, not title.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
SYNC = Path('/Users/wangyifei/rushlab/a-little-hoof/comp-480-580/plugins')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def rel(path):
    return str(path.relative_to(ROOT))


def capture(plugin, session, export):
    manifest = read(ROOT / 'study/task0/manifest.json')
    pilot = next(p for p in manifest['pilots'] if p['plugin_id'] == plugin)
    exported = [json.loads(line) for line in export.read_text(encoding='utf-8').splitlines() if line.strip()]
    rows = [r for r in exported if r.get('session_id') == session]
    if len(rows) != 1:
        raise ValueError('Expected exactly one matching exported session')
    row = rows[0]
    if row.get('type') != 'chat' or row.get('kind') != 'nanoagent' or row['plugin']['id'] != plugin:
        raise ValueError('Wrong export type/plugin')
    if len(row['turns']) != 1:
        raise ValueError('Pilot expected one turn; review multi-turn evidence separately')
    turn = row['turns'][0]
    if turn['prompt'] != pilot['planned_prompt']:
        raise ValueError('Actual prompt differs; record discrepancy before capture')
    matches = [(p, read(p)) for p in (SYNC / plugin / 'chats').glob('*/chat.json')]
    matches = [(p, c) for p, c in matches if c.get('session') == session]
    if len(matches) != 1:
        raise ValueError('Expected one synced own-session chat.json')
    chat_path, chat = matches[0]
    if chat['turns'] != [{k: v for k, v in t.items() if k != 'messages'} for t in row['turns']]:
        raise ValueError('Synced chat does not match exported turns')
    destination = ROOT / 'study/task0/evidence' / session
    destination.mkdir(parents=True, exist_ok=True)
    files = []
    for source in [chat_path, *sorted(chat_path.parent.glob('turns/*/graph.json')),
                   *sorted(chat_path.parent.glob('turns/*/messages.json'))]:
        relative = source.relative_to(chat_path.parent)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        if target.exists() and target.read_bytes() != raw:
            raise ValueError(f'Refusing changed evidence overwrite: {target}')
        if not target.exists():
            shutil.copyfile(source, target)
        files.append({'source': str(source), 'copy': rel(target), 'sha256': sha(raw), 'bytes': len(raw)})
    for index, exported_turn in enumerate(row['turns'], 1):
        folder = destination / f'turns/{index:03}'
        if read(folder / 'messages.json') != exported_turn['messages']:
            raise ValueError('Synced messages differ from export')
        graph = read(folder / 'graph.json')
        nodes = graph['nodes']
        if len({n['id'] for n in nodes}) != len(nodes):
            raise ValueError('Duplicate graph node IDs')
    ui = {}
    for name in ('screenshot.png', 'accessibility.txt', 'result.png', 'result-accessibility.txt',
                 'graph.png', 'graph-accessibility.txt', 'ui_observation.json'):
        path = destination / name
        if path.exists():
            ui[name] = {'path': rel(path), 'sha256': sha(path.read_bytes())}
    ui_complete = all(name in ui for name in ('screenshot.png', 'accessibility.txt', 'ui_observation.json'))
    provenance_path = destination / 'provenance.json'
    write(provenance_path, {'session_id': session, 'plugin': plugin,
                           'captured_at_utc': datetime.now(timezone.utc).isoformat(),
                           'export': {'path': rel(export), 'sha256': sha(export.read_bytes()),
                                      'method': 'installed_supported_rushlab_nanoagent_export_CLI',
                                      'filters': {'plugin': plugin, 'since': '2026-11-23'}},
                           'synced_files': files, 'ui_evidence': ui,
                           'chat_turns_equal_export_without_messages': True,
                           'researcher_evidence_only': 'Graphs can contain hidden reference answers; do not expose to benchmark agents.'})
    results = []
    for tool in turn.get('tools', []):
        raw = tool.get('output')
        value = json.loads(raw) if isinstance(raw, str) else raw
        results.append({'tool_name': tool.get('name'), 'arguments': tool.get('arguments'),
                        'is_error': tool.get('isError'), 'output': value.get('output') if isinstance(value, dict) else None,
                        'verdict': value.get('verdict') if isinstance(value, dict) else None,
                        'wrapper_output_sha256': sha(raw.encode('utf-8')) if isinstance(raw, str) else None})
    valid = [r['verdict'].get('valid') for r in results if isinstance(r.get('verdict'), dict)]
    success = (all(v is True for v in valid) if valid and len(valid) == len(results) else None)
    expected_invocation = len(results) == 1 and results[0]['tool_name'] == pilot['task_id'] and results[0]['arguments'] == pilot['case_input']
    if not expected_invocation:
        success = False if results else None
    status = 'completed_verified' if success is True and not turn.get('error') else 'completed_with_failure_or_unknown'
    prior = next((a for a in pilot['actual_attempts'] if a['session_id'] == session), None)
    ordinal = pilot['actual_attempts'].index(prior) + 1 if prior else len(pilot['actual_attempts']) + 1
    attempt = {'attempt_label': f"{pilot['pilot_id']}-attempt-{ordinal:02}", 'session_id': session,
               'interaction': 'native_computer_use_plugin_nanoagent_session', 'status': status,
               'actual_dispatched_prompt': turn['prompt'], 'actual_prompt_sha256': sha(turn['prompt'].encode('utf-8')),
               'prompt_capture_status': 'confirmed_exact_native_export_prompt', 'task_invoked': bool(results),
               'requested_task_and_case_match': expected_invocation,
               'actual_system_prompts': [{'text': step['message'], 'sha256': sha(step['message'].encode('utf-8'))}
                                        for step in (turn.get('messages') or {}).get('steps', [])
                                        if step.get('source') == 'system' and isinstance(step.get('message'), str)],
               'effective_sampling_settings': None, 'effective_run_limits': None,
               'settings_missing_reason': 'Sampling settings and effective task call/output/time/cost limits were not captured by this export.',
               'model_response_received': bool(turn.get('answer') or turn.get('tools')), 'task_success': success,
               'task_results': results, 'final_answer': turn.get('answer'), 'error': turn.get('error'),
               'metrics': turn.get('metrics'),
               'metric_scope': 'Native exported turn metrics retained verbatim; separate graph analysis pending independent analyzer.',
               'plugin_version': turn.get('version'), 'model': (turn.get('metrics') or {}).get('model'),
               'agent': (turn.get('messages') or {}).get('agent'),
               'run_timestamps': {'session_created_at': row.get('created_at'), 'session_updated_at': row.get('updated_at'),
                                  'source': 'native_export', 'timing_caution': 'Use metrics.duration_s for reported run latency, not session timestamp subtraction.'},
               'evidence': {'trace_export': rel(export), 'trace_sha256': sha(export.read_bytes()),
                            'synced_directory': rel(destination), 'provenance': rel(provenance_path),
                            'provenance_sha256': sha(provenance_path.read_bytes()),
                            'ui': ui},
               'evidence_status': 'native_export_synced_graph_messages_and_UI_saved' if ui_complete else 'native_export_synced_graph_messages_saved_UI_incomplete'}
    if ordinal > 1:
        attempt['retry_reason'] = 'Fresh session after user reported saving a fresh key; prior authentication failures remain separate attempts.'
    if prior:
        pilot['actual_attempts'][ordinal - 1] = attempt
    else:
        pilot['actual_attempts'].append(attempt)
    pilot['status'] = status
    manifest['status'] = ('initial_pilots_captured_pending_review' if all(p['status'] == 'completed_verified' for p in manifest['pilots'])
                          else 'initial_app_pilots_in_progress')
    auth = manifest['authentication_observation']
    auth.setdefault('earlier_failures', {'http_status': 401, 'reported_error': 'API key expired', 'attempts': 2})
    auth.pop('error_code', None)
    auth.pop('reported_error', None)
    manifest['authentication_observation']['status'] = 'model_response_observed_after_fresh_key_save'
    manifest['authentication_observation']['latest_successful_response_session_id'] = session
    manifest['authentication_observation']['action'] = 'Authentication now permits model responses; preserve both earlier 401 failures as separate attempts.'
    manifest['authentication_observation']['replacement_validity_verified'] = True
    manifest['authentication_observation']['validity_verification_scope'] = 'Successful live model response after user-reported fresh key Save, not an inspection of the credential.'
    manifest['authentication_observation']['source_diagnosis']['provider_validity_verified'] = True
    source_files = []
    source_ids = []
    for p in manifest['pilots']:
        for a in p['actual_attempts']:
            path = a['evidence']['trace_export']
            if a is p['actual_attempts'][-1] and path not in source_files:
                source_files.append(path)
            source_ids.append(a['session_id'])
    manifest['current_summary_sources'] = {'files': source_files,
        'selection_reason': 'Latest export per plugin contains its current attempts. Earlier overlapping exports are preserved but must not be passed again.',
        'session_ids': source_ids}
    write(ROOT / 'study/task0/manifest.json', manifest)
    preflight_path = ROOT / 'checks/local_preflight.json'
    preflight = read(preflight_path)
    all_attempts = [a for p in manifest['pilots'] for a in p['actual_attempts']]
    preflight['experiment_status'].update({'initial_exploration_attempts': len(all_attempts),
        'completed_task_runs': sum(a.get('task_success') is True for a in all_attempts),
        'authentication_status': 'successful_live_model_response_observed',
        'failure': 'Two earlier 401 preflight failures preserved; authentication now permits model responses.',
        'latest_session_id': session,
        'authentication_diagnosis': 'Fresh key Save followed by successful live model response. No credential content was inspected.',
        'measured_results_available': True,
        'measurement_scope': 'Initial descriptive Session pilots; exported outer usage kept distinct from nested graph call accounting.'})
    write(preflight_path, preflight)
    print(json.dumps({'plugin': plugin, 'session_id': session, 'status': status,
                      'evidence': rel(destination)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--export', required=True, type=Path)
    args = parser.parse_args()
    capture(args.plugin, args.session, args.export.resolve())
