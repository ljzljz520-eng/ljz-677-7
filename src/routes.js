'use strict';
const express = require('express');
const multer = require('multer');
const path = require('path');
const XLSX = require('xlsx');
const { COURSES } = require('./courses');
const { computeCheckDigit } = require('./validator');

/** 修正 multer 对中文文件名的 latin1 解码问题 */
function fixFileName(name) {
  try { return Buffer.from(name, 'latin1').toString('utf8'); } catch { return name; }
}

function sendWorkbook(res, wb, filename) {
  const buf = XLSX.write(wb, { type: 'buffer', bookType: 'xlsx' });
  res.setHeader('Content-Disposition',
    `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`);
  res.setHeader('Content-Type',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  res.send(buf);
}

function createRouter({ store, queue }) {
  const router = express.Router();

  const upload = multer({
    storage: multer.diskStorage({
      destination: store.uploadDir,
      filename: (req, file, cb) => cb(null,
        `${Date.now()}-${Math.random().toString(36).slice(2, 8)}${path.extname(file.originalname)}`),
    }),
    limits: { fileSize: 20 * 1024 * 1024 },
    fileFilter: (req, file, cb) => {
      const ext = path.extname(file.originalname).toLowerCase();
      if (['.xlsx', '.xls', '.csv'].includes(ext)) cb(null, true);
      else cb(new Error('仅支持 .xlsx / .xls / .csv 文件'));
    },
  });

  /** 创建导入任务（上传文件） */
  router.post('/tasks', upload.single('file'), (req, res) => {
    if (!req.file) return res.status(400).json({ error: '请上传文件（字段名 file）' });
    const id = store.nextId();
    const task = {
      id,
      filename: fixFileName(req.file.originalname),
      storedPath: req.file.path,
      size: req.file.size,
      status: 'queued',
      percent: 0,
      totalRows: 0, validCount: 0, invalidCount: 0,
      successCount: 0, failCount: 0,
      error: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      finishedAt: null,
    };
    store.createTask(task);
    store.addLog(id, 'INFO', `任务创建，文件「${task.filename}」（${task.size} 字节），已进入队列`);
    queue.enqueue(id);
    res.status(201).json({ taskId: id });
  });

  /** 任务列表（前端轮询进度） */
  router.get('/tasks', (req, res) => {
    const q = queue.stats();
    res.json(store.listTasks().map(({ storedPath, ...t }) => ({ ...t, queue: q })));
  });

  router.get('/tasks/:id', (req, res) => {
    const t = store.getTask(req.params.id);
    if (!t) return res.status(404).json({ error: '任务不存在' });
    const { storedPath, ...pub } = t;
    res.json(pub);
  });

  /** 任务日志 */
  router.get('/tasks/:id/logs', (req, res) => {
    if (!store.getTask(req.params.id)) return res.status(404).json({ error: '任务不存在' });
    res.json(store.getLogs(req.params.id));
  });

  /** 记录明细（可按状态过滤：valid/invalid/success/failed） */
  router.get('/tasks/:id/records', (req, res) => {
    if (!store.getTask(req.params.id)) return res.status(404).json({ error: '任务不存在' });
    let recs = store.getRecords(req.params.id);
    if (req.query.status) recs = recs.filter(r => r.status === req.query.status);
    res.json(recs.slice(0, 500));
  });

  /** 下载修正模板（校验失败 + 平台退回的记录，含异常原因列） */
  router.get('/tasks/:id/correction-template', (req, res) => {
    const t = store.getTask(req.params.id);
    if (!t) return res.status(404).json({ error: '任务不存在' });
    const bad = store.getRecords(t.id)
      .filter(r => r.status === 'invalid' || r.status === 'failed');
    if (!bad.length) return res.status(404).json({ error: '该任务没有异常记录，无需修正' });
    const aoa = [['行号', '姓名', '证件号', '课程名称', '学时数', '异常原因']];
    for (const r of bad) aoa.push([r.rowNo, r.name, r.idNumber, r.course, r.hours, r.error]);
    const ws = XLSX.utils.aoa_to_sheet(aoa);
    ws['!cols'] = [{ wch: 6 }, { wch: 12 }, { wch: 22 }, { wch: 20 }, { wch: 8 }, { wch: 42 }];
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, '待修正记录');
    sendWorkbook(res, wb, `任务${t.id}_修正模板.xlsx`);
  });

  /** 下载空白导入模板（含示例行） */
  router.get('/template', (req, res) => {
    const id1 = '110101199003077' + '75';
    const id2 = '320583199208154' + '83';
    const aoa = [
      ['姓名', '证件号', '课程名称', '学时数'],
      ['张三', id1.slice(0, 17) + computeCheckDigit(id1.slice(0, 17)), '安全生产法律法规', '8'],
      ['李四', id2.slice(0, 17) + computeCheckDigit(id2.slice(0, 17)), 'C002', '16.5'],
    ];
    const ws = XLSX.utils.aoa_to_sheet(aoa);
    ws['!cols'] = [{ wch: 12 }, { wch: 22 }, { wch: 20 }, { wch: 8 }];
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, '学时导入');
    sendWorkbook(res, wb, '学时导入模板.xlsx');
  });

  /** 课程目录 */
  router.get('/courses', (req, res) => res.json(COURSES));

  return router;
}

module.exports = { createRouter };
