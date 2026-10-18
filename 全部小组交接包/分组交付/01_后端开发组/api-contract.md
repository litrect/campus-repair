# A2 接口契约修订稿 0.2

依据需求规格说明书 5.6；本稿给出可供联调的完整约定，包含原表遗漏的取消、日志和评价汇总等功能。除图片上传采用 multipart/form-data 外，请求和响应使用 JSON。新增约定是 A2 设计建议，尚未将原说明书升级为新的已批准版本。

## 通用规则

- 登录以外的请求带 `Authorization: Bearer <token>`。token 提供用户 ID；后端每次查询该用户是否启用及其当前角色，不能信任请求体传来的 `studentId`、`operatorId`、`status` 或 `isOvertime`。建议采用 Flask 依赖 itsdangerous 的限时签名 token，有效期 8 小时，细则见实施说明；这是设计建议。
- 成功使用 HTTP 2xx 与 `{ "code": 0, "message": "成功", "data": ... }`；失败使用对应 HTTP 状态与非零 `code`。建议 `400` 参数错误、`401` 未登录、`403` 无权限、`404` 不存在或不可访问、`409` 状态或版本冲突、`422` 业务规则不满足。
- 改派、接单、完成、确认、驳回、取消均带 `version`；评价仅新增评价行，不要求工单版本。所有工单更新返回新版本。页面冲突时刷新详情再决定是否重试。
- 所有 BIGINT 类型的 ID 在 JSON 中使用十进制字符串，避免浏览器整数精度丢失；`version`、评分、分页计数使用 JSON 整数，拒绝布尔值冒充数字。
- 列表使用 `page`（默认 1）、`pageSize`（默认 20，上限 100）；响应统一 `{items:[],total:0,page:1,pageSize:20}`。普通工单按 `create_time DESC,id DESC`，日志按 `order_version ASC`。
- 时间统一输出带时区的 `YYYY-MM-DDTHH:mm:ss+08:00`；日期过滤的 `from` 含边界、`to` 不含边界。缺省范围为全部时间，`from >= to` 返回 400。
- 图片上限 2 MiB（2,097,152 字节）；超限返回 HTTP 413。格式白名单 PNG/JPEG，验证实际文件内容而非仅扩展名。

## 接口清单

| 功能 | 方法和路径 | 角色 | 关键请求 | 成功数据 |
| --- | --- | --- | --- | --- |
| 登录 | `POST /api/auth/login` | 公开 | `username,password` | `token,expiresIn,user{id,realName,role}` |
| 表单选项 | `GET /api/meta/order-options` | 已登录用户 | 无 | `categories,urgencies` |
| 上传图片 | `POST /api/uploads/images` | 学生 | multipart 字段 `file` | `imageUrl` |
| 提交报修 | `POST /api/orders` | 学生 | `category,location,description,urgency,imageUrl?`；请求头 `Idempotency-Key` | `id,orderNo,status,version` |
| 我的报修 | `GET /api/orders/my` | 学生 | `page,pageSize,status?` | 分页工单摘要 |
| 我的维修工单 | `GET /api/orders/assigned-to-me` | 维修工 | `page,pageSize,status?` | 分页工单摘要 |
| 工单详情 | `GET /api/orders/{id}` | 有权限的角色 | 无 | 完整工单、当前版本与维修记录 |
| 待派单 | `GET /api/orders/pending` | 管理员 | `page,pageSize` | 状态为 `CREATED` 的列表 |
| 可选维修工 | `GET /api/workers/available` | 管理员 | `category?` | 启用维修工、技能、当前工单数、推荐分 |
| 派单或改派 | `POST /api/orders/{id}/assign` | 管理员 | `workerId,version` | 工单新状态与版本 |
| 接单 | `POST /api/orders/{id}/accept` | 当前维修工 | `version` | `PROCESSING,version` |
| 提交完成 | `POST /api/orders/{id}/finish` | 当前维修工 | `version,repairRecord` | `DONE,version` |
| 确认完成 | `POST /api/orders/{id}/confirm` | 报修学生 | `version` | `CLOSED,version` |
| 驳回 | `POST /api/orders/{id}/reject` | 报修学生 | `version,reason` | `PROCESSING,version` |
| 取消 | `POST /api/orders/{id}/cancel` | 学生或管理员 | `version,reason` | `CANCELLED,version` |
| 流转记录 | `GET /api/orders/{id}/logs` | 有权限的角色 | 无 | 按 `create_time,id` 排序的日志 |
| 评价 | `POST /api/orders/{id}/evaluate` | 报修学生 | `score,content?` | 评价 ID；重复提交返回 409 |
| 评价汇总 | `GET /api/stats/evaluations` | 管理员 | `workerId?,page,pageSize` | 平均分、评价数和列表 |
| 工单统计 | `GET /api/stats/orders` | 管理员 | `metric,groupBy,from?,to?,category?,status?` | `metric,groupBy,total,buckets` |
| 超时工单 | `GET /api/orders/overtime` | 管理员 | `scope=active或history,page,pageSize` | 超时工单列表 |

说明书 5.6 有 13 个接口，本稿共 20 个业务接口，其中 7 个为实现已有功能补充：表单选项、上传图片、我的维修工单、可选维修工、取消、流转记录、评价汇总。图片访问路由另见下文。

## 关键请求与响应示例

提交报修，请求头 `Idempotency-Key: 6ddcf270-1d0c-4e85-b3a9-68e3b6e42a1e`：

```json
{
  "category": "水电",
  "location": "A栋101",
  "description": "水龙头漏水",
  "urgency": "HIGH",
  "imageUrl": null
}
```

```json
{
  "code": 0,
  "message": "提交成功",
  "data": { "id": "101", "orderNo": "BX202610120001", "status": "CREATED", "version": 0 }
}
```

首次创建返回 HTTP 201；同一学生使用同一幂等键重试时返回 HTTP 200 和既有工单 ID，不修改状态、不增加日志；同一键不同摘要返回 409。`orderNo` 建议使用 32 位 UUID 十六进制字符串，数据库唯一键兜底并限制碰撞重试次数；示例编号仅用于展示，不表示已设计日期流水号分配器。

派单：

```json
{ "workerId": "2", "version": 0 }
```

成功后返回：

```json
{
  "code": 0,
  "message": "派单成功",
  "data": { "id": "101", "status": "ASSIGNED", "workerId": "2", "version": 1 }
}
```

当前页面版本过期时：

```json
{ "code": 409, "message": "该工单刚被其他人处理，请刷新后重试", "data": null }
```

## 字段与页面对照

| 页面或动作 | API 输入或输出 | 数据库字段 |
| --- | --- | --- |
| 报修表单 | `category,location,description,imageUrl,urgency` | 同名字段 `image_url` 使用蛇形命名 |
| 报修列表与详情 | `id,orderNo,status,createTime,version` | `id,order_no,status,create_time,version` |
| 派单选择 | `workerId,version` | `worker_id,version`；服务端写 `assign_time` |
| 维修结果 | `repairRecord,version` | `repair_record,finish_time,version`；日志留副本 |
| 学生确认 | `version` | `status,close_time,version` |
| 驳回 | `reason,version` | 日志 `remark`；`status,version` |
| 评价 | `score,content` | `evaluation.score,content` |
| 超时列表 | 输出 `deadline,isOvertime` | `deadline,is_overtime` |

请求的 camelCase 与数据库的 snake_case 由后端显式映射，不直接将请求 JSON 拼接进 SQL。原说明书没有规定响应 `data` 的具体结构，本页示例供前后端联调冻结。

## 校验和权限顺序

先校验 token 与账号启用状态，再检查接口角色，再检查工单可见性，最后校验状态、版本及业务字段。未登录或 token 无效返回 401；角色无权使用接口返回 403；工单不存在或不属于该用户返回统一 404；已知工单版本过期或状态不合法返回 409。停用/不存在/非维修工的派单目标返回 422。任何失败不得留下半完成工单或日志。

| 字段 | 请求校验 |
| --- | --- |
| username/password | 必填字符串，用户名最长 50 字符；密码不 trim，登录错误统一提示账号或密码错误，不返回密码哈希。 |
| Idempotency-Key | 必填，1–64 位 ASCII 字母、数字、下划线或连字符，区分大小写；新一次提交生成新值。 |
| category | 必填，trim 后必须属于 `/api/meta/order-options` 返回值，最长 20 字符。 |
| location/description | 必填字符串，trim 后非空，分别不超过 100/500 字符。 |
| urgency | 缺省 NORMAL，仅 HIGH/NORMAL/LOW，大小写严格匹配。 |
| imageUrl | 可省略或 null；只能引用当前学生上传的有效本机图片，不接受任意外链或路径。 |
| workerId/路径 id | 正十进制整数字符串，范围不超过有符号 BIGINT，拒绝 0、负数和小数。 |
| version | 必填整数，范围 0 至 2147483646；后台达到上限时拒绝继续更新并记录错误。 |
| repairRecord | trim 后 1–500 字符；每次提交完成均必填。 |
| reject.reason | trim 后 1–500 字符，必填。 |
| cancel.reason | 可选，最长 500 字符。 |
| score/content | score 为整数 1–5；content 可省略，最长 300 字符。 |

未知字段返回 400，防止客户端误传身份或状态字段。一般参数错误返回 400，图片超限返回 413，禁止只通过前端按钮控制权限。

## 数据结构

`OrderSummary` 包含 `id,orderNo,category,location,urgency,status,workerId,createTime,deadline,isOvertime,isCurrentlyOverdue,version`。布尔值使用 JSON boolean，`workerId`、`deadline` 可为 null。

`OrderDetail` 在摘要上增加 `description,imageUrl,repairRecord,studentId,assignTime,acceptTime,finishTime,closeTime,evaluation`；没有记录时为 null。`evaluation` 若存在为 `{id,score,content,createTime}`。不返回 `request_hash`、`request_token`、密码或不必要的手机号。

`OrderLog` 包含 `id,eventType,fromStatus,toStatus,orderVersion,operatorId,fromWorkerId,toWorkerId,remark,createTime`；系统事件 operatorId 为 null。日志列表仍按工单权限读取，不单独对外公开。

维修工候选为 `{id,realName,skill,activeOrderCount,recommendationScore}`；排序为推荐分降序、当前工单数升序、ID 升序。评分公式见实施细则。

评价汇总响应为 `{workerId,averageScore,evaluationCount,items,total,page,pageSize}`；不传 workerId 时平均分基于全部符合条件的评价逐条计算。`items` 为评价及其 `orderId,workerId`，无评价平均分为 null。

工单统计 `metric` 为 `created`（默认）或 `completed`，分别过滤 create_time 或 close_time；`completed` 限 CLOSED。`groupBy` 为 `category,status,worker,day`，默认 category。`buckets` 为 `[{key,count}]`，worker 分组可附 `workerName`，未指派的 key 为 null。工单总量不与日志表联表累计，避免一单多日志导致重复计数。

超时列表 `scope=active` 为默认，仅返回仍在 CREATED/ASSIGNED/PROCESSING 且当前已逾期的工单；`scope=history` 返回曾超时工单，包括已结束的工单，须使用实施细则中的有效历史判定，不能只依赖尚未刷新的缓存标记。

## 上传与站内提示

上传文件保存在本机受控目录 `uploads/<studentId>/<uuid>.png或.jpg`，路径由服务端生成。返回相对 API URL `/api/uploads/images/<studentId>/<filename>`；创建工单时核验路径归属和文件存在。访问图片的 GET 路由同样校验 token：上传者、管理员、与该图片关联工单的当前维修工可访问。浏览器使用带鉴权头的 fetch 获取 Blob 后展示，不能依赖普通 img 标签自动携带 Bearer token。

站内提示以现有列表接口轮询和数量徽标实现，建议前台可见时每 30 秒查询一次，页面离开停止轮询。提示包括新派工单、待确认工单、管理员待派与超时数量。此四表方案不提供独立消息收件箱、已读状态或消息送达记录；若要求这些能力，需明确扩展需求与表设计。
