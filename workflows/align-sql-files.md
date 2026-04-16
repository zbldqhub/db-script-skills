# Workflow：批量格式化对齐已有 SQL 脚本

## 触发条件

用户说"格式化 SQL"、"对齐脚本"、"整理 INSERT"、"排版 SQL 文件"、"批量对齐"、"美化 sql"等。

## 需要收集的信息

1. **目标类型**：是单个文件，还是一个目录？
2. **目标路径**：文件或目录的完整路径
3. 是否需要限定处理的表？（默认处理所有 `cx_` 前缀配置表）

## 核心规则

- `align_sql_values.py` 默认只处理 **配置表** 的 INSERT 语句：
  `cx_fld`、`cx_fldvalue`、`cx_entity`、`cx_func`、`cx_funcgrp`、`cx_plugin`、`cx_sysdef`、`cx_syscfg`、`cx_layer`、`cx_maplayer`、`cx_mapservice`、`cx_sqlexp`、`cx_sqlpro`、`cx_userhabit`
- **不要**对测试数据表、日志表、大量业务数据表的 INSERT 使用该脚本对齐。
- 如需额外指定其他表，使用 `--tables` 参数：`--tables "teacher,student"`

## 执行步骤

### 方案 A：单个文件

```bash
python db-script-generator/scripts/align_sql_values.py \
  --input "D:\project\01-Application\02-cx_fld.sql"
```

### 方案 B：批量对齐整个目录（Windows PowerShell）

```powershell
Get-ChildItem "D:\project\01-Application\*.sql" | ForEach-Object {
    python db-script-generator/scripts/align_sql_values.py --input $_.FullName
}
```

### 方案 C：批量对齐整个目录（CMD）

```cmd
for %f in ("D:\project\01-Application\*.sql") do python db-script-generator/scripts/align_sql_values.py --input "%f"
```

### 方案 D：指定额外表名对齐

```bash
python db-script-generator/scripts/align_sql_values.py \
  --input "D:\project\01-Application\09-data.sql" \
  --tables "teacher,student,cx_fld,cx_fldvalue"
```

## 输出结果

- 脚本为**原地修改**（in-place），会直接覆盖传入的文件内容。
- 所有目标表内的 INSERT 语句会按中文显示宽度做列对齐。
- 不同 `tabname` 的 INSERT 块之间会自动插入空行分隔。
