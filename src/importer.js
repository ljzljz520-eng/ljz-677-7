'use strict';
/**
 * 导入流水线：解析文件 → 逐行校验 → 分批上送行业平台 → 汇总落库。
 * 进度（percent）：校验阶段 0-50%，上送阶段 50-100%。
 */
const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');
const iconv = require('iconv-lite');
const { validateRecord } = require('./validator');
const { COURSES } = require('./courses');

const HEADER_ALIASES = {
  name: ['姓名', '学员姓名', 'name'],
  idNumber: ['证件号', '证件号码', '身份证号', '身份证', 'idnumber'],
  course: ['课程名称', '课程', '课程名', '课程编码', 'course'],
  hours: ['学时数', '学时', 'hours'],
};

function normHeader(h) {
  return String(h || '').replace(/[\s*　]/g, '').toLowerCase();
}

function mapHeaders(headerRow) {
  const map = {};
  headerRow.forEach((h, idx) => {
    const n = normHeader(h);
    for (const [field, aliases] of Object.entries(HEADER_ALIASES)) {
      if (!(field in map) && aliases.some(a => a.toLowerCase() === n)) map[field] = idx;
    }
  });
  return map;
}

/** CSV 解码：优先 UTF-8（含 BOM），失败回退 GBK */
function decodeCsvBuffer(buf) {
  if (buf.length >= 3 && buf[0] === 0xEF && buf[1] === 0xBB && buf[2] === 0xBF) {
    return buf.slice(3).toString('utf8');
  }
  if (buf.length >= 2 && buf[0] === 0xFF && buf[1] === 0xFE) {
    return iconv.decode(buf.slice(2), 'utf16-le');
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buf);
  } catch {
    return iconv.decode(buf, 'gbk');
  }
}

/** 简单 CSV 解析（支持引号转义），全部按字符串处理，避免 18 位证件号被转成科学计数法 */
function parseCsv(buf) {
  const text = decodeCsvBuffer(buf);
  const rows = [];
  let row = [], cur = '', inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { cur += '"'; i++; }
        else inQuotes = false;
      } else cur += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ',') { row.push(cur); cur = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(cur); cur = '';
      if (row.some(x => x !== '')) rows.push(row);
      row = [];
    } else cur += c;
  }
  if (cur !== '' || row.length) {
    row.push(cur);
    if (row.some(x => x !== '')) rows.push(row);
  }
  return rows;
}

/** 解析上传文件为二维数组（第一行为表头） */
function parseFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.csv') return parseCsv(fs.readFileSync(filePath));
  const wb = XLSX.readFile(filePath);
  const ws = wb.Sheets[wb.SheetNames[0]];
  return XLSX.utils.sheet_to_json(ws, { header: 1, raw: false, defval: '' });
}

function createImporter({ store, platform, batchSize = 50 }) {
  async function processTask(taskId) {
    const task = store.getTask(taskId);
    if (!task) return;
    const log = (level, msg) => store.addLog(taskId, level, msg);

    try {
      store.updateTask(taskId, { status: 'validating', percent: 0 });
      log('INFO', `开始处理文件「${task.filename}」`);

      const aoa = parseFile(task.storedPath);
      if (!aoa.length) throw new Error('文件为空或无法解析');

      const hmap = mapHeaders(aoa[0]);
      const missing = ['name', 'idNumber', 'course', 'hours'].filter(f => !(f in hmap));
      if (missing.length) {
        throw new Error(`缺少必需列（${missing.join(', ')}），表头应包含：姓名、证件号、课程名称、学时数`);
      }

      const dataRows = aoa.slice(1).filter(r => r.some(c => String(c).trim() !== ''));
      const total = dataRows.length;
      store.updateTask(taskId, { totalRows: total });
      log('INFO', `解析完成，共 ${total} 行数据，开始校验`);

      // ---- 阶段一：校验 ----
      const seen = new Set();
      const records = [];
      for (let i = 0; i < total; i++) {
        const r = dataRows[i];
        const rec = {
          rowNo: i + 2, // Excel 行号（含表头）
          name: String(r[hmap.name] ?? '').trim(),
          idNumber: String(r[hmap.idNumber] ?? '').trim(),
          course: String(r[hmap.course] ?? '').trim(),
          hours: String(r[hmap.hours] ?? '').trim(),
          status: 'valid',
          error: '',
        };
        const errs = validateRecord(rec, COURSES, seen);
        if (errs.length) { rec.status = 'invalid'; rec.error = errs.join('；'); }
        records.push(rec);
        if (i % 500 === 499) { // 大文件让出事件循环并刷新进度
          store.updateTask(taskId, { percent: Math.round((i + 1) / total * 45) });
          await new Promise(r => setImmediate(r));
        }
      }

      const valid = records.filter(r => r.status === 'valid');
      const invalid = records.filter(r => r.status === 'invalid');
      store.setRecords(taskId, records);
      store.updateTask(taskId, {
        validCount: valid.length,
        invalidCount: invalid.length,
        percent: valid.length ? 50 : 100,
      });
      log('INFO', `校验完成：有效 ${valid.length} 条，无效 ${invalid.length} 条`);
      invalid.slice(0, 20).forEach(r => log('WARN', `第${r.rowNo}行 校验失败：${r.error}`));
      if (invalid.length > 20) log('WARN', `…其余 ${invalid.length - 20} 条校验失败明细请下载修正模板查看`);

      // ---- 阶段二：分批上送行业平台 ----
      let success = 0, failed = 0;
      if (valid.length) {
        store.updateTask(taskId, { status: 'uploading' });
        log('INFO', `开始上送行业平台，共 ${valid.length} 条，每批 ${batchSize} 条`);
        for (let i = 0; i < valid.length; i += batchSize) {
          const batch = valid.slice(i, i + batchSize);
          const results = await platform.submitBatch(batch);
          for (let j = 0; j < batch.length; j++) {
            const rec = batch[j];
            const res = results[j];
            if (res.success) { rec.status = 'success'; success++; }
            else {
              rec.status = 'failed'; rec.error = res.error; failed++;
              log('ERROR', `第${rec.rowNo}行 上送失败：${res.error}`);
            }
          }
          const done = Math.min(i + batchSize, valid.length);
          store.setRecords(taskId, records);
          store.updateTask(taskId, {
            successCount: success,
            failCount: failed,
            percent: 50 + Math.round(done / valid.length * 50),
          });
          log('INFO', `上送进度 ${done}/${valid.length}（成功 ${success}，失败 ${failed}）`);
        }
      }

      store.setRecords(taskId, records);
      store.updateTask(taskId, {
        status: 'completed',
        percent: 100,
        successCount: success,
        failCount: failed,
        finishedAt: new Date().toISOString(),
      });
      const badTotal = invalid.length + failed;
      log('INFO', `任务完成：上送成功 ${success} 条，上送失败 ${failed} 条，校验无效 ${invalid.length} 条` +
        (badTotal ? '，可下载修正模板处理异常记录' : ''));
      store.save(true);
    } catch (e) {
      store.updateTask(taskId, {
        status: 'failed',
        error: e.message,
        finishedAt: new Date().toISOString(),
      });
      log('ERROR', `任务失败：${e.message}`);
      store.save(true);
    }
  }

  return { processTask };
}

module.exports = { createImporter, parseFile, parseCsv, mapHeaders };
