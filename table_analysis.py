"""Deterministic table parsing and auditable Decimal calculations, no model code."""
from __future__ import annotations

import csv
from decimal import Decimal, localcontext
import hashlib
import io
import json
import re
from typing import Any


class TableAnalysisError(ValueError):
    """Invalid/ambiguous source data: caller must surface, not guess a result."""


def _table(columns, rows, row_numbers, source_id, filename, index, **metadata):
    if not columns or len(set(columns)) != len(columns) or any(not c for c in columns):
        raise TableAnalysisError("表头缺失或重复，无法唯一指定列")
    if any(len(row) != len(columns) for row in rows):
        raise TableAnalysisError("表格行列数不一致")
    digest = hashlib.sha256(json.dumps([source_id, filename, columns, rows, row_numbers], ensure_ascii=False).encode()).hexdigest()[:20]
    return {"id": f"table:{digest}:{index}", "columns": columns, "rows": rows,
            "row_numbers": row_numbers, "source_id": source_id, "filename": filename, **metadata}


def _md_cells(line: str) -> list[str]:
    return [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def parse_tables(content: str, source_id: str = "", filename: str = "") -> list[dict]:
    """Parse Markdown tables, CSV (including quoted multiline cells), or table_json.

    Markdown/CSV row_numbers are exact physical starting lines (1 based).
    PDF payload row_numbers are table-relative and page_number disambiguates them.
    """
    text = content.strip()
    if not text:
        return []
    if text.startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if payload is not None:
            values = payload if isinstance(payload, list) else [payload]
            tables = []
            for item in values:
                if not isinstance(item, dict) or "columns" not in item or "rows" not in item:
                    continue
                table = dict(item)
                table.setdefault("source_id", source_id)
                table.setdefault("filename", filename)
                table.setdefault("row_numbers", list(range(1, len(table["rows"]) + 1)))
                validated = _table(table["columns"], table["rows"], table["row_numbers"],
                                   table["source_id"], table["filename"], len(tables))
                tables.append({**validated, **table})
            return tables
    lines = content.splitlines()
    tables = []
    i = 0
    while i + 1 < len(lines):
        separator = _md_cells(lines[i + 1])
        if "|" in lines[i] and len(separator) >= 1 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
            columns = _md_cells(lines[i])
            start = i
            i += 2
            rows, numbers = [], []
            while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                rows.append(_md_cells(lines[i])); numbers.append(i + 1); i += 1
            tables.append(_table(columns, rows, numbers, source_id, filename, len(tables),
                                 format="markdown", header_line=start + 1, row_number_scope="source"))
        else:
            i += 1
    if tables:
        return tables
    if "," not in content and "\t" not in content and ";" not in content:
        return []
    try:
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=",\t;")
    except csv.Error:
        if not filename.lower().endswith(".csv"):
            return []
        dialect = csv.excel
    reader = csv.reader(io.StringIO(content), dialect=dialect, strict=True)
    parsed, numbers = [], []
    try:
        previous = 0
        for row in reader:
            start = previous + 1
            previous = reader.line_num
            if row and any(cell.strip() for cell in row):
                parsed.append([cell.strip() for cell in row]); numbers.append(start)
    except csv.Error as exc:
        raise TableAnalysisError(f"CSV 解析失败: {exc}") from exc
    if len(parsed) < 2:
        return []
    return [_table(parsed[0], parsed[1:], numbers[1:], source_id, filename, 0,
                   format="csv", header_line=numbers[0], row_number_scope="source")]


_NUMBER = re.compile(r"^([+\-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[+\-]?\.\d+)(?:[eE]([+\-]?\d+))?\s*([^\d]*)$")


def _number(raw: Any) -> tuple[Decimal, str]:
    text = str(raw).strip().replace("−", "-")
    match = _NUMBER.fullmatch(text)
    if not match:
        raise TableAnalysisError(f"无法识别数值 {text!r}；空值/范围/不规范千分位不可自动猜测")
    number = Decimal(match[1].replace(",", "") + ("e" + match[2] if match[2] else ""))
    if not number.is_finite():
        raise TableAnalysisError("非有限数值不可计算")
    return number, match[3].strip()


def calculate_table(table: dict, operation: str, column: str | None = None,
                    filters: list | dict | None = None, group_by: str | None = None,
                    *, unit: str | None = None, precision: int = 40) -> dict:
    """Whitelisted operations only. difference/ratio require exactly two rows,
    in source order: first minus/divided by second. count counts filtered rows.
    Filters: {column:value} equality or [{column,op,value}], op eq/ne/gt/ge/lt/le.
    Decimal results are JSON strings, division rounded at explicit precision.
    """
    allowed = {"sum", "mean", "min", "max", "count", "difference", "ratio", "group_sum"}
    if operation not in allowed:
        raise TableAnalysisError(f"不支持操作 {operation!r}，仅允许 {sorted(allowed)}")
    if not isinstance(precision, int) or not 1 <= precision <= 200:
        raise TableAnalysisError("precision 必须为1至200的整数")
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    numbers = table.get("row_numbers", [])
    if len(numbers) != len(rows):
        raise TableAnalysisError("row_numbers 与实际行数不一致，不能生成准确引用")
    if len(set(columns)) != len(columns):
        raise TableAnalysisError("重复列名，无法唯一指定列")
    def require(name):
        if name not in columns:
            raise TableAnalysisError(f"缺少列 {name!r}；可用列: {columns}")
        return columns.index(name)
    column_index = require(column) if column is not None else None
    if operation != "count" and column_index is None:
        raise TableAnalysisError("该操作必须指定 column")
    group_index = require(group_by) if group_by is not None else None
    if operation == "group_sum" and group_index is None:
        raise TableAnalysisError("group_sum 必须指定 group_by")
    predicates = ([{"column": key, "op": "eq", "value": value} for key, value in filters.items()]
                  if isinstance(filters, dict) else filters or [])
    prepared = []
    for predicate in predicates:
        if not isinstance(predicate, dict) or "column" not in predicate or "value" not in predicate:
            raise TableAnalysisError("过滤条件需要 column, op, value")
        op = predicate.get("op", "eq")
        if op not in {"eq", "ne", "gt", "ge", "lt", "le"}:
            raise TableAnalysisError(f"不支持过滤操作 {op}")
        prepared.append((require(predicate["column"]), op, predicate["value"]))
    selected = []
    for row_index, row in enumerate(rows):
        cells = [row.get(name, "") for name in columns] if isinstance(row, dict) else row
        if len(cells) != len(columns):
            raise TableAnalysisError(f"第 {numbers[row_index]} 行列数不一致")
        keep = True
        for idx, op, value in prepared:
            left, right = str(cells[idx]).strip(), str(value).strip()
            if op in {"eq", "ne"}:
                matched = left == right if op == "eq" else left != right
            else:
                a, ua = _number(left); b, ub = _number(right)
                if ua != ub:
                    raise TableAnalysisError("过滤比较存在混合单位")
                matched = {"gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b}[op]
            keep = keep and matched
        if keep:
            selected.append((row_index, cells))
    if not selected and operation != "count":
        raise TableAnalysisError("过滤后没有可计算行")
    evidence = []
    values, units = [], set()
    for row_index, cells in selected:
        entry = {"table_id": table.get("id", ""), "source_id": table.get("source_id", ""),
                 "filename": table.get("filename", ""), "row_number": numbers[row_index],
                 "row_number_scope": table.get("row_number_scope", "source"),
                 "column": column, "raw_value": cells[column_index] if column_index is not None else None,
                 "row": dict(zip(columns, cells))}
        for key in ("page_number", "bbox", "asset_key"):
            if key in table:
                entry[key] = table[key]
        if operation != "count":
            number, suffix = _number(cells[column_index])
            units.add(suffix)
            values.append(number)
            entry["numeric_value"] = str(number)
            entry["unit"] = suffix
        evidence.append(entry)
    if len(units) > 1:
        raise TableAnalysisError(f"混合单位 {sorted(units)}，不能自动换算或合计")
    detected_unit = next(iter(units), "")
    declared = unit or (table.get("units", {}).get(column, "") if isinstance(table.get("units"), dict) else "")
    if detected_unit and declared and detected_unit != declared:
        raise TableAnalysisError(f"数值单位 {detected_unit} 与声明单位 {declared} 不一致")
    result_unit = detected_unit or declared
    with localcontext() as ctx:
        # Sum/difference use enough precision for exact finite input arithmetic.
        exact_precision = max([precision] + [len(v.as_tuple().digits) + abs(v.as_tuple().exponent) + max(0, v.adjusted()) + 10 for v in values])
        ctx.prec = exact_precision
        if operation == "count":
            result = len(selected); formula = f"count({len(selected)} source rows)"; result_unit = "rows"
        elif operation == "sum":
            result = str(sum(values, Decimal(0))); formula = " + ".join(map(str, values))
        elif operation == "mean":
            total = sum(values, Decimal(0)); ctx.prec = precision
            result = str(total / Decimal(len(values))); formula = f"({' + '.join(map(str, values))}) / {len(values)}"
        elif operation in {"min", "max"}:
            result = str(min(values) if operation == "min" else max(values)); formula = f"{operation}({', '.join(map(str, values))})"
        elif operation in {"difference", "ratio"}:
            if len(values) != 2:
                raise TableAnalysisError(f"{operation} 需要恰好两行，当前 {len(values)} 行")
            if operation == "ratio":
                if values[1] == 0:
                    raise TableAnalysisError("ratio 分母为零")
                ctx.prec = precision
                result = str(values[0] / values[1]); result_unit = ""; symbol = "/"
            else:
                result = str(values[0] - values[1]); symbol = "-"
            formula = f"{values[0]} {symbol} {values[1]}"
        else:
            grouped = {}
            for (_, cells), number in zip(selected, values):
                key = str(cells[group_index])
                grouped[key] = grouped.get(key, Decimal(0)) + number
            result = {key: str(value) for key, value in grouped.items()}
            formula = f"sum({column}) grouped by {group_by}"
    return {"result": result, "operation": operation, "column": column, "group_by": group_by,
            "unit": result_unit, "used_rows": [entry["row_number"] for entry in evidence],
            "formula": formula, "evidence": evidence, "table_id": table.get("id", ""),
            "precision": precision if operation in {"ratio", "mean"} else None,
            "evidence_modality": "table_calculation", "is_literal": False}
