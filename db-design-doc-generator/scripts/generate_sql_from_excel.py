#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Excel 设计文档反向生成全量 SQL 脚本（01-table ~ 05-index）。
"""

import os
import re
import json
import argparse
import openpyxl

HEADERS = [
    'tabname', 'namec', 'colname', 'datatype', 'disporder', 'disptype',
    'nullable', 'newedit', 'editable', 'indexname', 'indextype', 'indexcols',
    'major_minor', 'reference', '字典值', '字段说明'
]


def quote_sql(val):
    if val is None:
        return 'null'
    s = str(val)
    if s.lower() == 'nan':
        return 'null'
    return "'" + s.replace("'", "''") + "'"


def parse_reference(ref_str):
    """解析 reference 列，如 othertable(othercol) -> (othertable, othercol)"""
    m = re.match(r'^(\w+)\s*\((\w+)\)$', str(ref_str).strip())
    if m:
        return m.group(1), m.group(2)
    return None, None


def parse_dict_values(dict_str):
    """解析 字典值 列，如 0=正常; 1=停用 -> [(0, 正常), (1, 停用)]"""
    if not dict_str or str(dict_str).strip() == '':
        return []
    result = []
    for part in str(dict_str).split(';'):
        part = part.strip()
        if not part:
            continue
        if '=' in part:
            dbvalue, dispc = part.split('=', 1)
            result.append((dbvalue.strip(), dispc.strip()))
    return result


def read_excel_file(filepath):
    """读取单个 Excel 文件，返回 [sheet_rows, ...]，每个 sheet_rows 是表头+数据行的列表"""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    all_sheets = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(row)
        if len(rows) >= 2:
            all_sheets.append(rows)
    return all_sheets


def build_table_sql(tables_info):
    """
    tables_info: {
      tabname: {
        'namec': str,
        'major': str,
        'minor': str,
        'columns': [{name, datatype, nullable, comment, reference}, ...],
        'indexes': {(indexname, indextype, indexcols)},
      }
    }
    """
    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 删除表")
    lines.append("-- ============================================================")
    lines.append("")
    for tabname in tables_info:
        lines.append(f"DROP TABLE IF EXISTS {tabname};")
    lines.append("")
    lines.append("-- ============================================================")
    lines.append("-- 创建表")
    lines.append("-- ============================================================")
    lines.append("")

    for tabname, info in tables_info.items():
        namec = info['namec']
        cols = info['columns']

        lines.append(f"-- {namec}")
        lines.append(f"create table {tabname}")
        lines.append("(")

        col_lines = []
        pk_col = None
        has_explicit_id = False

        for col in cols:
            if col['name'].lower() == 'id':
                has_explicit_id = True
                pk_col = 'id'

        # 如果没有显式 id，自动添加
        if not has_explicit_id:
            col_lines.append("    id serial primary key")
            pk_col = 'id'

        fks = []
        for col in cols:
            cname = col['name']
            dtype = col['datatype']
            nullable = col['nullable']
            null_str = ' null' if nullable else ' not null'

            col_def = f"    {cname} {dtype}{null_str}"
            if cname.lower() == 'id' and pk_col == 'id':
                if 'serial' not in dtype.lower() and 'bigserial' not in dtype.lower() and 'smallserial' not in dtype.lower():
                    # 如果 id 的类型里没有 serial，但规则要求自增，保持用户指定的类型但加 primary key
                    pass
                col_def = f"    {cname} {dtype} primary key"

            col_lines.append(col_def)

            ref = col.get('reference', '')
            if ref:
                ft, fc = parse_reference(ref)
                if ft and fc:
                    fks.append((cname, ft, fc))

        for fk_col, fk_ft, fk_fc in fks:
            col_lines.append(f"    CONSTRAINT {tabname}_{fk_col}_fkey FOREIGN KEY ({fk_col}) REFERENCES {fk_ft}({fk_fc})")

        lines.append(",\n".join(col_lines))
        lines.append(");")
        lines.append("")

        # 注释
        for col in cols:
            cname = col['name']
            comment = col.get('comment', '')
            if cname.lower() == 'id' and not comment:
                comment = 'ID'
            if comment:
                lines.append(f"comment on column {tabname}.{cname} is '{comment.replace(chr(39), chr(39)+chr(39))}';")

        if not has_explicit_id:
            lines.append(f"comment on column {tabname}.id is 'ID';")

        lines.append("")
        lines.append("")
        lines.append("")

    # 视图占位
    lines.append("-- ============================================================")
    lines.append("-- 创建视图（手动维护：先建子视图，再建父视图）")
    lines.append("-- ============================================================")
    lines.append("")

    return '\n'.join(lines) + '\n'


def build_index_sql(tables_info):
    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 删除索引")
    lines.append("-- ============================================================")
    lines.append("")

    for tabname, info in tables_info.items():
        indexes = info.get('indexes', [])
        if not indexes:
            continue
        lines.append(f"-- {tabname} 表索引")
        for idx_name, idx_type, idx_cols in indexes:
            lines.append(f"DROP INDEX IF EXISTS {idx_name};")
        lines.append("")

    lines.append("-- ============================================================")
    lines.append("-- 创建索引")
    lines.append("-- ============================================================")
    lines.append("")

    for tabname, info in tables_info.items():
        indexes = info.get('indexes', [])
        if not indexes:
            continue
        lines.append(f"-- {tabname} 表索引")
        for idx_name, idx_type, idx_cols in indexes:
            unique_str = 'UNIQUE ' if idx_type == 'UNIQUE INDEX' else ''
            lines.append(f"CREATE {unique_str}INDEX {idx_name} ON {tabname} USING btree ({idx_cols});")
        lines.append("")

    return '\n'.join(lines) + '\n'


def build_cx_entity_sql(tables_info, entity_defaults):
    lines = []
    majors = sorted({int(info['major']) for info in tables_info.values()})
    for maj in majors:
        lines.append(f"delete from cx_entity where major={maj};")
    lines.append("")

    for tabname, info in tables_info.items():
        defaults = dict(entity_defaults)
        defaults['name'] = tabname
        defaults['namec'] = info['namec']
        defaults['major'] = str(info['major'])
        defaults['minor'] = str(info['minor'])

        # 构建列名和值
        cols = list(defaults.keys())
        vals = [quote_sql(defaults[c]) for c in cols]
        lines.append(f"INSERT INTO cx_entity ({', '.join(cols)}) VALUES ({', '.join(vals)});")

    return '\n'.join(lines) + '\n'


def build_cx_fld_sql(tables_info, sys_val):
    lines = []
    for tabname, info in tables_info.items():
        cols = info['columns']
        has_fld = False
        for col in cols:
            if col['name'].lower() == 'id':
                continue
            if col.get('disptype') != '' or col.get('disporder') != '' or col.get('namec'):
                has_fld = True
                break
        if not has_fld:
            continue
        if lines and lines[-1].strip() != '':
            lines.append('')
        lines.append(f"delete from cx_fld where tabname='{tabname}';")
        for col in cols:
            cname = col['name']
            if cname.lower() == 'id':
                continue
            namec = col.get('namec', '')
            disptype = col.get('disptype', '')
            if disptype == '':
                disptype = '1'
            disporder = col.get('disporder', '')
            if disporder == '':
                disporder = '0'
            newedit = col.get('newedit', '')
            if newedit == '':
                newedit = '1'
            editable = col.get('editable', '')
            if editable == '':
                editable = '1'
            nullable = col.get('nullable', '')
            if nullable == '':
                nullable = '1'
            qrylevel = col.get('qrylevel', '1')
            if qrylevel == '':
                qrylevel = '1'
            isnum = '1' if col.get('datatype', '').lower() in ('integer', 'bigint', 'smallint', 'numeric', 'decimal', 'real', 'double precision') else '0'
            memo = col.get('comment', '')

            vals = [
                quote_sql(sys_val), quote_sql(tabname), quote_sql(cname), quote_sql(namec),
                disptype, isnum, disporder, newedit, editable, nullable,
                'null', quote_sql(qrylevel), 'null', 'null', quote_sql(memo), '0', '0', '0', 'null'
            ]
            lines.append(f"INSERT INTO cx_fld (sys, tabname, colname, namec, disptype, isnum, disporder, newedit, editable, nullable, defval, qrylevel, grasyn, params, memo, bzfld, ismcard, iu, description) VALUES ({', '.join(map(str, vals))});")
    return '\n'.join(lines) + '\n'


def build_cx_fldvalue_sql(tables_info, sys_val):
    lines = []
    for tabname, info in tables_info.items():
        cols = info['columns']
        has_value = False
        for col in cols:
            if col.get('dict_values'):
                has_value = True
                break
        if not has_value:
            continue
        if lines and lines[-1].strip() != '':
            lines.append('')
            lines.append('')
        lines.append(f"delete from cx_fldvalue where tabname='{tabname}';")
        for col in cols:
            dict_vals = col.get('dict_values', [])
            if not dict_vals:
                continue
            cname = col['name']
            prev = None
            for disporder, dbvalue, dispc in dict_vals:
                if prev is not None and prev != cname:
                    lines.append('')
                prev = cname
                vals = [
                    quote_sql(sys_val), quote_sql(tabname), quote_sql(cname),
                    str(disporder), quote_sql(dbvalue), quote_sql(dispc), 'null'
                ]
                lines.append(f"INSERT INTO cx_fldvalue (sys, tabname, colname, disporder, dbvalue, dispc, disp) VALUES ({', '.join(map(str, vals))});")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description='Generate full SQL scripts from Excel design documents.')
    parser.add_argument('--input', required=True, help='Input Excel file or directory containing .xlsx files')
    parser.add_argument('--output-dir', required=True, help='Output directory for SQL scripts')
    parser.add_argument('--sys', default='0', help='Default sys value for cx_fld and cx_fldvalue')
    parser.add_argument('--entity-defaults', help='Optional JSON file with default cx_entity columns beyond name/namec/major/minor')
    args = parser.parse_args()

    input_path = args.input
    output_dir = args.output_dir
    sys_val = args.sys

    entity_defaults = {
        'type': '1',
        'domains': '1',
        'glmaj': '0',
        'glmin': '0',
        'log': '0',
    }
    if args.entity_defaults:
        with open(args.entity_defaults, 'r', encoding='utf-8') as f:
            entity_defaults.update(json.load(f))

    excel_files = []
    if os.path.isdir(input_path):
        for f in os.listdir(input_path):
            if f.lower().endswith('.xlsx'):
                excel_files.append(os.path.join(input_path, f))
    else:
        excel_files.append(input_path)

    os.makedirs(output_dir, exist_ok=True)

    tables_info = {}

    for filepath in excel_files:
        print(f"Reading {filepath} ...")
        sheets = read_excel_file(filepath)
        for rows in sheets:
            header = rows[0]
            # 定位列索引
            def idx(name):
                try:
                    return header.index(name)
                except ValueError:
                    return -1

            idx_map = {h: idx(h) for h in HEADERS}

            data_rows = rows[1:]
            if not data_rows:
                continue

            # 表信息从第一行取
            first_row = data_rows[0]
            tabname = str(first_row[idx_map['tabname']]).strip() if idx_map['tabname'] >= 0 else ''
            if not tabname:
                continue

            namec = str(first_row[idx_map['namec']]).strip() if idx_map['namec'] >= 0 else ''
            major_minor = str(first_row[idx_map['major_minor']]).strip() if idx_map['major_minor'] >= 0 else ''
            major, minor = '0', '0'
            if '@' in major_minor:
                major, minor = major_minor.split('@', 1)

            columns = []
            indexes = {}

            for r in data_rows:
                cname = str(r[idx_map['colname']]).strip() if idx_map['colname'] >= 0 else ''
                if not cname:
                    continue
                datatype = str(r[idx_map['datatype']]).strip() if idx_map['datatype'] >= 0 else ''
                nullable_raw = r[idx_map['nullable']] if idx_map['nullable'] >= 0 else ''
                try:
                    nullable = bool(int(nullable_raw))
                except (ValueError, TypeError):
                    nullable = True

                disporder = str(r[idx_map['disporder']]).strip() if idx_map['disporder'] >= 0 else ''
                disptype = str(r[idx_map['disptype']]).strip() if idx_map['disptype'] >= 0 else ''
                newedit = str(r[idx_map['newedit']]).strip() if idx_map['newedit'] >= 0 else ''
                editable = str(r[idx_map['editable']]).strip() if idx_map['editable'] >= 0 else ''
                comment = str(r[idx_map['字段说明']]).strip() if idx_map['字段说明'] >= 0 else ''
                reference = str(r[idx_map['reference']]).strip() if idx_map['reference'] >= 0 else ''
                dict_str = str(r[idx_map['字典值']]).strip() if idx_map['字典值'] >= 0 else ''

                col_namec = str(r[idx_map['namec']]).strip() if idx_map['namec'] >= 0 else ''

                columns.append({
                    'name': cname,
                    'datatype': datatype,
                    'nullable': nullable,
                    'disporder': disporder,
                    'disptype': disptype,
                    'newedit': newedit,
                    'editable': editable,
                    'comment': comment,
                    'reference': reference,
                    'namec': col_namec,
                    'dict_values': [],
                })

                # 索引
                idx_name = str(r[idx_map['indexname']]).strip() if idx_map['indexname'] >= 0 else ''
                if idx_name:
                    idx_type = str(r[idx_map['indextype']]).strip() if idx_map['indextype'] >= 0 else 'INDEX'
                    idx_cols = str(r[idx_map['indexcols']]).strip() if idx_map['indexcols'] >= 0 else cname
                    indexes[idx_name] = (idx_name, idx_type, idx_cols)

                # 字典值
                if dict_str:
                    dict_vals = parse_dict_values(dict_str)
                    for i, (dbv, dispc) in enumerate(dict_vals, 1):
                        columns[-1]['dict_values'].append((i, dbv, dispc))

            tables_info[tabname] = {
                'namec': namec,
                'major': major,
                'minor': minor,
                'columns': columns,
                'indexes': list(indexes.values()),
            }

    if not tables_info:
        print("No tables found in Excel.")
        return

    # 生成各 SQL 文件
    files_map = {}
    files_map['01-table.sql'] = build_table_sql(tables_info)
    files_map['02-cx_fld.sql'] = build_cx_fld_sql(tables_info, sys_val)
    files_map['03-cx_fldvalue.sql'] = build_cx_fldvalue_sql(tables_info, sys_val)
    files_map['04-cx_entity.sql'] = build_cx_entity_sql(tables_info, entity_defaults)
    files_map['05-index.sql'] = build_index_sql(tables_info)

    for fname, content in files_map.items():
        path = os.path.join(output_dir, fname)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Generated: {path}")

    print("Done.")


if __name__ == '__main__':
    main()
