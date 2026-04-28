#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 PostgreSQL 生成函数和存储过程全量脚本 02-Procs/01-procs.sql。
"""

import os
import re
import argparse
import psycopg2


def main():
    parser = argparse.ArgumentParser(description='Generate 01-procs.sql from PostgreSQL.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--output-dir', required=True, help='Usually <project-root>/02-Procs/')
    parser.add_argument('--schema', default='zgis')
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()
    schema = args.schema

    cursor.execute("""
        SELECT p.oid, p.proname, pg_get_function_identity_arguments(p.oid) AS args, p.prokind
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = %s
        ORDER BY p.prokind, p.proname
    """, (schema,))
    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    if not rows:
        print("No functions or procedures found.")
        return

    funcs = [(r[1], r[2], r[3]) for r in rows if r[3] == 'f']
    procs = [(r[1], r[2], r[3]) for r in rows if r[3] == 'p']

    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 删除函数")
    lines.append("-- ============================================================")
    lines.append("")
    for name, fargs, _ in funcs:
        lines.append(f"DROP FUNCTION IF EXISTS {name}({fargs});")
    if funcs:
        lines.append("")

    if procs:
        lines.append("-- ============================================================")
        lines.append("-- 删除存储过程")
        lines.append("-- ============================================================")
        lines.append("")
        for name, fargs, _ in procs:
            lines.append(f"DROP PROCEDURE IF EXISTS {name}({fargs});")
        lines.append("")

    lines.append("-- ============================================================")
    lines.append("-- 创建函数")
    lines.append("-- ============================================================")
    lines.append("")

    conn2 = psycopg2.connect(args.db_url)
    cur2 = conn2.cursor()

    for name, fargs, kind in funcs:
        cur2.execute("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = %s AND prokind = 'f' LIMIT 1", (name,))
        defn = cur2.fetchone()[0]
        clean_defn = re.sub(rf'\b{re.escape(schema)}\.', '', defn)
        lines.append(f"-- {name}")
        lines.append(clean_defn.strip().rstrip(';') + ';')
        lines.append("")
        lines.append("")

    if procs:
        lines.append("-- ============================================================")
        lines.append("-- 创建存储过程")
        lines.append("-- ============================================================")
        lines.append("")
        for name, fargs, kind in procs:
            cur2.execute("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = %s AND prokind = 'p' LIMIT 1", (name,))
            defn = cur2.fetchone()[0]
            clean_defn = re.sub(rf'\b{re.escape(schema)}\.', '', defn)
            lines.append(f"-- {name}")
            lines.append(clean_defn.strip().rstrip(';') + ';')
            lines.append("")
            lines.append("")

    cur2.close()
    conn2.close()

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, '07-functions.sql')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Generated: {output_path} ({len(funcs)} functions, {len(procs)} procedures)")


if __name__ == '__main__':
    main()
