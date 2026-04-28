import psycopg2
import os
import re
import json
import argparse
from collections import defaultdict, deque

TARGET_TABLES = {'cx_fld', 'cx_fldvalue', 'cx_entity'}

def display_width(s):
    import unicodedata
    w = 0
    for ch in s:
        ea = unicodedata.east_asian_width(ch)
        if ea in ('F', 'W'):
            w += 2
        else:
            w += 1
    return w

def pad_to_width(s, width):
    pad = width - display_width(s)
    if pad <= 0:
        return s
    return s + ' ' * pad

def parse_values(line):
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

def extract_tabname(line):
    m = re.search(r"tabname\s*=\s*'([^']+)'", line, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def align_sql_file(filepath):
    target_tables = {'cx_fld', 'cx_fldvalue', 'cx_entity', 'cx_sysdef', 'cx_syscfg', 'cx_layer', 'cx_maplayer', 'cx_mapservice', 'cx_sqlexp', 'cx_sqlpro', 'cx_userhabit', 'cx_func', 'cx_plugin'}
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    raw_lines = [line.rstrip('\n').rstrip('\r') for line in lines]

    insert_rows = []
    max_cols = 0
    for idx, line in enumerate(raw_lines):
        table_match = re.match(r'^\s*INSERT\s+INTO\s+(\w+)', line, re.IGNORECASE)
        if not table_match:
            continue
        table_name = table_match.group(1).lower()
        if table_name not in target_tables:
            continue
        parsed = parse_values(line)
        if parsed:
            head, parts, tail = parsed
            insert_rows.append((idx, head, parts, tail))
            max_cols = max(max_cols, len(parts))

    if not insert_rows:
        return

    col_widths = [0] * max_cols
    for _, _, parts, _ in insert_rows:
        for i, part in enumerate(parts):
            col_widths[i] = max(col_widths[i], display_width(part))

    for idx, head, parts, tail in insert_rows:
        padded = []
        for i in range(max_cols):
            if i < len(parts):
                padded.append(pad_to_width(parts[i], col_widths[i]))
            else:
                padded.append('')
        raw_lines[idx] = head + ', '.join(padded) + tail

    result = []
    prev_tabname = None
    prev_is_insert = False
    for line in raw_lines:
        stripped = line.strip()
        if stripped == '':
            continue
        current_tabname = extract_tabname(line)
        is_delete = re.match(r'^\s*delete\s+from', line, re.IGNORECASE) is not None
        is_insert = re.match(r'^\s*INSERT\s+INTO', line, re.IGNORECASE) is not None

        need_blank = False
        if is_delete:
            if result:
                need_blank = True
            prev_tabname = current_tabname
            prev_is_insert = False
        elif is_insert and current_tabname is not None:
            if prev_is_insert and prev_tabname is not None and prev_tabname != current_tabname:
                need_blank = True
            prev_tabname = current_tabname
            prev_is_insert = True
        else:
            if prev_is_insert and result:
                need_blank = True
            prev_is_insert = False
            prev_tabname = None

        if need_blank:
            result.append('')
        result.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        for line in result:
            f.write(line + '\n')

def quote_sql(val):
    if val is None:
        return 'null'
    if isinstance(val, bool):
        return 'TRUE' if val else 'FALSE'
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val)
    if s.lower() == 'nan':
        return 'null'
    return "'" + s.replace("'", "''") + "'"

def format_type(row):
    data_type, char_max, num_prec, num_scale, udt_name, is_nullable, ordinal_position, column_default = row
    if column_default and 'nextval' in str(column_default):
        dt = data_type.lower()
        if dt == 'integer':
            return 'serial'
        elif dt == 'smallint':
            return 'smallserial'
        elif dt == 'bigint':
            return 'bigserial'
    if data_type == 'character varying':
        return f'varchar({char_max})' if char_max else 'varchar'
    elif data_type == 'character':
        return f'char({char_max})' if char_max else 'char'
    elif data_type == 'numeric':
        if num_prec is not None and num_scale is not None:
            return f'numeric({num_prec},{num_scale})'
        elif num_prec is not None:
            return f'numeric({num_prec})'
        else:
            return 'numeric'
    elif data_type == 'timestamp without time zone':
        return 'timestamp'
    elif data_type == 'timestamp with time zone':
        return 'timestamptz'
    elif data_type == 'double precision':
        return 'double precision'
    elif data_type == 'USER-DEFINED':
        return udt_name
    else:
        return data_type

def get_columns(cursor, table_name):
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return [r[0] for r in cursor.fetchall()]

def topo_sort(tables, fk_deps):
    """
    fk_deps: dict[src_table] = [dst_table, ...]  (src has FK to dst)
    Returns list in creation order (base tables first, dependent tables later).
    Drop order is reverse.
    """
    in_degree = {t: 0 for t in tables}
    adj = defaultdict(list)
    for t in tables:
        for dep in set(fk_deps.get(t, [])):
            if dep in in_degree and dep != t:
                adj[dep].append(t)
                in_degree[t] += 1
    q = deque([t for t in tables if in_degree[t] == 0])
    result = []
    while q:
        t = q.popleft()
        result.append(t)
        for nxt in adj[t]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                q.append(nxt)
    # Append any remaining tables that have cycles
    for t in tables:
        if t not in result:
            result.append(t)
    return result

def build_table_sql(cursor, schema, table_list, entity_map, col_map, pk_map, uk_map, fk_map):
    # Build FK dependency graph
    fk_deps = defaultdict(list)
    for tabname in table_list:
        for fk_col, fk_ft, fk_fc in fk_map.get(tabname, []):
            fk_deps[tabname].append(fk_ft)

    create_order = topo_sort(table_list, fk_deps)
    drop_order = list(reversed(create_order))

    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 删除表（先删有外键的，再删只有主键的）")
    lines.append("-- ============================================================")
    lines.append("")

    prev_has_fk = None
    for tabname in drop_order:
        has_fk = bool(fk_map.get(tabname))
        if prev_has_fk is not None and prev_has_fk != has_fk:
            lines.append("")
            lines.append("-- 只有主键约束的表（后删）")
            lines.append("")
        elif prev_has_fk is not None:
            lines.append("")
        prev_has_fk = has_fk
        lines.append(f"DROP TABLE IF EXISTS {tabname};")

    lines.append("")
    lines.append("-- ============================================================")
    lines.append("-- 创建表（先建只有主键的，再建有外键的）")
    lines.append("-- ============================================================")
    lines.append("")

    for idx, tabname in enumerate(create_order):
        if idx > 0:
            lines.append("")
            lines.append("")
            lines.append("")
        namec = entity_map.get(tabname, ('',))[0] or ''
        lines.append(f"-- {namec}")
        lines.append(f"create table {tabname}")
        lines.append("(")

        cols = [(tabname, c) for c in [k[1] for k in col_map.keys() if k[0] == tabname]]
        cols.sort(key=lambda k: col_map[k][6])  # ordinal_position index 6

        pk_cols = pk_map.get(tabname, [])
        col_lines = []
        for key in cols:
            dtype = format_type(col_map[key])
            nullable = col_map[key][5]
            null_str = '' if nullable == 'NO' else ' null'
            col_def = f"    {key[1]} {dtype}{null_str}"
            # 铁律：id 单主键时直接在字段定义上加 primary key
            if key[1].lower() == 'id' and pk_cols == ['id']:
                col_def += ' primary key'
            col_lines.append(col_def)

        if pk_cols and pk_cols != ['id']:
            col_lines.append(f"    CONSTRAINT {tabname}_pkey PRIMARY KEY ({', '.join(pk_cols)})")

        uk_cols = uk_map.get(tabname, [])
        if uk_cols:
            col_lines.append(f"    CONSTRAINT {tabname}_key UNIQUE ({', '.join(uk_cols)})")

        for fk_col, fk_ft, fk_fc in fk_map.get(tabname, []):
            col_lines.append(f"    CONSTRAINT {tabname}_{fk_col}_fkey FOREIGN KEY ({fk_col}) REFERENCES {fk_ft}({fk_fc})")

        lines.append(",\n".join(col_lines))
        lines.append(");")
        lines.append("")

        # COMMENT ON COLUMN
        cursor.execute("""
            SELECT a.attname, d.description
            FROM pg_class c
            JOIN pg_attribute a ON a.attrelid = c.oid
            LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = a.attnum
            WHERE c.relname = %s AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
            ORDER BY a.attnum
        """, (tabname,))
        comments = {r[0]: r[1] for r in cursor.fetchall()}

        for key in cols:
            colname = key[1]
            comment = comments.get(colname)
            if not comment:
                comment = colname  # fallback, but spec says comment on every column
            # id column always 'ID'
            if colname.lower() == 'id':
                comment = 'ID'
            lines.append(f"comment on column {tabname}.{colname} is '{comment.replace(chr(39), chr(39)+chr(39))}';")

    return '\n'.join(lines) + '\n'

def build_index_sql(index_map):
    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 删除索引")
    lines.append("-- ============================================================")
    lines.append("")

    for tabname, idx_list in index_map.items():
        if not idx_list:
            continue
        lines.append(f"-- {tabname} 表索引")
        for idx_name, idx_def in idx_list:
            lines.append(f"DROP INDEX IF EXISTS {idx_name};")
        lines.append("")

    lines.append("-- ============================================================")
    lines.append("-- 创建索引")
    lines.append("-- ============================================================")
    lines.append("")

    for tabname, idx_list in index_map.items():
        if not idx_list:
            continue
        lines.append(f"-- {tabname} 表索引")
        for idx_name, idx_def in idx_list:
            lines.append(f"{idx_def};")
        lines.append("")

    return '\n'.join(lines) + '\n'

def parse_index(indexdef):
    """Parse pg_indexes.indexdef to return (indexname, columns_string)"""
    m = re.search(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+\w+\.\w+\s+USING\s+\w+\s+\((.+)\)', indexdef)
    if m:
        return m.group(1), m.group(2)
    return None, None

def normalize_index_name(tablename, cols_str):
    """按照规范生成索引名：表名_字段1_字段2"""
    cols = [c.strip().split()[0] for c in cols_str.split(',')]
    name = f"{tablename}_{'_'.join(cols)}"
    if len(name) > 50:
        name = name[:50]
    return name

def generate_config_sql(cursor, table_name, delete_clause_fn, sort_columns):
    """Generic generator for config tables like cx_func, cx_plugin, etc."""
    cols = get_columns(cursor, table_name)
    if not cols:
        return None
    cols_insert = [c for c in cols if c != 'id']

    cursor.execute(f"SELECT * FROM {table_name} ORDER BY {', '.join(sort_columns)}")
    rows = cursor.fetchall()
    if not rows:
        return None

    lines = []
    lines.append(f"-- ============================================================")
    lines.append(f"-- 删除{table_name}定义")
    lines.append(f"-- ============================================================")
    deletes = set()
    for row in rows:
        clause = delete_clause_fn(row, cols)
        deletes.add(clause)
    for d in sorted(deletes):
        lines.append(d)
    lines.append("")
    lines.append(f"-- ============================================================")
    lines.append(f"-- 创建{table_name}定义")
    lines.append(f"-- ============================================================")
    lines.append("")

    for row in rows:
        vals = [quote_sql(v) for i, v in enumerate(row) if cols[i] != 'id']
        lines.append(f"INSERT INTO {table_name}({', '.join(cols_insert)}) VALUES ({', '.join(vals)});")
        lines.append("")

    return '\n'.join(lines) + '\n'

def main():
    parser = argparse.ArgumentParser(description='Generate standardized SQL scripts per V1.2 spec.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--output-dir', required=True, help='Usually <project-root>/01-Application/')
    parser.add_argument('--schema', default='zgis')
    parser.add_argument('--sys', default='0')
    parser.add_argument('--major', type=int)
    parser.add_argument('--tables')
    parser.add_argument('--with-config', action='store_true', help='Also generate 09-data.sql, 10-cx_func.sql, 11-cx_plugin.sql from existing database')
    args = parser.parse_args()

    db_url = args.db_url
    output_dir = args.output_dir
    schema = args.schema
    sys_num = args.sys

    os.makedirs(output_dir, exist_ok=True)

    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    if args.tables:
        table_list = [t.strip() for t in args.tables.split(',') if t.strip()]
    elif args.major is not None:
        cursor.execute("SELECT name FROM cx_entity WHERE major = %s ORDER BY minor", (args.major,))
        table_list = [r[0] for r in cursor.fetchall()]
    else:
        cursor.execute("SELECT name FROM cx_entity WHERE major > 0 ORDER BY major, minor")
        table_list = [r[0] for r in cursor.fetchall()]

    if not table_list:
        print("No tables matched.")
        return

    placeholders = ','.join(['%s'] * len(table_list))
    cursor.execute(f"SELECT name, namec, major, minor FROM cx_entity WHERE name IN ({placeholders}) ORDER BY major, minor", tuple(table_list))
    entity_map = {r[0]: r for r in cursor.fetchall()}

    cursor.execute(f"""
        SELECT table_name, column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, udt_name, is_nullable,
               ordinal_position, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name IN ({placeholders})
        ORDER BY table_name, ordinal_position
    """, (schema, *tuple(table_list)))
    col_map = {}
    for row in cursor.fetchall():
        key = (row[0], row[1])
        col_map[key] = row[2:]

    cursor.execute(f"""
        SELECT tc.table_name, tc.constraint_type, kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = %s AND tc.table_name IN ({placeholders})
          AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
        ORDER BY tc.table_name, tc.constraint_type, kcu.ordinal_position
    """, (schema, *tuple(table_list)))
    pk_map = defaultdict(list)
    uk_map = defaultdict(list)
    fk_map = defaultdict(list)
    for table_name, ctype, col_name, foreign_table, foreign_col in cursor.fetchall():
        if ctype == 'PRIMARY KEY':
            pk_map[table_name].append(col_name)
        elif ctype == 'UNIQUE':
            uk_map[table_name].append(col_name)
        elif ctype == 'FOREIGN KEY':
            fk_map[table_name].append((col_name, foreign_table, foreign_col))

    cursor.execute(f"""
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = %s AND tablename IN ({placeholders})
    """, (schema, *tuple(table_list)))
    raw_indexes = cursor.fetchall()

    # Rebuild index_map with normalized names
    index_map = {}
    for tablename, indexname, indexdef in raw_indexes:
        if indexname.endswith('_pkey'):
            continue
        # skip unique constraint indexes
        if 'UNIQUE INDEX' in indexdef:
            # check if it's a unique constraint managed by pg_constraint
            cursor.execute("""
                SELECT 1 FROM pg_constraint
                WHERE conname = %s AND contype = 'u'
            """, (indexname,))
            if cursor.fetchone():
                continue
        orig_name, cols_str = parse_index(indexdef)
        if not orig_name or not cols_str:
            continue
        norm_name = normalize_index_name(tablename, cols_str)
        norm_def = re.sub(rf'CREATE\s+(UNIQUE\s+)?INDEX\s+\w+\s+ON\s+\w+\.\w+',
                          rf'CREATE \1INDEX {norm_name} ON {tablename}',
                          indexdef)
        # also normalize schema reference
        norm_def = norm_def.replace(f'{schema}.', '')
        index_map.setdefault(tablename, []).append((norm_name, norm_def))

    # cx_fld
    cursor.execute(f"SELECT * FROM cx_fld WHERE tabname IN ({placeholders}) ORDER BY tabname, disporder", tuple(table_list))
    fld_rows = cursor.fetchall()
    fld_cols = get_columns(cursor, 'cx_fld')
    colname_idx = fld_cols.index('colname') if 'colname' in fld_cols else 3

    # cx_fldvalue
    cursor.execute(f"SELECT * FROM cx_fldvalue WHERE tabname IN ({placeholders}) ORDER BY tabname, colname, disporder", tuple(table_list))
    fldvalue_rows = cursor.fetchall()
    fldvalue_cols = get_columns(cursor, 'cx_fldvalue')

    # entity
    entity_cols = get_columns(cursor, 'cx_entity')

    cursor.close()
    conn.close()

    # Build files
    files_map = {}

    # 01-table.sql (needs cursor for column comments)
    conn2 = psycopg2.connect(db_url)
    cur2 = conn2.cursor()
    table_sql = build_table_sql(cur2, schema, table_list, entity_map, col_map, dict(pk_map), dict(uk_map), dict(fk_map))
    cur2.close()
    conn2.close()

    # Append views to 01-table.sql per V1.2 spec
    conn_views = psycopg2.connect(db_url)
    cur_views = conn_views.cursor()
    cur_views.execute("""
        SELECT table_name, view_definition
        FROM information_schema.views
        WHERE table_schema = %s
        ORDER BY table_name
    """, (schema,))
    view_map = {row[0]: row[1] for row in cur_views.fetchall()}

    if view_map:
        cur_views.execute("""
            SELECT DISTINCT v.table_name, u.table_name AS dependency
            FROM information_schema.view_table_usage u
            JOIN information_schema.views v
              ON u.view_name = v.table_name AND u.view_schema = v.table_schema
            WHERE v.table_schema = %s AND u.table_schema = %s
              AND u.table_name != v.table_name
        """, (schema, schema))
        all_deps = defaultdict(list)
        for view_name, dep in cur_views.fetchall():
            if dep in view_map:
                all_deps[view_name].append(dep)

        in_degree = {v: 0 for v in view_map}
        adj = defaultdict(list)
        for v in view_map:
            for dep in set(all_deps.get(v, [])):
                if dep in in_degree and dep != v:
                    adj[dep].append(v)
                    in_degree[v] += 1
        q = deque([v for v in view_map if in_degree[v] == 0])
        sorted_views = []
        while q:
            v = q.popleft()
            sorted_views.append(v)
            for nxt in adj[v]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    q.append(nxt)
        for v in view_map:
            if v not in sorted_views:
                sorted_views.append(v)

        view_lines = [
            "",
            "-- ============================================================",
            "-- 删除视图（先删父视图，再删子视图）",
            "-- ============================================================",
            "",
        ]
        for v in reversed(sorted_views):
            view_lines.append(f"DROP VIEW IF EXISTS {v};")
        view_lines.append("")
        view_lines.append("-- ============================================================")
        view_lines.append("-- 创建视图（先建子视图，再建父视图）")
        view_lines.append("-- ============================================================")
        view_lines.append("")
        for v in sorted_views:
            defn = view_map[v]
            if not defn:
                continue
            clean_defn = re.sub(rf'\b{re.escape(schema)}\.', '', defn)
            view_lines.append(f"CREATE OR REPLACE VIEW {v} AS")
            view_lines.append(f"{clean_defn.strip().rstrip(';')};")
            view_lines.append("")
            view_lines.append("")

        table_sql += '\n'.join(view_lines)

    cur_views.close()
    conn_views.close()
    files_map['01-table.sql'] = table_sql

    # 05-index.sql
    files_map['05-index.sql'] = build_index_sql(index_map)

    # 04-cx_entity.sql
    entity_lines = []
    majors = sorted(set(r[2] for r in entity_map.values()))
    for maj in majors:
        entity_lines.append(f"delete from cx_entity where major={maj};")
    entity_lines.append("")
    col_list_str = ', '.join(entity_cols)
    for row in entity_map.values():
        # row is (name, namec, major, minor)
        # Need full entity data - but we only have name/namec/major/minor from query.
        # Actually entity_map values are full rows from cx_entity.
        pass
    # Re-fetch full entity rows properly
    conn3 = psycopg2.connect(db_url)
    cur3 = conn3.cursor()
    placeholders = ','.join(['%s'] * len(table_list))
    cur3.execute(f"SELECT * FROM cx_entity WHERE name IN ({placeholders}) ORDER BY major, minor", tuple(table_list))
    full_entity_rows = cur3.fetchall()
    entity_cols = get_columns(cur3, 'cx_entity')
    entity_cols_insert = [c for c in entity_cols if c != 'id']
    cur3.close()
    conn3.close()

    entity_lines = []
    majors = sorted(set(r[entity_cols.index('major')] if 'major' in entity_cols else r[4] for r in full_entity_rows))
    for maj in majors:
        entity_lines.append(f"delete from cx_entity where major={maj};")
    entity_lines.append("")
    for row in full_entity_rows:
        vals = [quote_sql(v) for i, v in enumerate(row) if entity_cols[i] != 'id']
        entity_lines.append(f"INSERT INTO cx_entity ({', '.join(entity_cols_insert)}) VALUES ({', '.join(vals)});")
    files_map['04-cx_entity.sql'] = '\n'.join(entity_lines) + '\n'

    # 02-cx_fld.sql
    fld_lines = []
    tab_to_fld = {}
    for row in fld_rows:
        tabname = row[fld_cols.index('tabname')] if 'tabname' in fld_cols else row[2]
        if str(row[colname_idx]).lower() == 'id':
            continue
        tab_to_fld.setdefault(tabname, []).append(row)
    for tabname in table_list:
        rows = tab_to_fld.get(tabname, [])
        if not rows:
            continue
        if fld_lines and fld_lines[-1].strip() != '':
            fld_lines.append('')
        fld_lines.append(f"delete from cx_fld where tabname='{tabname}';")
        fld_cols_insert = [c for c in fld_cols if c != 'id']
        for row in rows:
            vals = [quote_sql(v) for i, v in enumerate(row) if fld_cols[i] != 'id']
            fld_lines.append(f"INSERT INTO cx_fld ({', '.join(fld_cols_insert)}) VALUES ({', '.join(vals)});")
    files_map['02-cx_fld.sql'] = '\n'.join(fld_lines) + '\n'

    # 03-cx_fldvalue.sql
    fldvalue_lines = []
    tab_to_fv = {}
    for row in fldvalue_rows:
        tabname = row[fldvalue_cols.index('tabname')] if 'tabname' in fldvalue_cols else row[2]
        tab_to_fv.setdefault(tabname, []).append(row)
    for tabname in table_list:
        rows = tab_to_fv.get(tabname, [])
        if not rows:
            continue
        if fldvalue_lines and fldvalue_lines[-1].strip() != '':
            fldvalue_lines.append('')
            fldvalue_lines.append('')
        fldvalue_lines.append(f"delete from cx_fldvalue where tabname='{tabname}';")
        prev_col = None
        for row in rows:
            colname = row[fldvalue_cols.index('colname')] if 'colname' in fldvalue_cols else row[3]
            if prev_col is not None and prev_col != colname:
                fldvalue_lines.append('')
            prev_col = colname
            fldvalue_cols_insert = [c for c in fldvalue_cols if c != 'id']
            vals = [quote_sql(v) for i, v in enumerate(row) if fldvalue_cols[i] != 'id']
            fldvalue_lines.append(f"INSERT INTO cx_fldvalue ({', '.join(fldvalue_cols_insert)}) VALUES ({', '.join(vals)});")
    files_map['03-cx_fldvalue.sql'] = '\n'.join(fldvalue_lines) + '\n'

    # 09-data.sql (system init data)
    data_tables = ['cx_sysdef', 'cx_syscfg', 'cx_layer', 'cx_maplayer', 'cx_mapservice', 'cx_sqlexp', 'cx_sqlpro', 'cx_userhabit']
    data_lines = []
    conn4 = psycopg2.connect(db_url)
    cur4 = conn4.cursor()
    for dt in data_tables:
        cur4.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", (dt,))
        if not cur4.fetchone():
            continue
        cols = get_columns(cur4, dt)
        cols_insert = [c for c in cols if c != 'id']
        cur4.execute(f"SELECT * FROM {dt} ORDER BY 1")
        rows = cur4.fetchall()
        if not rows:
            continue
        data_lines.append(f"/* {dt} */")
        data_lines.append(f"DELETE FROM {dt};")
        data_lines.append("")
        for row in rows:
            vals = [quote_sql(v) for i, v in enumerate(row) if cols[i] != 'id']
            data_lines.append(f"INSERT INTO {dt} ({', '.join(cols_insert)}) VALUES ({', '.join(vals)});")
        data_lines.append("")
        data_lines.append("")
    cur4.close()
    conn4.close()
    if data_lines:
        files_map['09-data.sql'] = '\n'.join(data_lines) + '\n'

    # 10-cx_func.sql
    conn5 = psycopg2.connect(db_url)
    cur5 = conn5.cursor()
    cur5.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'cx_func'")
    if cur5.fetchone():
        cur5.execute("SELECT * FROM cx_func ORDER BY sys, disporder")
        func_rows = cur5.fetchall()
        if func_rows:
            func_cols = get_columns(cur5, 'cx_func')
            func_cols_insert = [c for c in func_cols if c != 'id']
            func_lines = ["-- ============================================================", "-- 删除功能定义", "-- ============================================================"]
            sys_set = sorted(set(r[func_cols.index('sys')] if 'sys' in func_cols else r[1] for r in func_rows))
            for s in sys_set:
                func_lines.append(f"DELETE FROM cx_func WHERE sys='{s}';")
            func_lines.append("")
            func_lines.append("-- ============================================================")
            func_lines.append("-- 创建功能定义")
            func_lines.append("-- ============================================================")
            func_lines.append("")
            for row in func_rows:
                vals = [quote_sql(v) for i, v in enumerate(row) if func_cols[i] != 'id']
                func_lines.append(f"INSERT INTO cx_func({', '.join(func_cols_insert)}) VALUES ({', '.join(vals)});")
                func_lines.append("")
            files_map['10-cx_func.sql'] = '\n'.join(func_lines) + '\n'
    cur5.close()
    conn5.close()

    # 11-cx_plugin.sql
    conn6 = psycopg2.connect(db_url)
    cur6 = conn6.cursor()
    cur6.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'cx_plugin'")
    if cur6.fetchone():
        cur6.execute("SELECT * FROM cx_plugin ORDER BY sys, cata, name")
        plugin_rows = cur6.fetchall()
        if plugin_rows:
            plugin_cols = get_columns(cur6, 'cx_plugin')
            plugin_cols_insert = [c for c in plugin_cols if c != 'id']
            plugin_lines = ["-- ============================================================", "-- 删除插件定义", "-- ============================================================"]
            sys_set = sorted(set(r[plugin_cols.index('sys')] if 'sys' in plugin_cols else r[1] for r in plugin_rows))
            for s in sys_set:
                plugin_lines.append(f"DELETE FROM cx_plugin WHERE sys='{s}';")
            plugin_lines.append("")
            plugin_lines.append("-- ============================================================")
            plugin_lines.append("-- 创建插件定义")
            plugin_lines.append("-- ============================================================")
            plugin_lines.append("")
            for row in plugin_rows:
                vals = [quote_sql(v) for i, v in enumerate(row) if plugin_cols[i] != 'id']
                plugin_lines.append(f"INSERT INTO cx_plugin({', '.join(plugin_cols_insert)}) VALUES ({', '.join(vals)});")
                plugin_lines.append("")
            files_map['11-cx_plugin.sql'] = '\n'.join(plugin_lines) + '\n'
    cur6.close()
    conn6.close()

    # Write all files
    for fname, content in files_map.items():
        path = os.path.join(output_dir, fname)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Generated: {path}")

    # Align
    for fname in ('02-cx_fld.sql', '03-cx_fldvalue.sql', '04-cx_entity.sql', '09-data.sql', '10-cx_func.sql', '11-cx_plugin.sql'):
        path = os.path.join(output_dir, fname)
        if os.path.exists(path):
            align_sql_file(path)
            print(f"Aligned: {path}")

    print("Done.")

if __name__ == '__main__':
    main()
