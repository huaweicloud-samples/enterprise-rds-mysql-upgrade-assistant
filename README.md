# enterprise-rds-mysql-upgrade-assistant

[![Status](https://img.shields.io/badge/Status-Incubating-blue)]()
[![Huawei Cloud](https://img.shields.io/badge/Huawei%20Cloud-Samples-red)]()
[![Scenario](https://img.shields.io/badge/Scenario-enterprise-success)](https://3ms.huawei.com/docs/docinfo/1300901382590492672?bookstackId=866760814559879168&gid=3591759&l=zh-cn&documentkind=&attachmentIdx=5)

This solution is a major version (8.0 → 8.4) upgrade assistant for Huawei Cloud RDS for MySQL. It exposes upgrade tools as an MCP Server that clients such as Claude Desktop / Cursor can call, covering the complete flow of "discover instances → compatibility precheck → create a target-version instance and sync in real time → switch the connection entry → validate → clean up". It suits operations and architecture scenarios that require low-downtime major version upgrades for a batch of MySQL instances.

## Overview

This repository is created from the huaweicloud-samples automated repository request workflow.

## Getting Started

Add setup, deployment, and verification steps here.

## Contributing

Please use pull requests and follow the repository review rules.

## License

This project is licensed under the MIT-0 license.

## Maintainers

CODEOWNERS: @Ferguson2211

## Feedback

Please use GitHub Issues: https://github.com/huaweicloud-samples/enterprise-rds-mysql-upgrade-assistant/issues
