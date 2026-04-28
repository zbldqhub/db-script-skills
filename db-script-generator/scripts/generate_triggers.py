#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 PostgreSQL 生成触发器全量脚本 06-trigger.sql。
"""

import os
import re
import argparse
import psycopg2


def main():
    parser = argparse.ArgumentParser(description='Generate 06-trigger.sql from PostgreSQL.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--output-dir', required=True, help='Usually <project-root>/01-Application/')
    parser.add_argument('--schema', default='zgis')
    parser.add_argument('--sys')
    parser.add_argument('--major', type=int)
    parser.add_argument('--tables')
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()
    schema = args.schema

    table_filter = None
    if args.tables:
        table_filter = [t.strip() for t in args.tables.split(',') if t.strip()]
    elif args.major is not None:
        cursor.execute("SELECT name FROM cx_entity WHERE major = %s ORDER BY minor", (args.major,))
        table_filter = [r[0] for r in cursor.fetchall()]

    if table_filter:
        placeholders = ','.join(['%s'] * len(table_filter))
        cursor.execute(f"""
            SELECT 
                t.tgname AS trigger_name,
                c.relname AS table_name,
                pg_get_triggerdef(t.oid, true) AS trigger_def
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = %s
              AND NOT t.tgisinternal
              AND c.relname IN ({placeholders})
            ORDER BY c.relname, t.tgname
        """, (schema, *tuple(table_filter)))
    else:
        cursor.execute("""
            SELECT 
                t.tgname AS trigger_name,
                c.relname AS table_name,
                pg_get_triggerdef(t.oid, true) AS trigger_def
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = %s
              AND NOT t.tgisinternal
            ORDER BY c.relname, t.tgname
        """, (schema,))
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    if not rows:
        print("No triggers found.")
        return

    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 删除触发器")
    lines.append("-- ============================================================")
    lines.append("")
    for trigger_name, table_name, _ in rows:
        lines.append(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};")
    lines.append("")
    lines.append("-- ============================================================")
    lines.append("-- 创建触发器")
    lines.append("-- ============================================================")
    lines.append("")

    for trigger_name, table_name, trigger_def in rows:
        clean_def = re.sub(rf'\b{re.escape(schema)}\.', '', trigger_def)
        lines.append(f"-- {table_name} | {trigger_name}")
        lines.append(clean_def.strip().rstrip(';') + ';')
        lines.append("")
        lines.append("")

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, '06-trigger.sql')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Generated: {output_path} ({len(rows)} triggers)")


if __name__ == '__main__':
    main()
