# Workflow：从已有数据库初始化项目

## 触发条件

用户说"从数据库生成脚本"、"初始化项目"、"已有数据库，要生成标准目录和全量脚本"、"生成视图/触发器/存储过程"等。

## 需要收集的信息

1. **项目根目录**（`project-root`）放在哪里？
2. **单系统还是多系统？**
   - 单系统：`01-Application/` 下直接生成脚本文件
   - 多系统：`01-Application/<子系统名>/` 下分别生成脚本文件。需要列出各子系统的**名称**和对应的 **sys 码**
3. **数据库连接 URL** 和 **schema 名**（默认 `zgis`）
4. 需要按哪些 `major` 生成脚本？（如果用户不清楚，可传空，默认生成 `cx_entity.major > 0` 的所有表）
5. 是否需要同时生成 `09-data.sql`、`10-cx_func.sql`、`11-cx_plugin.sql`？
   - **默认不生成**。只有用户明确说"要系统配置脚本"时才加 `--with-config`

## 执行步骤

### 步骤1：初始化目录结构

```bash
# 单系统
python db-script-generator/scripts/init_project_dirs.py \
  --project-root "<project-root>" \
  --layout single

# 多系统
python db-script-generator/scripts/init_project_dirs.py \
  --project-root "<project-root>" \
  --layout multi \
  --systems '["15-表务&抄表管理系统","18-收费管理系统"]'
```

### 步骤2：生成全量脚本

**单系统：** 直接调用一次 `generate_db_scripts.py`

```bash
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application" \
  --schema zgis \
  --sys 0 \
  --major 90
```

**多系统：** 为每个子系统分别调用，指定各自的 `--sys`、`--major` 和 `--output-dir`

```bash
python db-script-generator/scripts/generate_db_scripts.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/01-Application/15-表务&抄表管理系统" \
  --schema zgis \
  --sys 15 \
  --major 41
```

如需同时生成 `09/10/11` 系统配置脚本，追加 `--with-config`。

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

- 单系统：`01-Application/` 下包含 `01-table.sql`（含视图）~ `11-cx_plugin.sql`
- 多系统：`01-Application/<子系统名>/` 下分别包含上述文件
