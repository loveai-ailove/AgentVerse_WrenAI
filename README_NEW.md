# AgentVerse_WrenAI 新环境重部署手册

本文档面向下面这个场景：

- 你在一台新的 Linux 机器上重新部署 `AgentVerse_WrenAI`
- 代码是刚从 GitHub `clone` 下来的
- MySQL 不是示例测试库，而是一个已经存在的业务数据库
- 数据库中已经有业务表和业务数据
- 你希望最终实现：
  - 使用 WrenAI 为 MySQL 建立语义层
  - 启动 `ask_service` 提供自然语言问数接口
  - 让 `AgentVerse` 通过 HTTP 节点调用这个接口

本文档不会使用根目录的 `docker-compose.yml` 初始化示例数据。
如果你接的是现有业务 MySQL，请把 `order-demo/` 视为示例，不要直接把它当成你的正式业务模型。

## 1. 总体目标

完整链路如下：

```text
用户
  -> AgentVerse 智能体 / 工作流
  -> HTTP 节点调用 ask_service
  -> ask_service
     -> WrenAI (MDL / Memory / SQL)
     -> MySQL
     -> vLLM(OpenAI 兼容接口)
  -> 返回结果给 AgentVerse
```

在一个全新的环境中，推荐按下面顺序完成部署：

1. `git clone` 项目源码
2. 安装 Python 和系统依赖
3. 创建虚拟环境并安装 `WrenAI`
4. 盘点现有 MySQL 表结构
5. 新建一个你自己的 Wren 项目目录
6. 为新数据库创建 `models/`、`relationships.yml`、`knowledge/`
7. 编译 MDL 并建立 Memory 索引
8. 配置并启动 `ask_service`
9. 在 `AgentVerse` 中配置 HTTP 节点并联调

## 2. 部署原则

在“新环境 + 新业务库”的场景下，最容易出问题的不是安装，而是建模范围过大、语义不清、问数不准。

因此建议遵循下面几条原则：

- 不要直接修改 `order-demo/`，新建一个单独的业务项目目录
- 不要一开始就把数据库所有表都建模进来
- 第一阶段只挑核心 10 到 30 张表上线
- 优先建模：
  - 核心事实表
  - 关键维表
  - 真实存在的主外键关系
  - 高频问数涉及的字段
- 强烈建议补充：
  - `knowledge/rules/*.md`
  - `knowledge/sql/*.md`
- 强烈建议给 Wren 使用只读数据库账号

## 3. 前置条件

请先准备好下面这些信息：

- GitHub 仓库地址
- 新环境机器的登录账号
- MySQL 连接信息
  - `host`
  - `port`
  - `database`
  - `user`
  - `password`
- vLLM OpenAI 兼容接口信息
  - `VLLM_BASE_URL`
  - `VLLM_API_KEY`
  - `VLLM_MODEL`
- `AgentVerse` 服务地址

建议环境：

- Linux
- Python 3.11 或 3.12
- 能访问 MySQL 和 vLLM

## 4. 克隆源码

下面以 `/home/lb/data` 为工作目录举例：

```bash
cd /home/lb/data
git clone <你的-github-repo-url> AgentVerse_WrenAI
cd /home/lb/data/AgentVerse_WrenAI
```

后续文档默认：

```bash
export PROJECT_ROOT=/home/lb/data/AgentVerse_WrenAI
```

## 5. 安装系统依赖

### 5.1 安装基础软件

```bash
sudo apt update
sudo apt install -y \
  python3.12 python3.12-venv python3-dev \
  build-essential pkg-config default-libmysqlclient-dev \
  curl git
```

### 5.2 验证 Python

```bash
python3.12 --version
pip --version
```

## 6. 创建虚拟环境并安装依赖

### 6.1 创建虚拟环境

```bash
cd "$PROJECT_ROOT"
python3.12 -m venv .venv
source "$PROJECT_ROOT/.venv/bin/activate"
```

### 6.2 安装 WrenAI

```bash
pip install --upgrade pip setuptools wheel
pip install "wrenai[mysql,memory,main]"
```

如果网络慢，可以使用镜像：

```bash
pip install "wrenai[mysql,memory,main]" \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 6.3 安装 ask_service 依赖

```bash
pip install -r "$PROJECT_ROOT/ask_service/requirements.txt"
```

### 6.4 验证安装

```bash
wren version
wren docs connection-info mysql
```

## 7. 为新业务库做接入准备

### 7.1 为 Wren 创建只读账号

如果你有权限，建议给 Wren 单独创建一个只读账号。

示例 SQL：

```sql
CREATE USER 'wren_reader'@'%' IDENTIFIED BY 'YourStrongPassword';
GRANT SELECT ON your_database.* TO 'wren_reader'@'%';
FLUSH PRIVILEGES;
```

如果数据库权限由 DBA 管理，请让 DBA 提供一个只读账号。

### 7.2 先盘点数据库结构

不要直接对全库盲建模型。先导出表、字段、主键、关系候选。

示例 SQL：

```sql
SELECT
  TABLE_NAME,
  TABLE_COMMENT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'your_database'
ORDER BY TABLE_NAME;
```

```sql
SELECT
  TABLE_NAME,
  COLUMN_NAME,
  DATA_TYPE,
  IS_NULLABLE,
  COLUMN_KEY,
  COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'your_database'
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

```sql
SELECT
  TABLE_NAME,
  INDEX_NAME,
  COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'your_database'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

```sql
SELECT
  TABLE_NAME,
  REFERENCED_TABLE_NAME,
  COLUMN_NAME,
  REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'your_database'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, COLUMN_NAME;
```

建议把这些结果保存成 CSV 或 Excel，方便后续建模。

### 7.3 第一阶段只选核心表

如果你的数据库表很多，推荐先选 10 到 30 张最核心的表做第一版问数。

优先选择：

- 主事实表
- 关键维表
- 高频分析表
- 有明确主键和关系的表

不建议首期直接纳入：

- 日志表
- 任务中间表
- 临时同步表
- 历史归档表
- 命名混乱且业务含义不明的表

## 8. 创建你的 Wren 项目目录

不要直接改 `order-demo/`。推荐新建一个独立目录。

下面假设你的业务项目名是 `biz-analytics`：

```bash
export WREN_PROJECT_NAME=biz-analytics
export WREN_PROJECT_DIR="$PROJECT_ROOT/$WREN_PROJECT_NAME"
```

创建目录：

```bash
mkdir -p "$WREN_PROJECT_DIR/models"
mkdir -p "$WREN_PROJECT_DIR/cubes"
mkdir -p "$WREN_PROJECT_DIR/views"
mkdir -p "$WREN_PROJECT_DIR/knowledge/rules"
mkdir -p "$WREN_PROJECT_DIR/knowledge/sql"
```

推荐最终目录结构如下：

```text
AgentVerse_WrenAI/
├── ask_service/
├── order-demo/                          # 示例项目，保留参考，不作为你的正式业务模型
└── biz-analytics/                       # 你的新业务 Wren 项目
    ├── connection_info.json
    ├── wren_project.yml
    ├── relationships.yml
    ├── models/
    ├── cubes/
    ├── views/
    ├── knowledge/
    │   ├── rules/
    │   └── sql/
    ├── .wren/                           # 运行后生成
    └── target/                          # 构建后生成
```

## 9. 配置 Wren 项目基础文件

### 9.1 创建 `connection_info.json`

你可以直接参考示例模板：

```bash
cp "$PROJECT_ROOT/order-demo/connection_info.example.json" \
   "$WREN_PROJECT_DIR/connection_info.json"
```

然后把内容改成你的数据库：

```json
{
  "datasource": "mysql",
  "host": "127.0.0.1",
  "port": 3306,
  "database": "your_database",
  "user": "your_readonly_user",
  "password": "your_readonly_password"
}
```

### 9.2 创建 `wren_project.yml`

示例内容：

```yaml
schema_version: 5
name: biz_analytics
version: "0.1.0"
catalog: wren
schema: public
data_source: mysql
```

说明：

- `name` 建议使用业务上能识别的项目名
- `data_source` 对 MySQL 固定写 `mysql`

### 9.3 创建 `relationships.yml`

如果当前还没梳理好关系，建议先创建空文件结构：

```yaml
relationships: []
```

后续确认真实关系后再补。

## 10. 创建 `models/`

### 10.1 一张表对应一个模型目录

例如你选择了下面两张核心表：

- `fact_order`
- `dim_customer`

则目录可以这样建：

```bash
mkdir -p "$WREN_PROJECT_DIR/models/fact_order"
mkdir -p "$WREN_PROJECT_DIR/models/dim_customer"
```

### 10.2 模型文件模板

每张表一个 `metadata.yml`。

模板如下：

```yaml
name: fact_order
table_reference:
  schema: your_database
  table: fact_order
properties:
  description: 订单事实表，一行代表一笔订单。
columns:
  - name: id
    type: BIGINT
    is_calculated: false
    not_null: true
    is_primary_key: true
    properties:
      description: 订单主键
  - name: customer_id
    type: BIGINT
    is_calculated: false
    not_null: false
    properties:
      description: 客户 ID，关联 dim_customer.id
  - name: order_amount
    type: DOUBLE
    is_calculated: false
    not_null: false
    properties:
      description: 订单金额
  - name: created_at
    type: TIMESTAMP
    is_calculated: false
    not_null: false
    properties:
      description: 下单时间
primary_key: id
cached: false
```

### 10.3 类型映射建议

MySQL 常见类型可按下面思路映射：

- `int / integer` -> `INTEGER`
- `bigint` -> `BIGINT`
- `decimal / numeric / double / float` -> `DOUBLE`
- `varchar / char / text` -> `VARCHAR`
- `datetime / timestamp` -> `TIMESTAMP`
- `date` -> `DATE`
- `tinyint(1)` -> 视业务决定是否映射成 `BOOLEAN`

如果不确定，优先保持与示例风格一致，先保证可运行，再逐步校正。

### 10.4 编写字段描述的原则

字段描述会直接影响问数准确率。

建议优先写清楚：

- 主键和外键含义
- 金额字段口径
- 时间字段口径
- 状态字段取值含义
- 地区、组织、租户字段含义

## 11. 创建关系文件

如果数据库中存在明确关系，请写入 `relationships.yml`。

示例：

```yaml
relationships:
  - name: fact_order_customer
    models:
      - fact_order
      - dim_customer
    join_type: MANY_TO_ONE
    condition: fact_order.customer_id = dim_customer.id
```

编写原则：

- 只写真实存在的关系
- 不要凭字段名猜关系
- 高优先级先建高频问数会用到的关联

## 12. 创建 `knowledge/` 以提升准确率

### 12.1 业务规则文件

文件：

```text
$WREN_PROJECT_DIR/knowledge/rules/business-rules.md
```

建议至少写清楚：

- 收入口径
- 有效订单口径
- 默认时间字段
- 状态字段含义
- 地区字段来源

示例：

```md
## 指标口径

- revenue 指已支付订单金额，统一使用 `fact_order.pay_amount`
- order count 指有效订单数，不包含取消订单
- 默认时间分析字段使用 `fact_order.created_at`

## 维度口径

- 客户地区统一使用 `dim_customer.region_name`
- 渠道统一使用 `fact_order.channel_name`

## 状态约定

- `PAID` 表示已支付
- `CANCELLED` 表示已取消
- `REFUNDED` 表示已退款
```

### 12.2 示例 SQL 文件

目录：

```text
$WREN_PROJECT_DIR/knowledge/sql/
```

示例文件：

```md
---
nl: 按客户地区统计订单数和销售额
sql: |
  SELECT
    c.region_name,
    COUNT(*) AS order_count,
    SUM(o.pay_amount) AS total_revenue
  FROM "fact_order" o
  JOIN "dim_customer" c ON o.customer_id = c.id
  WHERE o.order_status <> 'CANCELLED'
  GROUP BY 1
  ORDER BY total_revenue DESC
source: seed
tags:
  - revenue
  - region
  - order
---
```

建议首批至少沉淀 10 到 20 个高频问题示例。

## 13. 可选创建 `cubes/`

如果你的场景经常做聚合分析，推荐增加 cube。

典型适合做 cube 的主题：

- 销售统计
- 订单统计
- 用户增长
- 库存分析
- 财务汇总

如果只是先打通最小链路，`cube` 不是硬性前提。

## 14. 构建 Wren 项目

### 14.1 校验与构建

```bash
source "$PROJECT_ROOT/.venv/bin/activate"
cd "$WREN_PROJECT_DIR"

wren context validate
wren context build
```

成功后会生成：

- `target/mdl.json`

### 14.2 建立 Memory 索引

```bash
source "$PROJECT_ROOT/.venv/bin/activate"
cd "$WREN_PROJECT_DIR"

export HF_ENDPOINT=https://hf-mirror.com
wren memory index --mdl "$WREN_PROJECT_DIR/target/mdl.json"
```

说明：

- 首次执行可能会下载并初始化嵌入模型
- 首次比较慢是正常现象
- 执行完成后会生成 `.wren/memory/`

### 14.3 先做基础连通验证

建议先用真实 SQL 做连通测试：

```bash
wren --mdl "$WREN_PROJECT_DIR/target/mdl.json" \
  --connection-file "$WREN_PROJECT_DIR/connection_info.json" \
  --sql 'SELECT COUNT(*) AS total_rows FROM "fact_order"' \
  --output json
```

如果有跨表关系，再做一个 join 测试。

## 15. 配置 `ask_service`

### 15.1 复制配置模板

```bash
cp "$PROJECT_ROOT/ask_service/.env.example" \
   "$PROJECT_ROOT/ask_service/.env"
```

### 15.2 按你的新项目修改 `.env`

示例：

```dotenv
ASK_HOST=127.0.0.1
ASK_PORT=18082

VLLM_BASE_URL=http://127.0.0.1:8000/v1
VLLM_API_KEY=your-api-key
VLLM_MODEL=your-model-name

WREN_PROJECT_PATH=biz-analytics
WREN_MDL_PATH=biz-analytics/target/mdl.json
WREN_CONN_FILE=biz-analytics/connection_info.json
WREN_MEMORY_PATH=biz-analytics/.wren/memory

WREN_STRICT_MODE=true
QUERY_TIMEOUT_SEC=90
MAX_RESULT_ROWS=200
DEFAULT_RECALL_LIMIT=3
DEFAULT_FETCH_LIMIT=6
```

重点确认：

- `VLLM_BASE_URL`
- `VLLM_API_KEY`
- `VLLM_MODEL`
- `WREN_PROJECT_PATH`
- `WREN_MDL_PATH`
- `WREN_CONN_FILE`
- `WREN_MEMORY_PATH`

## 16. 启动与验证 `ask_service`

### 16.1 启动 vLLM

如果你的 vLLM 未启动，先启动它，并验证：

```bash
curl http://127.0.0.1:8000/v1/models
```

### 16.2 启动 ask_service

```bash
source "$PROJECT_ROOT/.venv/bin/activate"
cd "$PROJECT_ROOT/ask_service"
python main.py
```

说明：

- 启动入口会读取 `ask_service/.env`
- 当前版本中，MemoryStore 改为后台预热
- 所以服务通常会先起来，Memory 预热期间 `/status` 可能显示 `warming_up`

### 16.3 健康检查

```bash
curl http://127.0.0.1:18082/health
```

### 16.4 状态检查

```bash
curl http://127.0.0.1:18082/status
```

重点看：

- `memory_state`
- `memory_init_error`
- `query_timeout_sec`

说明：

- `memory_state=warming_up` 表示服务已启动，但 Memory 仍在后台预热
- `memory_state=ready` 表示问数已基本可用

### 16.5 问数测试

建议先用一条你已经确认答案的真实业务问题：

```bash
curl -X POST http://127.0.0.1:18082/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "按客户地区统计订单数和销售额"
  }'
```

如果返回：

- `200` 且 `ok=true`，说明问数成功
- `503` 且 `error.code=MEMORY_WARMING_UP`，说明服务已启动，但 Memory 还没预热完成

## 17. 在 AgentVerse 中配置 HTTP 节点

### 17.1 HTTP 节点基本配置

- URL：`http://127.0.0.1:18082/api/ask`
- Method：`POST`
- Headers：

```json
{
  "Content-Type": "application/json"
}
```

- Timeout：`90`

### 17.2 请求体

最简单配置：

```json
{
  "question": "{{用户输入}}"
}
```

如果你还要加区域限制：

```json
{
  "question": "{{用户输入}}",
  "allowed_regions": ["华东", "华北"]
}
```

### 17.3 条件分支

建议在工作流中判断：

- `httpResult.need_clarification`
- `httpResult.ok`

建议逻辑：

- 如果 `httpResult.need_clarification=true`，回复 `httpResult.clarification_question`
- 如果 `httpResult.ok=true`，回复 `httpResult.summary`
- 如果 HTTP 节点报错或 `httpResult.ok=false`，进入兜底提示

## 18. 可选 systemd 部署

如果你希望长期运行 `ask_service`，可以使用 systemd。

参考文件：

- `ask_service/systemd/ask-service.service`

部署步骤：

```bash
sudo cp "$PROJECT_ROOT/ask_service/systemd/ask-service.service" \
  /etc/systemd/system/ask-service.service
```

然后按你的机器实际情况修改：

- `User`
- `WorkingDirectory`
- `EnvironmentFile`
- `ExecStart`

之后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ask-service
sudo systemctl start ask-service
sudo systemctl status ask-service
```

## 19. 推荐上线顺序

建议按下面的顺序推进：

1. `git clone`
2. 安装 Python 与依赖
3. 创建虚拟环境并安装 WrenAI
4. 盘点 MySQL 表结构
5. 选出第一批核心表
6. 新建业务 Wren 项目目录
7. 配置 `connection_info.json`
8. 编写 `models/`
9. 编写 `relationships.yml`
10. 补 `knowledge/rules`
11. 补 `knowledge/sql`
12. 执行 `wren context validate`
13. 执行 `wren context build`
14. 执行 `wren memory index`
15. 配置 `ask_service/.env`
16. 启动 `ask_service`
17. 测试 `/health`、`/status`、`/api/ask`
18. 在 `AgentVerse` 中配置 HTTP 节点
19. 用真实高频问题回归测试

## 20. 多表数据库下如何保证准确率

如果数据库表很多，建议这样控制准确率：

- 首批只接 10 到 30 张核心表
- 关键指标一定写进 `knowledge/rules`
- 高频问题一定写进 `knowledge/sql`
- 核心统计口径尽量做成 `cube`
- 不清楚的表和字段，先不上线
- 先做一个业务域，再逐步扩域

最容易影响准确率的因素通常是：

- 字段描述太少
- 表关系写错
- 业务口径不统一
- 示例 SQL 太少
- 一次性引入太多弱相关表

## 21. 常见问题

### 21.1 `wren context validate` 失败

优先检查：

- YAML 缩进
- 字段类型是否合理
- 主键字段是否存在
- 关系中的模型名和字段名是否写对

### 21.2 `wren memory index` 很慢

原因通常是首次初始化嵌入模型。

建议：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 21.3 `ask_service` 已启动但 `/api/ask` 返回 503

先看 `/status`：

- 如果 `memory_state=warming_up`，说明 Memory 还在预热
- 如果 `memory_state=error`，检查 `memory_init_error`

### 21.4 问数结果不准

优先检查：

- `models/*.yml` 的字段描述是否足够明确
- `relationships.yml` 是否正确
- `knowledge/rules` 是否覆盖关键业务口径
- `knowledge/sql` 是否沉淀了高频正确 SQL

## 22. 最终交付检查清单

上线前建议确认下面这些项都已完成：

- 源码已成功 clone
- 虚拟环境已创建
- `WrenAI` 已安装成功
- 新业务项目目录已创建
- `connection_info.json` 已配置
- `models/` 已完成第一版
- `relationships.yml` 已完成第一版
- `knowledge/rules` 已补充
- `knowledge/sql` 已补充
- `target/mdl.json` 已生成
- `.wren/memory/` 已生成
- `ask_service/.env` 已配置
- `/health` 正常
- `/status` 正常
- `/api/ask` 可返回有效 JSON
- `AgentVerse` HTTP 节点已配置
- 已用真实问题做回归验证

到这里，一个新的 `AgentVerse_WrenAI + 新业务 MySQL` 环境就部署完成了。
