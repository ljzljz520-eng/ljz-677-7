'use strict';
/**
 * 导入数据校验规则：
 *  - 姓名：2-30 个中文（可含·）或英文字符
 *  - 证件号：18 位身份证（GB 11643 校验位 + 出生日期合法性），或 5-20 位字母数字（护照等其他证件）
 *  - 课程：必须存在于课程目录（按编码或名称匹配）
 *  - 学时数：0 < n <= 90，且为 0.5 的整数倍
 *  - 文件内去重：同一证件号 + 同一课程只保留第一条
 */
const ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
const ID_CHECK_CHARS = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2'];

/** 计算 17 位身份证本体的校验位 */
function computeCheckDigit(id17) {
  let sum = 0;
  for (let i = 0; i < 17; i++) sum += Number(id17[i]) * ID_WEIGHTS[i];
  return ID_CHECK_CHARS[sum % 11];
}

function isValidIdCard(id) {
  if (!/^\d{17}[\dXx]$/.test(id)) return false;
  const y = Number(id.slice(6, 10));
  const m = Number(id.slice(10, 12));
  const d = Number(id.slice(12, 14));
  if (y < 1900 || y > new Date().getFullYear()) return false;
  if (m < 1 || m > 12) return false;
  const dim = new Date(y, m, 0).getDate();
  if (d < 1 || d > dim) return false;
  return computeCheckDigit(id.slice(0, 17)) === id[17].toUpperCase();
}

function validateName(v) {
  if (!v) return '姓名为空';
  if (/^[一-龥·]{2,30}$/.test(v)) return null;
  if (/^[A-Za-z][A-Za-z\s.\-]{1,29}$/.test(v)) return null;
  return '姓名格式不正确（应为2-30个中文或英文字符）';
}

function validateIdNumber(v) {
  if (!v) return '证件号为空';
  if (/^\d{17}[\dXx]$/.test(v)) {
    return isValidIdCard(v) ? null : '身份证号校验位或出生日期不合法';
  }
  if (/^[A-Za-z0-9]{5,20}$/.test(v)) return null; // 护照等其他证件
  return '证件号格式不正确（应为18位身份证或5-20位字母数字证件号）';
}

function findCourse(v, courses) {
  return courses.find(c => c.code === v || c.name === v) || null;
}

function validateCourse(v, courses) {
  if (!v) return '课程为空';
  if (!findCourse(v, courses)) return `课程「${v}」不在课程目录中`;
  return null;
}

function validateHours(v) {
  if (v === '' || v === null || v === undefined) return '学时数为空';
  const n = Number(v);
  if (!Number.isFinite(n)) return '学时数必须为数字';
  if (n <= 0) return '学时数必须大于0';
  if (n > 90) return '学时数超过上限（90）';
  if (Math.round(n * 2) !== n * 2) return '学时数必须为0.5的整数倍';
  return null;
}

/**
 * 校验整行。seen 为 Set，用于文件内去重（证件号+课程编码）。
 * 返回错误数组（空数组表示通过）。
 */
function validateRecord(row, courses, seen) {
  const errors = [];
  const eName = validateName(row.name); if (eName) errors.push(eName);
  const eId = validateIdNumber(row.idNumber); if (eId) errors.push(eId);
  const eCourse = validateCourse(row.course, courses); if (eCourse) errors.push(eCourse);
  const eHours = validateHours(row.hours); if (eHours) errors.push(eHours);
  if (!eId && !eCourse) {
    const course = findCourse(row.course, courses);
    const key = `${row.idNumber}::${course.code}`;
    if (seen.has(key)) errors.push('文件内重复记录（同一证件号+同一课程）');
    else seen.add(key);
  }
  return errors;
}

module.exports = {
  computeCheckDigit,
  isValidIdCard,
  validateName,
  validateIdNumber,
  validateCourse,
  validateHours,
  validateRecord,
  findCourse,
};
