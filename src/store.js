'use strict';
/**
 * 轻量 JSON 文件持久化（零外部依赖）。
 * 生产环境可替换为 SQLite/PostgreSQL，接口保持不变。
 */
const fs = require('fs');
const path = require('path');

const LOG_CAP = 500; // 每个任务最多保留的日志条数

class Store {
  constructor(dataDir) {
    this.dataDir = dataDir || path.join(__dirname, '..', 'data');
    this.dbFile = path.join(this.dataDir, 'db.json');
    this.uploadDir = path.join(this.dataDir, 'uploads');
    fs.mkdirSync(this.uploadDir, { recursive: true });
    this.logDir = path.join(__dirname, '..', 'logs');
    fs.mkdirSync(this.logDir, { recursive: true });
    this.db = { seq: 1, tasks: [], records: {}, logs: {} };
    this._timer = null;
    this._load();
  }

  _load() {
    try {
      if (fs.existsSync(this.dbFile)) {
        const parsed = JSON.parse(fs.readFileSync(this.dbFile, 'utf8'));
        this.db = Object.assign({ seq: 1, tasks: [], records: {}, logs: {} }, parsed);
      }
    } catch (e) {
      console.error('[store] 数据文件加载失败，使用空库:', e.message);
    }
  }

  /** 防抖落盘；immediate=true 时立即写 */
  save(immediate = false) {
    if (immediate) { this._write(); return; }
    if (this._timer) return;
    this._timer = setTimeout(() => { this._timer = null; this._write(); }, 300);
    if (this._timer.unref) this._timer.unref();
  }

  _write() {
    const tmp = this.dbFile + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(this.db));
    fs.renameSync(tmp, this.dbFile);
  }

  nextId() { const id = this.db.seq++; this.save(); return id; }

  createTask(task) { this.db.tasks.push(task); this.save(); return task; }

  updateTask(id, patch) {
    const t = this.getTask(id);
    if (!t) return null;
    Object.assign(t, patch, { updatedAt: new Date().toISOString() });
    this.save();
    return t;
  }

  getTask(id) { return this.db.tasks.find(t => t.id === Number(id)); }

  listTasks() { return [...this.db.tasks].sort((a, b) => b.id - a.id); }

  setRecords(taskId, records) { this.db.records[String(taskId)] = records; this.save(); }

  getRecords(taskId) { return this.db.records[String(taskId)] || []; }

  addLog(taskId, level, message) {
    const key = String(taskId);
    if (!this.db.logs[key]) this.db.logs[key] = [];
    const arr = this.db.logs[key];
    const ts = new Date().toISOString();
    arr.push({ ts, level, message });
    if (arr.length > LOG_CAP) arr.splice(0, arr.length - LOG_CAP);
    this.save();
    // 同步镜像到文件日志
    fs.appendFile(
      path.join(this.logDir, 'import.log'),
      `${ts} [${level}] [task#${taskId}] ${message}\n`,
      () => {}
    );
  }

  getLogs(taskId) { return this.db.logs[String(taskId)] || []; }
}

module.exports = { Store };
