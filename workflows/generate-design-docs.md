# Workflow：生成数据库设计文档

## 触发条件

用户说"生成设计文档"、"出 Excel"、"画 ER 图"、"表结构文档"、"数据库设计交付物"等。

## 需要收集的信息

1. **数据来源**：
   - **方案 A**：从 PostgreSQL 数据库生成（需要数据库连接信息）
   - **方案 B**：从本地全量 SQL 脚本生成（需要提供脚本目录）
2. **项目根目录**（用于确定输出目录 `00-Design/01-Excel` 和 `00-Design/02-ER`）
3. 是否需要自定义 `major-map`？
   - 如果需要按子系统名称命名文件（如 `41` → `15-表务&抄表管理系统`），则创建 `major_map.json`
   - 如果不需要，文件名默认为 `{major}.xlsx` / `{major}.svg`

## 执行步骤（方案 A：从数据库生成）

### 步骤1：创建输出目录

```bash
mkdir "<project-root>/00-Design/01-Excel"
mkdir "<project-root>/00-Design/02-ER"
```

### 步骤2（可选）：准备 Major Map

```json
{
  "41": "15-表务&抄表管理系统",
  "42": "25-车辆管理系统",
  "47": "18-收费管理系统"
}
```

### 步骤3：生成 Excel

```bash
python db-design-doc-generator/scripts/generate_excel.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/00-Design/01-Excel" \
  --schema zgis \
  --major-map major_map.json
```

### 步骤4：生成 SVG ER 图

```bash
python db-design-doc-generator/scripts/generate_er.py \
  --db-url "postgresql://user:pass@host:port/dbname" \
  --output-dir "<project-root>/00-Design/02-ER" \
  --schema zgis \
  --major-map major_map.json
```

### 步骤5：清理临时文件

检查 `00-Design/02-ER` 中是否有 `.mmd` 临时文件，如有则删除。

---

## 执行步骤（方案 B：从全量 SQL 脚本生成）

### 步骤1：创建输出目录

同上。

### 步骤2（可选）：准备 Major Map

同上。

### 步骤3：生成 Excel

```bash
python db-design-doc-generator/scripts/generate_excel_from_sql.py \
  --input-dir "<project-root>/01-Application" \
  --output-dir "<project-root>/00-Design/01-Excel" \
  --major-map major_map.json
```

### 步骤4：生成 SVG ER 图

```bash
python db-design-doc-generator/scripts/generate_er_from_sql.py \
  --input-dir "<project-root>/01-Application" \
  --output-dir "<project-root>/00-Design/02-ER" \
  --major-map major_map.json
```

### 步骤5：清理临时文件

同上。

## 输出结果

- `00-Design/01-Excel/`：按 major 分组的 `.xlsx` 文件
- `00-Design/02-ER/`：按 major 分组的 `.svg` 文件
