# A2 实施细则与数据库执行说明

版本 0.2。本文件规定本次设计稿的实现方式；SLA 数值、分类清单等业务选择仍是待评审建议。所有 MySQL 连接开启严格 SQL 模式、关闭 autocommit 以显式管理业务事务，并设置 `time_zone='+08:00'`。日期精度为秒。

## 1 创建与幂等

服务端取得当前启用学生 ID，将 category/location/description trim，默认 urgency=NORMAL，将缺失图片转成 null。仅对这五个创建字段按固定键序、UTF-8 编码、无额外空白的 JSON 计算 SHA-256；序列化规则应集中为一个函数。request_token 来自 Idempotency-Key，request_hash 存该摘要；身份从当前用户取得，不从请求体读取。

先查 `(student_id,request_token)`：若存在，摘要相同返回既有 ID，摘要不同返回 409。若不存在，在一个事务内插入工单与 CREATE 日志（order_version=0）。并发插入撞到唯一键时回滚该事务，开启新事务重新读取，再比较摘要。工单编号碰撞仅能按 `uk_order_no` 单独重试，不能把所有唯一键异常都当幂等命中。日志失败必须回滚工单。

幂等重试返回既有工单当前状态与版本；不会把已派单的工单恢复为 CREATED。创建字段在当前范围内不提供修改接口，摘要在生命周期内保持不变。

## 2 状态变化与事务边界

统一入口为 `change_status(conn, order_id, expected_version, event, actor, payload)`。它依据事件、当前状态与用户共同判定权限，而不是让客户端直接指定任意目标状态。

1. 开始事务，查询工单；检查当前用户权限和可见性。
2. 将客户端 expected_version 与数据库 version 比较；不相同立即回滚并返回 409。
3. 从迁移表确定目标状态，校验所需字段。派单读取目标维修工时使用共享锁，检查角色 WORKER 和 is_active=1；停用操作也须走受控事务，避免“校验后、提交前被停用”的竞争。
4. 固定本次 `event_time`，计算字段更新与超时标志。条件更新使用 `id`、旧 `status`、客户端 `expected_version`；维修工动作额外带 `worker_id=actor.id`。
5. 检查影响行数恰为 1，插入日志，order_version=expected_version+1；日志与工单使用同一事件时间。
6. 一次提交；异常统一回滚。数据库死锁或锁等待超时回滚完整事务，再返回可重试错误，禁止只重试日志插入。

PyMySQL 派单语句示意如下，`%s` 是参数占位符，不能字符串拼接。超时字段的计算值由下节规则得出。

```sql
UPDATE repair_order
SET worker_id=%s, assign_time=%s, status='ASSIGNED',
    is_overtime=%s, version=version+1
WHERE id=%s AND status='CREATED' AND version=%s;

INSERT INTO order_log
  (order_id,event_type,from_status,to_status,order_version,
   operator_id,from_worker_id,to_worker_id,remark,create_time)
VALUES (%s,'ASSIGN','CREATED','ASSIGNED',%s,%s,NULL,%s,%s,%s);
```

改派保持 ASSIGNED，更新维修工和 assign_time，日志必须记旧、新维修工。接单写 accept_time；完成写 finish_time 与 repair_record；驳回清空 finish_time，保留最近维修记录，驳回原因写日志；确认写 close_time；取消不写 close_time，取消时刻记录在 CANCEL 日志。

评价必须在同一事务内检查工单为 CLOSED、学生归属后插入，order_id 唯一键兜底。同一工单不能修改或删除评价；重复评价返回 409。评价不修改 repair_order，不需要其 version。日志只追加，不开放编辑或删除接口。

数据库能约束外键、值域、单行字段完整性、日志合法迁移组合和唯一性；不能仅靠 DDL 保证操作人的业务权限或每次更新必有日志，后端统一入口及事务仍是必需的。

## 3 超时计算

待评审建议配置为 HIGH=4 小时、NORMAL=24 小时、LOW=72 小时，起点为 create_time。该组数值不是原说明书的既定要求；开发演示采用时须标明，需求组确认后写入配置。历史工单保存创建时计算的 deadline，配置变更不追溯重算。deadline 为 null 表示未配置，不作为“未超时”参与 SLA 达标率统计。

边界定义为严格 `event_time > deadline`，恰好到期不超时。原期限在改派、驳回后保持不变。首次完成后暂停当前超时判断；若学生驳回，立即恢复维修中并对原期限判定，不增加一轮宽限期。

| 当前状态或动作 | 有效超时判定 |
| --- | --- |
| CREATED/ASSIGNED/PROCESSING 查询 | now > deadline。 |
| FINISH 动作 | 用本次 finish_time 比 deadline，即使扫描尚未执行也必须持久化。 |
| DONE/CLOSED 查询 | 用 finish_time 比 deadline，不能把等待学生确认的时间计为维修超时。 |
| CONFIRM 动作 | 保留历史标记，并用现有 finish_time 补算。 |
| REJECT 动作 | 保留历史标记，并用本次驳回时间比原 deadline；清空 finish_time。 |
| CANCEL 动作 | 用本次取消时间比 deadline，保留历史标记。 |
| CANCELLED 历史查询 | 原有标记，或 CANCEL 日志 create_time > deadline。 |

`effectiveEverOvertime = (is_overtime=1) OR 上表相应的有效超时判定`，deadline=null 时仅保留已有标记。`isCurrentlyOverdue` 仅对 CREATED/ASSIGNED/PROCESSING 且 now > deadline 为 true。曾超时但已完成的工单属于历史超时，不出现在默认当前预警列表。

每次业务变更在同一事务中把 `is_overtime` 更新为旧值 OR 本次判定。扫描任务每 60 秒检查有效历史超时且标记仍为 0 的工单，以版本条件更新 0→1，并插入 OVERTIME 日志；操作者为空，状态前后一致。若版本已变化则本轮跳过并重新读取，不用旧数据覆盖。业务动作已经标记的工单不再增加 OVERTIME 日志。未达成 0→1 不递增版本，避免扫描不断制造用户版本冲突。

## 4 派单推荐与统计

待评审分类建议：水电、门锁、网络、家具、其他。服务端配置是唯一来源，前端读取 meta 接口；数据库保留 VARCHAR(20) 以允许调整。skill 按逗号分割后做完整标签相等比较，不能将“水”当成“水电”命中。

推荐分建议为 `100 × skillMatch - 10 × activeOrderCount`；skillMatch 为 0 或 1，activeOrderCount 只统计 ASSIGNED 和 PROCESSING。只返回启用维修工，同分按当前工单数升序、用户 ID 升序。该公式是可解释的规则评分，原说明书未指定具体权重；管理员仍可手动选择任一启用维修工。

工单统计可按 category/status/worker/day 分组。created 指标过滤 create_time；completed 指标过滤 close_time 且仅 CLOSED。传入时间区间均左闭右开，按 +08:00 解释。维修工工作量以最终 worker_id 归属；评价只取真实存在的评价，AVG(score) 以原始评分计算，展示可保留两位小数。若与 order_log 联查，应先按工单去重，不能因日志条数夸大数量。

## 5 登录与本机运行

建议使用 `itsdangerous.URLSafeTimedSerializer` 生成签名 token，载荷只含 uid；服务端密钥使用随机值并在本机配置持久化，有效期建议 8 小时。每次请求验证签名/时限并查询用户启用状态和当前角色。前端退出时清除 token；本方案不提供单个 token 的即时服务端撤销，若课程要求此能力，需另加会话存储设计。数据库 password 最长 255，使用密码库生成和验证哈希；不能将 SQL 的 SHA2 作为密码哈希算法。

前端依赖、本地图片与测试数据应随本机演示准备，不依赖 CDN。应用 API 不返回密码哈希。读取他人工单统一 404；操作角色无权则 403。

## 6 执行与回退

此处脚本用于新建数据库，不是已有 schema 的升级脚本。在 MySQL 客户端执行前检查服务器版本至少 8.0.16，并确认目标 `campus_repair` 是新库。schema.sql 含建库操作，需要相应权限；若使用已有数据库，应由数据库负责人先审定迁移差异，不能直接重复执行。

```sql
SOURCE C:/你的项目目录/A2/schema.sql;
SOURCE C:/你的项目目录/A2/seed.sql;
SHOW TABLES;
SHOW CREATE TABLE repair_order;
SELECT id, username, role, is_active FROM `user`;
```

MySQL DDL 有隐式提交，建表失败不能假设 ROLLBACK 会撤销已经创建的表。停止后先检查已创建对象，修复原因，再在新测试库重试。交付脚本不含 DROP，不自动清空既有数据。seed.sql 仅插入四个演示用户，重复执行会因唯一键报错；它没有修改密码或覆盖原账号的逻辑。

`verify_delivery.py` 在一个**不存在的新测试库**执行真实数据库验证。示例：

```powershell
python A2/verify_delivery.py --mysql "C:/Program Files/MySQL/MySQL Server 8.0/bin/mysql.exe" --host 127.0.0.1 --port 3306 --user root --database a2_verify_20261012
```

有密码时通过当前进程环境变量 MYSQL_PWD 传入，不写入脚本或命令行参数。脚本不删除测试库，不连接生产地址做默认测试；执行结束后保留测试结果，测试库由负责人按需清理。验证范围与实际记录见 verification-report.md。
