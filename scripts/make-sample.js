'use strict';
/** 生成演示用导入文件 data/sample.xlsx：混合有效记录、校验失败记录、平台退回记录 */
const path = require('path');
const XLSX = require('xlsx');
const { computeCheckDigit } = require('../src/validator');
const { COURSES } = require('../src/courses');

const SURNAMES = ['张', '王', '李', '赵', '刘', '陈', '杨', '黄', '周', '吴'];
const GIVEN = ['伟', '芳', '娜', '敏', '静', '磊', '军', '洋', '勇', '艳', '杰', '涛'];

function makeId(i) {
  const area = ['110101', '320583', '440305', '510107'][i % 4];
  const year = 1985 + (i % 20);
  const month = String(1 + (i % 12)).padStart(2, '0');
  const day = String(1 + (i % 28)).padStart(2, '0');
  const seq = String(100 + (i % 900));
  const body = `${area}${year}${month}${day}${seq}`;
  return body + computeCheckDigit(body);
}

const rows = [['姓名', '证件号', '课程名称', '学时数']];

// 1) 110 条有效记录（其中一部分会被模拟平台退回：证件号数字和%17==0，或学时>60）
for (let i = 0; i < 110; i++) {
  const name = SURNAMES[i % 10] + GIVEN[(i * 7) % 12];
  const course = COURSES[i % COURSES.length];
  const hours = [4, 8, 12, 16, 24, 32][i % 6];
  rows.push([name, makeId(i), i % 3 === 0 ? course.code : course.name, String(hours)]);
}
// 两条学时合法(<=90)但平台会退回(>60)的记录
rows.push(['钱进', makeId(200), 'C001', '72']);
rows.push(['孙强', makeId(201), 'C005', '80']);

// 2) 校验失败记录
rows.push(['', makeId(300), 'C001', '8']);                 // 姓名为空
rows.push(['张', makeId(301), 'C001', '8']);                // 姓名太短
rows.push(['李雷', '123', 'C001', '8']);                    // 证件号格式错误
rows.push(['韩梅', '11010119900307775X', 'C002', '8']);     // 身份证校验位错误
rows.push(['Jim Green', makeId(302), '量子物理导论', '8']); // 课程不存在
rows.push(['周舟', makeId(303), 'C003', '0']);              // 学时为 0
rows.push(['吴迪', makeId(304), 'C003', '120']);            // 学时超上限
rows.push(['郑爽', makeId(305), 'C004', '7.3']);            // 学时不为 0.5 的倍数
rows.push(['冯刚', makeId(306), 'C004', 'abc']);            // 学时非数字

// 3) 文件内重复记录
rows.push(['陈晨', makeId(400), 'C006', '16']);
rows.push(['陈晨', makeId(400), 'C006', '16']);             // 同人同课程重复

const ws = XLSX.utils.aoa_to_sheet(rows);
ws['!cols'] = [{ wch: 12 }, { wch: 22 }, { wch: 20 }, { wch: 8 }];
const wb = XLSX.utils.book_new();
XLSX.utils.book_append_sheet(wb, ws, '学时导入');
const out = path.join(__dirname, '..', 'data', 'sample.xlsx');
XLSX.writeFile(wb, out);
console.log(`已生成 ${out}，共 ${rows.length - 1} 行数据`);
