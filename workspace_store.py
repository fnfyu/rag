"""PostgreSQL workspace storage.

Knowledge bases own collections; conversations and research tasks share them.
Document versions are independent evidence, never an implicit 'latest effective'
selection. Public records omit filesystem paths. Task context/outline preserve
chapter checkpoints and evidence references; only saving a report increments
its revision. Missing lookups return None; invalid mutations raise ValueError.
"""

import uuid
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from utils import get_db_connection
from souls_domain import normalize_profile, normalize_metadata

TASK_STATUSES = {'draft', 'planning', 'running', 'completed', 'partial', 'error'}


def _id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex}'


def _record(row: Any, *, private: bool = False) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    if not private:
        result.pop('file_path', None)
    for key in ('created_at', 'updated_at', 'release_date'):
        if result.get(key) is not None and hasattr(result[key], 'isoformat'):
            result[key] = result[key].isoformat()
    return result


def _one(sql: str, params: tuple = (), *, private: bool = False) -> dict[str, Any] | None:
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql, params)
        return _record(cursor.fetchone(), private=private)


def _many(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(sql, params)
        return [_record(row) for row in cursor.fetchall()]


def list_knowledge_bases() -> list[dict[str, Any]]:
    return _many('SELECT * FROM knowledge_bases ORDER BY updated_at DESC, id')


def get_knowledge_base(knowledge_base_id: str) -> dict[str, Any] | None:
    return _one('SELECT * FROM knowledge_bases WHERE id = %s', (knowledge_base_id,))


def create_knowledge_base(title: str, description: str = '', game_profile: dict | None = None) -> dict[str, Any]:
    profile = normalize_profile(game_profile or {})
    if not title.strip():
        raise ValueError('Knowledge-base title is required')
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            'INSERT INTO knowledge_bases (id, title, description, collection_name, game_profile) VALUES (%s, %s, %s, %s, %s) RETURNING *',
            (_id('kb'), title.strip(), description, _id('kb_collection'), Json(profile)),
        )
        result = _record(cursor.fetchone())
        connection.commit()
        return result


def update_game_profile(kb_id: str, profile: dict) -> dict[str, Any]:
    """Replace task defaults, never silently relabel existing evidence."""
    profile = normalize_profile(profile)
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('SELECT * FROM knowledge_bases WHERE id = %s FOR UPDATE', (kb_id,))
        kb = cursor.fetchone()
        if kb is None:
            raise ValueError('Knowledge base does not exist')
        old_game = (kb.get('game_profile') or {}).get('game_id')
        new_game = profile.get('game_id')
        if old_game != new_game:
            cursor.execute('SELECT domain_metadata FROM document_versions WHERE knowledge_base_id = %s', (kb_id,))
            documents = cursor.fetchall()
            if old_game and documents:
                raise ValueError('Cannot change game_id with existing documents; create a new knowledge base')
            if any((row['domain_metadata'] or {}).get('game_id') not in {None, new_game} for row in documents):
                raise ValueError('Existing documents belong to another game; create a new knowledge base')
        cursor.execute('UPDATE knowledge_bases SET game_profile = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *',
                       (Json(profile), kb_id))
        result = _record(cursor.fetchone())
        connection.commit()
        return result


def update_document_metadata(version_id: str, domain_metadata: dict) -> dict[str, Any]:
    """Manual full replacement, recorded as user_declared even for official tier."""
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('SELECT v.*, kb.game_profile FROM document_versions v JOIN knowledge_bases kb ON kb.id = v.knowledge_base_id '
                       'WHERE v.id = %s OR v.source_id = %s FOR UPDATE OF kb, v', (version_id, version_id))
        row = cursor.fetchone()
        if row is None:
            raise ValueError('Document version does not exist')
        # Defaults describe the upload time, not a retroactive patch assignment.
        kb_profile = row['game_profile'] or {}
        scope = {'game_id': kb_profile['game_id']} if kb_profile.get('game_id') else {}
        metadata = normalize_metadata(domain_metadata, scope, manual=True)
        cursor.execute('UPDATE document_versions SET domain_metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *',
                       (Json(metadata), row['id']))
        result = _record(cursor.fetchone())
        connection.commit()
        return result


def list_research_tasks(knowledge_base_id: str | None = None) -> list[dict[str, Any]]:
    if knowledge_base_id is None:
        return _many('SELECT * FROM research_tasks ORDER BY updated_at DESC, id')
    return _many('SELECT * FROM research_tasks WHERE knowledge_base_id = %s ORDER BY updated_at DESC, id', (knowledge_base_id,))


def get_research_task(task_id: str) -> dict[str, Any] | None:
    return _one('SELECT * FROM research_tasks WHERE id = %s', (task_id,))


def _outline(outline: list | None) -> list[dict[str, Any]]:
    result = []
    for chapter in outline or []:
        if not isinstance(chapter, dict):
            raise ValueError('Outline chapters must be objects')
        result.append({**chapter, 'id': chapter.get('id') or _id('chapter'),
                       'title': chapter.get('title', ''), 'question': chapter.get('question', ''),
                       'enabled': chapter.get('enabled', True)})
    return result


def create_research_task(
    knowledge_base_id: str, title: str, question: str = '',
    outline: list | None = None, context: dict | None = None,
) -> dict[str, Any]:
    if not get_knowledge_base(knowledge_base_id):
        raise ValueError(f"Knowledge base '{knowledge_base_id}' does not exist")
    if not title.strip():
        raise ValueError('Research-task title is required')
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            'INSERT INTO research_tasks (id, knowledge_base_id, title, question, outline, context) VALUES (%s, %s, %s, %s, %s, %s) RETURNING *',
            (_id('task'), knowledge_base_id, title.strip(), question, Json(_outline(outline)), Json(context or {})),
        )
        result = _record(cursor.fetchone())
        connection.commit()
        return result


def update_research_task(task_id: str, **updates: Any) -> dict[str, Any]:
    """Replace supplied fields atomically; preserve unspecified checkpoint fields.

    A report can only be changed through save_report_revision. Progress/context
    updates do not create report revisions. Context is a full replacement, so a
    caller resuming a task should merge its existing context before updating.
    """
    allowed = {'title', 'question', 'outline', 'status', 'context'}
    if set(updates) - allowed:
        raise ValueError(f'Unsupported task fields: {sorted(set(updates) - allowed)}')
    if 'status' in updates and updates['status'] not in TASK_STATUSES:
        raise ValueError('Invalid research-task status')
    if 'title' in updates and not str(updates['title']).strip():
        raise ValueError('Research-task title is required')
    if 'context' in updates and not isinstance(updates['context'], dict):
        raise ValueError('Task context must be an object')
    if not updates:
        result = get_research_task(task_id)
        if result is None:
            raise ValueError(f"Research task '{task_id}' does not exist")
        return result
    values = dict(updates)
    if 'outline' in values:
        values['outline'] = _outline(values['outline'])
    parameters = [Json(value) if key in {'outline', 'context'} else value for key, value in values.items()]
    assignments = ', '.join(f'{key} = %s' for key in values)
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f'UPDATE research_tasks SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *', (*parameters, task_id))
        result = _record(cursor.fetchone())
        if result is None:
            raise ValueError(f"Research task '{task_id}' does not exist")
        connection.commit()
        return result


def save_report_revision(
    task_id: str, report: dict, kind: str = 'generated', changes: list | dict | None = None,
) -> dict[str, Any]:
    """Append an immutable report snapshot and return the updated TASK.

    The row lock allocates monotonically increasing report revisions, beginning
    at 1. Report persistence and the task's latest snapshot share a transaction.
    Chapter statuses and source-version references inside report are retained.
    """
    if not isinstance(report, dict):
        raise ValueError('Report must be an object')
    if changes is not None and not isinstance(changes, (list, dict)):
        raise ValueError('Changes must be an array or object')
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('SELECT revision FROM research_tasks WHERE id = %s FOR UPDATE', (task_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Research task '{task_id}' does not exist")
        revision = row['revision'] + 1
        cursor.execute(
            'INSERT INTO report_versions (id, task_id, revision, report, kind, changes) VALUES (%s, %s, %s, %s, %s, %s)',
            (_id('report'), task_id, revision, Json(report), kind, Json(changes) if changes is not None else None),
        )
        cursor.execute('UPDATE research_tasks SET report = %s, revision = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *',
                       (Json(report), revision, task_id))
        result = _record(cursor.fetchone())
        connection.commit()
        return result


def list_report_revisions(task_id: str) -> list[dict[str, Any]]:
    return _many('SELECT * FROM report_versions WHERE task_id = %s ORDER BY revision DESC', (task_id,))


def get_report_revision(task_id: str, revision: int) -> dict[str, Any] | None:
    return _one('SELECT * FROM report_versions WHERE task_id = %s AND revision = %s', (task_id, revision))


def get_document_version(version_id: str) -> dict[str, Any] | None:
    return _one('SELECT * FROM document_versions WHERE id = %s OR source_id = %s', (version_id, version_id))


def resolve_document_version(version_id: str) -> dict[str, Any] | None:
    """INTERNAL ONLY: return a version including private file_path for downloads."""
    return _one('SELECT * FROM document_versions WHERE id = %s OR source_id = %s', (version_id, version_id), private=True)


def list_document_versions(knowledge_base_id: str, document_series_id: str | None = None) -> list[dict[str, Any]]:
    if document_series_id is None:
        return _many('SELECT * FROM document_versions WHERE knowledge_base_id = %s ORDER BY created_at DESC, id', (knowledge_base_id,))
    return _many('SELECT * FROM document_versions WHERE knowledge_base_id = %s AND document_series_id = %s ORDER BY created_at DESC, id',
                 (knowledge_base_id, document_series_id))


def list_document_series(knowledge_base_id: str) -> list[dict[str, Any]]:
    series = _many('SELECT * FROM document_series WHERE knowledge_base_id = %s ORDER BY created_at DESC, id', (knowledge_base_id,))
    grouped = {item['id']: item for item in series}
    for item in series:
        item['versions'] = []
    for version in list_document_versions(knowledge_base_id):
        grouped[version['document_series_id']]['versions'].append(version)
    return series


def create_document_version(
    knowledge_base_id: str, filename: str, file_path: str, sha256: str,
    version_label: str | None = None, release_date: str | None = None,
    applicability: dict | str | None = None,
    *, domain_metadata: dict | None = None,
) -> dict[str, Any]:
    """Create a queued version; reuse identical content AND version descriptors.

    Reuse is restricted to this filename series in this knowledge base. A new
    release/applicability descriptor remains a distinct evidence version even
    when its bytes happen to match. The returned record never includes a path.
    """
    file_type = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'unknown'
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('SELECT game_profile FROM knowledge_bases WHERE id = %s FOR UPDATE', (knowledge_base_id,))
        kb = cursor.fetchone()
        if kb is None:
            raise ValueError(f"Knowledge base '{knowledge_base_id}' does not exist")
        profile = kb['game_profile'] or {}
        scope = {'game_id': profile['game_id']} if profile.get('game_id') else {}
        metadata = normalize_metadata(domain_metadata, scope, manual=False) if domain_metadata is not None else {}
        # Serialize version creation for the same series (including dedup lookup).
        cursor.execute(
            'INSERT INTO document_series (id, knowledge_base_id, filename, filename_key) VALUES (%s, %s, %s, %s) '
            'ON CONFLICT (knowledge_base_id, filename_key) DO UPDATE SET filename = document_series.filename RETURNING *',
            (_id('series'), knowledge_base_id, filename, filename.casefold()),
        )
        series = cursor.fetchone()
        cursor.execute(
            'SELECT * FROM document_versions WHERE document_series_id = %s AND sha256 = %s '
            'AND version_label IS NOT DISTINCT FROM %s AND release_date IS NOT DISTINCT FROM %s::date '
            'AND applicability IS NOT DISTINCT FROM %s::jsonb AND domain_metadata = %s::jsonb '
            'AND status IN (\'queued\', \'ready\') ORDER BY created_at LIMIT 1',
            (series['id'], sha256, version_label, release_date, Json(applicability) if applicability is not None else None, Json(metadata)),
        )
        existing = cursor.fetchone()
        if existing:
            connection.commit()
            return _record(existing)
        version_id = _id('version')
        cursor.execute(
            'INSERT INTO document_versions (id, knowledge_base_id, document_series_id, source_id, filename, file_path, file_type, sha256, version_label, release_date, applicability, domain_metadata) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s) RETURNING *',
            (version_id, knowledge_base_id, series['id'], version_id, filename, file_path, file_type, sha256,
             version_label, release_date, Json(applicability) if applicability is not None else None, Json(metadata)),
        )
        result = _record(cursor.fetchone())
        connection.commit()
        return result


def update_document_version(version_id: str, status: str, chunk_count: int = 0, error: str | None = None) -> dict[str, Any]:
    if status not in {'queued', 'ready', 'error'}:
        raise ValueError('Invalid document-version status')
    with get_db_connection() as connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute('UPDATE document_versions SET status = %s, chunk_count = %s, error = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s RETURNING *',
                       (status, chunk_count, error, version_id))
        result = _record(cursor.fetchone())
        if result is None:
            raise ValueError(f"Document version '{version_id}' does not exist")
        connection.commit()
        return result
