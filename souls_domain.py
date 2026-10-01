"""Game conditions and draft templates; no patch facts or combat formulas.

Unknown metadata is not verified compatibility. Editions and patch labels are
literal identifiers. Templates only draft an outline for user confirmation.
"""
from copy import deepcopy
import json
import ipaddress
from urllib.parse import urlparse

_GAMES = {
    'elden-ring': ('艾尔登法环 Elden Ring', [('standard', '标准版')], ['ER', '艾尔登法环'],
                   '自由属性规划必须基于玩家输入；不可移用黑夜君临角色、遗物和远征机制。'),
    'nightreign': ('艾尔登法环黑夜君临 Elden Ring Nightreign', [('standard', '标准版')], ['黑夜君临', 'Elden Ring Nightreign'],
                  '围绕角色、遗物、远征和队伍条件；不提供艾尔登法环式自由属性加点。'),
    'dark-souls-1': ('黑暗之魂1 Dark Souls', [('original', '原版'), ('remastered', 'Remastered')], ['DS1', '黑魂1'],
                     '原版和Remastered不可默认共享规则；属性输入包含resistance。'),
    'dark-souls-2': ('黑暗之魂2 Dark Souls II', [('standard', '标准版'), ('scholar', 'Scholar of the First Sin')], ['DS2', '黑魂2'],
                     '标准版和Scholar必须明确区分；属性输入包含adaptability。'),
    'dark-souls-3': ('黑暗之魂3 Dark Souls III', [('standard', '标准版')], ['DS3', '黑魂3'],
                     '独立核查本作规则；属性输入包含luck，不移用其他作品阈值。'),
}
_FIELDS = ['edition', 'patch', 'dlc', 'platform', 'mode', 'cycle', 'progress', 'player_level', 'character', 'spoiler_policy']
STATS = {
    'elden-ring': [('vigor', '生命力'), ('mind', '集中力'), ('endurance', '耐力'), ('strength', '力气'), ('dexterity', '灵巧'), ('intelligence', '智力'), ('faith', '信仰'), ('arcane', '感应')],
    'nightreign': [],
    'dark-souls-1': [('vitality', '体力'), ('attunement', '记忆力'), ('endurance', '持久力'), ('strength', '筋力'), ('dexterity', '技量'), ('resistance', '耐力'), ('intelligence', '理力'), ('faith', '信仰')],
    'dark-souls-2': [('vigor', '生命力'), ('endurance', '持久力'), ('vitality', '体力'), ('attunement', '记忆力'), ('strength', '筋力'), ('dexterity', '技量'), ('adaptability', '适应力'), ('intelligence', '理力'), ('faith', '信仰')],
    'dark-souls-3': [('vigor', '生命力'), ('attunement', '集中力'), ('endurance', '持久力'), ('vitality', '体力'), ('strength', '筋力'), ('dexterity', '技量'), ('intelligence', '理力'), ('faith', '信仰'), ('luck', '运气')],
}
_DLCS = {
    'elden-ring': [('shadow-of-the-erdtree', 'Shadow of the Erdtree'), ('tarnished-pack', 'Tarnished Pack')],
    'nightreign': [('the-forsaken-hollows', 'The Forsaken Hollows')],
    'dark-souls-1': [('artorias-of-the-abyss', 'Artorias of the Abyss')],
    'dark-souls-2': [('crown-of-the-sunken-king', 'Crown of the Sunken King'), ('crown-of-the-old-iron-king', 'Crown of the Old Iron King'), ('crown-of-the-ivory-king', 'Crown of the Ivory King')],
    'dark-souls-3': [('ashes-of-ariandel', 'Ashes of Ariandel'), ('the-ringed-city', 'The Ringed City')],
}
_TEMPLATE_INFO = {
    'boss': ('Boss攻略', '在明确进度和剧透条件下查证应对策略'),
    'build': ('构筑规划', '基于玩家资源和已标注来源比较方案'),
    'route': ('路线规划', '按进度、目标和可进入内容规划路线'),
    'patch-impact': ('补丁影响', '对比明确补丁原文及受影响策略'),
    'guide-conflict': ('攻略冲突', '定位不同攻略条件和引用差异'),
}


def templates_for(game_id: str) -> list[dict]:
    if game_id not in _GAMES:
        raise ValueError('Unknown game_id')
    result = []
    for template_id, (title, description) in _TEMPLATE_INFO.items():
        subject = '角色、遗物、远征与队伍配合' if game_id == 'nightreign' else '玩家输入属性、装备和资源预算'
        if template_id == 'build' and game_id == 'nightreign':
            title = '角色 / 遗物 / 远征队伍'
            description = '规划角色、遗物和远征队伍；不是自由属性加点'
        middle = {
            'boss': ('应对方案', '哪些来源支持目标Boss的机制和应对？遵守剧透政策。'),
            'build': ('方案与预算', f'基于{subject}比较可用方案，不假设职业初值或伤害公式。'),
            'route': ('路线与前置条件', '哪些路线满足当前进度、内容访问权和剧透政策？'),
            'patch-impact': ('补丁对比', '逐字引用指定补丁的变化；区分历史变化与当前攻略适用性。'),
            'guide-conflict': ('冲突定位', '分别引用冲突原文，比较游戏、版本、模式和前置条件。'),
        }[template_id]
        outline = [
            {'id': 'conditions', 'title': '适用条件与资料范围', 'question': '核对游戏、edition、patch、模式、DLC访问权和未知条件。', 'enabled': True},
            {'id': 'analysis', 'title': middle[0], 'question': middle[1], 'enabled': True},
            {'id': 'recommendations', 'title': '建议与证据缺口', 'question': '区分可推荐、历史对比、待确认和缺少证据的结论。', 'enabled': True},
        ]
        extra = {
            'boss': [
                {'id': 'preparation', 'title': '准备与资源', 'question': '核对当前可取得的装备、消耗品及前置条件；没有原文不推测抗性。', 'enabled': True},
                {'id': 'execution', 'title': '动作信号与应对窗口', 'question': '按来源梳理目标Boss阶段、动作信号、安全窗口和失误恢复；不编造招架资格或帧数。', 'enabled': True}],
            'build': [
                {'id': 'budget', 'title': '遗物与远征资源' if game_id == 'nightreign' else '属性与负重预算',
                 'question': '比较角色、遗物和远征资源的条件，不移用其他游戏属性体系。' if game_id == 'nightreign' else '仅按明确起点、目标属性、装备重量及最大负重复算预算，不预设职业数值、软上限或伤害公式。', 'enabled': True},
                {'id': 'alternatives', 'title': '方案取舍与取得路径', 'question': '按玩家已有资源、玩法和进度比较方案，引用取得路径和必要条件；无法确认的道具不假定可用。', 'enabled': True}],
            'route': [
                {'id': 'prerequisites', 'title': '解锁与前置条件', 'question': '查证路线所需解锁、关键物品和前置任务，遵守剧透范围，不把别作同名区域混入。', 'enabled': True},
                {'id': 'missables', 'title': '可错过内容与替代路线', 'question': '仅按原文说明不可逆分支、可能错过的内容及替代路线；未探索信息遵守剧透条件。', 'enabled': True}],
            'patch-impact': [
                {'id': 'dependencies', 'title': '攻略依赖与影响候选', 'question': '把具体补丁变更关联到攻略依赖，分别引用原文与旧结论；不直接宣告结论失效。', 'enabled': True},
                {'id': 'current-applicability', 'title': '当前适用性与复核行动', 'question': '核对本机补丁、PVE/PVP、平台和DLC条件，说明哪些建议仍待确认；历史公告不等于当前最新。', 'enabled': True}],
            'guide-conflict': [
                {'id': 'source-comparison', 'title': '来源与条件对照', 'question': '区分官方变更、社区攻略和玩家数据，比较日期、发行版、版本和模式；来源等级不等于真实性证明。', 'enabled': True},
                {'id': 'conditional-choice', 'title': '条件化选择', 'question': '按实际玩家条件提出有依据的选择；条件未知时保留冲突，不强行选择一个答案。', 'enabled': True}],
        }[template_id]
        outline[2:2] = extra
        result.append({'id': template_id, 'title': title, 'description': description,
                       'outline': outline, 'question_hint': '请填写具体目标、现有资源及希望避免的剧透；确认提纲后再运行。'})
    return result


def catalog() -> list[dict]:
    return [{'id': game_id, 'title': title, 'editions': [{'id': key, 'label': label} for key, label in editions],
             'platforms': ['PC', 'PlayStation', 'Xbox', 'other'], 'modes': ['pve', 'coop'] if game_id == 'nightreign' else ['pve', 'pvp', 'coop', 'other'],
             'fields': {'profile': _FIELDS.copy(), 'stats': [{'id': key, 'label': label} for key, label in STATS[game_id]]},
             'dlcs': [{'id': key, 'label': label} for key, label in _DLCS[game_id]], 'aliases': aliases.copy(),
             'templates': [{key: value for key, value in template.items() if key in {'id', 'title', 'description'}}
                           for template in templates_for(game_id)], 'rule_notes': [notes]}
            for game_id, (title, editions, aliases, notes) in _GAMES.items()]


def normalize_profile(profile: dict, *, game_id: str | None = None) -> dict:
    if not isinstance(profile, dict):
        raise ValueError('Game profile must be an object')
    if game_id and profile.get('game_id') and profile['game_id'] != game_id:
        raise ValueError('Game profile game_id mismatch')
    result = {key: deepcopy(value) for key, value in profile.items() if key in {'game_id', *_FIELDS}}
    if game_id:
        result['game_id'] = game_id
    if not result:
        return {}
    gid = result.get('game_id')
    if gid not in _GAMES:
        raise ValueError('Unknown or missing game_id')
    edition = result.get('edition')
    if edition and edition not in {entry[0] for entry in _GAMES[gid][1]}:
        raise ValueError('Unknown edition for this game')
    for key in ('edition', 'patch', 'platform', 'mode', 'cycle', 'progress', 'character'):
        if key in result and result[key] is not None:
            result[key] = str(result[key]).strip()
    if gid == 'nightreign' and result.get('mode') == 'pvp':
        raise ValueError('Nightreign PvP is not applicable; use PvE expedition/coop conditions')
    if 'dlc' in result:
        if not isinstance(result['dlc'], list) or any(not isinstance(value, str) for value in result['dlc']):
            raise ValueError('dlc must be a list of strings; omit when unknown')
        result['dlc'] = list(dict.fromkeys(result['dlc']))
    if result.get('player_level') is not None:
        level = result['player_level']
        if isinstance(level, bool) or str(level).strip() != str(int(level)) or int(level) < 0:
            raise ValueError('player_level must be a nonnegative integer')
        result['player_level'] = int(level)
    result.setdefault('spoiler_policy', 'none')
    if result['spoiler_policy'] not in {'none', 'bosses', 'full'}:
        raise ValueError('Unknown spoiler_policy')
    return result


def domain_instruction(profile: dict) -> str:
    profile = normalize_profile(profile)
    if not profile:
        return '资料尚未标注游戏条件，不能自动视为某款游戏资料；先确认知识库范围。'
    return (f'游戏条件（用户声明，不是已验证事实）：{json.dumps(profile, ensure_ascii=False)}。'
            + _GAMES[profile['game_id']][3]
            + '只按明确游戏、edition、模式、平台及补丁原文判断适用性；补丁ID逐字匹配，不按semver或latest推定正确。'
            '标签不能覆盖原文游戏归属；原文谈其他作品或发行版时指出误标或对比语境，不借用其规则。条件未知必须列为待确认。历史patch_notes只用于变化对比，不证明当前建议有效。'
            '推荐需要满足资料requires_dlc；任务未声明dlc表示未知，不等于无DLC。'
            'spoiler_policy=none只沿用玩家已明确给出的目标实体，避免揭露未指定Boss身份、未知区域、剧情与结局；bosses仅允许目标Boss攻略所需细节，仍避免剧情与结局；full允许剧透。'
            '没有资料引用不得编造版本号、伤害公式、属性软上限或轻中重负重阈值。用户选择official不等于verified_capture。')


def task_payload(profile: dict, template_id: str, goal: str, player: dict | None = None) -> dict:
    profile = normalize_profile(profile)
    if not profile:
        raise ValueError('A game profile is required')
    template = next((item for item in templates_for(profile['game_id']) if item['id'] == template_id), None)
    if template is None:
        raise ValueError('Unknown template_id')
    if not str(goal).strip():
        raise ValueError('A goal is required')
    if player is not None and not isinstance(player, dict):
        raise ValueError('player must be an object')
    applicability = domain_instruction(profile)
    return {'title': f"{template['title']}：{goal.strip()}"[:200], 'question': goal.strip(),
            'outline': deepcopy(template['outline']),
            'context': {'game': {**profile, 'template_id': template_id, 'player': deepcopy(player or {})},
                        'applicability': applicability}}


def applicable_versions(profile: dict, versions: list[dict], selected_ids: list[str] | None = None) -> dict:
    profile = normalize_profile(profile)
    included, excluded, warnings = [], [], []
    selected = set(selected_ids) if selected_ids is not None else None
    for version in versions:
        vid = version.get('id', version.get('source_id', ''))
        if selected is not None and vid not in selected and version.get('source_id') not in selected:
            continue
        metadata = version.get('domain_metadata') or {}
        if not metadata.get('game_id'):
            warnings.append(f'{vid}: game未知，须知识库手工标注；未自动纳入游戏范围。')
            excluded.append({'id': vid, 'reason': 'game_unknown_requires_annotation'})
            continue
        reason = None
        historical = False
        unknown = []
        for key in ('game_id', 'edition', 'mode', 'patch', 'platform'):
            expected, actual = profile.get(key), metadata.get(key)
            if expected and actual and str(expected) != str(actual):
                if key == 'patch' and metadata.get('source_kind') == 'patch_notes':
                    historical = True
                else:
                    reason = f'{key}_mismatch'
                    break
            elif not expected or not actual:
                unknown.append(key)
        if reason:
            excluded.append({'id': vid, 'reason': reason})
            continue
        required = metadata.get('requires_dlc') or []
        dlc_access = 'not_required'
        if required:
            if 'dlc' not in profile:
                dlc_access = 'unknown'
                warnings.append(f'{vid}: DLC访问权未知，仅供查证；确认前不得推荐所需内容。')
            elif not set(required).issubset(set(profile['dlc'])):
                excluded.append({'id': vid, 'reason': 'requires_dlc_not_owned'})
                continue
            else:
                dlc_access = 'satisfied'
        if unknown:
            warnings.append(f'{vid}: 条件未知: {", ".join(unknown)}；不能声明兼容已验证。')
        if historical:
            warnings.append(f'{vid}: 历史补丁，仅用于对比，不作为当前攻略依据。')
        included.append({**version, 'historical': historical,
                         'compatibility': 'unknown' if unknown or dlc_access == 'unknown' else 'declared_match',
                         'actualDLCAccess': dlc_access,
                         'requires_confirmation': bool(unknown) or dlc_access == 'unknown',
                         'recommendable': not historical and not unknown and dlc_access != 'unknown'})
    if selected is not None:
        known = {v.get('id') for v in versions} | {v.get('source_id') for v in versions}
        warnings.extend(f'{vid}: 所选资料版本不存在。' for vid in sorted(selected - known))
    return {'versions': included, 'excluded': excluded, 'warnings': warnings}


# Upload and manual annotation share this seam. Only the collector may attest a
# verified capture; manual mutations strip claims to verification and private paths.
_METADATA_FIELDS = {'game_id', 'edition', 'patch', 'dlc', 'platform', 'mode', 'requires_dlc',
                    'source_kind', 'source_tier', 'source_url', 'captured_at', 'published_at',
                    'provenance', 'title', 'capture_sha256', 'content_sha256'}


def normalize_metadata(metadata: dict, profile: dict | None = None, *, manual: bool = True) -> dict:
    if not isinstance(metadata, dict):
        raise ValueError('domain_metadata must be an object')
    profile = normalize_profile(profile or {})
    result = {key: deepcopy(value) for key, value in metadata.items() if key in _METADATA_FIELDS}
    if profile.get('game_id') and result.get('game_id') and profile['game_id'] != result['game_id']:
        raise ValueError('Document game_id differs from knowledge base; create a new knowledge base')
    for key in ('game_id', 'edition', 'patch', 'mode', 'dlc', 'platform'):
        if key not in result and key in profile:
            result[key] = deepcopy(profile[key])
    if result.get('game_id'):
        normalized = normalize_profile({key: result[key] for key in ('game_id', 'edition', 'patch', 'mode', 'dlc', 'platform') if key in result})
        for key in ('game_id', 'edition', 'patch', 'mode', 'dlc', 'platform'):
            if key in normalized:
                result[key] = normalized[key]
    if 'requires_dlc' in result and (not isinstance(result['requires_dlc'], list) or any(not isinstance(v, str) for v in result['requires_dlc'])):
        raise ValueError('requires_dlc must be a list of strings')
    if result.get('source_url'):
        parsed = urlparse(str(result['source_url']))
        if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('source_url must be a public HTTP(S) URL without credentials')
        hostname = parsed.hostname.lower()
        if hostname == 'localhost' or hostname.endswith(('.localhost', '.local')):
            raise ValueError('source_url must not expose a local host')
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError('source_url must not expose a private network address')
    if result.get('source_kind', 'guide') not in {'patch_notes', 'guide', 'reference', 'player_sheet'}:
        raise ValueError('Unknown source_kind')
    result.setdefault('source_kind', 'guide')
    result.setdefault('source_tier', 'player')
    if result['source_tier'] not in {'official', 'community', 'player'}:
        raise ValueError('Unknown source_tier')
    if manual:
        result['provenance'] = 'user_declared'
        result.pop('capture_sha256', None)
        result.pop('content_sha256', None)
    return result
