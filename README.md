# 校园报修系统

包含学生报修、管理员派单、维修人员接单与维修、确认与评价等功能。

- `houduan/`：Flask、MySQL 后端、数据库脚本、测试及开发文档。
- `qianduan/campus-repair-frontend/`：Vue 3、TypeScript 前端和 package-lock.json。
- `全部小组交接包/`：原始需求、接口约定及分组交付资料。
- `本地打开校园报修系统.cmd`：本地环境准备完成后的启动入口。
- `一键启动校园报修系统.cmd`：使用已配置的 cpolar 隧道启动。

## 在新电脑上准备环境

首次安装请按 [新电脑环境准备指南](新电脑环境准备指南.md) 操作，包含软件安装、数据库初始化、前端构建及一键启动。

仓库不包含本机数据库、密码、密钥、Python 虚拟环境、MySQL 安装包或 node_modules。
克隆仓库后，需要根据 `houduan/README.md` 配置 Python、MySQL、数据库及虚拟环境，
再按 `qianduan/campus-repair-frontend/README.md` 安装前端依赖并执行 `npm run build`。
本地入口为 http://127.0.0.1:5000 。cpolar 需要单独安装并配置自己的账号及隧道。

预置演示账号仅用于开发联调；对外使用前请更换演示密码。

接口自动测试、前端构建与已执行的浏览器联调结果详见 `houduan/docs/09_前后端联调记录.md`；
部分页面及性能验收仍待完成。
