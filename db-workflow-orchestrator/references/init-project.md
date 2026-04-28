# Workflow：从已有数据库初始化项目

## 触发条件

用户说"从数据库生成脚本"、"初始化项目"、"已有数据库，要生成标准目录和全量脚本"、"生成视图/触发器/存储过程"等。

## 需要收集的信息

1. **项目根目录**（`project-root`）放在哪里？
2. **数据库连接 URL** 和 **schema 名**（默认 `zgis`）
3. 需要按哪些 `major` 生成脚本？（如果用户不清楚，可传空，默认生成 `cx_entity.major > 0` 的所有表）
4. `generate_db_scripts.py` 默认会生成 `01-table.sql`（含视图）~ `11-cx_plugin.sql` 全套脚本。若数据库中无对应数据，某些文件可能为空或不存在。

## 执行步骤

### 步骤1：初始化目录结构

```bash
python db-script-generator/scripts/init_project_dirs.py \
  --project-root "<project-root>"
```

### 步骤2：生成全量脚本

直接调用 `generate_db_scripts.py`，指定 `major`：

```bash
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis \
  --major 41
```

如果有多个 `major`，逐个执行或改用 `run_all.py`。

`generate_db_scripts.py` 默认已包含 `09-data.sql`、`10-cx_func.sql`、`11-cx_plugin.sql` 的生成。

### 步骤3：生成函数/存储过程、触发器（可选）

`generate_db_scripts.py` 在生成 `01-table.sql` 时已自动包含视图定义。

如果数据库中存在函数/存储过程和触发器，应继续生成：

```bash
# 生成函数和存储过程
python db-script-generator/scripts/generate_procs.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis

# 生成触发器（必须在函数生成之后执行）
python db-script-generator/scripts/generate_triggers.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis
```

### 步骤4（可选）：格式化对齐

对 `01-Application` 下的配置表 INSERT 进行对齐：

```bash
# Windows PowerShell 示例
Get-ChildItem "<project-root>/01-Application/*.sql" | ForEach-Object {
    python db-script-generator/scripts/align_sql_values.py --input $_.FullName
}
```

## 输出结果

`01-Application/` 下包含 `01-table.sql`（含视图）~ `11-cx_plugin.sql`
