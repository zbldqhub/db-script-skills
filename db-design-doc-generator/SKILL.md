---
name: db-design-doc-generator
description: Generate database design documentation (Excel table specs and SVG ER diagrams) from PostgreSQL databases or from existing full SQL script directories. Also supports generating full SQL scripts from Excel design documents. Use when the user asks to generate Excel design documents, ER diagrams, table structure docs, or database design deliverables from a PostgreSQL schema or SQL scripts; or when converting Excel specs back into SQL scripts.
---

# 数据库设计文档生成器

本 Skill 提供脚本，用于在 PostgreSQL 数据库、全量 SQL 脚本、Excel 设计文档三者之间进行转换：

- **数据库 → Excel / ER 图**
- **全量 SQL 脚本 → Excel / ER 图**
- **Excel 设计文档 → 全量 SQL 脚本**

## 前置依赖

- Python 包：`psycopg2-binary`、`openpyxl`
- ER 图生成（可选）：`@mermaid-js/mermaid-cli` 全局安装（`npm install -g @mermaid-js/mermaid-cli`）

## 脚本能力清单

| 脚本 | 用途 | 输入 | 输出 | 自由度 |
|------|------|------|------|--------|
| `generate_excel.py` | 从 PostgreSQL 按 major 分组生成 `.xlsx` | 数据库 | Excel | 低 |
| `generate_er.py` | 从 PostgreSQL 按 major 分组生成 `.svg` | 数据库 | SVG | 低 |
| `generate_excel_from_sql.py` | 从全量 SQL 脚本目录生成 `.xlsx` | `01-table.sql` ~ `05-index.sql` | Excel | 低 |
| `generate_er_from_sql.py` | 从全量 SQL 脚本目录生成 `.svg` | `01-table.sql` ~ `05-index.sql` | SVG | 低 |
| `generate_sql_from_excel.py` | 从 Excel 设计文档反向生成全量 SQL 脚本 | `.xlsx` | `01-table.sql` ~ `05-index.sql` | 低 |

---

### `generate_excel.py`

按 `cx_entity.major` 分组，每个 major 生成一个 `.xlsx` 文件。

```bash
python scripts/generate_excel.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/00-Design/01-Excel" \
  --schema zgis \
  --major-map major_map.json
```

**参数：**
- `--db-url`：数据库连接 URL
- `--output-dir`：输出目录
- `--schema`：目标 schema（默认 `zgis`）
- `--major-map`：（可选）major 到文件名的映射 JSON

**输出特性：**
- Sheet 名使用 `cx_entity.namec`（限 31 字符，自动去重加后缀）
- `id` 列的 `namec` 强制为 `ID`
- `id` 列的 `disporder/disptype/nullable/newedit/editable` 固定为 `0,1,0,0,0`

---

### `generate_er.py`

按 `cx_entity.major` 分组，每个 major 生成一个 `.svg` ER 图。

```bash
python scripts/generate_er.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/00-Design/02-ER" \
  --schema zgis \
  --major-map major_map.json
```

**输出特性：**
- 仅输出 SVG（无 PNG）
- 数据类型中的逗号/括号会清洗为 Mermaid 安全格式
- 关系线来源：真实外键约束 + 启发式推断
- 带 `*` 标签的连线表示启发式推断关系

---

### `generate_excel_from_sql.py`

从本地全量 SQL 脚本目录解析表结构、字段注释、索引、值域、实体元数据，生成 Excel 设计文档。

```bash
python scripts/generate_excel_from_sql.py \
  --input-dir "<project-root>/01-Application" \
  --output-dir "<project-root>/00-Design/01-Excel" \
  --major-map major_map.json
```

**输入要求：** `input-dir` 下必须包含：
- `01-table.sql`
- `02-cx_fld.sql`（可选）
- `03-cx_fldvalue.sql`（可选）
- `04-cx_entity.sql`（可选，用于表中文名和 major/minor）
- `05-index.sql`（可选）

**输出特性：**
- 列结构与 `generate_excel.py` 完全一致
- `reference` 列来源于 `01-table.sql` 中的显式 `FOREIGN KEY` 约束
- `字典值` 列来源于 `03-cx_fldvalue.sql`

---

### `generate_er_from_sql.py`

从本地全量 SQL 脚本目录生成 SVG ER 图。

```bash
python scripts/generate_er_from_sql.py \
  --input-dir "<project-root>/01-Application" \
  --output-dir "<project-root>/00-Design/02-ER" \
  --major-map major_map.json
```

**特性：**
- 同时解析显式外键约束和启发式推断关系
- 生成逻辑与 `generate_er.py` 保持一致

---

### `generate_sql_from_excel.py`

从 Excel 设计文档反向生成全量 SQL 脚本（`01-table` ~ `05-index`）。适用于以 Excel 为设计源头的场景。

```bash
python scripts/generate_sql_from_excel.py \
  --input "<project-root>/00-Design/01-Excel/design.xlsx" \
  --output-dir "<project-root>/01-Application" \
  --sys "0"
```

**参数：**
- `--input`：输入 Excel 文件路径，或包含多个 `.xlsx` 的目录
- `--output-dir`：SQL 脚本输出目录
- `--sys`：`cx_fld` / `cx_fldvalue` 的默认 `sys` 值（默认 `0`）
- `--entity-defaults`：（可选）JSON 文件，提供 `cx_entity` 除 `name/namec/major/minor` 外的其他列默认值

**Excel 规范要求：**
- 每个表独占一个 sheet，sheet 名为表中文名（`namec`）
- 表头必须包含以下 16 列：
  `tabname`, `namec`, `colname`, `datatype`, `disporder`, `disptype`, `nullable`, `newedit`, `editable`, `indexname`, `indextype`, `indexcols`, `major_minor`, `reference`, `字典值`, `字段说明`
- `major_minor` 格式：`major@minor`，如 `41@1`
- `reference` 格式：`othertable(othercol)`
- `字典值` 格式：`0=正常; 1=停用`

**生成规则：**
- 如果 Excel 中没有 `id` 字段，自动生成 `id serial primary key`
- `id` 字段不会出现在 `02-cx_fld.sql` 中
- 索引按 `indexname` 去重，生成到 `05-index.sql`
- 外键约束生成到 `01-table.sql`
- `cx_entity` 的默认列值为：`type=1, domains=1, glmaj=0, glmin=0, log=0`

**`entity-defaults` JSON 示例：**
```json
{
  "type": "1",
  "domains": "1",
  "glmaj": "0",
  "glmin": "0",
  "log": "0"
}
```

---

## Major Map JSON 格式

```json
{
  "41": "15-表务&抄表管理系统",
  "42": "25-车辆管理系统",
  "47": "18-收费管理系统"
}
```

若未提供 `--major-map`，文件名默认为 `{major}.xlsx` / `{major}.svg`。

---

## 故障排查

- `mmdc` 未找到：确保 `@mermaid-js/mermaid-cli` 已全局安装且在 PATH 中
- Excel 生成报错 `ImportError`：安装缺失的 Python 包
  ```bash
  pip install psycopg2-binary openpyxl
  ```
