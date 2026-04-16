#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地数据库脚本同步工具

功能：根据 JSON 变更配置，同步更新全量脚本（01-table / 02-cx_fld / 03-cx_fldvalue / 04-cx_entity）
      并在指定增量脚本末尾追加变更块。全程不连接数据库。

用法：
    python scripts/update_db_scripts.py --config changes.json
"""

import argparse
import json
import os
import re
from datetime import datetime

# -----------------------------------------------------------
# 常量
# -----------------------------------------------------------
DEFAULT_FLD_TEMPLATE = (
    "INSERT INTO cx_fld (sys, tabname, colname, namec, disptype, isnum, disporder, "
    "newedit, editable, nullable, defval, qrylevel, grasyn, params, memo, bzfld, ismcard, iu, description) "
    "VALUES ('{sys}', '{tabname}', '{colname}', '{namec}', {disptype}, {isnum}, {disporder}, "
    "{newedit}, {editable}, {nullable}, null, {qrylevel}, null, null, null, 0, 0, 0, null);"
)

DEFAULT_FLDVALUE_TEMPLATE = (
    "INSERT INTO cx_fldvalue (sys, tabname, colname, disporder, dbvalue, dispc, disp) "
    "VALUES ('{sys}', '{tabname}', '{colname}', {disporder}, '{dbvalue}', '{dispc}', null);"
)

DEFAULT_ENTITY_TEMPLATE = (
    "INSERT INTO cx_entity (name, namec, type, major, minor, domains, glmaj, glmin, log) "
    "VALUES ('{name}', '{namec}', '{type}', '{major}', '{minor}', '{domains}', '{glmaj}', '{glmin}', '{log}');"
)

# -----------------------------------------------------------
# 工具函数
# -----------------------------------------------------------
def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

# -----------------------------------------------------------
# 01-table.sql 处理
# -----------------------------------------------------------
def modify_table_sql(content, changes):
    lines = content.splitlines()
    result = list(lines)

    for ch in changes:
        action = ch['action']
        table = ch['table']

        if action == 'create_table':
            result = _table_create_table(result, table, ch.get('columns', []))
        elif action == 'add_columns':
            result = _table_add_columns(result, table, ch['columns'])
        elif action == 'drop_columns':
            result = _table_drop_columns(result, table, ch['columns'])

    return '\n'.join(result)

def _find_table_block(lines, table):
    """返回 (start_idx, end_idx, base_indent)"""
    start_idx = None
    for i, line in enumerate(lines):
        if re.match(rf'^\s*create\s+table\s+{re.escape(table)}\s*\(', line, re.IGNORECASE):
            start_idx = i
            break
    if start_idx is None:
        raise ValueError(f"在 01-table.sql 中未找到表 {table}")

    # 找到匹配的 );
    end_idx = None
    paren_depth = 0
    for i in range(start_idx, len(lines)):
        line = lines[i]
        paren_depth += line.count('(') - line.count(')')
        if paren_depth == 0 and ');' in line:
            end_idx = i
            break
    if end_idx is None:
        raise ValueError(f"表 {table} 的 CREATE TABLE 语句未正确闭合")

    # 计算基础缩进
    base_indent = '    '  # 默认4空格
    for i in range(start_idx + 1, end_idx):
        m = re.match(r'^(\s+)', lines[i])
        if m:
            base_indent = m.group(1)
            break

    return start_idx, end_idx, base_indent

def _table_create_table(lines, table, columns):
    """在 01-table.sql 末尾追加新的 CREATE TABLE"""
    indent = '    '
    col_lines = []
    comment_lines = []
    for col in columns:
        name = col['name']
        definition = col['definition']
        comment = col.get('comment', '')
        col_lines.append(f"{indent}{name:<8} {definition}")
        if comment:
            comment_lines.append(f"comment on column {table}.{name} is '{comment}';")

    # 最后一行不加逗号
    if col_lines:
        col_lines[-1] = col_lines[-1].rstrip().rstrip(',')

    block_lines = [
        "",
        f"-- {table}",
        f"create table {table}",
        "(",
    ]
    block_lines.extend(col_lines)
    block_lines.append(");")
    if comment_lines:
        block_lines.append("")
        block_lines.extend(comment_lines)
    block_lines.append("")
    block_lines.append("")
    block_lines.append("")

    return lines + block_lines

def _table_add_columns(lines, table, columns):
    start_idx, end_idx, indent = _find_table_block(lines, table)

    insert_pos = end_idx  # 在 ); 所在行之前插入
    comment_insert_pos = end_idx + 1

    # 找到该表最后一个 comment on column 之后的位置
    for i in range(end_idx + 1, len(lines)):
        if re.match(rf"^\s*comment\s+on\s+column\s+{re.escape(table)}\.", lines[i], re.IGNORECASE):
            comment_insert_pos = i + 1
        else:
            # 一旦遇到非 comment 行且非空行，就停止
            stripped = lines[i].strip()
            if stripped and not stripped.startswith('--'):
                if not re.match(rf"^\s*comment\s+on\s+column\s+{re.escape(table)}\.", stripped, re.IGNORECASE):
                    break

    new_lines = []
    new_comments = []
    for col in columns:
        name = col['name']
        definition = col['definition']
        comment = col.get('comment', '')
        # 字段行（注意逗号：如果是插入到最后一行之前，需要给前一行加逗号）
        new_lines.append(f"{indent}{name:<8} {definition}")
        if comment:
            new_comments.append(f"comment on column {table}.{name} is '{comment}';")

    # 处理逗号
    # 在 end_idx 前一行（即最后一个字段行）末尾如果没有逗号，要加上
    prev_line = lines[insert_pos - 1]
    if not prev_line.rstrip().endswith(','):
        lines[insert_pos - 1] = prev_line.rstrip() + ','

    # 在新字段最后一行不加逗号（因为后面是 );）
    if new_lines:
        new_lines[-1] = new_lines[-1].rstrip().rstrip(',')

    # 插入字段
    lines = lines[:insert_pos] + new_lines + lines[insert_pos:]
    comment_insert_pos += len(new_lines)

    # 插入注释
    if new_comments:
        lines = lines[:comment_insert_pos] + new_comments + lines[comment_insert_pos:]

    return lines

def _table_drop_columns(lines, table, columns):
    start_idx, end_idx, indent = _find_table_block(lines, table)

    drop_set = set(columns)

    # 先删除字段行和注释行
    new_lines = []
    for i, line in enumerate(lines):
        # 删除 comment on column
        if re.match(rf"^\s*comment\s+on\s+column\s+{re.escape(table)}\.", line, re.IGNORECASE):
            col_match = re.search(rf"{re.escape(table)}\.(\w+)", line, re.IGNORECASE)
            if col_match and col_match.group(1) in drop_set:
                continue

        # 删除字段定义行
        if start_idx < i < end_idx:
            m = re.match(rf'^{re.escape(indent)}(\w+)\s+', line)
            if m and m.group(1) in drop_set:
                continue

        new_lines.append(line)

    # 修复最后一个字段末尾的逗号：找到新的 end_idx 位置，检查前一行
    new_start, new_end, _ = _find_table_block(new_lines, table)
    if new_start is not None and new_end is not None and new_end > new_start + 1:
        last_field_line = new_lines[new_end - 1]
        # 如果最后一行字段以逗号结尾，去掉它
        if last_field_line.rstrip().endswith(','):
            new_lines[new_end - 1] = last_field_line.rstrip()[:-1]

    return new_lines

# -----------------------------------------------------------
# 04-cx_entity.sql 处理
# -----------------------------------------------------------
def modify_entity_sql(content, changes):
    lines = content.splitlines()
    added_majors = set()
    for ch in changes:
        if ch['action'] == 'create_table':
            tabname = ch['table']
            major = str(ch.get('major', '0'))
            added_majors.add(major)
            namec = ch.get('namec', tabname)
            minor = str(ch.get('minor', '1'))
            defaults = {
                'name': tabname,
                'namec': namec,
                'type': ch.get('type', '1'),
                'major': major,
                'minor': minor,
                'domains': ch.get('domains', '1'),
                'glmaj': ch.get('glmaj', '0'),
                'glmin': ch.get('glmin', '0'),
                'log': ch.get('log', '0'),
            }
            insert_line = DEFAULT_ENTITY_TEMPLATE.format(**defaults)
            lines.append(insert_line)
    if added_majors:
        # 确保每个新增的 major 前面都有 delete 语句
        # 简单处理：如果 delete 不存在，在文件开头补
        for major in sorted(added_majors):
            found = any(re.match(rf"^\s*delete\s+from\s+cx_entity\s+where\s+major\s*=\s*{re.escape(major)}", ln, re.IGNORECASE) for ln in lines)
            if not found:
                lines.insert(0, f"delete from cx_entity where major={major};")
    return '\n'.join(lines)

# -----------------------------------------------------------
# 02-cx_fld.sql / 03-cx_fldvalue.sql 处理
# -----------------------------------------------------------
def modify_config_sql(content, table_name, config_type, changes_list):
    """
    config_type: 'fld' 或 'fldvalue'
    changes_list: [{'action':'add_fld', 'flds':[...]}, {'action':'remove_fld', 'columns':[...]}]
    """
    lines = content.splitlines()
    delete_line_idx = None
    for i, line in enumerate(lines):
        if re.match(rf"^\s*delete\s+from\s+cx_{config_type}\s+where\s+tabname\s*=\s*['\"]?{re.escape(table_name)}['\"]?", line, re.IGNORECASE):
            delete_line_idx = i
            break

    if delete_line_idx is None:
        # 如果找不到该表的配置块，且是添加操作，则在文件末尾新建一个块
        if any(c['action'].startswith('add_') for c in changes_list):
            block = [f"delete from cx_{config_type} where tabname='{table_name}';"]
            for ch in changes_list:
                if ch['action'] == f'add_{config_type}':
                    block.extend(_generate_config_inserts(config_type, ch))
            content += '\n' + '\n'.join(block) + '\n'
        return content

    # 找到该配置块的结束位置（下一个 delete 语句或文件末尾）
    block_end = len(lines)
    for i in range(delete_line_idx + 1, len(lines)):
        if re.match(rf"^\s*delete\s+from\s+cx_", lines[i], re.IGNORECASE):
            block_end = i
            break

    # 收集该块内已有的 INSERT 行
    insert_lines = lines[delete_line_idx + 1:block_end]

    for ch in changes_list:
        action = ch['action']
        if action == f'remove_{config_type}':
            cols = set(ch.get('columns', []))
            insert_lines = [
                ln for ln in insert_lines
                if not _line_contains_colname(ln, table_name, cols, config_type)
            ]
        elif action == f'add_{config_type}':
            insert_lines.extend(_generate_config_inserts(config_type, ch))

    new_block = lines[:delete_line_idx + 1] + insert_lines + lines[block_end:]
    return '\n'.join(new_block)

def _line_contains_colname(line, tabname, colset, config_type):
    """判断 INSERT 行是否包含指定表的指定字段"""
    if config_type == 'fld':
        # INSERT INTO cx_fld ... VALUES ('sys', 'tabname', 'colname', ...)
        m = re.search(r"VALUES\s*\([^)]*['\"]" + re.escape(tabname) + r"['\"]\s*,\s*['\"](\w+)['\"]", line)
        if m and m.group(1) in colset:
            return True
    elif config_type == 'fldvalue':
        # INSERT INTO cx_fldvalue ... VALUES ('sys', 'tabname', 'colname', ...)
        m = re.search(r"VALUES\s*\([^)]*['\"]" + re.escape(tabname) + r"['\"]\s*,\s*['\"](\w+)['\"]", line)
        if m and m.group(1) in colset:
            return True
    return False

def _generate_config_inserts(config_type, change):
    lines = []
    table = change['table']
    sys = change.get('sys', '0')

    if config_type == 'fld':
        for fld in change.get('flds', []):
            defaults = {
                'sys': sys, 'tabname': table, 'colname': fld['colname'],
                'namec': fld.get('namec', fld['colname']),
                'disptype': fld.get('disptype', 1),
                'isnum': fld.get('isnum', 0),
                'disporder': fld.get('disporder', 0),
                'newedit': fld.get('newedit', 1),
                'editable': fld.get('editable', 1),
                'nullable': fld.get('nullable', 1),
                'qrylevel': fld.get('qrylevel', 1),
            }
            lines.append(DEFAULT_FLD_TEMPLATE.format(**defaults))
    elif config_type == 'fldvalue':
        for val in change.get('values', []):
            colname = val['colname']
            for item in val.get('items', []):
                defaults = {
                    'sys': sys, 'tabname': table, 'colname': colname,
                    'disporder': item.get('disporder', 1),
                    'dbvalue': item['dbvalue'],
                    'dispc': item['dispc'],
                }
                lines.append(DEFAULT_FLDVALUE_TEMPLATE.format(**defaults))
    return lines

# -----------------------------------------------------------
# 增量脚本生成
# -----------------------------------------------------------
def generate_upgrade_block(changes, author=None, comment=None):
    lines = []
    today = datetime.now().strftime('%Y-%m-%d')
    lines.append(f"\n-- {today}")
    if comment:
        lines.append(f"-- {comment}")
    if author:
        lines.append(f"-- {author}")
    lines.append("")

    for ch in changes:
        action = ch['action']
        table = ch['table']

        if action == 'create_table':
            lines.append(f"-- 创建 {table}")
            col_defs = []
            comment_lines = []
            for col in ch.get('columns', []):
                col_defs.append(f"    {col['name']} {col['definition']}")
                if col.get('comment'):
                    comment_lines.append(f"comment on column {table}.{col['name']} is '{col['comment']}';")
            if col_defs:
                col_defs[-1] = col_defs[-1].rstrip().rstrip(',')
            lines.append(f"CREATE TABLE {table} (")
            lines.append(",\n".join(col_defs))
            lines.append(");")
            if comment_lines:
                lines.extend(comment_lines)
            lines.append("")

        elif action == 'drop_columns':
            cols = ch['columns']
            lines.append(f"-- 删除 {table} 的字段")
            for c in cols:
                lines.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {c};")
            lines.append("")

        elif action == 'add_columns':
            lines.append(f"-- 在 {table} 上增加字段")
            for col in ch['columns']:
                lines.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col['name']} {col['definition']};")
                if col.get('comment'):
                    lines.append(f"comment on column {table}.{col['name']} is '{col['comment']}';")
            lines.append("")

        elif action == 'remove_fld':
            cols = ch['columns']
            cols_str = "','".join(cols)
            lines.append(f"delete from cx_fld where tabname = '{table}' and colname in ('{cols_str}');")
            lines.append("")

        elif action == 'add_fld':
            cols = [f['colname'] for f in ch.get('flds', [])]
            cols_str = "','".join(cols)
            lines.append(f"delete from cx_fld where tabname = '{table}' and colname in ('{cols_str}');")
            for ln in _generate_config_inserts('fld', ch):
                lines.append(ln)
            lines.append("")

        elif action == 'remove_fldvalue':
            cols = ch['columns']
            cols_str = "','".join(cols)
            lines.append(f"delete from cx_fldvalue where tabname = '{table}' and colname in ('{cols_str}');")
            lines.append("")

        elif action == 'add_fldvalue':
            cols = [v['colname'] for v in ch.get('values', [])]
            cols_str = "','".join(cols)
            lines.append(f"delete from cx_fldvalue where tabname = '{table}' and colname in ('{cols_str}');")
            for ln in _generate_config_inserts('fldvalue', ch):
                lines.append(ln)
            lines.append("")

    return '\n'.join(lines)

# -----------------------------------------------------------
# 主流程
# -----------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='同步更新数据库全量脚本与增量脚本')
    parser.add_argument('--config', '-c', required=True, help='JSON 配置文件路径')
    args = parser.parse_args()

    with open(args.config, 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    project_root = cfg.get('project_root', '.')
    system = cfg['system']
    target_upgrade = cfg.get('target_upgrade', '02-Upgrade/update2026.sql')
    author = cfg.get('author', '')
    comment = cfg.get('comment', '')
    changes = cfg['changes']

    app_dir = os.path.join(project_root, '01-Application', system)
    table_sql_path = os.path.join(app_dir, '01-table.sql')
    fld_sql_path = os.path.join(app_dir, '02-cx_fld.sql')
    fldvalue_sql_path = os.path.join(app_dir, '03-cx_fldvalue.sql')
    entity_sql_path = os.path.join(app_dir, '04-cx_entity.sql')
    upgrade_path = os.path.join(project_root, target_upgrade)

    # 1. 处理 01-table.sql
    if os.path.exists(table_sql_path):
        content = read_file(table_sql_path)
        content = modify_table_sql(content, changes)
        write_file(table_sql_path, content)
        print(f"[OK] 已更新 {table_sql_path}")
    else:
        # 如果文件不存在且包含 create_table，直接新建
        if any(ch['action'] == 'create_table' for ch in changes):
            content = ""
            content = modify_table_sql(content, changes)
            ensure_dir(os.path.dirname(table_sql_path))
            write_file(table_sql_path, content)
            print(f"[OK] 已新建 {table_sql_path}")
        else:
            print(f"[WARN] 未找到 {table_sql_path}")

    # 2. 处理 02-cx_fld.sql
    if os.path.exists(fld_sql_path):
        content = read_file(fld_sql_path)
        fld_changes_by_table = {}
        for ch in changes:
            if ch['action'] in ('add_fld', 'remove_fld'):
                fld_changes_by_table.setdefault(ch['table'], []).append(ch)
        for table, chlist in fld_changes_by_table.items():
            content = modify_config_sql(content, table, 'fld', chlist)
        write_file(fld_sql_path, content)
        print(f"[OK] 已更新 {fld_sql_path}")
    else:
        print(f"[WARN] 未找到 {fld_sql_path}")

    # 3. 处理 03-cx_fldvalue.sql
    if os.path.exists(fldvalue_sql_path):
        content = read_file(fldvalue_sql_path)
        fldvalue_changes_by_table = {}
        for ch in changes:
            if ch['action'] in ('add_fldvalue', 'remove_fldvalue'):
                fldvalue_changes_by_table.setdefault(ch['table'], []).append(ch)
        for table, chlist in fldvalue_changes_by_table.items():
            content = modify_config_sql(content, table, 'fldvalue', chlist)
        write_file(fldvalue_sql_path, content)
        print(f"[OK] 已更新 {fldvalue_sql_path}")
    else:
        print(f"[WARN] 未找到 {fldvalue_sql_path}")

    # 4. 处理 04-cx_entity.sql（create_table 时追加）
    if any(ch['action'] == 'create_table' for ch in changes):
        if os.path.exists(entity_sql_path):
            content = read_file(entity_sql_path)
        else:
            content = ""
        content = modify_entity_sql(content, changes)
        ensure_dir(os.path.dirname(entity_sql_path))
        write_file(entity_sql_path, content)
        print(f"[OK] 已更新 {entity_sql_path}")

    # 5. 追加增量脚本
    ensure_dir(os.path.dirname(upgrade_path))
    upgrade_block = generate_upgrade_block(changes, author, comment)
    with open(upgrade_path, 'a', encoding='utf-8') as f:
        f.write(upgrade_block)
    print(f"[OK] 已追加增量脚本到 {upgrade_path}")

if __name__ == '__main__':
    main()
