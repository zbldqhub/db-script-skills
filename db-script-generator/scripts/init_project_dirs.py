import os
import argparse
import json

def main():
    parser = argparse.ArgumentParser(description='Initialize standard database script directories per V1.2 spec.')
    parser.add_argument('--project-root', required=True, help='Project root directory (the folder that will contain 00-Design, 01-Application, etc.)')
    parser.add_argument('--layout', default='single', choices=['single', 'multi'], help='Directory layout: single system or multiple subsystems')
    parser.add_argument('--systems', help='JSON array of subsystem names, required when layout=multi. Example: ["15-表务&抄表管理系统","18-收费管理系统"]')
    args = parser.parse_args()

    base = args.project_root

    dirs = [
        os.path.join(base, '00-Design'),
        os.path.join(base, '01-Application'),
        os.path.join(base, '02-Procs'),
        os.path.join(base, '03-Upgrade'),
        os.path.join(base, '04-Release'),
        os.path.join(base, '05-TestData'),
        os.path.join(base, '06-Temp'),
    ]

    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"Created: {d}")

    if args.layout == 'multi':
        if not args.systems:
            print("ERROR: --systems is required when layout=multi")
            return
        systems = json.loads(args.systems)
        for sys_name in systems:
            sys_dir = os.path.join(base, '01-Application', sys_name)
            os.makedirs(sys_dir, exist_ok=True)
            print(f"Created: {sys_dir}")

    print("Done.")

if __name__ == '__main__':
    main()
