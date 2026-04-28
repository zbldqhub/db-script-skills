import os
import argparse

def main():
    parser = argparse.ArgumentParser(description='Initialize standard database script directories per V1.2 spec.')
    parser.add_argument('--project-root', required=True, help='Project root directory (the folder that will contain 00-Design, 01-Application, etc.)')
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

    print("Done.")

if __name__ == '__main__':
    main()
