#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import psycopg2
import argparse
from datetime import datetime

NUMERIC_TYPES = {
    'integer', 'bigint', 'smallint', 'numeric', 'decimal', 'real',
    'double precision', 'serial', 'bigserial', 'smallserial'
}

TIMESTAMP_TYPES = {
    'timestamp without time zone', 'timestamp with time zone',
    'timestamp', 'timestamptz'
}


def main():
    parser = argparse.ArgumentParser(description='Auto-fix common cx_fld issues. NEVER inserts id fields.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--schema', default='zgis')
    parser.add_argument('--apply', action='store_true', help='Apply fixes; default is dry-run')
    parser.add_argument('--output', help='Output SQL file of fixes (always generated)')
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()
    schema = args.schema

    fixes = []

    # 1. Fix colname casing (non-act% tables)
    cursor.execute("""
        SELECT tabname, colname
        FROM cx_fld
        WHERE tabname NOT LIKE 'act%%' AND colname != LOWER(colname)
    """)
    casing_rows = cursor.fetchall()
    if casing_rows:
        fixes.append("-- Fix colname casing (lowercase for non-act tables)")
        fixes.append("UPDATE cx_fld SET colname = LOWER(colname) WHERE tabname NOT LIKE 'act%' AND colname != LOWER(colname);")
        fixes.append("")

    # 2. Remove forbidden 'id' configurations from cx_fld
    cursor.execute("SELECT tabname, colname FROM cx_fld WHERE LOWER(colname) = 'id'")
    id_rows = cursor.fetchall()
    if id_rows:
        fixes.append("-- Remove forbidden 'id' configurations from cx_fld")
        tabnames = sorted(set(r[0] for r in id_rows))
        for t in tabnames:
            fixes.append(f"DELETE FROM cx_fld WHERE tabname = '{t}' AND LOWER(colname) = 'id';")
        fixes.append("")

    # 3. Remove orphan cx_fld records (column no longer exists in actual table)
    cursor.execute("""
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema = %s
    """, (schema,))
    actual_set = set(cursor.fetchall())

    cursor.execute("SELECT tabname, colname FROM cx_fld")
    fld_rows = cursor.fetchall()
    orphan_tabnames = {}
    for tabname, colname in fld_rows:
        if (tabname, colname) not in actual_set:
            orphan_tabnames.setdefault(tabname, []).append(colname)

    if orphan_tabnames:
        fixes.append("-- Remove orphan cx_fld records (column does not exist in actual table)")
        for tabname in sorted(orphan_tabnames.keys()):
            cols = orphan_tabnames[tabname]
            if len(cols) == 1:
                fixes.append(f"DELETE FROM cx_fld WHERE tabname = '{tabname}' AND colname = '{cols[0]}';")
            else:
                col_list = ", ".join([f"'{c}'" for c in cols])
                fixes.append(f"DELETE FROM cx_fld WHERE tabname = '{tabname}' AND colname IN ({col_list});")
        fixes.append("")

    # 4. Sync sys field from cx_entity (where cx_fld.sys mismatches cx_entity.sys)
    cursor.execute("""
        SELECT DISTINCT f.tabname, e.sys
        FROM cx_fld f
        JOIN cx_entity e ON f.tabname = e.name
        WHERE f.sys != e.sys
    """)
    sys_sync_rows = cursor.fetchall()
    if sys_sync_rows:
        fixes.append("-- Sync cx_fld.sys from cx_entity.sys")
        for tabname, target_sys in sys_sync_rows:
            fixes.append(f"UPDATE cx_fld SET sys = '{target_sys}' WHERE tabname = '{tabname}';")
        fixes.append("")

    # 5. Fix isnum mismatch
    cursor.execute("""
        SELECT c.table_name, c.column_name, c.data_type, f.isnum
        FROM information_schema.columns c
        JOIN cx_fld f ON c.table_name = f.tabname AND c.column_name = f.colname
        WHERE c.table_schema = %s
    """, (schema,))
    isnum_fixes = []
    for table_name, column_name, data_type, isnum in cursor.fetchall():
        actual_type = data_type.lower()
        is_numeric = actual_type in NUMERIC_TYPES
        try:
            isnum_val = int(isnum) if isnum is not None else 0
        except (ValueError, TypeError):
            isnum_val = 0
        if isnum_val == 1 and not is_numeric:
            isnum_fixes.append((table_name, column_name, 0))
        elif isnum_val != 1 and is_numeric:
            isnum_fixes.append((table_name, column_name, 1))

    if isnum_fixes:
        fixes.append("-- Fix isnum mismatch")
        for tabname, colname, target in isnum_fixes:
            fixes.append(f"UPDATE cx_fld SET isnum = {target} WHERE tabname = '{tabname}' AND colname = '{colname}';")
        fixes.append("")

    # 6. Fix timestamp fields disptype to 3 (when not 3 or 5)
    cursor.execute("""
        SELECT c.table_name, c.column_name, c.data_type, f.disptype
        FROM information_schema.columns c
        JOIN cx_fld f ON c.table_name = f.tabname AND c.column_name = f.colname
        WHERE c.table_schema = %s
          AND c.data_type IN ('timestamp without time zone', 'timestamp with time zone')
    """, (schema,))
    ts_fixes = []
    for table_name, column_name, data_type, disptype in cursor.fetchall():
        try:
            disptype_val = int(disptype) if disptype is not None else -1
        except (ValueError, TypeError):
            disptype_val = -1
        if disptype_val not in (3, 5):
            ts_fixes.append((table_name, column_name))

    if ts_fixes:
        fixes.append("-- Fix timestamp fields disptype to 3 (default for timestamp)")
        for tabname, colname in ts_fixes:
            fixes.append(f"UPDATE cx_fld SET disptype = 3 WHERE tabname = '{tabname}' AND colname = '{colname}';")
        fixes.append("")

    cursor.close()

    if not fixes:
        print("No issues found. Nothing to fix.")
        conn.close()
        return

    sql_content = "\n".join(fixes)

    header = [
        f"-- cx_fld Auto-Fix Script",
        f"-- Generated: {datetime.now().isoformat()}",
        f"-- Mode: {'APPLY' if args.apply else 'DRY-RUN'}",
        f"-- Core Rule: id columns are NEVER configured in cx_fld",
        "",
    ]
    full_sql = "\n".join(header) + sql_content

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(full_sql)
        print(f"Fix script saved: {args.output}")
    else:
        print(full_sql)

    if args.apply:
        cur = conn.cursor()
        for stmt in fixes:
            stmt = stmt.strip()
            if not stmt or stmt.startswith('--'):
                continue
            cur.execute(stmt)
        conn.commit()
        cur.close()
        print("Fixes applied to database.")
    else:
        print("\n(Dry-run mode: no changes applied. Use --apply to execute.)")

    conn.close()


if __name__ == '__main__':
    main()
