# 培训学时记录导入系统

管理员批量上传学员培训学时记录（CSV / Excel），系统完成 **解析 → 本地校验 → 分批上送行业平台**，
平台退回的异常明细可下载 **修正模板**，修正后直接重新上传，支持多轮修正直至全部入库。
内置 **任务队列、实时进度条、任务日志**。

## 快速开始

```bash
# 1. 准备环境（Python 3.11+）
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 2. 生成演示数据（27 行，含各类典型错误）
.venv/bin/python scripts/make_sample.py

# 3. 启动服务
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

# 4. 浏览器打开 http://localhost:8000 ，上传 sample_data/sample_records.csv
#    API 文档：http://localhost:8000/docs
```

运行测试：

```bash
.venv/bin/python -m pytest tests/ -v
```

## 业务流程

```
上传文件 ──▶ 任务入队 ──▶ [PARSING] 解析 CSV/XLSX
                        ──▶ [VALIDATING] 本地校验（姓名/证件号/课程/学时/日期/文件内查重）
                        ──▶ [UPLOADING] 分批上送行业平台（50 条/批）
                        ──▶ DONE / DONE_WITH_ERRORS / FAILED
                                   │
              有异常 ──▶ 下载修正模板（含异常来源+错误码+原因）
                        ──▶ 管理员修正后直接重新上传（自动识别修正模板格式）
                        ──▶ 重新完整校验与上送（可多轮迭代）
```

## 文件格式

必要列（表头支持常见别名）：`姓名、证件号、课程代码、课程名称、学时、培训日期(YYYY-MM-DD)`

修正模板在原始列后附加 `原始行号、异常来源、错误码、错误原因` 四列，重新上传时自动忽略附加列。

## 本地校验规则

| 字段 | 规则 |
|---|---|
| 姓名 | 必填，2-30 位中文/英文（可含 ·） |
| 证件号 | 18 位身份证，GB 11643 加权校验码 + 出生日期合法性 |
| 课程 | 代码须存在于课程目录，名称须与代码匹配 |
| 学时 | 数字，0 < 学时 ≤ 45，最多 1 位小数，且不超过课程上限 |
| 培训日期 | YYYY-MM-DD，有效日期，不晚于当天 |
| 查重 | 文件内 同学员+同课程+同日期 判重 |

## 行业平台（模拟）

`app/platform_client.py` 用确定性规则模拟平台侧校验，便于演示与测试；接入真实平台时替换为 HTTP 调用即可：

| 错误码 | 含义 | 触发规则（演示用） |
|---|---|---|
| P1001 | 学员未在行业平台注册 | 证件号第 17 位为 `9` |
| P2001 | 学时超过课程平台上限 | 平台目录上限（AQ-102→12，AQ-105→4，低于本地） |
| P2002 | 重复上报 | 平台台账已存在 同学员+同课程+同日期（SQLite 持久化） |
| P3001 | 平台未收录该课程 | 如 AQ-106 本地新课未同步 |

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/jobs` | 上传文件，创建导入任务（multipart） |
| GET | `/api/jobs` | 任务列表（含队列等待数） |
| GET | `/api/jobs/{id}` | 任务状态与进度（百分比、各阶段计数） |
| GET | `/api/jobs/{id}/logs?after_id=` | 任务日志（增量拉取） |
| GET | `/api/jobs/{id}/errors` | 异常明细（本地校验 + 平台退回） |
| GET | `/api/jobs/{id}/correction-template` | 下载修正模板（CSV，带 BOM） |
| GET | `/api/courses` | 本地/平台课程目录对照 |

## 项目结构

```
app/
├── main.py             # FastAPI 入口与路由
├── tasks.py            # 任务队列（内存队列 + worker 线程）与导入流水线
├── importer.py         # CSV/XLSX 解析、表头别名、修正模板识别
├── validation.py       # 姓名/证件号/课程/学时/日期校验
├── platform_client.py  # 模拟行业平台（上送、异常明细、台账）
├── database.py         # SQLite：任务、日志、异常明细、平台台账
├── courses.py          # 本地课程目录
└── static/index.html   # 管理界面（上传、进度条、日志、异常明细、模板下载）
scripts/make_sample.py  # 生成演示数据
tests/                  # 31 个单元/端到端测试
```

## 说明与扩展点

- **任务队列**：当前为单进程内存队列 + 可配置 worker 数；多实例部署时可平滑替换为
  Celery/RQ（流水线 `process_job` 无需改动）。
- **进度**：校验阶段按行推进（5%→50%），上送阶段按批推进（50%→100%），前端轮询渲染进度条。
- **日志**：落库（`job_logs` 表）+ 控制台，前端按 `after_id` 增量拉取。
- **数据目录**：默认 `./data`（SQLite、上传文件），可用环境变量 `TRAINING_IMPORT_HOME` 覆盖。
