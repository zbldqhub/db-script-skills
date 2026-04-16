import psycopg2
import os
import json
import argparse
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def quote_sql(val):
    if val is None:
        return 'null'
    s = str(val)
    if s.lower() == 'nan':
        return 'null'
    return "'" + s.replace("'", "''") + "'"

def get_columns(cursor, table_name):
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position", (table_name,))
    return [r[0] for r in cursor.fetchall()]

def build_fld_insert(fld_cols, fld_data, sys_val):
    vals = []
    for c in fld_cols:
        if c == 'sys':
            vals.append(quote_sql(sys_val))
        elif c == 'id':
            vals.append('null')
        else:
            vals.append(quote_sql(fld_data.get(c)))
    return f"INSERT INTO cx_fld ({', '.join(fld_cols)}) VALUES ({', '.join(vals)});"

def build_fldvalue_insert(fldvalue_cols, fv_data, sys_val):
    vals = []
    for c in fldvalue_cols:
        if c == 'sys':
            vals.append(quote_sql(sys_val))
        elif c == 'id':
            vals.append('null')
        else:
            vals.append(quote_sql(fv_data.get(c)))
    return f"INSERT INTO cx_fldvalue ({', '.join(fldvalue_cols)}) VALUES ({', '.join(vals)});"

def main():
    parser = argparse.ArgumentParser(description='Generate delta SQL script per V1.2 spec (YYYYMMDD.sql).')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--project-root', required=True, help='Project root directory')
    parser.add_argument('--author', required=True)
    parser.add_argument('--changes', required=True, help='JSON file describing changes')
    parser.add_argument('--date', help='Date for script name (YYYYMMDD). Default is today.')
    parser.add_argument('--schema', default='zgis')
    args = parser.parse_args()

    with open(args.changes, 'r', encoding='utf-8-sig') as f:
        changes = json.load(f)

    date_str = args.date or datetime.now().strftime('%Y%m%d')
    db_root = args.project_root
    upgrade_dir = os.path.join(db_root, '03-Upgrade')
    os.makedirs(upgrade_dir, exist_ok=True)

    delta_path = os.path.join(upgrade_dir, f'{date_str}.sql')
    is_new_file = not os.path.exists(delta_path)

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()

    fld_cols = get_columns(cursor, 'cx_fld')
    fldvalue_cols = get_columns(cursor, 'cx_fldvalue')

    sections = []

    # DDL changes
    ddl_lines = []
    for ch in changes:
        action = ch['action']
        tabname = ch['table']
        if action == 'create_table':
            cols = ch.get('columns', [])
            pk = ch.get('pk', [])
            col_defs = []
            for c in cols:
                ctype = c['type']
                nullable = c.get('nullable', True)
                null_str = '' if nullable else ' NOT NULL'
                col_def = f"    {c['name']} {ctype}{null_str}"
                # 铁律：id 单主键时直接在字段定义上加 primary key
                if c['name'].lower() == 'id' and pk == ['id']:
                    col_def += ' primary key'
                col_defs.append(col_def)
            if pk and pk != ['id']:
                col_defs.append(f"    CONSTRAINT {tabname}_pkey PRIMARY KEY ({', '.join(pk)})")
            ddl_lines.append(f"CREATE TABLE IF NOT EXISTS {tabname} (")
            ddl_lines.append(",\n".join(col_defs))
            ddl_lines.append(");")
            for c in cols:
                comment = c.get('comment', c['name'])
                if c['name'].lower() == 'id':
                    comment = 'ID'
                ddl_lines.append(f"COMMENT ON COLUMN {tabname}.{c['name']} IS '{comment.replace(chr(39), chr(39)+chr(39))}';")
        elif action == 'add_column':
            col = ch['column']
            ctype = ch['type']
            nullable = ch.get('nullable', True)
            null_str = '' if nullable else ' NOT NULL'
            ddl_lines.append(f"ALTER TABLE {tabname} ADD COLUMN IF NOT EXISTS {col} {ctype}{null_str};")
        elif action == 'drop_column':
            col = ch['column']
            ddl_lines.append(f"ALTER TABLE {tabname} DROP COLUMN IF EXISTS {col};")
        elif action == 'alter_type':
            col = ch['column']
            new_type = ch['new_type']
            ddl_lines.append(f"ALTER TABLE {tabname} ALTER COLUMN {col} TYPE {new_type};")
        elif action == 'add_index':
            idx_name = ch['index_name']
            idx_def = ch['index_def']
            ddl_lines.append(f"DROP INDEX IF EXISTS {idx_name};")
            ddl_lines.append(f"{idx_def};")
        elif action == 'drop_index':
            idx_name = ch['index_name']
            ddl_lines.append(f"DROP INDEX IF EXISTS {idx_name};")

    if ddl_lines:
        sections.append({
            'author': args.author,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'purpose': 'DDL 变更',
            'lines': ddl_lines
        })

    # Config changes grouped by table
    cfg_tables = {}
    for ch in changes:
        action = ch['action']
        tabname = ch['table']
        if action not in ('add_fld', 'drop_fld', 'add_fldvalue', 'drop_fldvalue'):
            continue
        cfg_tables.setdefault(tabname, []).append(ch)

    for tabname, chgs in cfg_tables.items():
        cfg_lines = []
        purpose_parts = []
        for ch in chgs:
            action = ch['action']
            if action == 'add_fld':
                colname = ch['fld'].get('colname')
                if str(colname).lower() == 'id':
                    print(f"[FORBIDDEN] Skipped adding id to cx_fld: {tabname}.{colname}")
                    continue
                sys_val = ch.get('sys', '0')
                cfg_lines.append(f"DELETE FROM cx_fld WHERE tabname = '{tabname}' AND colname = '{colname}';")
                cfg_lines.append(build_fld_insert(fld_cols, ch['fld'], sys_val))
                purpose_parts.append(f"增加/更新字段配置 {colname}")
            elif action == 'drop_fld':
                colname = ch['column']
                cfg_lines.append(f"DELETE FROM cx_fld WHERE tabname = '{tabname}' AND colname = '{colname}';")
                purpose_parts.append(f"删除字段配置 {colname}")
            elif action == 'add_fldvalue':
                colname = ch['column']
                values = ch.get('values', [])
                sys_val = ch.get('sys', '0')
                cfg_lines.append(f"DELETE FROM cx_fldvalue WHERE tabname = '{tabname}' AND colname = '{colname}';")
                for v in values:
                    v['tabname'] = tabname
                    v['colname'] = colname
                    cfg_lines.append(build_fldvalue_insert(fldvalue_cols, v, sys_val))
                purpose_parts.append(f"增加字典值 {colname}")
            elif action == 'drop_fldvalue':
                colname = ch['column']
                cfg_lines.append(f"DELETE FROM cx_fldvalue WHERE tabname = '{tabname}' AND colname = '{colname}';")
                purpose_parts.append(f"删除字典值 {colname}")
        if cfg_lines:
            sections.append({
                'author': args.author,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'purpose': f"配置变更：{tabname} ({', '.join(purpose_parts)})",
                'lines': cfg_lines
            })

    cursor.close()
    conn.close()

    if not sections:
        print("No changes to apply.")
        return

    out_lines = []
    for sec in sections:
        out_lines.append("-- ============================================================")
        out_lines.append(f"-- 作者：{sec['author']}")
        out_lines.append(f"-- 创建日期：{sec['date']}")
        out_lines.append(f"-- 脚本用途：{sec['purpose']}")
        out_lines.append("-- ============================================================")
        out_lines.extend(sec['lines'])
        out_lines.append("")
        out_lines.append("")

    with open(delta_path, 'a' if not is_new_file else 'w', encoding='utf-8') as f:
        if not is_new_file:
            f.write("\n\n")
        f.write('\n'.join(out_lines).rstrip() + '\n')

    print(f"{'Created' if is_new_file else 'Appended'} delta script: {delta_path}")
    print("Done.")

if __name__ == '__main__':
    main()
