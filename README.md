# DB Script Skills

一套面向 PostgreSQL 的数据库脚本编写与设计文档生成工具集，适用于遵循《数据库脚本规范 V1.2》的项目。全程支持单系统与多系统两种目录布局。

## 包含内容

本仓库整合了以下两部分官方 Skill，以及一个本地扩展脚本：

| 目录 | 说明 |
|------|------|
| `db-script-generator/` | **数据库脚本生成器**：从 PostgreSQL 元数据生成全量安装脚本（`01-table` ~ `11-cx_plugin`）、增量升级脚本、数据库一致性检查报告及自动修复脚本。 |
| `db-design-doc-generator/` | **数据库设计文档生成器**：根据 `cx_entity` / `cx_fld` / `cx_fldvalue` 元数据生成 Excel 表结构规格书和 SVG ER 图。 |
| `local-script-extensions/` | **本地无库脚本同步扩展**：在不连接数据库的情况下，根据 JSON 变更配置直接修改全量脚本和增量脚本。 |

---

## db-script-generator 快速开始

### 1. 初始化目录

```bash
# 单系统
python db-script-generator/scripts/init_project_dirs.py \
  --project-root "./my-project" \
  --layout single

# 多系统
python db-script-generator/scripts/init_project_dirs.py \
  --project-root "./my-project" \
  --layout multi \
  --systems '["15-表务&抄表管理系统","18-收费管理系统"]'
```

### 2. 从已有数据库生成全量脚本

```bash
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "./my-project/01-Application/15-表务&抄表管理系统" \
  --schema zgis \
  --sys 15 \
  --major 41
```

### 3. 表结构变更（生成增量 + 同步更新全量）

1. 编写 `changes.json` 描述变更（`create_table` / `add_column` / `add_fld` / `add_fldvalue` 等）。
2. 执行到数据库（dry-run 预览）：
   ```bash
   python db-script-generator/scripts/sync_db_from_changes.py \
     --db-url "postgresql://..." \
     --schema zgis \
     --changes changes.json \
     --table-meta table_meta.json
   ```
3. 生成增量脚本：
   ```bash
   python db-script-generator/scripts/apply_schema_changes.py \
     --db-url "postgresql://..." \
     --project-root "./my-project" \
     --author "你的名字" \
     --changes changes.json
   ```
4. 重新生成该子系统的全量脚本（同步骤 2）。

### 4. 格式化对齐已有 SQL

```bash
python db-script-generator/scripts/align_sql_values.py \
  --input "./my-project/01-Application/02-cx_fld.sql"
```

更多细节请参考 [`db-script-generator/SKILL.md`](db-script-generator/SKILL.md)。

---

## db-design-doc-generator 快速开始

```bash
# 生成 Excel 设计文档
python db-design-doc-generator/scripts/generate_excel.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --output "./design.xlsx"

# 生成 SVG ER 图
python db-design-doc-generator/scripts/generate_er.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --output "./er_diagram.svg"
```

更多细节请参考 [`db-design-doc-generator/SKILL.md`](db-design-doc-generator/SKILL.md)。

---

## local-script-extensions 本地无库扩展

当你**不想连接数据库**，只想根据需求直接修改本地全量脚本和增量脚本时，使用此扩展。

### 用法

```bash
python local-script-extensions/update_db_scripts.py \
  --config local-script-extensions/changes_example.json
```

### 支持的变更类型

| action | 作用 |
|--------|------|
| `add_columns` | 全量 `01-table.sql` 加字段 + 注释；增量生成 `ADD COLUMN` |
| `drop_columns` | 全量 `01-table.sql` 删字段 + 注释；增量生成 `DROP COLUMN` |
| `add_fld` | 全量 `02-cx_fld.sql` 加配置；增量生成 `delete + INSERT` |
| `remove_fld` | 全量 `02-cx_fld.sql` 删配置；增量生成 `delete` |
| `add_fldvalue` | 全量 `03-cx_fldvalue.sql` 加值域；增量生成 `delete + INSERT` |
| `remove_fldvalue` | 全量 `03-cx_fldvalue.sql` 删值域；增量生成 `delete` |

### 配置文件示例

参见 [`local-script-extensions/changes_example.json`](local-script-extensions/changes_example.json)。

---

## 目录结构

```
db-script-skills/
├── README.md
├── db-script-generator/
│   ├── SKILL.md
│   └── scripts/
│       ├── align_sql_values.py
│       ├── apply_schema_changes.py
│       ├── check_db_consistency.py
│       ├── fix_cx_fld.py
│       ├── generate_db_scripts.py
│       ├── init_project_dirs.py
│       ├── run_all.py
│       └── sync_db_from_changes.py
├── db-design-doc-generator/
│   ├── SKILL.md
│   └── scripts/
│       ├── generate_er.py
│       └── generate_excel.py
└── local-script-extensions/
    ├── update_db_scripts.py
    └── changes_example.json
```

---

## 环境要求

- Python 3.10+
- `psycopg2` 或 `psycopg2-binary`（db-script-generator / db-design-doc-generator 使用）
- `openpyxl`、`svglib` 等（设计文档生成器使用，详见各 SKILL.md）

---

## License

MIT
