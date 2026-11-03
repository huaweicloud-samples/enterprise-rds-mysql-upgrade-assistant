# 架构说明

本实践在华为云上落地一套 **RDS for MySQL 大版本（8.0 → 8.4）低中断升级助手**，通过 MCP 工具暴露给 Claude Desktop / Cursor 等客户端，编排「发现实例 → 预检 → 建绿环境 → 同步 → 切换 → 验证 → 清理」全流程。

## 组件

| 组件 | 职责 |
|-|-|
| MCP Server（`src/rds_upgrade_mcp/server.py`） | 以 stdio 暴露升级工具，对接 MCP 客户端 |
| 后端（`huaweicloud_backend.py`） | 封装华为云 SDK（RDS / DRS / IAM），实现实例发现、建绿、同步、切换、清理 |
| 预检 SQL（`scripts/precheck`、`scripts/validate`） | 与数据库引擎无关的 MySQL 兼容性检查，本地 `mysql` 客户端执行 |
| RDS for MySQL | 源实例（待升级）与目标实例（green） |
| 数据复制服务 DRS | 在源与目标实例间做全量 + 增量同步，支撑自建蓝绿 |
| 云解析 PrivateZone | 可选：切换时更新私有域名记录指向 green，应用无感重连 |

## 架构图

```mermaid
flowchart TD
    A[MCP 客户端<br/>Claude Desktop / Cursor] -->|stdio| B[MCP Server]
    B --> C[后端 SDK 封装]
    C --> D[RDS for MySQL 源实例 8.0]
    C --> E[RDS for MySQL 目标实例 8.4 green]
    C --> F[数据复制服务 DRS<br/>源→绿 实时同步]
    E -->|连接入口| G[应用]
    F -.同步延迟≈0.--> C
    C -->|切换连接入口| H[云解析 PrivateZone / 连接串]
    H --> G
```

## 升级流程（自建蓝绿）

华为云 RDS for MySQL 不提供托管式蓝绿部署，本实践以「目标实例 + DRS 同步 + 连接入口切换」三段式自建等效流程：

1. **发现**：列出目标区域 `mysql` 引擎、版本前缀 `8.0` 的实例。
2. **预检**：对源实例执行 MySQL 8.0→8.4 兼容性 SQL（字符集、sql_mode、保留字、视图）。
3. **建绿**：基于源实例拓扑（规格/可用区/网络）新建目标版本实例。
4. **同步**：启动 DRS 全量 + 增量任务，持续追平源与目标。
5. **监测**：轮询 DRS 任务状态与 green 实例状态，确认同步延迟趋近于 0。
6. **切换**：将应用连接入口指向 green 端点（更新私有域名解析或连接配置），应用重连。
7. **验证**：连接 green 实例，确认引擎版本与业务表可用。
8. **清理**：停止 DRS 任务、删除 green 实例；确认无误后可删除源实例。

> 回滚：切换前保留源实例与反向 DRS 任务，将连接入口指回源即可回滚。

## 凭据与安全

- 实例密码、AK/SK 一律通过环境变量 / 凭据管理在运行时注入，不写入任何交付文件（质量门禁 C8）。
- 后端最小权限：仅 `rds`、`drs` 相关操作与必要的网络/解析权限。
