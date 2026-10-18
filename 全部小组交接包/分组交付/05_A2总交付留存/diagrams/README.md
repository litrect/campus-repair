# A2 七张设计图

SVG 可直接插入报告，放大不会模糊；Mermaid 文件用于修改源图。system-design.md 中的图代码是统一来源，变更后须重新导出对应 SVG。

| 图 | SVG 导出 | Mermaid 源文件 |
| --- | --- | --- |
| 数据库 E-R 图 | [查看](01-er.svg) | [编辑](01-er.mmd) |
| 工单状态机图 | [查看](02-state.svg) | [编辑](02-state.mmd) |
| 类图 | [查看](03-class.svg) | [编辑](03-class.mmd) |
| 提交报修时序图 | [查看](04-create.svg) | [编辑](04-create.mmd) |
| 派单与改派时序图 | [查看](05-assign.svg) | [编辑](05-assign.mmd) |
| 接单与维修完成时序图 | [查看](06-repair.svg) | [编辑](06-repair.mmd) |
| 确认驳回与评价时序图 | [查看](07-confirm.svg) | [编辑](07-confirm.mmd) |

渲染器为 Mermaid 11.4.1，neutral 主题，Microsoft YaHei 字体，时序图 mirrorActors=false。渲染在本机执行，SVG 查看不依赖外网。图中方法名为概念表达，实际 Python 函数与事务入口定义以 implementation-notes.md 为准。
