import psycopg2
import os
import re
import subprocess
import json
import argparse

def format_datatype(data_type, char_len, num_prec, num_scale, column_default):
    if column_default and 'nextval' in str(column_default):
        if data_type == 'integer':
            return 'serial'
        elif data_type == 'smallint':
            return 'smallserial'
        elif data_type == 'bigint':
            return 'bigserial'
    if data_type == 'character varying':
        return f'varchar({char_len})' if char_len else 'varchar'
    elif data_type == 'character':
        return f'char({char_len})' if char_len else 'char'
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
        return 'double'
    else:
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

def main():
    parser = argparse.ArgumentParser(description='Generate ER diagrams (SVG) from PostgreSQL.')
    parser.add_argument('--db-url', required=True, help='PostgreSQL connection URL')
    parser.add_argument('--output-dir', required=True, help='Output directory for SVG files')
    parser.add_argument('--schema', default='zgis', help='Database schema (default: zgis)')
    parser.add_argument('--major-map', help='Optional JSON file mapping major numbers to filenames')
    args = parser.parse_args()

    db_url = args.db_url
    output_dir = args.output_dir
    schema = args.schema

    major_to_file = {}
    if args.major_map:
        with open(args.major_map, 'r', encoding='utf-8') as f:
            major_to_file = {int(k): v for k, v in json.load(f).items()}

    print("Connecting to database...")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    cursor.execute("SELECT name, namec, major, minor FROM cx_entity WHERE major > 0 ORDER BY major, minor")
    entities = cursor.fetchall()
    entity_map = {}
    tables_by_major = {}
    for name, namec, major, minor in entities:
        entity_map[name] = (namec or name, major, minor)
        tables_by_major.setdefault(major, []).append(name)

    for major in tables_by_major.keys():
        if major not in major_to_file:
            major_to_file[major] = str(major)

    all_entity_names = set(entity_map.keys())

    cursor.execute("""
        SELECT table_name, column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, ordinal_position, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name IN (SELECT name FROM cx_entity WHERE major > 0)
        ORDER BY table_name, ordinal_position
    """, (schema,))
    col_map = {}
    for row in cursor.fetchall():
        key = (row[0], row[1])
        col_map[key] = row[2:]

    cursor.execute("""
        SELECT kcu.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu 
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s
          AND tc.table_name IN (SELECT name FROM cx_entity WHERE major > 0)
    """, (schema,))
    pk_set = set()
    for table_name, column_name in cursor.fetchall():
        pk_set.add((table_name, column_name))

    cursor.execute("""
        SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu 
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu 
          ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s
          AND tc.table_name IN (SELECT name FROM cx_entity WHERE major > 0)
    """, (schema,))
    fk_rows = cursor.fetchall()

    cursor.close()
    conn.close()

    fk_map = {}
    for table_name, column_name, foreign_table, foreign_column in fk_rows:
        fk_map[(table_name, column_name)] = foreign_table

    os.makedirs(output_dir, exist_ok=True)

    for major, filename_base in sorted(major_to_file.items()):
        tables = tables_by_major.get(major, [])
        if not tables:
            print(f"Skipping {filename_base} (no tables)")
            continue

        table_set = set(tables)
        external_tables = set()
        for (src, scol), dst in fk_map.items():
            if src in table_set and dst not in table_set:
                external_tables.add(dst)

        inferred_fk_map = {}
        for tabname in tables:
            cols = [k[1] for k in col_map.keys() if k[0] == tabname]
            for colname in cols:
                if (tabname, colname) in fk_map:
                    continue
                target, ok = infer_fk(tabname, colname, all_entity_names)
                if ok and target:
                    inferred_fk_map[(tabname, colname)] = target
                    if target not in table_set:
                        external_tables.add(target)

        all_tables_in_diagram = list(tables) + sorted(external_tables)
        diagram_set = set(all_tables_in_diagram)

        lines = ["erDiagram"]

        for tabname in all_tables_in_diagram:
            namec, _, _ = entity_map.get(tabname, (tabname, 0, 0))
            display_name = sanitize_mermaid(namec)
            lines.append(f'    {tabname}["{display_name}"] {{')

            cols = [(tabname, c) for c in [k[1] for k in col_map.keys() if k[0] == tabname]]
            cols.sort(key=lambda k: col_map[k][4] if col_map[k][4] is not None else 9999)

            for key in cols:
                data_type, char_len, num_prec, num_scale, ord_pos, column_default = col_map[key]
                dtype = format_datatype(data_type, char_len, num_prec, num_scale, column_default)
                dtype = mermaid_safe_dtype(dtype)
                colname = key[1]
                flags = []
                if key in pk_set:
                    flags.append("PK")
                is_fk = key in fk_map or key in inferred_fk_map
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
