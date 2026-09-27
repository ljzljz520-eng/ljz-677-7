'use strict';
/**
 * 行业平台客户端（模拟实现）。
 * 真实对接时替换 createPlatformClient 内的 submitBatch 为 HTTP 调用即可，
 * 返回结构保持 [{ rowNo, success, error }]。
 *
 * 模拟规则（确定性，便于演示与测试）：
 *  - 证件号数字和 % 17 === 0  → 学员未注册
 *  - 单课程学时 > 60          → 超过平台上限
 */
const DEFAULT_DELAY_MS = 150;

function digitSum(s) {
  let t = 0;
  for (const ch of String(s)) if (ch >= '0' && ch <= '9') t += Number(ch);
  return t;
}

function platformCheck(rec) {
  if (digitSum(rec.idNumber) % 17 === 0) return '行业平台：学员未注册或证件信息不符';
  if (Number(rec.hours) > 60) return '行业平台：单课程学时超过平台上限(60)';
  return null;
}

function createPlatformClient(opts = {}) {
  const delayMs = opts.delayMs ?? DEFAULT_DELAY_MS;
  return {
    /** 提交一批记录，返回逐条结果 */
    async submitBatch(records) {
      if (delayMs) await new Promise(r => setTimeout(r, delayMs));
      return records.map(r => {
        const error = platformCheck(r);
        return { rowNo: r.rowNo, success: !error, error };
      });
    },
  };
}

module.exports = { createPlatformClient };
