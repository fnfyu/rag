"""One offline V3 contract integration: real captures, in-memory repository/index.

No PostgreSQL/model quality claim, no live crawling, no user data mutation.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from langchain_core.documents import Document
from starter import app
from backend import get_rag_service
from evidence import build_sources, format_sources
from reporting import ScopedEvidence, merge_sources, outline_signature, report_markdown, report_html
from souls_domain import catalog, templates_for, normalize_metadata
from souls_impact import extract_changes, _task_rows
import souls_api as api
import workspace_store as store


class Memory:
    def __init__(self):
        self.kbs, self.versions, self.private, self.tasks = {}, {}, {}, {}

    def create_kb(self, title, description='', game_profile=None):
        identifier = f'kb_{len(self.kbs) + 1}'
        row = {'id': identifier, 'title': title, 'description': description,
               'collection_name': 'collection_' + identifier, 'game_profile': deepcopy(game_profile or {})}
        self.kbs[identifier] = row
        return deepcopy(row)

    def create_version(self, kb, filename, path, digest, label=None, release_date=None, applicability=None, *, domain_metadata=None):
        identifier = f'version_{len(self.versions) + 1}'
        row = {'id': identifier, 'source_id': identifier, 'knowledge_base_id': kb, 'filename': filename,
               'document_series_id': 'series_' + filename, 'sha256': digest, 'version_label': label,
               'release_date': release_date, 'applicability': applicability, 'domain_metadata': deepcopy(domain_metadata or {}), 'status': 'queued'}
        self.versions[identifier] = row; self.private[identifier] = {**row, 'file_path': path}
        return deepcopy(row)

    def update_version(self, identifier, status, chunk_count=0, error=None):
        self.versions[identifier].update(status=status, chunk_count=chunk_count, error=error)
        return deepcopy(self.versions[identifier])

    def create_task(self, kb, title, question='', outline=None, context=None):
        identifier = f'task_{len(self.tasks) + 1}'
        row = {'id': identifier, 'knowledge_base_id': kb, 'title': title, 'question': question, 'outline': outline or [],
               'context': deepcopy(context or {}), 'status': 'draft', 'report': None, 'revision': 0}
        self.tasks[identifier] = row
        return deepcopy(row)


class FakeClient:
    def __init__(self, service):
        self.service = service

    def get_or_create_collection(self, name):
        service = self.service
        class RawCollection:
            def get(self, **kwargs):
                documents = service.retrieve_trace('snapshot', name, where=kwargs.get('where')).documents
                return {'ids': [document.metadata['source'] for document in documents],
                        'documents': [document.page_content for document in documents],
                        'metadatas': [document.metadata for document in documents]}
        return RawCollection()


class FakeIndex:
    text_extensions = {'.txt', '.md', '.csv'}

    def __init__(self):
        self.settings = SimpleNamespace(ollama_model=None, research_model_timeout_seconds=1)
        self.llm, self.documents = object(), []
        self.client = FakeClient(self)
        self.filters = []

    def index_document(self, path, collection, source_id, filename, *, source_metadata=None):
        self.documents.append(Document(page_content=Path(path).read_text(encoding='utf-8'), metadata={'source': source_id, 'filename': filename, **(source_metadata or {})}))
        return 1

    def retrieve_trace(self, query, collection, *, where=None, **kwargs):
        self.filters.append(where)
        source_filter = (where or {}).get('source')
        values = set(source_filter.get('$in', [])) if isinstance(source_filter, dict) else {source_filter} if source_filter else None
        return SimpleNamespace(documents=[document for document in self.documents if values is None or document.metadata['source'] in values])

    def compose_context(self, documents):
        return SimpleNamespace(documents=documents)

    def _read_text(self, path):
        return path.read_text(encoding='utf-8')


def run():
    game_ids = [game['id'] for game in catalog()]
    assert len(game_ids) == 5 and len(set(game_ids)) == 5
    assert all(len(template['outline']) == 5 for game in game_ids for template in templates_for(game))
    corpus = []
    for game in game_ids:
        manifest = json.loads((ROOT / 'knowledge' / 'souls' / game / 'manifest.json').read_text(encoding='utf-8'))
        for article in manifest['articles']:
            assert article['game_id'] == game and sha256(article['content'].encode()).hexdigest() == article['content_sha256']
            corpus.append(article)
    assert len(corpus) == 6
    nr_patch = next(article for article in corpus if article['source_kind'] == 'patch_notes')
    assert nr_patch['patch'] == '1.03.1' and nr_patch['published_at'].startswith('2025-12-17')
    repository, service = Memory(), FakeIndex()
    data_root = ROOT / 'data'; data_root.mkdir(exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='souls-check-', dir=data_root)
    directory = Path(temporary.name).resolve()
    assert directory.parent == data_root.resolve() and directory.name.startswith('souls-check-')
    fake_settings = SimpleNamespace(upload_dir=directory, ensure_storage_directories=lambda: None)
    functions = {
        'create_knowledge_base': repository.create_kb,
        'get_knowledge_base': lambda identifier: deepcopy(repository.kbs.get(identifier)),
        'list_knowledge_bases': lambda: deepcopy(list(repository.kbs.values())),
        'create_document_version': repository.create_version,
        'get_document_version': lambda identifier: deepcopy(repository.versions.get(identifier)),
        'resolve_document_version': lambda identifier: deepcopy(repository.private[identifier]),
        'list_document_versions': lambda kb, *args: deepcopy([version for version in repository.versions.values() if version['knowledge_base_id'] == kb]),
        'update_document_version': repository.update_version,
        'create_research_task': repository.create_task,
        'list_research_tasks': lambda kb=None: deepcopy([task for task in repository.tasks.values() if kb is None or task['knowledge_base_id'] == kb]),
    }
    try:
        with patch.multiple(store, **functions), patch.object(api, 'settings', fake_settings), patch.object(api, 'get_rag_service', lambda: service), patch.object(api, 'fetch_article', lambda game, url, **kwargs: deepcopy(next(article for article in corpus if article['game_id'] == game and article['url'] == url))):
            with TestClient(app) as client:
                assert client.get('/health').status_code == 200
                assert not any(get_rag_service().health_report()['resources_loaded'].values())
                assert client.get('/games').status_code == 200
                assert app.openapi()['info']['version'] == '3.0.0'
                kb_by_game = {}
                for game in game_ids:
                    article = next(article for article in corpus if article['game_id'] == game)
                    response = client.post(f'/games/{game}/knowledge-bases', json={'title': game, 'profile': {'edition': article['edition']}})
                    assert response.status_code == 201, response.text
                    kb_by_game[game] = response.json()
                for article in corpus:
                    kb = kb_by_game[article['game_id']]
                    body = {'knowledge_base_id': kb['id'], 'source_id': article['source_id'], 'url': article['url'], 'edition': article['edition']}
                    response = client.post(f"/games/{article['game_id']}/import", json=body)
                    assert response.status_code == 202, response.text
                    imported = response.json()
                    assert 'file_path' not in imported['version']
                    assert client.get('/games/imports/' + imported['import_id']).json()['status'] == 'completed'
                    duplicate = client.post(f"/games/{article['game_id']}/import", json=body).json()
                    assert duplicate['version_id'] == imported['version_id'] and duplicate['reused']
                assert len(repository.versions) == 6 and len(service.documents) == 6
                nr_kb = kb_by_game['nightreign']
                wrong = client.post('/games/elden-ring/tasks', json={'knowledge_base_id': nr_kb['id'], 'conditions_confirmed': True, 'template_id': 'boss', 'goal': 'do not mix games'})
                assert wrong.status_code == 422
                task = client.post('/games/nightreign/tasks', json={'knowledge_base_id': nr_kb['id'], 'conditions_confirmed': True, 'template_id': 'patch-impact', 'goal': '核对历史补丁调整，不宣称当前最新', 'profile': {'spoiler_policy': 'full'}}).json()
                assert task['status'] == 'draft' and task['context']['game']['game_id'] == 'nightreign'
                impact = client.post('/games/nightreign/impact', json={'knowledge_base_id': nr_kb['id']})
                assert impact.status_code == 200 and impact.json()['changes'] and impact.json()['coverage']['latest_version_confirmed'] is False
                weight = client.post('/games/elden-ring/calculate', json={'operation': 'loadout_weight', 'data': {'items': [{'weight': 0.1}, {'weight': 0.2}], 'max_load': 1}}).json()
                assert weight['result']['total_weight'] == '0.3' and weight['result']['classification'] is None
                assert client.post('/games/nightreign/calculate', json={'operation': 'stat_budget', 'data': {}}).json()['status'] == 'not_applicable'
                assert client.post('/games/nightreign/calculate', json={'operation': 'loadout_weight', 'data': {}}).json()['status'] == 'not_applicable'
                comparison = client.post('/games/nightreign/calculate', json={'operation': 'table_comparison', 'data': {'left': 12, 'right': 10}}).json()
                assert comparison['result']['percent_change'] == '20.0'
                imports = client.get('/games/imports', params={'knowledge_base_id': nr_kb['id']}).json()
                assert len(imports) == 2 and all(not item['active'] for item in imports)
            all_versions = list(repository.versions.values())
            scoped = ScopedEvidence(service, all_versions, [], profile={'game_id': 'nightreign', 'edition': 'standard'})
            enriched = scoped.retrieve_trace('角色调整', 'fixture').documents
            assert len(enriched) == 2 and all(document.metadata['game_id'] == 'nightreign' for document in enriched)
            graph_snapshot = scoped.client.get_or_create_collection('fixture').get(where={'source': 'unrelated'})
            assert len(graph_snapshot['ids']) == 2 and set(graph_snapshot['ids']) == set(scoped.where['source']['$in'])
            empty = ScopedEvidence(service, [], [], profile={'game_id': 'elden-ring'})
            assert empty.where is not None and not empty.retrieve_trace('nothing', 'fixture').documents
            source = build_sources(enriched)[0]
            assert source['source_url'].startswith('https://') and '游戏 nightreign' in format_sources([source])
            report = {'title': '引用条件', 'question': '实际资料', 'game': {'game_id': 'nightreign'}, 'sources': [], 'sections': []}
            first = merge_sources(report, [source])[0]
            assert merge_sources(report, [source])[0]['id'] == first['id']
            changed = deepcopy(source); changed['domain_metadata']['patch'] = 'explicit-condition-change'
            assert merge_sources(report, [changed])[0]['id'] != first['id']
            report['sections'] = [{'id': 'chapter', 'title': '引用', 'content': f"原文依据 [{first['id']}]"}]
            assert '游戏与攻略条件' in report_markdown(report) and '原始来源' in report_html(report)
            outline = {'id': 'chapter', 'title': '同一章', 'question': 'same'}
            assert outline_signature(outline, {'game': {'game_id': 'nightreign'}}) != outline_signature(outline, {'game': {'game_id': 'elden-ring'}})
            manual = normalize_metadata({'game_id': 'elden-ring', 'source_tier': 'official', 'provenance': 'verified_capture', 'capture_sha256': 'made-up'})
            assert manual['provenance'] == 'user_declared' and 'capture_sha256' not in manual
            version = next(version for version in all_versions if version['domain_metadata']['source_kind'] == 'patch_notes')
            literal = extract_changes(version, 'Wylder\n- Increased damage.\n')
            assert literal[0]['quote'] == '- Increased damage.' and literal[0]['start_line'] == 2
            old = {'id': 'old', 'title': '旧攻略', 'revision': 1, 'context': {'game': {'game_id': 'nightreign'}}, 'report': {'sources': [], 'sections': [{'id': 's', 'title': '角色', 'content': 'Wylder strategy', 'audit': {'claims': [{'id': 'c', 'text': 'Wylder strategy'}]}}]}}
            affected, _ = _task_rows('nightreign', [old], literal)
            assert affected[0]['sections'][0]['claims'][0]['status'] == 'needs_confirmation'
        print('PASS V3: five game KBs, six real captures, draft guides, import reuse/status, scope isolation, provenance, Decimal tools, patch candidates, condition-aware citations/exports. No model/DB benchmark claim.')
    finally:
        api._IMPORTS.clear()
        # Verified fixed workspace child above; no real uploads/indexes are touched.
        temporary.cleanup()


if __name__ == '__main__':
    run()
