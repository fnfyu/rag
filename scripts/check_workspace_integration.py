"""One focused offline V2 integration check, NOT a real-model quality benchmark.

Uses a memory repository/scripted model solely to exercise persistence contracts,
chapter scope and citation identity. PDF geometry and Decimal arithmetic are real.
Never connects to PostgreSQL/Ollama or mutates an existing collection.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'  # This check's process only.

from fastapi.testclient import TestClient
from langchain_core.documents import Document
import pymupdf
from config import Settings
from context_composer import compose_context
import starter
import report_api
import document_api
from reporting import ACTIVE_TASKS
from table_analysis import parse_tables, calculate_table
import workspace_store as store


class ScriptedModel:
    def bind(self, **kwargs):
        return self

    async def ainvoke(self, messages):
        system, data = messages[0][1], json.loads(messages[1][1])
        if '拆解用户研究问题' in system:
            value = {'tasks': [{'id': 'T1', 'question': data['question'], 'depends_on': []}]}
        elif '判断资料是否足够' in system:
            value = {'coverage': [{'task_id': task['id'], 'evidence_ids': [e['id'] for e in data['evidence']]} for task in data['tasks']], 'missing': []}
        elif '抽取所有可核验事实性结论' in system:
            value = {'claims': [{'text': data['answer'], 'answer_start': 0, 'answer_end': len(data['answer']), 'unit_id': data['units'][0]['unit_id']}], 'truncated': False}
        elif '来源一致性辅助审计员' in system:
            by_id = {source['id']: source for source in data['sources']}
            value = {'claims': [{'id': claim['id'], 'verdict': 'supported', 'reason': '脚本化一致性fixture', 'evidence': [
                {'source_id': claim['citation_ids'][0], 'quote': by_id[claim['citation_ids'][0]]['content']}]} for claim in data['claims']]}
        elif '只编写指定章节' in system:
            identifier = re.search(r'^\[(S\d+)\]', data['sources'], re.M).group(1)
            amount = '24' if '24GB' in data['sources'] else '16'
            return SimpleNamespace(content=f'Orion内存为{amount}GB [{identifier}]。')
        elif '报告提纲' in system:
            value = {'sections': [{'title': '配置', 'question': '配置需求'}, {'title': '适用范围', 'question': '适用范围'}]}
        else:
            raise AssertionError(f'Unexpected scripted model operation: {system[:40]}')
        return SimpleNamespace(content=json.dumps(value, ensure_ascii=False))


class Collection:
    def __init__(self, service):
        self.service, self.where = service, None

    def get(self, *, where=None, **kwargs):
        self.where = where
        documents = self.service.selected(where)
        return {'documents': [d.page_content for d in documents], 'metadatas': [d.metadata for d in documents]}


class Service:
    text_extensions = {'.md', '.csv', '.txt'}
    def __init__(self):
        self.settings = Settings(ollama_model='scripted-fixture', graph_enabled=True, context_neighbor_chars=0)
        self.llm = ScriptedModel()
        self.documents = [Document(page_content=f'Orion内存为{number}GB。', metadata={
            'source': identifier, 'filename': 'orion.md', 'chunk_id': f'{identifier}:0:0', 'child_chunk_id': f'{identifier}:0:0',
            'parent_id': f'{identifier}:parent:0', 'original_content': f'Orion内存为{number}GB。',
            'parent_content': f'Orion内存为{number}GB。', 'child_start_char': 0, 'child_end_char': len(f'Orion内存为{number}GB。'),
            'start_line': 1, 'end_line': 1, 'parent_start_line': 1, 'location_scope': 'source'}) for identifier, number in [('V1', 16), ('V2', 24)]]
        self.collection = Collection(self)
        self.client = SimpleNamespace(get_or_create_collection=lambda name: self.collection)
        self.filters = []

    def selected(self, where):
        identifiers = where['source']['$in'] if where else ['V1', 'V2']
        return [deepcopy(d) for d in self.documents if d.metadata['source'] in identifiers]

    def retrieve_trace(self, query, collection, *, where=None, **kwargs):
        self.filters.append(where)
        documents = self.selected(where)
        return SimpleNamespace(documents=documents, to_public_dict=lambda: {
            'requested_method': 'rerank', 'effective_method': 'rrf', 'status': 'success',
            'stages': {'bm25': {'status': 'success', 'count': len(documents), 'duration_ms': 0}}})

    def compose_context(self, documents):
        return compose_context(documents, token_budget=6000, max_documents=8, neighbor_chars=0)

    @staticmethod
    def _read_text(path):
        return path.read_text(encoding='utf-8')


class MemoryWorkspace:
    def __init__(self, root):
        self.kb = {'id': 'KB', 'title': 'Fixture workspace', 'collection_name': 'fixture'}
        self.versions = []
        for identifier, number in [('V1', 16), ('V2', 24)]:
            path = root / f'{identifier}.md'; path.write_text(f'Orion内存为{number}GB。', encoding='utf-8')
            self.versions.append({'id': identifier, 'knowledge_base_id': 'KB', 'document_series_id': 'SERIES', 'source_id': identifier,
                'version_label': identifier, 'status': 'ready', 'filename': 'orion.md', 'file_path': str(path), 'release_date': None, 'applicability': None})
        self.task = {'id': 'TASK', 'knowledge_base_id': 'KB', 'title': '部署研究', 'question': '核对部署内存与适用范围',
                     'outline': [{'id': 'C1', 'title': '配置', 'question': '内存要求', 'enabled': True},
                                 {'id': 'C2', 'title': '适用范围', 'question': '部署范围', 'enabled': True}],
                     'status': 'draft', 'report': None, 'revision': 0, 'context': {'selected_version_ids': ['V1']}}
        self.history = []

    def get(self, identifier):
        return deepcopy(self.task) if identifier == self.task['id'] else None

    def update(self, identifier, **changes):
        assert identifier == self.task['id']; self.task.update(deepcopy(changes)); return deepcopy(self.task)

    def save(self, identifier, report, kind='generated', changes=None):
        self.task['revision'] += 1; self.task['report'] = deepcopy(report)
        self.history.append({'task_id': identifier, 'revision': self.task['revision'], 'report': deepcopy(report), 'kind': kind, 'changes': deepcopy(changes)})
        return deepcopy(self.task)

    def resolve_version(self, identifier, private=True):
        value = next((deepcopy(v) for v in self.versions if v['id'] == identifier or v['source_id'] == identifier), None)
        if value and not private: value.pop('file_path', None)
        return value


def main():
    data_root = ROOT / 'data'; data_root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='v2-integration-', dir=data_root) as directory:
        temporary = Path(directory).resolve()
        assert temporary.is_relative_to(data_root.resolve()) and temporary.name.startswith('v2-integration-')
        # Verified absolute temporary target before TemporaryDirectory's cleanup.
        memory, service = MemoryWorkspace(temporary), Service()
        store.get_research_task = memory.get; store.update_research_task = memory.update; store.save_report_revision = memory.save
        store.get_knowledge_base = lambda identifier: deepcopy(memory.kb)
        store.list_document_versions = lambda *args: [memory.resolve_version(v['id'], False) for v in memory.versions]
        store.get_document_version = lambda identifier: memory.resolve_version(identifier, False)
        store.resolve_document_version = memory.resolve_version
        store.list_research_tasks = lambda *args: [memory.get('TASK')]
        store.list_report_revisions = lambda identifier: deepcopy(memory.history)
        store.get_report_revision = lambda identifier, revision: next((deepcopy(v) for v in memory.history if v['revision'] == revision), None)
        report_api.get_rag_service = lambda: service; document_api.get_rag_service = lambda: service
        document_api.settings.asset_dir = temporary / 'assets'
        client = TestClient(starter.app)
        response = client.post('/research-tasks/TASK/run', json={'resume': True})
        assert response.status_code == 202, response.text
        original = client.get('/research-tasks/TASK').json()
        assert original['status'] == 'completed', original['context']['progress']
        assert original['revision'] == 1 and not original['active'] and len(original['report']['sections']) == 2
        assert all(source['source_id'] == 'V1' for source in original['report']['sources'])
        assert service.collection.where == {'source': {'$in': ['V1']}}
        first_ids = [source['id'] for source in original['report']['sources']]
        second_content = original['report']['sections'][1]['content']
        client.patch('/research-tasks/TASK', json={'context': {'selected_version_ids': ['V2']}})
        response = client.post('/research-tasks/TASK/revise', json={'section_id': 'C1', 'instruction': '按所选版本定向修正内存参数'})
        assert response.status_code == 202, response.text
        revised = client.get('/research-tasks/TASK').json()
        assert revised['revision'] == 2, revised['context']['progress']
        assert '24GB' in revised['report']['sections'][0]['content']
        assert revised['report']['sections'][1]['content'] == second_content
        assert revised['report']['sources'][0]['id'] == first_ids[0]
        difference = client.get('/research-tasks/TASK/diff?from_revision=1&to_revision=2').json()
        assert [s['id'] for s in difference['sections']] == ['C1']
        for format in ('markdown', 'html', 'json'):
            result = client.get(f'/research-tasks/TASK/export?format={format}')
            assert result.status_code == 200 and 'attachment' in result.headers['content-disposition']
        restored = client.post('/research-tasks/TASK/restore/1').json()
        assert restored['revision'] == 3 and restored['report']['sections'][1]['content'] == second_content
        assert memory.history[0]['report'] == original['report']
        assert not ACTIVE_TASKS
        assert all(where is not None for where in service.filters)
        comparison = client.get('/documents/series/SERIES/compare?left_version=V1&right_version=V2')
        assert comparison.status_code == 200, comparison.text
        assert comparison.json()['changes'][0]['before'] == 'Orion内存为16GB。'
        assert comparison.json()['affected_tasks'][0]['section_ids'] == ['C1', 'C2']
        csv_path = temporary / 'cost.csv'; csv_path.write_text('Group,Amount\nA,0.1\nB,0.2\n', encoding='utf-8')
        memory.versions.append({'id': 'CSV', 'knowledge_base_id': 'KB', 'document_series_id': 'COST', 'source_id': 'CSV', 'status': 'ready', 'filename': 'cost.csv', 'file_path': str(csv_path)})
        pages = client.get('/documents/versions/CSV/pages').json()
        assert pages[0]['is_virtual_page'] and pages[0]['label'] == '文本资料（无分页）'
        result = client.post('/documents/versions/CSV/tables/calculate', json={'table_id': pages[0]['tables'][0]['id'], 'operation': 'sum', 'column': 'Amount'})
        assert result.status_code == 200 and result.json()['result'] == '0.3', result.text
        assert result.json()['used_rows'] == [2, 3]
        pdf_path = temporary / 'layout.pdf'
        pdf = pymupdf.open(); page = pdf.new_page(width=320, height=220)
        for x in (30, 150, 280): page.draw_line((x, 40), (x, 160))
        for y in (40, 80, 120, 160): page.draw_line((30, y), (280, y))
        for position, text in [((40, 65), 'Name'), ((160, 65), 'Amount'), ((40, 105), 'A'), ((160, 105), '0.1'), ((40, 145), 'B'), ((160, 145), '0.2')]: page.insert_text(position, text)
        pdf.save(pdf_path); pdf.close()
        memory.versions.append({'id': 'PDF', 'knowledge_base_id': 'KB', 'document_series_id': 'LAYOUT', 'source_id': 'PDF', 'status': 'ready', 'filename': 'layout.pdf', 'file_path': str(pdf_path)})
        pdf_pages_response = client.get('/documents/versions/PDF/pages')
        assert pdf_pages_response.status_code == 200, pdf_pages_response.text
        pdf_page = pdf_pages_response.json()[0]
        assert pdf_page['width'] == 320 and pdf_page['regions'] and pdf_page['tables']
        asset = client.get(pdf_page['asset_url']); assert asset.status_code == 200 and asset.content.startswith(b'\x89PNG')
        result = client.post('/documents/versions/PDF/tables/calculate', json={'table_id': pdf_page['tables'][0]['id'], 'operation': 'sum', 'column': 'Amount'})
        assert result.status_code == 200 and result.json()['result'] == '0.3', result.text
        selected = client.post('/documents/versions/CSV/tables/calculate', json={'table_id': pages[0]['tables'][0]['id'], 'operation': 'difference', 'column': 'Amount', 'row_a': 1, 'row_b': 0})
        assert selected.status_code == 200 and selected.json()['result'] == '0.1', selected.text
        print(json.dumps({'scope': 'offline V2 integration; scripted model/memory repository, not model quality',
                          'chapter_checkpoints_and_resume': True, 'selected_version_vector_lexical_graph_scope': True,
                          'local_revision_preserves_other_chapter': True, 'stable_citation_ids': True,
                          'immutable_history_restore_diff_export': True, 'literal_version_diff_and_affected_claims': True,
                          'real_pdf_regions_preview_tables': True, 'decimal_result': '0.3'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
