#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 PostgreSQL 生成视图全量脚本 06-views.sql。
自动处理视图依赖顺序（基视图优先）。
"""

import os
import re
import argparse
import psycopg2
from collections import defaultdict, deque


def topo_sort(views, deps):
    """
    deps: dict[view_name] = [dependency_view_names]
    Returns list sorted by dependency order (base views first).
    """
    in_degree = {v: 0 for v in views}
    adj = defaultdict(list)
    for v in views:
        for dep in set(deps.get(v, [])):
            if dep in in_degree and dep != v:
                adj[dep].append(v)
                in_degree[v] += 1
    q = deque([v for v in views if in_degree[v] == 0])
    result = []
    while q:
        v = q.popleft()
        result.append(v)
        for nxt in adj[v]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                q.append(nxt)
    # append any remaining (cycles)
    for v in views:
        if v not in result:
            result.append(v)
    return result


def main():
    parser = argparse.ArgumentParser(description='Generate 06-views.sql from PostgreSQL.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--output-dir', required=True, help='Usually <project-root>/01-Application/')
    parser.add_argument('--schema', default='zgis')
    args = parser.parse_args()

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()
    schema = args.schema

    # 1. 获取所有视图
    cursor.execute("""
        SELECT table_name, view_definition
        FROM information_schema.views
        WHERE table_schema = %s
        ORDER BY table_name
    """, (schema,))
    view_map = {row[0]: row[1] for row in cursor.fetchall()}

    if not view_map:
        cursor.close()
        conn.close()
        print("No views found.")
        return

    # 2. 获取视图之间的依赖关系
    cursor.execute("""
        SELECT DISTINCT v.table_name, u.table_name AS dependency
        FROM information_schema.view_table_usage u
        JOIN information_schema.views v
          ON u.view_name = v.table_name AND u.view_schema = v.table_schema
        WHERE v.table_schema = %s AND u.table_schema = %s
          AND u.table_name != v.table_name
    """, (schema, schema))
    all_deps = defaultdict(list)
    for view_name, dep in cursor.fetchall():
        if dep in view_map:  # 只保留视图到视图的依赖
            all_deps[view_name].append(dep)

    cursor.close()
    conn.close()

    # 3. 拓扑排序
    sorted_views = topo_sort(list(view_map.keys()), all_deps)

    lines = []
    lines.append("-- ============================================================")
    lines.append("-- 删除视图（先删依赖视图，再删基视图）")
    lines.append("-- ============================================================")
    lines.append("")
    for v in reversed(sorted_views):
        lines.append(f"DROP VIEW IF EXISTS {v};")
    lines.append("")
    lines.append("-- ============================================================")
    lines.append("-- 创建视图（先建基视图，再建依赖视图）")
    lines.append("-- ============================================================")
    lines.append("")

    for v in sorted_views:
        defn = view_map[v]
        if not defn:
            continue
        lines.append(f"-- {v}")
        # 清洗定义，去除 schema 前缀（如 zgis.xxx → xxx）
        clean_defn = re.sub(rf'\b{re.escape(schema)}\.', '', defn)
        lines.append(f"CREATE OR REPLACE VIEW {v} AS")
        lines.append(f"{clean_defn.strip().rstrip(';')};")
        lines.append("")
        lines.append("")

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, '06-views.sql')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Generated: {output_path} ({len(sorted_views)} views)")


if __name__ == '__main__':
    main()
