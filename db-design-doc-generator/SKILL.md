---
name: db-design-doc-generator
description: Generate database design documentation (Excel table specs and SVG ER diagrams) from PostgreSQL databases using cx_entity / cx_fld / cx_fldvalue metadata. Use when the user asks to generate Excel design documents, ER diagrams, table structure docs, or database design deliverables from a PostgreSQL schema.
---

# Database Design Document Generator

Generate standardized database design deliverables (Excel + SVG ER diagrams) from PostgreSQL.
Designed for schemas that use `cx_entity`, `cx_fld`, `cx_fldvalue` and `information_schema` metadata.

## Prerequisites

- Python packages: `psycopg2-binary`, `openpyxl`
- For ER diagrams: `@mermaid-js/mermaid-cli` installed globally (`npm install -g @mermaid-js/mermaid-cli`)

## Bundled Scripts

- `scripts/generate_excel.py` — Generates per-subsystem `.xlsx` files. Each table becomes a sheet with 16 standard columns (`tabname`, `namec`, `colname`, `datatype`, `disporder`, `disptype`, `nullable`, `newedit`, `editable`, `indexname`, `indextype`, `indexcols`, `major_minor`, `reference`, `字典值`, `字段说明`).
- `scripts/generate_er.py` — Generates per-subsystem `.svg` ER diagrams using Mermaid. Includes real FK constraints plus heuristic inferred relationships (`glid`, `_id` suffix fields, common reference fields like `user_id`, `applyuserid`, etc.).

## Workflow

1. **Create output directories** if they do not exist:
   - `{PROJECT_ROOT}/00-Design/01-Excel`
   - `{PROJECT_ROOT}/00-Design/02-ER`

2. **Determine the database connection URL** and the target `schema` (usually `zgis`).

3. **Determine `major` mapping** (optional). The scripts group tables by `cx_entity.major`.
   - If a custom filename per major is needed (e.g., `41` → `15-表务&抄表管理系统`), create a temporary JSON mapping file and pass it via `--major-map`.
   - If omitted, filenames default to `{major}.xlsx` / `{major}.svg`.

4. **Run the Excel script**:
   ```bash
   python scripts/generate_excel.py \
     --db-url "postgresql://user:pass@host:port/dbname" \
     --output-dir "{PROJECT_ROOT}\00-Design\01-Excel" \
     --schema zgis \
     --major-map major_map.json
   ```

5. **Run the ER script**:
   ```bash
   python scripts/generate_er.py \
     --db-url "postgresql://user:pass@host:port/dbname" \
     --output-dir "{PROJECT_ROOT}\00-Design\02-ER" \
     --schema zgis \
     --major-map major_map.json
   ```

6. **Clean up** any intermediate files (e.g., `.mmd` temp files) if the ER script did not auto-remove them.

## Major Map JSON Format

```json
{
  "41": "15-表务&抄表管理系统",
  "42": "25-车辆管理系统",
  "47": "18-收费管理系统"
}
```

## Important Behavior

- **Excel**: Sheet names use `cx_entity.namec` (Chinese table name) with a 31-char limit and auto-deduplication suffixes.
- **Excel ID fields**: `id` column `namec` is forced to `ID`, and `disporder/disptype/nullable/newedit/editable` are fixed to `0,1,0,0,0`.
- **ER diagrams**: Only SVG is produced (no PNG). Datatypes with commas/parentheses are sanitized for Mermaid compatibility (e.g., `numeric(10,2)` → `numeric_10_2`).
- **ER inferred relations**: Labels ending with `*` indicate heuristic inferred relationships rather than database-level foreign keys.

## Troubleshooting

- If `mmdc` is not found, ensure `@mermaid-js/mermaid-cli` is installed globally and available on PATH.
- If Excel generation fails with `ImportError`, install missing Python packages:
  ```bash
  pip install psycopg2-binary openpyxl
  ```
