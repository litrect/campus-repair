-- 仅供本机演示；与 schema.sql 在同一数据库执行。
-- 演示密码均为 Demo@123456，存储的是 Werkzeug PBKDF2 哈希。
-- 仅作可复现测试夹具，不代表生产账号或真实联系方式。重复执行将因用户名唯一键失败。
USE campus_repair;
SET time_zone = '+08:00';

INSERT INTO `user` (username, password, real_name, role, phone, skill) VALUES
('admin', 'pbkdf2:sha256:600000$a2admin2026$a8c9136162155e62b7b7d4a2d5b9aa04b2d2a98c6bff1cd2d9b1a78d64fbb8c0', '后勤管理员', 'ADMIN', '13800000000', NULL),
('worker1', 'pbkdf2:sha256:600000$a2worker12026$d667e28e299fee6263551493627d7a372c51ed1a3b2844719cda9beb1022f7fd', '王师傅', 'WORKER', '13800000001', '水电,门锁'),
('worker2', 'pbkdf2:sha256:600000$a2worker22026$5ed6112c2a57881ea16380c46a5a0a6bcf3a25d16bb9b032526b106c4fe162ff', '李师傅', 'WORKER', '13800000002', '网络,家具'),
('stu1', 'pbkdf2:sha256:600000$a2student2026$8360227d0b8f2494ef736b45fd1f79c6ebb228204d44d0a77d09606ae712d5c4', '张同学', 'STUDENT', '13800000003', NULL);
