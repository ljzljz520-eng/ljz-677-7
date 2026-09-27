'use strict';
const path = require('path');
const express = require('express');
const { Store } = require('./src/store');
const { TaskQueue } = require('./src/taskQueue');
const { createPlatformClient } = require('./src/platformClient');
const { createImporter } = require('./src/importer');
const { createRouter } = require('./src/routes');

const PORT = Number(process.env.PORT || 3000);

// ---- 组装依赖 ----
const store = new Store(process.env.DATA_DIR);
const queue = new TaskQueue({ concurrency: Number(process.env.QUEUE_CONCURRENCY || 1) });
const platform = createPlatformClient({ delayMs: Number(process.env.PLATFORM_DELAY_MS || 150) });
const importer = createImporter({ store, platform, batchSize: Number(process.env.BATCH_SIZE || 50) });
queue.setProcessor(importer.processTask);

// ---- 服务重启恢复：未完成任务重新入队 ----
for (const t of store.listTasks()) {
  if (['queued', 'validating', 'uploading'].includes(t.status)) {
    store.updateTask(t.id, { status: 'queued', percent: 0 });
    store.addLog(t.id, 'WARN', '服务重启，任务重新入队（行业平台上送具备幂等性，重复上送不会产生重复学时）');
    queue.enqueue(t.id);
  }
}

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use('/api', createRouter({ store, queue }));
// 统一错误处理（含 multer 错误）
app.use((err, req, res, next) => { // eslint-disable-line no-unused-vars
  res.status(400).json({ error: err.message || '请求失败' });
});

app.listen(PORT, () => {
  console.log(`培训学时记录导入系统已启动: http://localhost:${PORT}`);
});
