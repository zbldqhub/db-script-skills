import argparse
import re
import unicodedata

# 默认处理所有 cx_ 前缀的配置表；用户可通过 --tables 指定额外表
def is_default_target(table_name):
    return table_name.startswith('cx_')

def display_width(s):
    """计算字符串显示宽度：中文=2，其他=1"""
    w = 0
    for ch in s:
        ea = unicodedata.east_asian_width(ch)
        if ea in ('F', 'W'):
            w += 2
        else:
            w += 1
    return w

def parse_values(line):
    """提取 INSERT ... VALUES (...) 中括号内的字段列表"""
    m = re.search(r'^(.*?VALUES\s*\()(.+?)(\)\s*;.*)$', line, re.IGNORECASE)
    if not m:
        return None
    head, content, tail = m.group(1), m.group(2), m.group(3)
    parts = []
    current = []
    in_string = False
    quote_char = None
    i = 0
    while i < len(content):
        ch = content[i]
        if not in_string and ch in ("'", '"'):
            in_string = True
            quote_char = ch
            current.append(ch)
        elif in_string and ch == quote_char:
            # 检查转义引号
            if i + 1 < len(content) and content[i + 1] == quote_char:
                current.append(ch)
                current.append(content[i + 1])
                i += 1
            else:
                current.append(ch)
                in_string = False
                quote_char = None
        elif not in_string and ch == ',':
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        parts.append(''.join(current).strip())
    return head, parts, tail

def pad_to_width(s, width):
    """按显示宽度左对齐填充空格"""
    pad = width - display_width(s)
    if pad <= 0:
        return s
    return s + ' ' * pad

def extract_tabname(line):
    """从 delete/INSERT 语句中提取 tabname='xxx'"""
    m = re.search(r"tabname\s*=\s*'([^']+)'", line, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def align_file(filepath, target_tables=None):
    target_set = {t.lower() for t in target_tables} if target_tables else None
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    raw_lines = [line.rstrip('\n').rstrip('\r') for line in lines]

    # 1. 收集目标 INSERT 行
    insert_rows = []  # (line_index, head, parts, tail)
    max_cols = 0
    for idx, line in enumerate(raw_lines):
        table_match = re.match(r'^\s*INSERT\s+INTO\s+(\w+)', line, re.IGNORECASE)
        if not table_match:
            continue
        table_name = table_match.group(1).lower()
        is_target = (table_name in target_set) if target_set else is_default_target(table_name)
        if not is_target:
            continue
        parsed = parse_values(line)
        if parsed:
            head, parts, tail = parsed
            insert_rows.append((idx, head, parts, tail))
            max_cols = max(max_cols, len(parts))

    if not insert_rows:
        print(f"Skipped (no target INSERT lines): {filepath}")
        return

    # 计算每列最大显示宽度
    col_widths = [0] * max_cols
    for _, _, parts, _ in insert_rows:
        for i, part in enumerate(parts):
            col_widths[i] = max(col_widths[i], display_width(part))

    # 2. 重写目标 INSERT 行
    for idx, head, parts, tail in insert_rows:
        padded = []
        for i in range(max_cols):
            if i < len(parts):
                padded.append(pad_to_width(parts[i], col_widths[i]))
            else:
                padded.append('')
        raw_lines[idx] = head + ', '.join(padded) + tail

    # 3. 规范化空行
    result = []
    prev_tabname = None
    prev_is_insert = False

    for line in raw_lines:
        stripped = line.strip()
        if stripped == '':
            continue  # 跳过原始空行，稍后重建

        current_tabname = extract_tabname(line)
        is_delete = re.match(r'^\s*delete\s+from', line, re.IGNORECASE) is not None
        is_insert = re.match(r'^\s*INSERT\s+INTO', line, re.IGNORECASE) is not None

        need_blank = False
        if is_delete:
            if result:  # 非首行
                need_blank = True
            prev_tabname = current_tabname
            prev_is_insert = False
        elif is_insert and current_tabname is not None:
            if prev_is_insert and prev_tabname is not None and prev_tabname != current_tabname:
                need_blank = True
            prev_tabname = current_tabname
            prev_is_insert = True
        else:
            # 其他行（如注释、分隔线）
            if prev_is_insert and result:
                # 在 INSERT 块后面出现其他行时，加个空行分隔更美观
                need_blank = True
            prev_is_insert = False
            prev_tabname = None

        if need_blank:
            result.append('')
        result.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        for line in result:
            f.write(line + '\n')

    print(f"Aligned: {filepath}")

def main():
    parser = argparse.ArgumentParser(
        description='Align SQL INSERT values for configuration tables (default: all cx_* tables).'
    )
    parser.add_argument('--input', action='append', help='SQL file to process (can be used multiple times)')
    parser.add_argument('--tables', help='Comma-separated list of target tables to align (overrides default cx_* behavior)')
    parser.add_argument('files', nargs='*', help='SQL files to process')
    args = parser.parse_args()
    files = []
    if args.input:
        files.extend(args.input)
    if args.files:
        files.extend(args.files)
    if not files:
        parser.print_help()
        return
    target_tables = [t.strip().lower() for t in args.tables.split(',') if t.strip()] if args.tables else None
    for filepath in files:
        align_file(filepath, target_tables=target_tables)

if __name__ == '__main__':
    main()
