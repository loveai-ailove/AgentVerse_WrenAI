# WrenAI + AgentVerse 使用手册

> **此文档已过时，请优先参阅 [README_NEW.md](./README_NEW.md)**  
> 部分配置项（如 `CONTEXT_THRESHOLD`、`WREN_EMBEDDING_MODEL`、错误码列表）可能不完整，  
> 接口行为（如 `summary` 不再由 ask_service 生成）可能已变更。

本文档从一个新使用者第一次接手项目的角度编写，目标是帮助你完成下面这件事：

- 基于已有的 MySQL 业务数据库安装 `WrenAI`
- 手工创建并配置一个可运行的 Wren 项目
- 启动 `ask_service` 提供自然语言问数接口
- 在 `AgentVerse` 中通过 HTTP 节点接入该接口

本文档默认前提如下：

- MySQL 数据库已经存在
- 数据库中已经有业务表和业务数据
- 不需要初始化测试数据
- 只需要完成项目文件的创建、配置、启动和联调

## 1. 总体架构

整体链路如下：

```text
用户
  -> AgentVerse 智能体 / 工作流
  -> HTTP 节点调用 ask_service
  -> ask_service
     -> WrenAI Memory / MDL / SQL 执行
     -> MySQL
     -> vLLM(OpenAI 兼容接口)
  -> 返回结果给 AgentVerse
  -> AgentVerse 回复用户
```

各组件职责如下：

- `WrenAI`：负责语义建模、关系建模、Memory 检索、SQL 执行
- `ask_service`：负责自然语言问数编排
- `vLLM`：负责 NL2SQL 和结果总结
- `AgentVerse`：负责对话入口、工作流编排和最终回复

## 2. 目录说明

下面是示例工程目录。每个节点后面只保留一种状态说明：

- `手工创建`：表示需要你自己创建或维护
- `命令生成`：表示执行命令后会自动出现

```text
/home/lb/data/AgentVerse_WrenAI                    # 项目根目录，统一放置 Wren 项目、ask_service 和文档；手工创建
├── README.md                                      # 使用手册；手工创建
├── .gitignore                                     # Git 忽略规则；手工创建
├── .env                                           # 本地 MySQL 容器变量，仅在需要容器测试时使用；手工创建
├── .env.example                                   # MySQL 容器变量模板；手工创建
├── docker-compose.yml                             # 示例 MySQL 测试容器编排；手工创建
├── ask_service/                                   # 问数 HTTP 服务目录；手工创建
│   ├── .env                                       # ask_service 本地配置文件；手工创建
│   ├── .env.example                               # ask_service 配置模板；手工创建
│   ├── app.py                                     # ask_service 主程序；手工创建
│   ├── requirements.txt                           # ask_service 依赖清单；手工创建
│   └── systemd/                                   # systemd 部署文件目录；手工创建
│       └── ask-service.service                    # systemd 服务文件；手工创建
├── mysql-init/                                    # 示例初始化 SQL 目录，仅在你想本地造测试库时使用；手工创建
│   └── 01_init_orders.sql                         # 示例初始化脚本；手工创建
└── order-demo/                                    # WrenAI 项目目录；手工创建
    ├── connection_info.json                       # MySQL 连接配置；手工创建
    ├── connection_info.example.json               # MySQL 连接模板；手工创建
    ├── wren_project.yml                           # Wren 项目主配置；手工创建
    ├── relationships.yml                          # 模型关系定义；手工创建
    ├── models/                                    # 模型定义目录；手工创建
    │   ├── customers/                             # customers 表模型目录；手工创建
    │   │   └── metadata.yml                       # customers 模型定义；手工创建
    │   └── orders/                                # orders 表模型目录；手工创建
    │       └── metadata.yml                       # orders 模型定义；手工创建
    ├── cubes/                                     # Cube 定义目录；手工创建
    │   └── order_metrics/                         # 示例订单统计 cube 目录；手工创建
    │       └── metadata.yml                       # cube 定义文件；手工创建
    ├── knowledge/                                 # 业务语义与示例问法目录；手工创建
    │   ├── rules/                                 # 业务规则目录；手工创建
    │   │   └── business-rules.md                  # 业务口径说明；手工创建
    │   └── sql/                                   # 问法到 SQL 示例目录；手工创建
    │       ├── revenue-by-member-level.md         # 示例问法与 SQL；手工创建
    │       └── revenue-by-status.md               # 示例问法与 SQL；手工创建
    ├── .wren/                                     # Wren 运行期目录；命令生成
    │   └── memory/                                # Memory 索引目录；命令生成
    └── target/                                    # 构建产物目录；命令生成
        └── mdl.json                               # 编译后的 MDL；命令生成
```

说明：

- `order-demo/` 是真正的 WrenAI 项目目录
- `ask_service/` 是对外提供问数接口的服务目录
- `.env`、`docker-compose.yml`、`mysql-init/` 只是辅助示例；如果你已经有业务 MySQL，可以不使用它们

## 3. 前置条件

请先确认以下环境已经具备：

- Linux 服务器或开发机
- Python 3.11 或 3.12
- 已有可访问的 MySQL 数据库
- 已部署好的 vLLM OpenAI 兼容接口
- `AgentVerse` 已经可用

建议先确认：

```bash
python3 --version
pip --version
```

如果还未安装基础依赖，可执行：

```bash
sudo apt update
sudo apt install -y \
  python3.12 python3.12-venv python3-dev \
  build-essential pkg-config default-libmysqlclient-dev \
  curl git
```

## 4. 基于 pip 安装 WrenAI

### 4.1 创建虚拟环境

```bash
cd /home/lb/data/AgentVerse_WrenAI
python3.12 -m venv .venv
source /home/lb/data/AgentVerse_WrenAI/.venv/bin/activate
```

### 4.2 安装 WrenAI

```bash
pip install --upgrade pip setuptools wheel
pip install "wrenai[mysql,memory,main]"
```

如果网络较慢，可切换国内源：

```bash
pip install "wrenai[mysql,memory,main]" \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4.3 验证安装

```bash
wren version
wren docs connection-info mysql
```

如果上面两条命令都能成功返回，说明 WrenAI 已安装完成。

## 5. 手工创建和配置 WrenAI 项目

本节演示如何基于“已经存在的业务 MySQL”手工创建一个 Wren 项目。

这里不会初始化任何测试数据，只关注这些工作：

- 创建目录
- 创建配置文件
- 创建模型文件
- 创建关系文件
- 创建可选的 cube 和 knowledge 文件

为了方便说明，下面仍然使用两张示例表：

- `customers`
- `orders`

并通过：

- `orders.customer_id = customers.id`

建立关系。

如果你的业务表不同，请按同样结构替换。

### 5.0 先理解“必选文件”和“可选文件”

最小可运行的 Wren 项目，通常至少需要这些内容：

**必须创建**

- `order-demo/wren_project.yml`
- `order-demo/connection_info.json`
- `order-demo/models/<table>/metadata.yml`

**通常也必须创建**

- `order-demo/relationships.yml`

说明：

- 如果你的模型之间完全没有关联，可以把 `relationships.yml` 写成空数组
- 但这个文件本身仍建议创建，这样项目结构更完整

**可选但强烈建议创建**

- `order-demo/knowledge/rules/business-rules.md`
- `order-demo/knowledge/sql/*.md`

说明：

- 不创建 `knowledge`，Wren 仍然可以运行
- 但自然语言问数效果通常会明显下降

**可选创建**

- `order-demo/cubes/*`
- `order-demo/views/*`

说明：

- `cube` 适合固定口径聚合分析，不是 Wren 启动的硬性前提
- `views` 适合封装复杂业务查询，不是示例项目必需项

### 5.1 创建目录

```bash
mkdir -p /home/lb/data/AgentVerse_WrenAI/order-demo/views
mkdir -p /home/lb/data/AgentVerse_WrenAI/order-demo/models/customers
mkdir -p /home/lb/data/AgentVerse_WrenAI/order-demo/models/orders
mkdir -p /home/lb/data/AgentVerse_WrenAI/order-demo/cubes/order_metrics
mkdir -p /home/lb/data/AgentVerse_WrenAI/order-demo/knowledge/rules
mkdir -p /home/lb/data/AgentVerse_WrenAI/order-demo/knowledge/sql
```

建议按下面的优先级理解这些目录：

- `models/`：必须有
- `relationships.yml`：通常要有
- `knowledge/`：强烈建议有
- `cubes/`：可选
- `views/`：可选

### 5.2 创建连接文件

建议先复制模板文件：

```bash
cp /home/lb/data/AgentVerse_WrenAI/order-demo/connection_info.example.json \
   /home/lb/data/AgentVerse_WrenAI/order-demo/connection_info.json
```

文件路径：

- [connection_info.example.json](file:///home/lb/data/AgentVerse_WrenAI/order-demo/connection_info.example.json)
- [connection_info.json](file:///home/lb/data/AgentVerse_WrenAI/order-demo/connection_info.json)

示例内容：

```json
{
  "datasource": "mysql",
  "host": "127.0.0.1",
  "port": 3306,
  "database": "your_database",
  "user": "your_user",
  "password": "your_password"
}
```

请按你的 MySQL 实际连接信息修改：

- `host`
- `port`
- `database`
- `user`
- `password`

建议给 Wren 单独创建只读账号。

如果你接的是现有业务数据库，这一步是最先要完成的配置项之一。

### 5.3 创建项目主配置

文件路径：

- [wren_project.yml](file:///home/lb/data/AgentVerse_WrenAI/order-demo/wren_project.yml)

示例内容：

```yaml
schema_version: 5
name: order_demo
version: "0.1.0"
catalog: wren
schema: public
data_source: mysql
```

### 5.4 创建模型文件

模型文件按表拆分，每张表一个目录。

#### customers 模型

文件路径：

- [customers/metadata.yml](file:///home/lb/data/AgentVerse_WrenAI/order-demo/models/customers/metadata.yml)

这个文件定义：

- 表名
- 主键
- 字段类型
- 字段描述

#### orders 模型

文件路径：

- [orders/metadata.yml](file:///home/lb/data/AgentVerse_WrenAI/order-demo/models/orders/metadata.yml)

这个文件定义：

- 订单事实表
- 订单字段
- 与客户表关联的 `customer_id`

### 5.5 创建关系文件

文件路径：

- [relationships.yml](file:///home/lb/data/AgentVerse_WrenAI/order-demo/relationships.yml)

当前示例内容：

```yaml
relationships:
  - name: orders_customer
    models:
      - orders
      - customers
    join_type: MANY_TO_ONE
    condition: orders.customer_id = customers.id
```

如果你的业务表之间存在外键或稳定的主从关系，建议明确写进 `relationships.yml`。

核心原则是：

- 只写真实存在且业务含义明确的关系
- 不要凭字段名臆造关系
- 优先建模高频查询中会用到的关联关系

### 5.6 创建 cube 文件

文件路径：

- [order_metrics/metadata.yml](file:///home/lb/data/AgentVerse_WrenAI/order-demo/cubes/order_metrics/metadata.yml)

当前示例中定义了：

- `total_revenue`
- `order_count`
- `avg_order_amount`

以及常见维度：

- `product_category`
- `order_status`
- `payment_method`
- `region`

以及时间维：

- `created_at`

#### cube 文件是不是必须创建

不是必须。

如果只是为了让 Wren 能完成：

- `context validate`
- `context build`
- `memory index`
- `wren --sql`

那么没有 cube 也可以。

但如果你的问数场景经常涉及：

- 收入汇总
- 订单量统计
- 趋势分析
- 按地区、按状态、按品类聚合

那么建议创建 cube，因为它可以把高频的聚合逻辑提前结构化，减少大模型自由拼 SQL 的不稳定性。

#### 什么情况下建议创建 cube

满足以下任意情况时，建议创建：

- 有明显的事实表，比如订单表、流水表、交易表
- 需要频繁做 `SUM/COUNT/AVG`
- 需要按时间、地区、状态、品类做聚合
- 某些统计口径相对稳定，经常重复使用

#### 创建 cube 的核心原则

- 一个 cube 通常围绕一个核心事实对象建立
  - 例如：`orders` -> `order_metrics`
- `measures` 只放稳定、可复用的指标
  - 例如：`total_revenue`、`order_count`、`avg_order_amount`
- `dimensions` 放经常用于分组分析的字段
  - 例如：地区、状态、支付方式、品类
- `time_dimensions` 放默认的时间分析字段
  - 例如：`created_at`
- 不要把所有字段都塞进 cube
  - cube 是“常用统计视角”，不是模型字段的简单复制

#### 创建 cube 时建议优先挑哪些字段

优先挑这几类：

- 指标字段
  - `amount`
  - `price`
  - `revenue`
  - `qty`
- 维度字段
  - `status`
  - `region`
  - `category`
  - `channel`
- 时间字段
  - `created_at`
  - `paid_at`
  - `biz_date`

#### 示例 cube 的理解方式

当前示例 [order_metrics/metadata.yml](file:///home/lb/data/AgentVerse_WrenAI/order-demo/cubes/order_metrics/metadata.yml) 的设计逻辑是：

- `base_object: orders`
  - 表示围绕订单事实表建立聚合
- `total_revenue`
  - 用 `SUM(total_amount)` 表示收入
- `order_count`
  - 用 `COUNT(*)` 表示订单数
- `avg_order_amount`
  - 用 `AVG(total_amount)` 表示客单价
- `dimensions`
  - 选择最常见的统计维度
- `time_dimensions`
  - 使用 `created_at` 作为默认时间轴

### 5.7 创建业务规则和示例 SQL

规则文件路径：

- [business-rules.md](file:///home/lb/data/AgentVerse_WrenAI/order-demo/knowledge/rules/business-rules.md)

示例 SQL 文件路径：

- [revenue-by-status.md](file:///home/lb/data/AgentVerse_WrenAI/order-demo/knowledge/sql/revenue-by-status.md)
- [revenue-by-member-level.md](file:///home/lb/data/AgentVerse_WrenAI/order-demo/knowledge/sql/revenue-by-member-level.md)

这两类文件的作用分别是：

- `rules`：定义业务口径、字段含义、默认时间字段
- `sql`：沉淀常见问法与正确 SQL

#### 这两类文件是不是必须创建

严格来说不是必须，但非常推荐创建。

原因是：

- 没有 `rules`，模型只知道字段结构，不知道你的业务口径
- 没有 `sql` 示例，`memory recall` 和 ask_service 很难稳定命中历史正确问法

#### `business-rules.md` 的核心作用

这个文件主要解决“业务含义”问题，而不是“数据库结构”问题。

推荐写这几类内容：

- 指标口径
  - revenue 是什么
  - order count 怎么算
- 时间口径
  - 默认按 `created_at` 还是 `paid_at`
- 状态口径
  - `PAID`、`COMPLETED`、`REFUNDED` 的业务含义
- 维度口径
  - 地区取客户地区还是订单地区

#### 编写 `business-rules.md` 的核心原则

- 只写“会影响 SQL 生成和结果解释”的规则
- 只写“业务口径”，不要重复字段结构定义
- 优先写容易误解的概念
  - 收入
  - 有效订单
  - 时间字段
  - 退款是否计入
- 语言尽量明确，避免模糊描述

#### `knowledge/sql/*.md` 的核心作用

这些文件用来沉淀：

- 常见业务问法
- 对应的正确 SQL

它会直接影响：

- `wren memory recall`
- ask_service 的历史示例召回效果
- NL2SQL 的稳定性

#### 编写 SQL 示例文件的核心原则

- 只保存“已经确认正确”的 SQL
- 一条文件对应一种清晰问法
- 问法尽量贴近真实业务用户的表达
- SQL 尽量简洁、稳定、可复用
- 优先沉淀高频问题

推荐优先沉淀这几类问题：

- 按状态统计销售额
- 按地区统计订单数
- 按会员等级统计收入
- 按月份统计趋势
- 最近 7 天 / 30 天统计

#### 什么时候优先补 `rules`，什么时候优先补 `sql`

- 如果问题主要是“模型不懂业务含义”
  - 优先补 `rules`
- 如果问题主要是“某些常见问法老是生成错 SQL”
  - 优先补 `knowledge/sql`

### 5.8 构建 Wren 项目

```bash
source /home/lb/data/AgentVerse_WrenAI/.venv/bin/activate
cd /home/lb/data/AgentVerse_WrenAI/order-demo

wren context validate
wren context build
```

执行成功后，会生成：

- [mdl.json](file:///home/lb/data/AgentVerse_WrenAI/order-demo/target/mdl.json)

### 5.9 建立 Memory 索引

```bash
source /home/lb/data/AgentVerse_WrenAI/.venv/bin/activate
cd /home/lb/data/AgentVerse_WrenAI/order-demo

export HF_ENDPOINT=https://hf-mirror.com
wren memory index --mdl /home/lb/data/AgentVerse_WrenAI/order-demo/target/mdl.json
```

说明：

- 第一次执行时，`MemoryStore` 可能会下载并初始化向量模型
- 首次构建会比较慢，属于正常现象

执行后会生成：

- `order-demo/.wren/memory/`

### 5.10 手工验证 Wren 功能

下面的 SQL 与 Cube 示例仍基于 `customers` 和 `orders` 两张演示表。

如果你的业务数据库使用的是其他表，请把示例 SQL 改成你自己的表和字段。

#### 基础 SQL 查询

```bash
wren --mdl /home/lb/data/AgentVerse_WrenAI/order-demo/target/mdl.json \
  --connection-file /home/lb/data/AgentVerse_WrenAI/order-demo/connection_info.json \
  --sql 'SELECT COUNT(*) AS total_orders FROM "orders"' \
  --output json
```

#### 跨表查询

```bash
wren --mdl /home/lb/data/AgentVerse_WrenAI/order-demo/target/mdl.json \
  --connection-file /home/lb/data/AgentVerse_WrenAI/order-demo/connection_info.json \
  --sql 'SELECT c.member_level, COUNT(*) AS order_count, SUM(o.total_amount) AS total_revenue FROM "orders" o JOIN "customers" c ON o.customer_id = c.id GROUP BY 1 ORDER BY total_revenue DESC' \
  --output json
```

#### Cube 查询

```bash
wren cube query \
  --mdl /home/lb/data/AgentVerse_WrenAI/order-demo/target/mdl.json \
  --connection-file /home/lb/data/AgentVerse_WrenAI/order-demo/connection_info.json \
  --cube order_metrics \
  --measures total_revenue,order_count \
  --dimensions order_status \
  --output json
```

#### Memory 召回

```bash
wren memory recall -q "按客户会员等级统计销售额"
```

如果以上测试都正常，说明 WrenAI 核心功能已可用。

## 6. 启动和测试 ask_service

`ask_service` 用于把：

- WrenAI
- vLLM
- 自然语言问数

三者串起来，并通过 HTTP 暴露给 AgentVerse。

### 6.1 安装 ask_service 依赖

```bash
source /home/lb/data/AgentVerse_WrenAI/.venv/bin/activate
pip install -r /home/lb/data/AgentVerse_WrenAI/ask_service/requirements.txt
```

依赖文件路径：

- [requirements.txt](file:///home/lb/data/AgentVerse_WrenAI/ask_service/requirements.txt)

### 6.2 配置 ask_service

建议先复制模板文件：

```bash
cp /home/lb/data/AgentVerse_WrenAI/ask_service/.env.example \
   /home/lb/data/AgentVerse_WrenAI/ask_service/.env
```

配置文件路径：

- [.env.example](file:///home/lb/data/AgentVerse_WrenAI/ask_service/.env.example)
- [.env](file:///home/lb/data/AgentVerse_WrenAI/ask_service/.env)

当前配置项如下：

```dotenv
# ask_service 监听地址；通常本机部署保持 127.0.0.1 即可
ASK_HOST=127.0.0.1

# ask_service 监听端口；需要与 AgentVerse HTTP 节点填写的端口一致
ASK_PORT=18082

# vLLM 的 OpenAI 兼容接口地址；ask_service 通过它调用大模型
VLLM_BASE_URL=http://127.0.0.1:8000/v1

# vLLM 的 API Key；如果你的服务不校验，可保留 dummy；如果校验，请填写真实值
VLLM_API_KEY=your-api-key

# ask_service 调用的大模型名称；必须与 /v1/models 返回的模型名一致
VLLM_MODEL=your-model-name

# Wren 项目根目录；相对 AgentVerse_WrenAI 根目录解析
WREN_PROJECT_PATH=order-demo

# Wren 编译后的 mdl.json 路径；相对 AgentVerse_WrenAI 根目录解析
WREN_MDL_PATH=order-demo/target/mdl.json

# Wren 连接数据库用的 connection_info.json 路径；相对 AgentVerse_WrenAI 根目录解析
WREN_CONN_FILE=order-demo/connection_info.json

# Wren Memory 索引目录；相对 AgentVerse_WrenAI 根目录解析
WREN_MEMORY_PATH=order-demo/.wren/memory

# 是否开启 Wren 严格模式；true 表示只允许查询 MDL 中定义的对象，推荐开启
WREN_STRICT_MODE=true

# 单次问数请求的超时时间（秒）；包含 LLM 调用和 SQL 执行
QUERY_TIMEOUT_SEC=90

# 单次 SQL 最多返回多少行；避免结果集过大
MAX_RESULT_ROWS=200

# Memory recall 默认召回多少条相似问法
DEFAULT_RECALL_LIMIT=3

# Memory fetch 默认返回多少条上下文结果
DEFAULT_FETCH_LIMIT=6
```

你需要重点确认：

- `VLLM_BASE_URL`
- `VLLM_API_KEY`
- `VLLM_MODEL`
- `WREN_PROJECT_PATH`
- `WREN_MDL_PATH`
- `WREN_CONN_FILE`
- `WREN_MEMORY_PATH`

说明：

- 这些 Wren 路径是相对 `AgentVerse_WrenAI` 根目录解析的
- 不需要写绝对路径

### 6.3 启动 vLLM

如果 vLLM 尚未启动，请先启动你的 OpenAI 兼容模型服务。

启动后验证：

```bash
curl http://127.0.0.1:8000/v1/models
```

### 6.4 启动 ask_service

```bash
source /home/lb/data/AgentVerse_WrenAI/.venv/bin/activate
cd /home/lb/data/AgentVerse_WrenAI/ask_service
python main.py
```

说明：

- 启动入口会读取 `ask_service/.env` 中的 `ASK_HOST` 与 `ASK_PORT`
- `workers` 固定为 `1`，不要改大
- 首次启动如果卡在 `Waiting for application startup`，通常是 `MemoryStore` 首次加载模型

服务主文件：

- [app.py](file:///home/lb/data/AgentVerse_WrenAI/ask_service/app.py)

### 6.5 健康检查

```bash
curl http://127.0.0.1:18082/health
```

### 6.6 状态检查

```bash
curl http://127.0.0.1:18082/status
```

### 6.7 重新索引

当你修改了：

- `models/`
- `relationships.yml`
- `knowledge/`

之后，可以执行：

```bash
curl -X POST http://127.0.0.1:18082/admin/reindex
```

### 6.8 测试问数接口

#### 测试 1：会员等级统计

```bash
curl -X POST http://127.0.0.1:18082/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "按客户会员等级统计销售额和订单数"
  }'
```

#### 测试 2：按地区统计

```bash
curl -X POST http://127.0.0.1:18082/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "按客户地区统计销售额和订单数"
  }'
```

#### 测试 3：限制地区

```bash
curl -X POST http://127.0.0.1:18082/api/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "统计销售额和订单数",
    "allowed_regions": ["华东", "华北"]
  }'
```

### 6.9 ask_service 返回结果说明

正常返回示例字段：

- `ok`
- `trace_id`
- `need_clarification`
- `sql`
- `rows`
- `summary`
- `chart`
- `latency_ms`

重点判断：

- `ok=true` 表示成功
- `need_clarification=true` 表示还需要补充查询条件
- `sql` 表示最终执行的 SQL
- `rows` 表示结构化结果
- `summary` 表示给用户展示的自然语言答案

### 6.10 查看日志

`app.py` 已经内置了：

- 启动日志
- 请求日志
- SQL 执行耗时日志

前台启动时，直接在终端里查看即可。

重点关注以下事件：

- `startup_memory_ready`
- `startup_completed`
- `ask_request_received`
- `ask_context_ready`
- `sql_dry_run_finished`
- `sql_query_finished`
- `ask_request_completed`
- `ask_request_failed`

## 7. 如何在 AgentVerse 中进行配置和测试

### 7.1 使用方式

在 AgentVerse 中，推荐通过工作流的 HTTP 节点调用：

- `http://127.0.0.1:18082/api/ask`

当前项目已放开 AgentVerse HTTP 节点对本地地址的访问限制，因此可以直接调用本机地址。

### 7.2 推荐工作流结构

建议建立一个“数据问答”工作流，结构如下：

```text
开始节点
  -> HTTP 请求节点（调用 ask_service）
  -> 条件分支节点（判断 need_clarification）
  -> 回复节点
```

也可以加一个 AI 节点做润色，但不是必须。

### 7.3 HTTP 节点配置

#### URL

```text
http://127.0.0.1:18082/api/ask
```

#### Method

```text
POST
```

#### Headers

```json
{
  "Content-Type": "application/json"
}
```

#### Body

把当前用户输入映射到 `question`：

```json
{
  "question": "{{用户输入}}"
}
```

如果你希望加区域过滤，也可以这样传：

```json
{
  "question": "{{用户输入}}",
  "allowed_regions": ["华东", "华北"]
}
```

### 7.4 条件分支节点

判断 ask_service 返回值中的：

- `need_clarification`

如果为 `true`：

- 回复 `clarification_question`

如果为 `false`：

- 回复 `summary`

### 7.5 回复节点建议

回复给用户时，建议直接使用：

- `summary`

如果你需要调试，也可以在后台显示：

- `sql`
- `rows`
- `trace_id`

### 7.6 在 AgentVerse 中测试

推荐测试问题：

- `按客户会员等级统计销售额和订单数`
- `按客户地区统计销售额和订单数`
- `按月份统计订单数和销售额趋势`
- `华东地区订单销售额是多少`

期望结果：

- 工作流能成功调用 ask_service
- ask_service 返回结构化 JSON
- AgentVerse 正确显示 `summary`
- 对需要补充条件的问题，能提示用户继续补充

## 8. 常见问题

### 8.1 `wren memory index` 很慢

原因：

- 首次会下载并初始化向量模型

建议：

- 提前设置镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 8.2 `ask_service` 启动卡在 application startup

原因：

- `MemoryStore` 首次加载模型

建议：

- 首次耐心等待
- 启动完成后后续请求会快很多

### 8.3 `/api/ask` 返回 `ok=false`

先看：

- `error.code`
- `error.message`

常见错误：

- `BAD_PLAN`
- `LLM_TIMEOUT`
- `LLM_API_ERROR`
- `INTERNAL_ERROR`

### 8.4 问数结果不准确

优先检查：

- `models/*.yml` 字段描述是否清楚
- `relationships.yml` 是否正确
- `knowledge/rules` 是否定义了业务口径
- `knowledge/sql` 是否沉淀了常见正确 SQL

## 9. 推荐操作顺序

建议严格按下面顺序进行：

1. 安装 Python 依赖和 WrenAI
2. 手工创建 `order-demo` 目录和配置文件
3. 配置已有业务 MySQL 的连接信息
4. 根据你的业务表编写 `models/` 和 `relationships.yml`
5. 按需补充 `cubes/`、`knowledge/rules/`、`knowledge/sql/`
6. 执行 `wren context validate`
7. 执行 `wren context build`
8. 执行 `wren memory index`
9. 手工验证 `wren --sql`、`wren cube query`
10. 配置并启动 `ask_service`
11. 测试 `/health`、`/status`、`/api/ask`
12. 在 AgentVerse 工作流中配置 HTTP 节点
13. 用真实自然语言问题进行回归测试

## 10. 后续优化建议

当数据库表越来越多时，不建议继续完全手工维护。

推荐后续演进成：

- 程序生成结构
- AI 补充语义
- 人工确认关键业务口径

也就是：

```text
MySQL schema
  -> 自动生成 Wren 模型骨架
  -> AI 补 description / rules / SQL examples
  -> 人工确认 revenue / 时间字段 / 状态口径
  -> ask_service / AgentVerse 使用
```

如果后续你准备走自动化建模路线，可以在当前目录下新增：

- `tools/extract_mysql_schema.py`
- `tools/generate_wren_structure.py`
- `tools/enrich_wren_with_ai.py`

用于批量生成和维护 Wren 项目文件。
