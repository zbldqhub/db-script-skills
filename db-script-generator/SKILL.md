---
name: db-script-generator
description: 根据《数据库脚本规范V1.2》从 PostgreSQL 元数据生成标准化的全量 SQL 脚本（01-table ~ 11-cx_plugin、06-views、02-Procs 下的函数/存储过程/触发器）、增量更新脚本、数据库一致性检查报告以及自动修复脚本。支持单系统与多系统两种项目布局。Use when the user asks to generate SQL installation scripts, delta upgrade scripts, database consistency checks, auto-fixes for cx_fld / cx_entity metadata, schema changes (create/alter tables), or generating views/procedures/triggers.
---

# 数据库脚本生成器

本 Skill 提供一组命令行脚本，严格遵循《数据库脚本规范 V1.2》，用于操作 PostgreSQL 数据库及其配套 SQL 脚本。所有脚本均位于 `scripts/` 目录。

## 脚本能力清单

| 脚本 | 用途 | 自由度 |
|------|------|--------|
| `init_project_dirs.py` | 初始化标准项目目录（`00-Design` ~ `06-Temp`） | 低 |
| `generate_db_scripts.py` | 从数据库元数据生成全量脚本 `01-table` ~ `11-cx_plugin` | 低 |
| `apply_schema_changes.py` | 根据 JSON 变更清单生成增量脚本 `03-Upgrade/YYYYMMDD.sql` | 低 |
| `sync_db_from_changes.py` | 将 DDL 和元数据变更实际执行到数据库（默认 dry-run） | 低 |
| `align_sql_values.py` | 对 SQL 文件中的 INSERT 语句做中文显示宽度对齐 | 低 |
| `check_db_consistency.py` | 输出数据库配置一致性检查报告 | 低 |
| `fix_cx_fld.py` | 自动修复常见配置问题（默认 dry-run） | 低 |
| `generate_views.py` | 从数据库生成视图脚本 `06-views.sql` | 低 |
| `generate_procs.py` | 从数据库生成函数/存储过程脚本 `01-procs.sql` | 低 |
| `generate_triggers.py` | 从数据库生成触发器脚本 `02-triggers.sql` | 低 |
| `run_all.py` | 读取配置文件，一键串行生成多个子系统的全量脚本 | 低 |

---

### `init_project_dirs.py`

初始化标准目录结构，支持单系统和多系统布局。

```bash
# 单系统
python scripts/init_project_dirs.py --project-root "<path>" --layout single

# 多系统
python scripts/init_project_dirs.py \
  --project-root "<path>" \
  --layout multi \
  --systems '["15-表务&抄表管理系统","18-收费管理系统"]'
```

**参数：**
- `--project-root`：项目根目录
- `--layout`：`single` 或 `multi`
- `--systems`：多系统时传入 JSON 数组（子系统名称列表）

---

### `generate_db_scripts.py`

从 PostgreSQL 元数据生成全量安装脚本。

```bash
python scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis \
  --sys 15 \
  --major 41
```

**参数：**
- `--db-url`：数据库连接 URL
- `--output-dir`：脚本输出目录
- `--schema`：目标 schema（默认 `zgis`）
- `--sys`：子系统编码
- `--major`：主类型码
- `--with-config`：（可选）同时生成 `09-data.sql`、`10-cx_func.sql`、`11-cx_plugin.sql`

---

### `apply_schema_changes.py`

读取 JSON 变更清单，生成增量升级脚本到 `03-Upgrade/YYYYMMDD.sql`。

```bash
python scripts/apply_schema_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --project-root "<project-root>" \
  --author "你的名字" \
  --changes changes.json
```

**参数：**
- `--db-url`：数据库连接 URL（用于获取当前日期）
- `--project-root`：项目根目录
- `--author`：作者名（写入增量脚本注释）
- `--changes`：JSON 变更文件路径

---

### `sync_db_from_changes.py`

将 `changes.json` 和 `table_meta.json` 描述的变更同步到数据库。默认 dry-run，确认后追加 `--apply` 执行。

```bash
# 预览
python scripts/sync_db_from_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --changes changes.json \
  --table-meta table_meta.json

# 执行
python scripts/sync_db_from_changes.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --changes changes.json \
  --table-meta table_meta.json \
  --apply
```

---

### `align_sql_values.py`

对 SQL 文件中的 `INSERT INTO ... VALUES (...)` 语句做中文显示宽度对齐，原地覆盖原文件。

```bash
# 单个文件
python scripts/align_sql_values.py --input "<path>/02-cx_fld.sql"

# 指定额外表名
python scripts/align_sql_values.py --input "<path>/02-cx_fld.sql" --tables "teacher,student"
```

**默认处理表：** `cx_fld`、`cx_fldvalue`、`cx_entity`、`cx_func`、`cx_funcgrp`、`cx_plugin`

---

### `check_db_consistency.py`

输出数据库配置一致性检查报告。本脚本**只负责检查并输出问题清单**，不会对数据库做任何修改。

检查项包括：`cx_fld` 禁忌 `id`、字段缺失/孤儿、大小写规范、`id` 主键约束、`isnum` 与数值类型匹配、`disptype` 与 `cx_fldvalue` / `timestamp` 类型匹配、时间字段是否使用 `timestamp` 等。

```bash
python scripts/check_db_consistency.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis
```

---

### `fix_cx_fld.py`

针对 `check_db_consistency.py` 发现的部分问题，自动生成修复 SQL 脚本。默认 **dry-run**，仅输出 SQL 不执行；追加 `--apply` 才会真正执行到数据库。

目前支持自动修复：字段名大小写、`id` 禁忌配置、孤儿字段清理、`sys` 同步、`isnum` 不匹配、`timestamp` 字段的 `disptype` 错误。

```bash
# 预览修复 SQL
python scripts/fix_cx_fld.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis

# 执行修复
python scripts/fix_cx_fld.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --schema zgis \
  --apply
```

---

### `generate_views.py`

从数据库生成视图全量脚本，自动处理视图依赖顺序（基视图优先创建）。

```bash
python scripts/generate_views.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis
```

输出文件：`06-views.sql`

---

### `generate_procs.py`

从数据库生成函数和存储过程全量脚本。

```bash
python scripts/generate_procs.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/02-Procs" \
  --schema zgis
```

输出文件：`01-procs.sql`

---

### `generate_triggers.py`

从数据库生成触发器全量脚本。

```bash
python scripts/generate_triggers.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/02-Procs" \
  --schema zgis
```

输出文件：`02-triggers.sql`

> **注意**：触发器通常依赖函数，因此建议先执行 `generate_procs.py`，再执行 `generate_triggers.py`。

---

### `run_all.py`

一键串行生成多个子系统的全量脚本。读取配置文件执行。

```bash
python scripts/run_all.py --config config.json
```

**配置文件格式（多系统）：**
```json
{
  "db_url": "postgresql://user:pass@host:port/dbname",
  "schema": "zgis",
  "project_root": "/path/to/project",
  "layout": "multi",
  "systems": [
    {"name": "15-表务&抄表管理系统", "sys": "15", "majors": [41, 42]},
    {"name": "18-收费管理系统", "sys": "18", "majors": [47]}
  ]
}
```

**单系统兼容格式：**
```json
{
  "db_url": "postgresql://user:pass@host:port/dbname",
  "schema": "zgis",
  "sys": "0",
  "project_root": "/path/to/project",
  "majors": [90]
}
```

---

## 规范与规则

所有数据库脚本必须遵循《数据库脚本规范 V1.2》。详细规则参见 [`references/db-rules.md`](references/db-rules.md)，包括但不限于：

- `cx_fld` 永远不要配置 `id` 字段
- 所有表必须包含 `id serial primary key`
- 字段名小写（`act%` 表除外）
- 命名规范（表、字段、视图、索引、函数等）
- 增量脚本幂等约定
