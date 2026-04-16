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

DATETIME_TYPES_TO_REJECT = {
    'date', 'time without time zone', 'time with time zone',
    'time', 'interval'
}


def main():
    parser = argparse.ArgumentParser(description='Check consistency between PostgreSQL schema and cx_fld / cx_entity metadata.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--schema', default='zgis')
    parser.add_argument('--output', help='Output report file path')
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()
    schema = args.schema

    issues = []

    # ------------------------------------------------------------------
    # 1. actual columns (table_name, column_name -> all info)
    # ------------------------------------------------------------------
    cursor.execute("""
        SELECT table_name, column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, udt_name, is_nullable,
               ordinal_position, column_default
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
    """, (schema,))
    actual_cols = {}
    for row in cursor.fetchall():
        actual_cols[(row[0], row[1])] = row[2:]

    # ------------------------------------------------------------------
    # 2. cx_entity
    # ------------------------------------------------------------------
    cursor.execute("SELECT name, major, minor FROM cx_entity WHERE major > 0 ORDER BY major, minor")
    entity_map = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}

    # ------------------------------------------------------------------
    # 3. primary keys
    # ------------------------------------------------------------------
    cursor.execute("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s
    """, (schema,))
    pk_map = {}
    for table_name, column_name in cursor.fetchall():
        pk_map.setdefault(table_name, []).append(column_name)

    # ------------------------------------------------------------------
    # 4. cx_fld (with isnum, disptype)
    # ------------------------------------------------------------------
    cursor.execute("SELECT tabname, colname, isnum, disptype FROM cx_fld")
    fld_rows = cursor.fetchall()
    fld_set = set()
    fld_meta = {}
    for tabname, colname, isnum, disptype in fld_rows:
        fld_set.add((tabname, colname))
        fld_meta[(tabname, colname)] = {'isnum': isnum, 'disptype': disptype}

    # ------------------------------------------------------------------
    # 5. cx_fldvalue 存在性
    # ------------------------------------------------------------------
    cursor.execute("SELECT tabname, colname FROM cx_fldvalue")
    fldvalue_set = set(cursor.fetchall())

    cursor.close()
    conn.close()

    # ==================================================================
    # 检查规则
    # ==================================================================

    # Rule 1: cx_fld must never configure 'id' column
    conn2 = psycopg2.connect(args.db_url)
    cur2 = conn2.cursor()
    cur2.execute("SELECT tabname, colname FROM cx_fld WHERE LOWER(colname) = 'id'")
    for tabname, colname in cur2.fetchall():
        issues.append(f"[FORBIDDEN] cx_fld configures 'id' column: {tabname}.{colname}")
    cur2.close()
    conn2.close()

    # Check 2: actual column exists but not in cx_fld (exclude id)
    for (tabname, colname), info in actual_cols.items():
        if colname.lower() == 'id':
            continue
        if tabname in entity_map and (tabname, colname) not in fld_set:
            issues.append(f"[MISSING_FLD] Actual column missing in cx_fld: {tabname}.{colname}")

    # Check 3: cx_fld exists but actual column missing
    for (tabname, colname) in fld_set:
        if colname.lower() == 'id':
            continue
        if (tabname, colname) not in actual_cols:
            issues.append(f"[ORPHAN_FLD] cx_fld column does not exist in actual table: {tabname}.{colname}")

    # Check 4: colname casing issue (non-act% tables should be lowercase)
    conn2 = psycopg2.connect(args.db_url)
    cur2 = conn2.cursor()
    cur2.execute("SELECT tabname, colname FROM cx_fld WHERE tabname NOT LIKE 'act%%' AND colname != LOWER(colname)")
    for tabname, colname in cur2.fetchall():
        issues.append(f"[CASING] cx_fld colname should be lowercase: {tabname}.{colname}")
    cur2.close()
    conn2.close()

    # Check 5: cx_entity table missing in actual schema
    for tabname in entity_map:
        actual_table_cols = [k for k in actual_cols.keys() if k[0] == tabname]
        if not actual_table_cols:
            issues.append(f"[MISSING_TABLE] cx_entity table does not exist in schema: {tabname}")

    # Check 6: id is not primary key
    for tabname in entity_map:
        pk_cols = pk_map.get(tabname, [])
        if 'id' not in pk_cols:
            # 还要检查表里面有没有 id 字段
            if (tabname, 'id') in actual_cols or any(k[0] == tabname and k[1].lower() == 'id' for k in actual_cols):
                issues.append(f"[PK_ID] Table {tabname}: 'id' is not the primary key")
            else:
                issues.append(f"[PK_ID] Table {tabname}: missing 'id' primary key column")

    # Check 7: isnum mismatch
    for (tabname, colname), meta in fld_meta.items():
        if (tabname, colname) not in actual_cols:
            continue
        actual_type = actual_cols[(tabname, colname)][0].lower()
        isnum = meta['isnum']
        is_numeric = actual_type in NUMERIC_TYPES
        try:
            isnum_val = int(isnum) if isnum is not None else 0
        except (ValueError, TypeError):
            isnum_val = 0

        if isnum_val == 1 and not is_numeric:
            issues.append(f"[ISNUM_MISMATCH] {tabname}.{colname}: isnum=1 but actual type is {actual_type}")
        elif isnum_val != 1 and is_numeric:
            issues.append(f"[ISNUM_MISMATCH] {tabname}.{colname}: isnum={isnum_val} but actual type is {actual_type}")

    # Check 8: disptype=2/6 but no fldvalue
    for (tabname, colname), meta in fld_meta.items():
        disptype = meta['disptype']
        try:
            disptype_val = int(disptype) if disptype is not None else -1
        except (ValueError, TypeError):
            disptype_val = -1
        if disptype_val in (2, 6):
            if (tabname, colname) not in fldvalue_set:
                issues.append(f"[DISPTYPE_FLDVALUE_MISSING] {tabname}.{colname}: disptype={disptype_val} but no cx_fldvalue entries found")

    # Check 9: disptype=3/5 but field is not timestamp
    for (tabname, colname), meta in fld_meta.items():
        if (tabname, colname) not in actual_cols:
            continue
        actual_type = actual_cols[(tabname, colname)][0].lower()
        disptype = meta['disptype']
        try:
            disptype_val = int(disptype) if disptype is not None else -1
        except (ValueError, TypeError):
            disptype_val = -1
        if disptype_val in (3, 5) and actual_type not in TIMESTAMP_TYPES:
            issues.append(f"[DISPTYPE_TIMESTAMP_MISMATCH] {tabname}.{colname}: disptype={disptype_val} but actual type is {actual_type}")

    # Check 10: field is timestamp but disptype is not 3/5
    for (tabname, colname), meta in fld_meta.items():
        if (tabname, colname) not in actual_cols:
            continue
        actual_type = actual_cols[(tabname, colname)][0].lower()
        disptype = meta['disptype']
        try:
            disptype_val = int(disptype) if disptype is not None else -1
        except (ValueError, TypeError):
            disptype_val = -1
        if actual_type in TIMESTAMP_TYPES and disptype_val not in (3, 5):
            issues.append(f"[TIMESTAMP_DISPTYPE_MISMATCH] {tabname}.{colname}: actual type is {actual_type} but disptype={disptype_val}")

    # Check 11: all datetime types must be timestamp (reject date/time/interval)
    for (tabname, colname), info in actual_cols.items():
        actual_type = info[0].lower()
        if actual_type in DATETIME_TYPES_TO_REJECT:
            issues.append(f"[DATATYPE_TIMESTAMP_REQUIRED] {tabname}.{colname}: actual type is {actual_type}, must use timestamp instead")

    # ==================================================================
    # 输出报告
    # ==================================================================
    report_lines = [
        f"-- Database Consistency Report",
        f"-- Schema: {schema}",
        f"-- Generated: {datetime.now().isoformat()}",
        f"-- Total Issues: {len(issues)}",
        "",
    ]
    if issues:
        report_lines.extend(issues)
    else:
        report_lines.append("No issues found.")
    report_lines.append("")

    report = "\n".join(report_lines)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report saved: {args.output}")
    else:
        print(report)


if __name__ == '__main__':
    main()
