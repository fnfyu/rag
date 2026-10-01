"""Decimal arithmetic on explicit player inputs or quoted source table values.

No defaults for starting stats, softcaps, weight classes or damage formulas.
A source_id/quote is a supplied attribution, not a tool-verified citation.
"""
from decimal import Decimal, InvalidOperation
from souls_domain import STATS


def calculate(game_id: str, operation: str, data: dict, conditions: dict | None = None) -> dict:
    if game_id not in STATS:
        raise ValueError('Unknown game_id')
    if not isinstance(data, dict) or (conditions is not None and not isinstance(conditions, dict)):
        raise ValueError('data and conditions must be objects')
    inputs = []

    def number(value, name):
        attribution = value if isinstance(value, dict) else {'value': value}
        try:
            result = Decimal(str(attribution['value']))
        except (InvalidOperation, ValueError, KeyError, TypeError) as error:
            raise ValueError(f'{name}: a numeric value is required') from error
        if not result.is_finite() or isinstance(attribution['value'], bool):
            raise ValueError(f'{name}: a finite numeric value is required')
        sourced = bool(attribution.get('source_id') and attribution.get('quote'))
        inputs.append({'name': name, 'value': str(result), 'provenance': 'source_attributed' if sourced else 'player_declared',
                       **({key: attribution[key] for key in ('source_id', 'quote')} if sourced else {})})
        return result

    def nonnegative(value, name):
        result = number(value, name)
        if result < 0:
            raise ValueError(f'{name} must be nonnegative')
        return result

    warnings = ['只复算输入；来源标记未由计算工具核验，未预设职业初值、软上限、伤害或防御公式。']
    if operation == 'stat_budget':
        if game_id == 'nightreign':
            return {'game_id': game_id, 'operation': operation, 'status': 'not_applicable',
                    'reason': 'Nightreign规划角色、遗物与远征队伍，不适用自由属性加点预算。',
                    'conditions': conditions or {}, 'inputs': [], 'warnings': warnings}
        current, target = data.get('current'), data.get('target')
        if not isinstance(current, dict) or not isinstance(target, dict):
            raise ValueError('stat_budget requires current and target stat objects')
        keys = [key for key, _ in STATS[game_id]]
        if set(current) != set(keys) or set(target) != set(keys):
            raise ValueError(f'current and target must explicitly include this game stats: {keys}')
        deltas = {}
        for key in keys:
            before = nonnegative(current[key], f'current.{key}')
            after = nonnegative(target[key], f'target.{key}')
            if before != before.to_integral_value() or after != after.to_integral_value():
                raise ValueError('Stats must be integers')
            deltas[key] = after - before
        total = sum(deltas.values(), Decimal(0))
        result = {'deltas': {key: str(value) for key, value in deltas.items()}, 'net_points': str(total),
                  'points_to_add': str(sum((max(value, Decimal(0)) for value in deltas.values()), Decimal(0))),
                  'points_to_remove': str(sum((max(-value, Decimal(0)) for value in deltas.values()), Decimal(0)))}
        if 'available_points' in data:
            result['remaining_points'] = str(nonnegative(data['available_points'], 'available_points') - result_decimal(result['points_to_add']))
        formula = 'delta[stat] = target[stat] - current[stat]; net_points = sum(delta); points_to_add = sum(max(delta,0))'
        warnings.append('减少属性仅表示输入差值，不证明可以洗点或退还点数。')
    elif operation == 'loadout_weight':
        if game_id == 'nightreign':
            return {'game_id': game_id, 'operation': operation, 'status': 'not_applicable',
                    'reason': '本项目未建立Nightreign的传统最大负重模型，不能移用其他魂系作品规则；可对明确资料数值使用table_comparison。',
                    'conditions': conditions or {}, 'inputs': [], 'warnings': warnings}
        equipment = data.get('equipment')
        if not isinstance(equipment, list) or not equipment:
            raise ValueError('equipment must be a nonempty list of weights or {weight,...} objects')
        weights = [nonnegative(item.get('weight') if isinstance(item, dict) and 'weight' in item else item,
                               f'equipment[{index}].weight') for index, item in enumerate(equipment)]
        maximum = nonnegative(data.get('max_load'), 'max_load')
        if maximum == 0:
            raise ValueError('max_load must be greater than zero')
        total = sum(weights, Decimal(0))
        percent = total / maximum * 100
        result = {'total_weight': str(total), 'max_load': str(maximum), 'ratio': str(total / maximum),
                  'ratio_percent': str(percent), 'classification': None}
        thresholds = data.get('thresholds', (conditions or {}).get('thresholds'))
        if thresholds is not None:
            if not isinstance(thresholds, list) or not thresholds:
                raise ValueError('thresholds must be ordered [{label,max_percent,inclusive?}]')
            previous = Decimal('-Infinity')
            for index, threshold in enumerate(thresholds):
                bound = nonnegative(threshold['max_percent'], f'thresholds[{index}].max_percent')
                if bound <= previous or not str(threshold.get('label', '')).strip():
                    raise ValueError('thresholds must have labels and increasing max_percent')
                previous = bound
                if result['classification'] is None and (percent <= bound if threshold.get('inclusive', False) else percent < bound):
                    result['classification'] = threshold['label']
            warnings.append('负重分类仅按用户提交阈值及inclusive条件；不证明其对当前版本有效。')
        else:
            warnings.append('未提供有来源/手工声明的阈值，不分类轻、中、重负重。')
        formula = 'total_weight = sum(equipment.weight); ratio_percent = total_weight / max_load * 100'
    elif operation in {'comparison', 'table_comparison'}:
        # Two actual table cells (or manually declared values), no inferred model.
        left, right = number(data.get('left'), 'left'), number(data.get('right'), 'right')
        result = {'difference': str(left - right), 'ratio': str(left / right) if right else None,
                  'percent_change': str((left - right) / right * 100) if right else None,
                  'unit': data.get('unit', '')}
        if not right:
            warnings.append('右值为0，比值和百分比变化未定义。')
        formula = 'difference = left-right; ratio = left/right; percent_change = (left-right)/right*100'
    else:
        raise ValueError('Supported operations: stat_budget, loadout_weight, table_comparison (comparison)')
    return {'game_id': game_id, 'operation': operation, 'status': 'calculated', 'result': result,
            'formula': formula, 'inputs': inputs, 'conditions': conditions or {},
            'provenance': 'source_attributed' if inputs and all(v['provenance'] == 'source_attributed' for v in inputs) else 'player_declared',
            'warnings': warnings}


def result_decimal(value: str) -> Decimal:
    return Decimal(value)
