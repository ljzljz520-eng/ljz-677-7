'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { Store } = require('../src/store');
const { TaskQueue } = require('../src/taskQueue');
const { createImporter } = require('../src/importer');
const { computeCheckDigit } = require('../src/validator');

function makeId(body17) { return body17 + computeCheckDigit(body17); }

test('导入流水线端到端：解析→校验→上送→异常统计', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'import-test-'));
  const store = new Store(dir);
  const queue = new TaskQueue({ concurrency: 1 });
  // 模拟平台：学时 > 60 退回
  const platform = {
    async submitBatch(records) {
      return records.map(r => ({
        rowNo: r.rowNo,
        success: Number(r.hours) <= 60,
        error: Number(r.hours) > 60 ? '行业平台：单课程学时超过平台上限(60)' : null,
      }));
    },
  };
  const importer = createImporter({ store, platform, batchSize: 2 });
  queue.setProcessor(importer.processTask);

  const id1 = makeId('11010119900307775');
  const id2 = makeId('32058319920815483');
  const id3 = makeId('44030519881120334');
  const id4 = makeId('51010719950612447');
  const csv = [
    '姓名,证件号,课程名称,学时数',
    `张三,${id1},C001,8`,            // 成功
    '李四,123,C001,8',               // 证件号无效（非18位身份证且不足5位）
    `王五,${id2},不存在的课程,8`,     // 课程无效
    `赵六,${id3},C002,8`,            // 成功
    `赵六,${id3},C002,8`,            // 重复
    `孙七,${id4},C003,72`,           // 平台退回(>60)
  ].join('\n');
  const file = path.join(dir, 'test.csv');
  fs.writeFileSync(file, csv);

  const id = store.nextId();
  store.createTask({
    id, filename: 'test.csv', storedPath: file, size: csv.length,
    status: 'queued', percent: 0,
    totalRows: 0, validCount: 0, invalidCount: 0, successCount: 0, failCount: 0,
    error: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), finishedAt: null,
  });
  queue.enqueue(id);
  await new Promise(r => setTimeout(r, 500)); // 等待队列处理完成

  const t = store.getTask(id);
  assert.strictEqual(t.status, 'completed');
  assert.strictEqual(t.percent, 100);
  assert.strictEqual(t.totalRows, 6);
  assert.strictEqual(t.invalidCount, 3); // 证件号、课程、重复
  assert.strictEqual(t.validCount, 3);
  assert.strictEqual(t.successCount, 2);
  assert.strictEqual(t.failCount, 1);

  const records = store.getRecords(id);
  assert.strictEqual(records.length, 6);
  const bad = records.filter(r => r.status === 'invalid' || r.status === 'failed');
  assert.strictEqual(bad.length, 4); // 修正模板应包含 4 行
  assert.ok(bad.every(r => r.error));

  const logs = store.getLogs(id);
  assert.ok(logs.some(l => l.message.includes('校验完成')));
  assert.ok(logs.some(l => l.message.includes('任务完成')));
});

test('缺少必需列时任务失败并记录日志', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'import-test-'));
  const store = new Store(dir);
  const importer = createImporter({ store, platform: { submitBatch: async () => [] } });
  const file = path.join(dir, 'bad.csv');
  fs.writeFileSync(file, '姓名,部门\n张三,一部\n');
  const id = store.nextId();
  store.createTask({
    id, filename: 'bad.csv', storedPath: file, size: 10,
    status: 'queued', percent: 0,
    totalRows: 0, validCount: 0, invalidCount: 0, successCount: 0, failCount: 0,
    error: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), finishedAt: null,
  });
  await importer.processTask(id);
  const t = store.getTask(id);
  assert.strictEqual(t.status, 'failed');
  assert.ok(t.error.includes('缺少必需列'));
});
