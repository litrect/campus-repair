# A2 系统设计与数据库交付包 0.2

项目：校园线上报修与后勤服务系统。依据：已上传的《需求规格说明书》V1.0（2026-10-11），重点核对第 3、5、6 章和附录 A。此目录是对原说明书的实施细化稿；原附件和 `sources/` 中的同步文件均未修改。

本版已修正首版权限、幂等、超时和日志设计中的问题，并在独立 MySQL 8.0.46 实例通过 17 项数据库验证。七张设计图已导出为 SVG。交付状态为“设计修订稿可评审”；应用尚未开发，不能将数据库测试结果作为端到端验收结果。

## 文件与使用顺序

1. [system-design.md](system-design.md)：业务规则、E-R 图、类图、状态图、四张时序图和字段设计。
2. [schema.sql](schema.sql)：MySQL 8.0.16+ 空库建库建表。先执行此文件。
3. [seed.sql](seed.sql)：可选的本机演示用户数据；后执行，不建议重复运行。
4. [api-contract.md](api-contract.md)：开发组对接用的接口、权限、参数与错误约定。
5. [review-and-tasks.md](review-and-tasks.md)：原说明书审查结果、待确认事项、任务拆解与验收清单。
6. [implementation-notes.md](implementation-notes.md)：事务、幂等、超时、派单推荐、登录、SQL 执行与回退细则。
7. [acceptance.md](acceptance.md)：全部 16 条功能和 8 条非功能需求追踪、24 个系统验收用例。
8. [diagrams/README.md](diagrams/README.md)：七张图的 SVG 和可编辑 Mermaid 文件。
9. [verification-report.md](verification-report.md)：实际核验范围、结果与局限；原始结果为 [verification-results.json](verification-results.json)。
10. [verify_delivery.py](verify_delivery.py)：可在新建测试库复现的数据库验证脚本。

## 与原说明书相比的主要修订建议

- 密码字段存哈希；演示账号也使用哈希，不采用原附录中的明文 `123456`。
- 补充外键、枚举检查、评分范围约束和查询索引。
- 增加 `request_token` 和 `request_hash`，区分大小写的联合唯一键与请求摘要共同支撑幂等。
- 增加 `repair_record` 和 `user.is_active`，使维修记录与“已停用维修工不可派”有明确数据承载。
- 扩展操作日志：记录操作后的版本、改派前后维修工，并约束事件与状态组合；系统首次超时标记也有日志。
- 接口统一以 `code: 0` 为成功；原先教学示例里的 `code: 200` 不作为交付约定。

SLA 数值、故障分类、推荐权重和 token 有效期已经给出具体建议，仍待小组接受后冻结。它们没有被冒称为原说明书的既定内容。

## 执行与核对

在 MySQL 8.0.16+ **新库**依次执行 `schema.sql`、`seed.sql`。演示用户初始密码见 seed.sql 注释。已有数据的数据库需要单独审定迁移方案，不能把这份新库脚本重复执行当作升级。完整操作与失败处理见实施细则。

复现验证时运行 verify_delivery.py，指定名称以 `a2_verify_` 开头且尚不存在的测试库；脚本拒绝改写已有库，不执行 DROP。17 项通过结果来自 MySQL 8.0.46，未对每个 8.0 小版本逐一验证。
