'use strict';
/**
 * 进程内 FIFO 任务队列（并发可配）。
 * 任务状态持久化在 Store 中，服务重启后未完成任务可重新入队。
 */
class TaskQueue {
  constructor({ concurrency = 1 } = {}) {
    this.concurrency = concurrency;
    this.queue = [];
    this.running = 0;
    this.active = new Set();
    this.processor = null;
  }

  setProcessor(fn) { this.processor = fn; }

  enqueue(taskId) {
    if (this.active.has(taskId) || this.queue.includes(taskId)) return false;
    this.queue.push(taskId);
    this._pump();
    return true;
  }

  _pump() {
    while (this.running < this.concurrency && this.queue.length > 0) {
      const taskId = this.queue.shift();
      this.running++;
      this.active.add(taskId);
      Promise.resolve()
        .then(() => this.processor(taskId))
        .catch(err => console.error(`[queue] 任务#${taskId} 处理异常:`, err))
        .finally(() => {
          this.running--;
          this.active.delete(taskId);
          this._pump();
        });
    }
  }

  stats() { return { pending: this.queue.length, running: this.running }; }
}

module.exports = { TaskQueue };
