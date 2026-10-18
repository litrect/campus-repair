# 本项目 MySQL 运行说明

安装与验证日期：2026-10-15。

MySQL Community Server 8.0.46，从官方 https://cdn.mysql.com/Downloads/MySQL-8.0/mysql-8.0.46-winx64.zip 下载 ZIP 包，解压到houduan/tools/mysql-8.0.46-winx64。数据保存在houduan/instance/mysql-data，错误日志在houduan/instance/mysql-error.log。

服务仅监听 127.0.0.1:3306，关闭 MySQL X Plugin，时区 +08:00，启用严格 SQL 模式。采用后台进程，未注册 Windows 自动启动服务，重启电脑后手动启动。

项目目录已由“后端”调整为 houduan，MySQL 直接使用实际绝对路径启动，不再使用 subst 或 R: 映射。所有现有数据库、账号及密码已保留。启动脚本根据自身位置计算程序、数据和日志路径，并同步更新本机配置。

## 启动、状态和停止

在“houduan”目录执行（步骤 3 建立项目 Python 环境后可使用其 Python）：

```powershell
$projectPython = 'C:\Users\31090\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $projectPython .\scripts\local_mysql.py status
& $projectPython .\scripts\local_mysql.py start
& $projectPython .\scripts\local_mysql.py stop
& $projectPython .\scripts\verify_local_database.py
```

不要重复运行 setup_local_mysql.py，数据库已建立，该脚本也会拒绝覆盖已有数据。

## 连接配置

应用数据库：campus_repair；应用账号：campus_app；连接地址：127.0.0.1；端口：3306。应用账号仅拥有本库 SELECT、INSERT、UPDATE 权限；管理初始化使用 root。

root 与应用密码均随机生成，保存在 instance/mysql-local.json，仅用于本机配置，不在聊天或文档中展示。instance/、tools/ 已加入 .gitignore。应用在步骤 3 读取本机配置，不能将真实凭据提交到版本库。

四个演示业务账号为 admin、worker1、worker2、stu1，演示密码均为 Demo@123456。业务账号与 MySQL 连接账号不同。

## 本次数据库验证

campus_repair 内四张表和四个演示用户已实际创建。验证在独立 a2_verify_20261015 库执行，17/17 通过，结果保存在 database-verification-results.json。覆盖外键、状态约束、密码哈希、幂等唯一键、评分范围、评价唯一性、完整流程、回滚、并发、旧版本拒绝、改派记录和超时完成。

测试库保留供核对，其测试工单不混入演示库；演示库此时无工单。迁移后使用 verify_local_database.py 创建新的时间戳命名验证库并重新验证，最新库名及结果以 database-verification-results.json 为准。此结果仅代表数据库及 SQL 事务模式，应用接口验收在后续步骤完成。
