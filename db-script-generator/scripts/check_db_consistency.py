import psycopg2
import argparse
from datetime import datetime

def quote_sql(val):
    if val is None:
        return 'null'
    s = str(val)
    if s.lower() == 'nan':
        return 'null'
    return "'" + s.replace("'", "''") + "'"

def format_type(data_type, char_max, num_prec, num_scale, udt_name, column_default):
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
    elif data_type == 'USER-DEFINED':
        return udt_name
    else:
        return data_type

def main():
    parser = argparse.ArgumentParser(description='Check consistency between PostgreSQL schema and cx_fld / cx_entity metadata.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--schema', default='zgis')
    parser.add_argument('--output', help='Output report file path')
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()
    schema = args.schema

    # 1. actual columns
    cursor.execute("""
        SELECT table_name, column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, udt_name, is_nullable, ordinal_position, column_default
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
    """, (schema,))
    actual_cols = {}
    for row in cursor.fetchall():
        actual_cols[(row[0], row[1])] = row[2:]

    # 2. cx_entity
    cursor.execute("SELECT name, major, minor FROM cx_entity WHERE major > 0 ORDER BY major, minor")
    entity_map = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}

    # 3. cx_fld
    cursor.execute("SELECT tabname, colname, namec, disptype, disporder, data_type FROM cx_fld")
    # Note: cx_fld itself has no data_type column in standard schema; we only have tabname/colname/config fields.
    # Re-fetch without assuming data_type.
    cursor.execute("SELECT tabname, colname FROM cx_fld")
    fld_set = set(cursor.fetchall())

    cursor.close()
    conn.close()

    issues = []

    # Rule: cx_fld must never configure 'id' column
    cursor = psycopg2.connect(args.db_url).cursor()
    cursor.execute("SELECT tabname, colname FROM cx_fld WHERE LOWER(colname) = 'id'")
    id_fld_rows = cursor.fetchall()
    cursor.close()
    for tabname, colname in id_fld_rows:
        issues.append(f"[FORBIDDEN] cx_fld configures 'id' column: {tabname}.{colname}")

    # Check: actual column exists but not in cx_fld (exclude id)
    for (tabname, colname), info in actual_cols.items():
        if colname.lower() == 'id':
            continue
        if tabname in entity_map and (tabname, colname) not in fld_set:
            issues.append(f"[MISSING_FLD] Actual column missing in cx_fld: {tabname}.{colname}")

    # Check: cx_fld exists but actual column missing
    for (tabname, colname) in fld_set:
        if colname.lower() == 'id':
            continue
        if (tabname, colname) not in actual_cols:
            issues.append(f"[ORPHAN_FLD] cx_fld column does not exist in actual table: {tabname}.{colname}")

    # Check: colname casing issue (non-act% tables should be lowercase)
    cursor = psycopg2.connect(args.db_url).cursor()
    cursor.execute("SELECT tabname, colname FROM cx_fld WHERE tabname NOT LIKE 'act%%' AND colname != LOWER(colname)")
    casing_rows = cursor.fetchall()
    cursor.close()
    for tabname, colname in casing_rows:
        issues.append(f"[CASING] cx_fld colname should be lowercase: {tabname}.{colname}")

    # Check: cx_entity table missing in actual schema
    for tabname in entity_map:
        actual_table_cols = [k for k in actual_cols.keys() if k[0] == tabname]
        if not actual_table_cols:
            issues.append(f"[MISSING_TABLE] cx_entity table does not exist in schema: {tabname}")

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
