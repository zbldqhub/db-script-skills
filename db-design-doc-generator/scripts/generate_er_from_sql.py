#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从全量 SQL 脚本目录解析并生成 SVG ER 图。
"""

import os
import re
import json
import argparse
import subprocess


def format_datatype(data_type):
    # SQL 脚本中已经存储了清洗后的类型名，这里只做简单标准化
    dt = data_type.lower()
    if dt == 'timestamp without time zone':
        return 'timestamp'
    if dt == 'timestamp with time zone':
        return 'timestamptz'
    if dt == 'double precision':
        return 'double'
    return data_type


def mermaid_safe_dtype(dtype):
    return re.sub(r'[^a-zA-Z0-9_]', '_', dtype)


def sanitize_mermaid(text):
    return text.replace('"', '\\"')


def infer_fk(tabname, colname, all_tables_set):
    col_lower = colname.lower()

    if col_lower in ('applyuserid', 'create_userid', 'inpuserid', 'userid', 'user_id'):
        if 'cx_user' in all_tables_set:
            return 'cx_user', True
    if col_lower == 'groupid' and 'cx_sysgroup' in all_tables_set:
        return 'cx_sysgroup', True
    if col_lower == 'roleid' and 'cx_sysrole' in all_tables_set:
        return 'cx_sysrole', True
    if col_lower == 'organid' and 'cx_organ' in all_tables_set:
        return 'cx_organ', True

    if col_lower == 'glid':
        suffixes = ['_detail', '_record', '_payment_terms']
        for suffix in suffixes:
            if tabname.endswith(suffix):
                parent = tabname[:-len(suffix)]
                if parent in all_tables_set:
                    return parent, True
        if tabname.startswith('afi_') and tabname != 'afi_information' and 'afi_information' in all_tables_set:
            return 'afi_information', True
        if tabname.startswith('hl_') and tabname != 'hl_indicator' and 'hl_indicator' in all_tables_set:
            return 'hl_indicator', True
        if tabname.startswith('sc_model_') and 'sc_model' in all_tables_set:
            return 'sc_model', True
        if tabname.startswith('rv_') and tabname not in ('rv_communities', 'rv_price_basic'):
            if 'rv_communities' in all_tables_set:
                return 'rv_communities', True
            if 'rv_price_basic' in all_tables_set:
                return 'rv_price_basic', True
        if tabname in ('wg_gd_area', 'wg_qx_area') and 'wg_area' in all_tables_set:
            return 'wg_area', True
        if tabname == 'mr_ticket' and 'mr_meter_basic_info' in all_tables_set:
            return 'mr_meter_basic_info', True
        if tabname in ('dma_rtudata', 'dma_rtudata_his') and 'dma_rtu_device' in all_tables_set:
            return 'dma_rtu_device', True
        if tabname == 'gsrtureplac' and 'gsrtudev' in all_tables_set:
            return 'gsrtudev', True
        if tabname in ('gsrwaquadata', 'gsrwaquadatahis') and 'gsaquamonit' in all_tables_set:
            return 'gsaquamonit', True
        if tabname in ('gsrwaquadata', 'gsrwaquadatahis') and 'gsmonitsite' in all_tables_set:
            return 'gsmonitsite', True

    if col_lower == 'parent_id':
        return tabname, True

    if col_lower.endswith('_id') and col_lower != 'id':
        prefix = col_lower[:-3]
        if prefix in all_tables_set:
            return prefix, True
        candidates = [t for t in all_tables_set if prefix in t.lower() and t != tabname]
        if candidates:
            candidates.sort(key=lambda t: (abs(len(t) - len(prefix)), t))
            return candidates[0], True

    if col_lower == 'client_id' and 'cx_apps' in all_tables_set:
        return 'cx_apps', True
    if col_lower == 'dirid' and 'cx_docdir' in all_tables_set:
        return 'cx_docdir', True
    if col_lower == 'entityid' and 'cx_entity' in all_tables_set:
        return 'cx_entity', True
    if col_lower == 'rtuid' and 'gsrtudev' in all_tables_set:
        return 'gsrtudev', True
    if col_lower == 'zone_id' and 'dma_zone' in all_tables_set:
        return 'dma_zone', True
    if col_lower == 'device_id':
        candidates = [t for t in all_tables_set if 'device' in t.lower() and t != tabname]
        if candidates:
            candidates.sort(key=lambda t: (abs(len(t) - len('device')), t))
            return candidates[0], True
    if col_lower in ('meterid', 'meter_id'):
        candidates = [t for t in all_tables_set if 'meter' in t.lower() and t != tabname]
        if candidates:
            candidates.sort(key=lambda t: (abs(len(t) - len('meter')), t))
            return candidates[0], True
    if col_lower in ('customerid', 'customer_id', 'correlativeid'):
        if 'customerinfo' in all_tables_set:
            return 'customerinfo', True
    if col_lower == 'type_id':
        candidates = [t for t in all_tables_set if 'type' in t.lower() and t != tabname]
        if candidates:
            candidates.sort(key=lambda t: (abs(len(t) - len('type')), t))
            return candidates[0], True
    if col_lower == 'warehouse_id':
        candidates = [t for t in all_tables_set if 'warehouse' in t.lower() and t != tabname]
        if candidates:
            return candidates[0], True
    if col_lower == 'driver_id':
        candidates = [t for t in all_tables_set if 'driver' in t.lower() and t != tabname]
        if candidates:
            return candidates[0], True
    if col_lower == 'manager_id':
        candidates = [t for t in all_tables_set if 'manager' in t.lower() and t != tabname]
        if candidates:
            return candidates[0], True
    if col_lower == 'dispatch_id':
        candidates = [t for t in all_tables_set if 'dispatch' in t.lower() and t != tabname]
        if candidates:
            return candidates[0], True
    if col_lower == 'shift_id':
        candidates = [t for t in all_tables_set if 'shift' in t.lower() and t != tabname]
        if candidates:
            return candidates[0], True
    if col_lower == 'dispatch_record_id':
        candidates = [t for t in all_tables_set if 'dispatch_record' in t.lower() and t != tabname]
        if candidates:
            return candidates[0], True
    if col_lower in ('eqpid', 'equipment_id'):
        candidates = [t for t in all_tables_set if ('eqp' in t.lower() or 'equipment' in t.lower()) and t != tabname]
        if candidates:
            candidates.sort(key=lambda t: (abs(len(t) - len('type')), t))
            return candidates[0], True
    if col_lower == 'prjid':
        candidates = [t for t in all_tables_set if ('project' in t.lower() or t.lower().startswith('prj')) and t != tabname]
        if candidates:
            candidates.sort(key=lambda t: (abs(len(t) - len('type')), t))
            return candidates[0], True
    if col_lower == 'linid' and 'lin' in all_tables_set:
        return 'lin', True
    if col_lower == 'pntid' and 'pnt' in all_tables_set:
        return 'pnt', True
    if col_lower == 'topic_config_id' and 'iot_topic_config' in all_tables_set:
        return 'iot_topic_config', True

    return None, False


def parse_create_table(sql_content):
    """
    解析 01-table.sql 内容，返回 {
      tabname: {
        'columns': [{name, datatype, pk}, ...],
        'pk_cols': [],
        'fks': [(col, ft, fc)]
      }
    }
    """
    tables = {}
    for m in re.finditer(
        r'^\s*create\s+table\s+(\w+)\s*\((.*?)\);',
        sql_content, re.IGNORECASE | re.DOTALL | re.MULTILINE
    ):
        tabname = m.group(1)
        body = m.group(2)
        lines = [ln.strip() for ln in body.split('\n') if ln.strip()]

        cols = []
        pk_cols = []
        fks = []

        for line in lines:
            line = line.rstrip(',').strip()
            if not line:
                continue

            # 约束行
            if re.match(r'^CONSTRAINT\s+', line, re.IGNORECASE):
                pk_m = re.match(r'^CONSTRAINT\s+\w+\s+PRIMARY\s+KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
                if pk_m:
                    pk_cols = [c.strip() for c in pk_m.group(1).split(',')]
                    continue
                fk_m = re.match(r'^CONSTRAINT\s+\w+\s+FOREIGN\s+KEY\s*\((\w+)\)\s+REFERENCES\s+(\w+)\s*\((\w+)\)', line, re.IGNORECASE)
                if fk_m:
                    fks.append((fk_m.group(1), fk_m.group(2), fk_m.group(3)))
                    continue
                continue

            # 字段定义行
            fm = re.match(r'^(\w+)\s+(.+)$', line, re.IGNORECASE)
            if not fm:
                continue
            colname = fm.group(1)
            rest = fm.group(2).strip()

            pk = False
            if re.search(r'\bprimary\s+key\b', rest, re.IGNORECASE):
                pk = True
                rest = re.sub(r'\bprimary\s+key\b', '', rest, flags=re.IGNORECASE).strip()
                if not pk_cols:
                    pk_cols = [colname]

            rest = re.sub(r'\bnot\s+null\b', '', rest, flags=re.IGNORECASE).strip()
            rest = re.sub(r'\bnull\b', '', rest, flags=re.IGNORECASE).strip()
            rest = rest.rstrip(',').strip()
            datatype = rest

            cols.append({'name': colname, 'datatype': datatype, 'pk': pk})

        tables[tabname] = {'columns': cols, 'pk_cols': pk_cols, 'fks': fks}
    return tables


def parse_cx_entity(filepath):
    """解析 04-cx_entity.sql，返回 {tabname: namec}"""
    entity_map = {}
    if not os.path.exists(filepath):
        return entity_map
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r"^\s*INSERT\s+INTO\s+cx_entity\s*\(([^)]+)\)\s*VALUES\s*\((.+)\)\s*;", line, re.IGNORECASE)
            if m:
                cols = [c.strip().strip('"').strip("'") for c in m.group(1).split(',')]
                parts = m.group(2).split(',')
                if len(cols) == len(parts):
                    mapping = dict(zip(cols, parts))
                else:
                    mapping = {}
                tabname = mapping.get('name', parts[0] if parts else '').strip().strip("'")
                namec = mapping.get('namec', parts[1] if len(parts) > 1 else '').strip().strip("'")
                if tabname:
                    entity_map[tabname] = namec
    return entity_map


def main():
    parser = argparse.ArgumentParser(description='Generate ER diagrams (SVG) from full SQL scripts.')
    parser.add_argument('--input-dir', required=True, help='Directory containing 01-table.sql ~ 05-index.sql')
    parser.add_argument('--output-dir', required=True, help='Output directory for SVG files')
    parser.add_argument('--major-map', help='Optional JSON file mapping major numbers to filenames')
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir

    major_to_file = {}
    if args.major_map:
        with open(args.major_map, 'r', encoding='utf-8') as f:
            major_to_file = {int(k): v for k, v in json.load(f).items()}

    table_sql_path = os.path.join(input_dir, '01-table.sql')
    entity_sql_path = os.path.join(input_dir, '04-cx_entity.sql')

    with open(table_sql_path, 'r', encoding='utf-8') as f:
        tables = parse_create_table(f.read())

    entity_map = parse_cx_entity(entity_sql_path)

    # 按 major 分组（尝试从 cx_entity.sql 第5列解析 major）
    tables_by_major = {}
    for tabname in tables:
        major = 0
        if os.path.exists(entity_sql_path):
            with open(entity_sql_path, 'r', encoding='utf-8') as f:
                for line in f:
                    m = re.match(r"^\s*INSERT\s+INTO\s+cx_entity\s*\([^)]+\)\s*VALUES\s*\((.+)\)\s*;", line, re.IGNORECASE)
                    if m:
                        parts = m.group(1).split(',')
                        if len(parts) >= 5:
                            t = parts[0].strip().strip("'")
                            if t == tabname:
                                try:
                                    major = int(parts[3].strip().strip("'"))
                                except (ValueError, TypeError):
                                    major = 0
                                break
        tables_by_major.setdefault(major, []).append(tabname)
        if major not in major_to_file:
            major_to_file[major] = str(major)

    all_entity_names = set(tables.keys())

    os.makedirs(output_dir, exist_ok=True)

    for major, filename_base in sorted(major_to_file.items()):
        table_list = tables_by_major.get(major, [])
        if not table_list:
            print(f"Skipping {filename_base} (no tables)")
            continue

        table_set = set(table_list)
        external_tables = set()

        # 显式外键
        fk_map = {}
        for tabname in table_list:
            for fc, ft, fcol in tables[tabname]['fks']:
                fk_map[(tabname, fc)] = ft
                if ft not in table_set:
                    external_tables.add(ft)

        # 启发式推断外键
        inferred_fk_map = {}
        for tabname in table_list:
            for col in tables[tabname]['columns']:
                colname = col['name']
                if (tabname, colname) in fk_map:
                    continue
                target, ok = infer_fk(tabname, colname, all_entity_names)
                if ok and target:
                    inferred_fk_map[(tabname, colname)] = target
                    if target not in table_set:
                        external_tables.add(target)

        all_tables_in_diagram = list(table_list) + sorted(external_tables)
        diagram_set = set(all_tables_in_diagram)

        lines = ["erDiagram"]

        for tabname in all_tables_in_diagram:
            display_name = sanitize_mermaid(entity_map.get(tabname, tabname))
            lines.append(f'    {tabname}["{display_name}"] {{')

            for col in tables.get(tabname, {}).get('columns', []):
                dtype = format_datatype(col['datatype'])
                dtype = mermaid_safe_dtype(dtype)
                colname = col['name']
                flags = []
                if col.get('pk'):
                    flags.append("PK")
                is_fk = (tabname, colname) in fk_map or (tabname, colname) in inferred_fk_map
                if is_fk:
                    flags.append("FK")
                flag_str = " ".join(flags)
                lines.append(f'        {dtype} {colname} {flag_str}')
            lines.append("    }")

        drawn = set()
        for (src, scol), dst in fk_map.items():
            if src in table_set and dst in diagram_set:
                label = sanitize_mermaid(scol)
                rel = f'    {src} }}|--|| {dst} : "{label}"'
                lines.append(rel)
                drawn.add((src, dst, scol))

        for (src, scol), dst in inferred_fk_map.items():
            if src in table_set and dst in diagram_set:
                if (src, dst, scol) in drawn:
                    continue
                label = sanitize_mermaid(scol) + "*"
                rel = f'    {src} }}|--|| {dst} : "{label}"'
                lines.append(rel)
                drawn.add((src, dst, scol))

        mmd_content = "\n".join(lines)
        mmd_path = os.path.join(output_dir, f"{filename_base}.mmd")
        svg_path = os.path.join(output_dir, f"{filename_base}.svg")

        with open(mmd_path, 'w', encoding='utf-8') as f:
            f.write(mmd_content)

        print(f"Generated {mmd_path}")

        cmd_svg = f'mmdc -i "{mmd_path}" -o "{svg_path}" -b white'
        try:
            result = subprocess.run(cmd_svg, capture_output=True, text=True, timeout=180, shell=True)
            if result.returncode == 0:
                print(f"  -> SVG saved: {svg_path}")
            else:
                print(f"  -> ERROR generating SVG: {result.stderr}")
        except Exception as e:
            print(f"  -> EXCEPTION: {e}")

    # cleanup intermediate mmd files
    for major, filename_base in sorted(major_to_file.items()):
        mmd_path = os.path.join(output_dir, f"{filename_base}.mmd")
        if os.path.exists(mmd_path):
            os.remove(mmd_path)

    print("Done.")


if __name__ == '__main__':
    main()
