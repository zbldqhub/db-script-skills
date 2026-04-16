import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DESIGN_SCRIPT_DIR = os.path.join(os.path.expanduser('~'), '.agents', 'skills', 'db-design-doc-generator', 'scripts')

def run_cmd(cmd_list, description):
    print(f"\n>>> {description}")
    print(" ".join(cmd_list))
    result = subprocess.run(cmd_list, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='One-shot generation of all database design deliverables per V1.2 spec.')
    parser.add_argument('--config', required=True, help='Path to JSON config file')
    args = parser.parse_args()

    with open(args.config, 'r', encoding='utf-8-sig') as f:
        cfg = json.load(f)

    db_url = cfg['db_url']
    schema = cfg.get('schema', 'zgis')
    project_root = cfg['project_root']
    major_map = cfg.get('major_map', {})
    layout = cfg.get('layout', 'single')

    # Normalize systems configuration (support both old flat majors and new systems array)
    systems = cfg.get('systems', [])
    if not systems and cfg.get('majors'):
        systems = [{
            'name': '',
            'sys': cfg.get('sys', '0'),
            'majors': cfg['majors']
        }]

    db_root = project_root
    er_dir = os.path.join(db_root, '00-Design')
    check_dir = os.path.join(db_root, 'CheckReports')

    # 1. Init directories
    init_cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, 'init_project_dirs.py'),
        '--project-root', db_root,
        '--layout', layout
    ]
    if layout == 'multi' and systems:
        init_cmd += ['--systems', json.dumps([s['name'] for s in systems])]
    run_cmd(init_cmd, "Initializing project directories")

    os.makedirs(check_dir, exist_ok=True)
    os.makedirs(er_dir, exist_ok=True)

    # 2. Consistency check
    report_path = os.path.join(check_dir, f"consistency_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql")
    run_cmd([
        sys.executable,
        os.path.join(SCRIPT_DIR, 'check_db_consistency.py'),
        '--db-url', db_url,
        '--schema', schema,
        '--output', report_path
    ], "Running database consistency check")

    major_map_path = None
    if major_map:
        fd, major_map_path = tempfile.mkstemp(suffix='.json')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(major_map, f, ensure_ascii=False)

    major_map_args = ['--major-map', major_map_path] if major_map_path else []

    # 3. Generate SQL scripts per system / major
    for system in systems:
        sys_name = system.get('name', '')
        sys_num = system.get('sys', '0')
        sys_majors = system.get('majors', [])
        sql_dir = os.path.join(db_root, '01-Application', sys_name) if sys_name else os.path.join(db_root, '01-Application')
        os.makedirs(sql_dir, exist_ok=True)
        for major in sys_majors:
            run_cmd([
                sys.executable,
                os.path.join(SCRIPT_DIR, 'generate_db_scripts.py'),
                '--db-url', db_url,
                '--output-dir', sql_dir,
                '--schema', schema,
                '--sys', str(sys_num),
                '--major', str(major)
            ], f"Generating SQL scripts for system={sys_name or 'default'}, major={major}")

    # 4. Generate Excel (optional)
    excel_out = cfg.get('excel_dir', os.path.join(db_root, '00-Design', '01-Excel'))
    if os.path.exists(os.path.join(DB_DESIGN_SCRIPT_DIR, 'generate_excel.py')):
        os.makedirs(excel_out, exist_ok=True)
        run_cmd([
            sys.executable,
            os.path.join(DB_DESIGN_SCRIPT_DIR, 'generate_excel.py'),
            '--db-url', db_url,
            '--output-dir', excel_out,
            '--schema', schema
        ] + major_map_args, "Generating Excel design documents")
    else:
        print("Warning: generate_excel.py not found, skipping Excel generation.")

    # 5. Generate ER diagrams (optional)
    if os.path.exists(os.path.join(DB_DESIGN_SCRIPT_DIR, 'generate_er.py')):
        run_cmd([
            sys.executable,
            os.path.join(DB_DESIGN_SCRIPT_DIR, 'generate_er.py'),
            '--db-url', db_url,
            '--output-dir', er_dir,
            '--schema', schema
        ] + major_map_args, "Generating ER diagrams")
    else:
        print("Warning: generate_er.py not found, skipping ER generation.")

    if major_map_path and os.path.exists(major_map_path):
        os.remove(major_map_path)

    print("\n========================================")
    print("All deliverables generated successfully.")
    print(f"SQL   : {sql_dir}")
    print(f"ER    : {er_dir}")
    print(f"Excel : {excel_out}")
    print(f"Report: {report_path}")
    print("========================================")

if __name__ == '__main__':
    main()
