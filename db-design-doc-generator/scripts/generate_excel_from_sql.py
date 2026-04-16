#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从全量 SQL 脚本目录解析并生成 Excel 设计文档。
"""

import os
import re
import json
import argparse
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

HEADERS = [
    'tabname', 'namec', 'colname', 'datatype', 'disporder', 'disptype',
    'nullable', 'newedit', 'editable', 'indexname', 'indextype', 'indexcols',
    'major_minor', 'reference', '字典值', '字段说明'
]


def parse_values(line):
    """解析 INSERT INTO ... VALUES (...) 语句，返回 (head, parts, tail)"""
    m = re.search(r'^(.*?VALUES\s*\()(.+?)(\)\s*;.*)$', line, re.IGNORECASE)
    if not m:
        return None
    head, content, tail = m.group(1), m.group(2), m.group(3)
    parts = []
    current = []
    in_string = False
    quote_char = None
    i = 0
    while i < len(content):
        ch = content[i]
        if not in_string and ch in ("'", '"'):
            in_string = True
            quote_char = ch
            current.append(ch)
        elif in_string and ch == quote_char:
            if i + 1 < len(content) and content[i + 1] == quote_char:
                current.append(ch)
                current.append(content[i + 1])
                i += 1
            else:
                current.append(ch)
                in_string = False
                quote_char = None
        elif not in_string and ch == ',':
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        parts.append(''.join(current).strip())
    return head, parts, tail


def extract_insert_rows(filepath, table_name):
    """从 SQL 文件中提取指定表的所有 INSERT 行数据，返回 [(cols, parts), ...]"""
    rows = []
    if not os.path.exists(filepath):
        return rows
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'^\s*INSERT\s+INTO\s+' + re.escape(table_name) + r'\s*\(([^)]+)\)\s*VALUES\s*\((.+)\)\s*;?', line, re.IGNORECASE)
            if m:
                cols = [c.strip().strip('"').strip("'") for c in m.group(1).split(',')]
                parts = parse_values('VALUES (' + m.group(2) + ');')
                if parts:
                    rows.append((cols, parts[1]))
    return rows


def parse_create_table(sql_content):
    """
    解析 01-table.sql 内容，返回 {
      tabname: {
        'columns': [{name, datatype, nullable, pk, comment, fk_reference}, ...],
        'pk_cols': [],
        'uk_cols': [],
        'fks': [(col, ft, fc)]
      }
    }
    """
    tables = {}
    comments = {}

    # 先解析所有 comment on column
    for m in re.finditer(
        r"^\s*comment\s+on\s+column\s+(\w+)\.(\w+)\s+is\s+'((?:[^']|'')*)'\s*;",
        sql_content, re.IGNORECASE | re.MULTILINE
    ):
        comments[(m.group(1).lower(), m.group(2).lower())] = m.group(3).replace("''", "'")

    # 匹配每个 CREATE TABLE 块
    for m in re.finditer(
        r'^\s*create\s+table\s+(\w+)\s*\((.*?)\);',
        sql_content, re.IGNORECASE | re.DOTALL | re.MULTILINE
    ):
        tabname = m.group(1)
        body = m.group(2)
        lines = [ln.strip() for ln in body.split('\n') if ln.strip()]

        cols = []
        pk_cols = []
        uk_cols = []
        fks = []

        for line in lines:
            line = line.rstrip(',').strip()
            if not line:
                continue

            # 约束行
            if re.match(r'^CONSTRAINT\s+', line, re.IGNORECASE):
                pk_m = re.match(r'^CONSTRAINT\s+\w+\s+PRIMARY\s+KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
                if pk_m:
                    pk_cols = [c.strip() for c in pk_m.group(1).split(',')]
                    continue
                uk_m = re.match(r'^CONSTRAINT\s+\w+\s+UNIQUE\s*\(([^)]+)\)', line, re.IGNORECASE)
                if uk_m:
                    uk_cols = [c.strip() for c in uk_m.group(1).split(',')]
                    continue
                fk_m = re.match(r'^CONSTRAINT\s+\w+\s+FOREIGN\s+KEY\s*\((\w+)\)\s+REFERENCES\s+(\w+)\s*\((\w+)\)', line, re.IGNORECASE)
                if fk_m:
                    fks.append((fk_m.group(1), fk_m.group(2), fk_m.group(3)))
                    continue
                continue

            # 字段定义行
            # 格式: name type [null|not null] [primary key]
            fm = re.match(r'^(\w+)\s+(.+)$', line, re.IGNORECASE)
            if not fm:
                continue
            colname = fm.group(1)
            rest = fm.group(2).strip()

            nullable = True
            if re.search(r'\bnot\s+null\b', rest, re.IGNORECASE):
                nullable = False
                rest = re.sub(r'\bnot\s+null\b', '', rest, flags=re.IGNORECASE).strip()
            elif re.search(r'\bnull\b', rest, re.IGNORECASE):
                nullable = True
                rest = re.sub(r'\bnull\b', '', rest, flags=re.IGNORECASE).strip()

            pk = False
            if re.search(r'\bprimary\s+key\b', rest, re.IGNORECASE):
                pk = True
                rest = re.sub(r'\bprimary\s+key\b', '', rest, flags=re.IGNORECASE).strip()
                if not pk_cols:
                    pk_cols = [colname]

            # 去掉末尾逗号（再处理一次）
            rest = rest.rstrip(',').strip()
            datatype = rest

            comment = comments.get((tabname.lower(), colname.lower()), '')

            fk_ref = ''
            for fc, ft, fcol in fks:
                if fc.lower() == colname.lower():
                    fk_ref = f"{ft}({fcol})"
                    break

            cols.append({
                'name': colname,
                'datatype': datatype,
                'nullable': nullable,
                'pk': pk,
                'comment': comment,
                'fk_reference': fk_ref,
            })

        tables[tabname] = {
            'columns': cols,
            'pk_cols': pk_cols,
            'uk_cols': uk_cols,
            'fks': fks,
        }

    return tables


def parse_index_sql(sql_content):
    """
    解析 05-index.sql，返回 {
      tabname: [(indexname, indextype, indexcols), ...]
    }
    """
    index_map = {}
    for m in re.finditer(
        r'^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+(\w+)\s+USING\s+\w+\s*\(([^)]+)\)\s*;',
        sql_content, re.IGNORECASE | re.MULTILINE
    ):
        is_unique = m.group(1) is not None
        idx_name = m.group(2)
        tabname = m.group(3)
        idx_cols = m.group(4)
        indextype = 'UNIQUE INDEX' if is_unique else 'INDEX'
        index_map.setdefault(tabname, []).append((idx_name, indextype, idx_cols))
    return index_map


def parse_cx_entity(filepath):
    """解析 04-cx_entity.sql，返回 {tabname: (namec, major, minor)}"""
    entity_map = {}
    rows = extract_insert_rows(filepath, 'cx_entity')
    for cols, parts in rows:
        if len(cols) != len(parts):
            continue
        mapping = dict(zip(cols, parts))
        tabname = mapping.get('name', '').strip("'")
        namec = mapping.get('namec', '').strip("'")
        major = mapping.get('major', '').strip("'")
        minor = mapping.get('minor', '').strip("'")
        if tabname:
            entity_map[tabname] = (namec, major, minor)
    return entity_map


def parse_cx_fld(filepath):
    """解析 02-cx_fld.sql，返回 {(tabname, colname): {namec, disptype, disporder, newedit, editable, nullable, memo}}"""
    fld_map = {}
    rows = extract_insert_rows(filepath, 'cx_fld')
    for cols, parts in rows:
        if len(cols) != len(parts):
            continue
        mapping = dict(zip(cols, parts))
        tabname = mapping.get('tabname', '').strip("'")
        colname = mapping.get('colname', '').strip("'")
        namec = mapping.get('namec', '').strip("'")
        disptype = mapping.get('disptype', '')
        disporder = mapping.get('disporder', '')
        newedit = mapping.get('newedit', '')
        editable = mapping.get('editable', '')
        nullable = mapping.get('nullable', '')
        memo = mapping.get('memo', '')
        fld_map[(tabname.lower(), colname.lower())] = {
            'namec': namec,
            'disptype': disptype,
            'disporder': disporder,
            'newedit': newedit,
            'editable': editable,
            'nullable': nullable,
            'memo': memo.strip("'") if memo and memo not in ('null', 'NULL') else '',
        }
    return fld_map


def parse_cx_fldvalue(filepath):
    """解析 03-cx_fldvalue.sql，返回 {(tabname, colname): [(dbvalue, dispc), ...]}"""
    dict_map = {}
    rows = extract_insert_rows(filepath, 'cx_fldvalue')
    for cols, parts in rows:
        if len(cols) != len(parts):
            continue
        mapping = dict(zip(cols, parts))
        tabname = mapping.get('tabname', '').strip("'")
        colname = mapping.get('colname', '').strip("'")
        dbvalue = mapping.get('dbvalue', '').strip("'")
        dispc = mapping.get('dispc', '').strip("'")
        dict_map.setdefault((tabname.lower(), colname.lower()), []).append((dbvalue, dispc))
    return dict_map


def get_memo(fld_info):
    memo = fld_info.get('memo', '')
    return memo if memo else ''


def main():
    parser = argparse.ArgumentParser(description='Generate Excel design documents from full SQL scripts.')
    parser.add_argument('--input-dir', required=True, help='Directory containing 01-table.sql ~ 05-index.sql')
    parser.add_argument('--output-dir', required=True, help='Output directory for Excel files')
    parser.add_argument('--major-map', help='Optional JSON file mapping major numbers to filenames')
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir

    major_to_file = {}
    if args.major_map:
        with open(args.major_map, 'r', encoding='utf-8') as f:
            major_to_file = {int(k): v for k, v in json.load(f).items()}

    table_sql_path = os.path.join(input_dir, '01-table.sql')
    fld_sql_path = os.path.join(input_dir, '02-cx_fld.sql')
    fldvalue_sql_path = os.path.join(input_dir, '03-cx_fldvalue.sql')
    entity_sql_path = os.path.join(input_dir, '04-cx_entity.sql')
    index_sql_path = os.path.join(input_dir, '05-index.sql')

    with open(table_sql_path, 'r', encoding='utf-8') as f:
        table_content = f.read()
    tables = parse_create_table(table_content)

    index_map = {}
    if os.path.exists(index_sql_path):
        with open(index_sql_path, 'r', encoding='utf-8') as f:
            index_map = parse_index_sql(f.read())

    entity_map = parse_cx_entity(entity_sql_path) if os.path.exists(entity_sql_path) else {}
    fld_map = parse_cx_fld(fld_sql_path) if os.path.exists(fld_sql_path) else {}
    dict_map = parse_cx_fldvalue(fldvalue_sql_path) if os.path.exists(fldvalue_sql_path) else {}

    # 按 major 分组
    tables_by_major = {}
    for tabname in tables:
        _, major, minor = entity_map.get(tabname, ('', 0, 0))
        try:
            major = int(major)
        except (ValueError, TypeError):
            major = 0
        tables_by_major.setdefault(major, []).append(tabname)
        if major not in major_to_file:
            major_to_file[major] = str(major)

    # 构建字段到索引的映射（每个字段只取第一个索引）
    col_index_map = {}
    for tablename, idx_list in index_map.items():
        assigned_cols = set()
        for idx_name, idx_type, idx_cols in idx_list:
            cols = [c.strip() for c in idx_cols.split(',')]
            for c in cols:
                if c not in assigned_cols:
                    col_index_map[(tablename, c)] = (idx_name, idx_type, idx_cols)
                    assigned_cols.add(c)
                    break

    header_fill = PatternFill(start_color='FFC000', end_color='FFC000', fill_type='solid')
    header_font = Font(bold=True)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    os.makedirs(output_dir, exist_ok=True)

    for major, filename_base in sorted(major_to_file.items()):
        table_list = tables_by_major.get(major, [])
        if not table_list:
            print(f"Skipping {filename_base} (no tables)")
            continue

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        for tabname in table_list:
            namec, maj, minor = entity_map.get(tabname, (tabname, major, 0))
            major_minor = f"{maj}@{minor}"

            base_sheet_name = (namec or tabname)[:31]
            sheet_name = base_sheet_name
            suffix = 1
            while sheet_name in wb.sheetnames:
                suffix_str = f"({suffix})"
                sheet_name = base_sheet_name[:31 - len(suffix_str)] + suffix_str
                suffix += 1
            ws = wb.create_sheet(title=sheet_name)

            for col_idx, h in enumerate(HEADERS, 1):
                cell = ws.cell(row=1, column=col_idx, value=h)
                cell.fill = header_fill
                cell.font = header_font
                cell.border = thin_border
                cell.alignment = Alignment(horizontal='center', vertical='center')

            cols_data = tables[tabname]['columns']
            for row_idx, col in enumerate(cols_data, 2):
                colname = col['name']
                datatype = col['datatype']
                lookup_key = (tabname.lower(), colname.lower())

                if lookup_key in fld_map:
                    f = fld_map[lookup_key]
                    f_namec = f['namec']
                    f_disptype = f['disptype']
                    f_disporder = f['disporder']
                    f_newedit = f['newedit']
                    f_editable = f['editable']
                    f_nullable = f['nullable']
                    f_memo = f['memo']
                else:
                    f_namec, f_disptype, f_disporder = '', '', ''
                    f_newedit, f_editable, f_nullable = '', '', ''
                    f_memo = ''

                if colname.lower() == 'id':
                    if not f_namec:
                        f_namec = 'ID'
                    f_disporder = 0
                    f_disptype = 1
                    f_nullable = 0
                    f_newedit = 0
                    f_editable = 0

                if f_nullable == '' or f_nullable is None:
                    nullable_val = 0 if not col['nullable'] else 1
                else:
                    try:
                        nullable_val = int(f_nullable)
                    except (ValueError, TypeError):
                        nullable_val = 0 if not col['nullable'] else 1

                idx_info = col_index_map.get((tabname, colname))
                if idx_info:
                    idx_name, idx_type, idx_cols = idx_info
                else:
                    idx_name, idx_type, idx_cols = '', '', ''

                reference = col['fk_reference']
                dict_vals = dict_map.get(lookup_key, [])
                dict_str = '; '.join([f"{db}={disp}" for db, disp in dict_vals])
                memo_str = get_memo({'memo': f_memo})
                if not memo_str:
                    memo_str = col.get('comment', '')

                values = [
                    tabname, f_namec or '', colname, datatype,
                    f_disporder if f_disporder != '' else '',
                    f_disptype if f_disptype != '' else '',
                    nullable_val,
                    f_newedit if f_newedit != '' else '',
                    f_editable if f_editable != '' else '',
                    idx_name, idx_type, idx_cols, major_minor,
                    reference, dict_str, memo_str,
                ]

                for col_idx, val in enumerate(values, 1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    cell.border = thin_border

            for col in ws.columns:
                max_length = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws.column_dimensions[col_letter].width = adjusted_width

        filepath = os.path.join(output_dir, f"{filename_base}.xlsx")
        wb.save(filepath)
        print(f"Saved: {filepath} ({len(table_list)} sheets)")

    print("Done.")


if __name__ == '__main__':
    main()
