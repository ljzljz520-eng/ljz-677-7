'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const {
  computeCheckDigit, isValidIdCard,
  validateName, validateIdNumber, validateCourse, validateHours, validateRecord,
} = require('../src/validator');
const { COURSES } = require('../src/courses');

const VALID_ID = '110101199003077' + '75'; // 本体17位
const VALID_ID_FULL = VALID_ID + computeCheckDigit(VALID_ID);

test('身份证校验位计算与验证', () => {
  assert.strictEqual(computeCheckDigit(VALID_ID), VALID_ID_FULL[17]);
  assert.ok(isValidIdCard(VALID_ID_FULL));
  // 篡改校验位
  const bad = VALID_ID_FULL.slice(0, 17) + (VALID_ID_FULL[17] === '1' ? '2' : '1');
  assert.ok(!isValidIdCard(bad));
  // 非法出生月份
  assert.ok(!isValidIdCard('110101199013077' + '75' + 'X'));
  // 长度不符
  assert.ok(!isValidIdCard('1101011990030775'));
});

test('证件号校验', () => {
  assert.strictEqual(validateIdNumber(VALID_ID_FULL), null);
  assert.strictEqual(validateIdNumber('E12345678'), null); // 护照类
  assert.ok(validateIdNumber(''));
  assert.ok(validateIdNumber('abc'));
  assert.ok(validateIdNumber('11010119900307775X')); // 校验位错
  assert.ok(validateIdNumber('1101 0119900307 7758')); // 含空格
});

test('姓名校验', () => {
  assert.strictEqual(validateName('张三'), null);
  assert.strictEqual(validateName('欧阳娜娜娜'), null);
  assert.strictEqual(validateName('John Doe'), null);
  assert.strictEqual(validateName('阿不都·外力'), null);
  assert.ok(validateName(''));
  assert.ok(validateName('张'));
  assert.ok(validateName('张三123'));
});

test('课程校验（编码或名称）', () => {
  assert.strictEqual(validateCourse('C001', COURSES), null);
  assert.strictEqual(validateCourse('安全生产法律法规', COURSES), null);
  assert.ok(validateCourse('量子物理导论', COURSES));
  assert.ok(validateCourse('', COURSES));
});

test('学时校验', () => {
  assert.strictEqual(validateHours('8'), null);
  assert.strictEqual(validateHours('0.5'), null);
  assert.strictEqual(validateHours('90'), null);
  assert.strictEqual(validateHours('16.5'), null);
  assert.ok(validateHours(''));
  assert.ok(validateHours('0'));
  assert.ok(validateHours('-3'));
  assert.ok(validateHours('90.5'));
  assert.ok(validateHours('7.3'));
  assert.ok(validateHours('abc'));
});

test('整行校验 + 文件内去重', () => {
  const seen = new Set();
  const row = { name: '张三', idNumber: VALID_ID_FULL, course: 'C001', hours: '8' };
  assert.deepStrictEqual(validateRecord(row, COURSES, seen), []);
  // 同人同课程第二条 → 重复
  const errs = validateRecord({ ...row }, COURSES, seen);
  assert.ok(errs.some(e => e.includes('重复')));
  // 同课程不同人 → 通过
  const other = { ...row, idNumber: '320583199208154' + '83' };
  other.idNumber = other.idNumber + computeCheckDigit(other.idNumber);
  assert.deepStrictEqual(validateRecord(other, COURSES, seen), []);
});
