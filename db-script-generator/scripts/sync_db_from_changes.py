import psycopg2
import os
import json
import argparse
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def quote_sql(val):
    if val is None:
        return 'null'
    s = str(val)
    if s.lower() == 'nan':
        return 'null'
    return "'" + s.replace("'", "''") + "'"

def get_columns(cursor, table_name):
    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (table_name,))
    return [r[0] for r in cursor.fetchall()]

def next_id_expr(table_name, id_col='id'):
    return f"nextval(pg_get_serial_sequence('{table_name}', '{id_col}'))"

def build_ddl_sql(ch, schema):
    action = ch['action']
    tabname = ch['table']
    lines = []
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
        create_sql = f"CREATE TABLE IF NOT EXISTS {schema}.{tabname} (\n" + ",\n".join(col_defs) + "\n);"
        lines.append(create_sql)
        for c in cols:
            comment = c.get('comment', c['name'])
            if c['name'].lower() == 'id':
                comment = 'ID'
            lines.append(f"COMMENT ON COLUMN {schema}.{tabname}.{c['name']} IS {quote_sql(comment)};")
    elif action == 'add_column':
        col = ch['column']
        ctype = ch['type']
        nullable = ch.get('nullable', True)
        null_str = '' if nullable else ' NOT NULL'
        lines.append(f"ALTER TABLE {schema}.{tabname} ADD COLUMN IF NOT EXISTS {col} {ctype}{null_str};")
    elif action == 'drop_column':
        lines.append(f"ALTER TABLE {schema}.{tabname} DROP COLUMN IF EXISTS {ch['column']};")
    elif action == 'alter_type':
        lines.append(f"ALTER TABLE {schema}.{tabname} ALTER COLUMN {ch['column']} TYPE {ch['new_type']};")
    elif action == 'add_index':
        idx_name = ch['index_name']
        idx_def = ch['index_def']
        lines.append(f"DROP INDEX IF EXISTS {idx_name};")
        lines.append(f"{idx_def};")
    elif action == 'drop_index':
        lines.append(f"DROP INDEX IF EXISTS {ch['index_name']};")
    return lines

def build_upsert_entity_sql(cursor, ent, schema):
    cols = get_columns(cursor, 'cx_entity')
    # cx_entity does not have a sys column in current schema
    vals = []
    for c in cols:
        if c == 'id':
            vals.append(next_id_expr('cx_entity'))
        else:
            vals.append(quote_sql(ent.get(c)))
    col_str = ', '.join(cols)
    val_str = ', '.join(vals)
    update_set = ', '.join([f"{c} = EXCLUDED.{c}" for c in cols if c not in ('id', 'name')])
    sql = f"INSERT INTO {schema}.cx_entity ({col_str}) VALUES ({val_str}) ON CONFLICT (name) DO UPDATE SET {update_set};"
    return sql

def build_fld_insert_sql(cursor, fld_data, tabname, schema):
    cols = get_columns(cursor, 'cx_fld')
    fld_defaults = {
        'disptype': '0',
        'isnum': '0',
        'disporder': '0',
        'newedit': '1',
        'editable': '1',
        'nullable': '1',
        'bzfld': '0',
        'ismcard': '0',
        'iu': '0',
        'qrylevel': '1',
    }
    vals = []
    for c in cols:
        if c == 'id':
            vals.append(next_id_expr('cx_fld'))
        elif c == 'tabname':
            vals.append(quote_sql(tabname))
        elif c == 'sys':
            vals.append(quote_sql(fld_data.get('sys', '0')))
        else:
            v = fld_data.get(c)
            if v is None and c in fld_defaults:
                v = fld_defaults[c]
            vals.append(quote_sql(v))
    col_str = ', '.join(cols)
    val_str = ', '.join(vals)
    return f"INSERT INTO {schema}.cx_fld ({col_str}) VALUES ({val_str});"

def build_fldvalue_insert_sql(cursor, fv_data, tabname, colname, schema):
    cols = get_columns(cursor, 'cx_fldvalue')
    fv_defaults = {
        'disporder': '1',
    }
    vals = []
    for c in cols:
        if c == 'id':
            vals.append(next_id_expr('cx_fldvalue'))
        elif c == 'tabname':
            vals.append(quote_sql(tabname))
        elif c == 'colname':
            vals.append(quote_sql(colname))
        elif c == 'sys':
            vals.append(quote_sql(fv_data.get('sys', '0')))
        else:
            v = fv_data.get(c)
            if v is None and c in fv_defaults:
                v = fv_defaults[c]
            vals.append(quote_sql(v))
    col_str = ', '.join(cols)
    val_str = ', '.join(vals)
    return f"INSERT INTO {schema}.cx_fldvalue ({col_str}) VALUES ({val_str});"

def main():
    parser = argparse.ArgumentParser(description='Sync DDL and metadata changes to PostgreSQL. Default dry-run; use --apply to execute.')
    parser.add_argument('--db-url', required=True)
    parser.add_argument('--schema', default='zgis')
    parser.add_argument('--changes', required=True, help='JSON file with DDL changes (supports create_table, add_column, drop_column, alter_type, add_index, drop_index)')
    parser.add_argument('--table-meta', help='JSON file with entities/flds/fldvalues to upsert')
    parser.add_argument('--apply', action='store_true', help='Actually execute SQL against the database')
    args = parser.parse_args()

    with open(args.changes, 'r', encoding='utf-8-sig') as f:
        changes = json.load(f)

    table_meta = {}
    if args.table_meta:
        with open(args.table_meta, 'r', encoding='utf-8-sig') as f:
            table_meta = json.load(f)

    conn = psycopg2.connect(args.db_url)
    cursor = conn.cursor()

    executed = []

    try:
        # DDL
        for ch in changes:
            action = ch['action']
            if action in ('add_fld', 'drop_fld', 'add_fldvalue', 'drop_fldvalue'):
                continue
            sqls = build_ddl_sql(ch, args.schema)
            for sql in sqls:
                print(f"[DRY-RUN] {sql}")
                executed.append(sql)
                if args.apply:
                    cursor.execute(sql)

        # Metadata
        if table_meta:
            # entities
            for ent in table_meta.get('entities', []):
                sql = build_upsert_entity_sql(cursor, ent, args.schema)
                print(f"[DRY-RUN] {sql}")
                executed.append(sql)
                if args.apply:
                    cursor.execute(sql)

            # flds
            for tabname, fld_rows in table_meta.get('flds', {}).items():
                # Enforce iron rule: never configure id in cx_fld
                fld_rows = [r for r in fld_rows if str(r.get('colname', '')).lower() != 'id']
                if fld_rows:
                    delete_sql = f"DELETE FROM {args.schema}.cx_fld WHERE tabname = {quote_sql(tabname)} AND colname != 'id'"
                    print(f"[DRY-RUN] {delete_sql}")
                    executed.append(delete_sql)
                    if args.apply:
                        cursor.execute(delete_sql)
                for fld in fld_rows:
                    sql = build_fld_insert_sql(cursor, fld, tabname, args.schema)
                    print(f"[DRY-RUN] {sql}")
                    executed.append(sql)
                    if args.apply:
                        cursor.execute(sql)

            # fldvalues
            for tabname, col_map in table_meta.get('fldvalues', {}).items():
                for colname, values in col_map.items():
                    delete_sql = f"DELETE FROM {args.schema}.cx_fldvalue WHERE tabname = {quote_sql(tabname)} AND colname = {quote_sql(colname)}"
                    print(f"[DRY-RUN] {delete_sql}")
                    executed.append(delete_sql)
                    if args.apply:
                        cursor.execute(delete_sql)
                    for v in values:
                        sql = build_fldvalue_insert_sql(cursor, v, tabname, colname, args.schema)
                        print(f"[DRY-RUN] {sql}")
                        executed.append(sql)
                        if args.apply:
                            cursor.execute(sql)

        if args.apply:
            conn.commit()
            print(f"\nCommitted {len(executed)} statements.")
        else:
            print(f"\nDry-run complete. {len(executed)} statements would be executed. Use --apply to commit.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        print("Transaction rolled back.")
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()
