# 校园报修系统

本目录为项目唯一新增文件保存位置。

前端开发交接资料：[前后端交接说明](handoff/frontend/前后端交接说明.md)，以及 [完整交接压缩包](handoff/校园报修系统_前后端交接包_v1.0.zip)。包含实际接口、页面规则、Postman 集合、TypeScript 类型及 fetch 示例。

当前进度：步骤 1～7 已完成；步骤 8 核心浏览器流程已通过，补充页面验收仍待完成。已接入 qianduan/campus-repair-frontend 的构建资源，同源运行说明及实际结果见 [前后端联调记录](docs/09_前后端联调记录.md)。

技术路线：Python 3.12 + Flask + PyMySQL + MySQL 8.0.16+。

完整技术决策、业务默认规则、目标目录、环境现状和后续顺序见 [项目基线](docs/01_项目基线.md)。业务默认值来自 A2 交接稿建议，未声称已获团队评审批准。

先在 ../qianduan/campus-repair-frontend 运行 npm run build，然后在本目录运行 `./scripts/start_backend.ps1` 启动 MySQL、API 和每 60 秒扫描一次的超时任务。访问 http://127.0.0.1:5000 使用系统。开发模式另在前端目录执行 npm run dev，访问5173端口。
