# 部署指导书

在华为云上落地并运行 RDS for MySQL 升级助手。所有命令中的路径均使用相对路径（如 `cd infra`），不含任何上游平台标识。

## 前置条件

- Python ≥ 3.10
- 已安装 `mysql` 客户端（用于本地预检 / 验证 SQL）
- 华为云账号，目标区域具备 RDS for MySQL、DRS 权限（默认 `cn-north-4`）
- 已配置环境变量（**真实值从环境变量注入，禁止写入文件**，质量门禁 C8）：

```bash
export HW_ACCESS_KEY=<HW_ACCESS_KEY>
export HW_SECRET_KEY=<HW_SECRET_KEY>
export HW_PROJECT_ID=<HW_PROJECT_ID>
export HW_REGION=cn-north-4
```

- 安装 Python 依赖：

```bash
python -m pip install -e .
```

## 配置 MCP 客户端

在 MCP 客户端配置中注册本 server（stdio 传输），示例 `mcp.json`：

```json
{
  "mcpServers": {
    "rds-mysql-upgrade": {
      "command": "python",
      "args": ["-m", "rds_upgrade_mcp.server"]
    }
  }
}
```

## 快速开始

```bash
# 1) 发现待升级实例
python -m rds_upgrade_mcp.server   # 在客户端中调用 discover_instances(region="cn-north-4")

# 2) 预检（对源实例执行 MySQL 兼容性检查）
# run_precheck(host="<源实例内网IP>", user="root", password="<DB_PASSWORD>")

# 3) 建绿 + 启动 DRS 同步
# create_blue_green(instance_id="<源实例ID>", target_version="8.4", green_password="<DB_PASSWORD>")

# 4) 监测同步就绪
# monitor_blue_green(deployment_id="<DRS任务ID>")

# 5) 切换连接入口到 green
# switchover(deployment_id="<DRS任务ID>", update_dns=true)

# 6) 验证
# validate_upgrade(instance_id="<green实例ID>", expected_version="8.4")

# 7) 清理
# cleanup_blue_green(deployment_id="<DRS任务ID>", delete_source=false)
```

## 部署示例基础设施（可选）

如需可复现的测试目标环境，用 Terraform 在 `infra/` 下创建：

```bash
cd infra
python -m pip install huaweicloud
terraform init
terraform plan
terraform apply -var="db_password=<DB_PASSWORD>"
```

## 清理资源

```bash
cd infra
terraform destroy -var="db_password=<DB_PASSWORD>"
```

示例环境删除后无运行态资源残留；生产场景请在升级助手清理步骤中确认 DRS 任务与 green 实例已释放。
