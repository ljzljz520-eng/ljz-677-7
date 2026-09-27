# 培训学时记录导入系统

管理员上传学员学时文件（Excel/CSV），系统经 **任务队列** 异步完成 **数据校验 → 分批上送行业平台**，前端实时展示 **进度条** 与 **日志**；平台退回的异常明细可一键下载 **修正模板**。

## 快速开始

```bash
npm start          # 启动服务，默认 http://localhost:3000
npm run sample     # 生成演示文件 data/sample.xlsx（123 行，含各类异常数据）
npm test           # 运行单元/集成测试
```

打开 http://localhost:3000 ，上传 `data/sample.xlsx` 即可看到完整流程：
排队 → 校验 → 上送 → 完成，异常记录可下载修正模板。

## 功能

- **文件上传**：`.xlsx / .xls / .csv`（CSV 自动识别 UTF-8/GBK 编码；证件号按文本处理，避免 18 位被转成科学计数法）
- **数据校验**
  - 姓名：2-30 个中文（可含 `·`）或英文字符
  - 证件号：18 位身份证（GB 11643 校验位 + 出生日期合法性），或 5-20 位字母数字（护照等）
  - 课程：必须在课程目录内（按编码或名称匹配，`GET /api/courses`）
  - 学时数：`0 < n ≤ 90` 且为 0.5 的整数倍
  - 文件内去重：同一证件号 + 同一课程只保留首条
- **任务队列**：进程内 FIFO 队列（`QUEUE_CONCURRENCY` 可调并发）；任务状态持久化，**服务重启后未完成任务自动重新入队**
- **进度条**：校验阶段 0-50%，上送阶段 50-100%，前端 1.5s 轮询刷新
- **日志**：每任务独立日志（页面实时查看，保留最近 500 条），并镜像写入 `logs/import.log`
- **修正模板**：校验失败 + 平台退回的记录合并导出 xlsx（含「异常原因」列），修正后可重新上传
- **行业平台对接**：`src/platformClient.js` 为模拟实现（确定性退回规则，便于演示）；真实对接时替换 `submitBatch` 为 HTTP 调用即可，返回结构 `[{ rowNo, success, error }]` 不变

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tasks` | 上传文件创建导入任务（multipart，字段名 `file`） |
| GET | `/api/tasks` | 任务列表（含进度、计数、队列状态） |
| GET | `/api/tasks/:id` | 任务详情 |
| GET | `/api/tasks/:id/logs` | 任务日志 |
| GET | `/api/tasks/:id/records?status=invalid` | 记录明细（可按 `valid/invalid/success/failed` 过滤） |
| GET | `/api/tasks/:id/correction-template` | 下载修正模板（无异常记录时 404） |
| GET | `/api/template` | 下载空白导入模板 |
| GET | `/api/courses` | 课程目录 |

## 导入文件格式

| 姓名 | 证件号 | 课程名称 | 学时数 |
|---|---|---|---|
| 张三 | 110101199003077758 | 安全生产法律法规 | 8 |
| 李四 | 320583199208154839 | C002 | 16.5 |

表头支持别名（如「身份证号/课程/学时」），课程列可填编码或名称。

## 目录结构

```
server.js            入口：组装依赖、恢复未完成任务、启动 HTTP
src/store.js         JSON 文件持久化（任务/记录/日志），防抖落盘
src/taskQueue.js     FIFO 任务队列（并发可配）
src/importer.js      导入流水线：解析 → 校验 → 分批上送 → 汇总
src/validator.js     姓名/证件号(含校验位)/课程/学时 校验规则
src/platformClient.js 行业平台客户端（模拟实现，可替换为真实 HTTP）
src/routes.js        REST API
src/courses.js       课程目录
public/index.html    管理页面（上传/进度条/日志/修正模板）
scripts/make-sample.js 生成演示数据
test/                node:test 单元与集成测试
```

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `PORT` | 3000 | 服务端口 |
| `DATA_DIR` | `./data` | 数据目录（db.json、上传文件） |
| `QUEUE_CONCURRENCY` | 1 | 队列并发数 |
| `BATCH_SIZE` | 50 | 上送平台批大小 |
| `PLATFORM_DELAY_MS` | 150 | 模拟平台每批延迟（演示进度条用） |

## 生产化说明

- 持久层可平滑替换为 SQLite/PostgreSQL（仅需重写 `store.js` 的实现，接口不变）
- 多实例部署时任务队列可替换为 Redis/RabbitMQ，`importer.processTask` 即为消费者逻辑
- 真实平台对接需保证幂等（建议以「证件号+课程编码」作为幂等键），重启重投不会产生重复学时
