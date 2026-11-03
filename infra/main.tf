# ----------------------------------------------------------------------------
# Example infrastructure for the RDS for MySQL upgrade assistant.
#
# This template provisions a demonstration target environment (a single HA
# RDS for MySQL 8.4 instance). In real use the assistant operates on
# PRE-EXISTING instances; this file exists only to give a reproducible,
# syntax-correct Terraform baseline for testing the upgrade flow.
#
# Credentials are NEVER hardcoded (gate C8): the huaweicloud provider reads
# HW_ACCESS_KEY / HW_SECRET_KEY / HW_PROJECT_ID from the environment, and the
# instance password comes from a variable supplied at apply time.
# Billable specs are written explicitly (gate C9): no data.xxx.ids[N] lookups.
# ----------------------------------------------------------------------------

terraform {
  required_providers {
    huaweicloud = {
      source  = "huaweicloud/huaweicloud"
      version = ">= 1.40.0"
    }
  }
}

provider "huaweicloud" {
  region = var.region
}

variable "region" {
  type    = string
  default = "cn-north-4"
}

variable "db_password" {
  type      = string
  sensitive = true
  # Supplied at apply time, e.g. -var="db_password=<DB_PASSWORD>"
  # Never commit a real value.
}

resource "huaweicloud_vpc" "demo" {
  name = "bgd-demo-vpc"
  cidr = "192.168.0.0/16"
}

resource "huaweicloud_vpc_subnet" "demo" {
  name       = "bgd-demo-subnet"
  cidr       = "192.168.0.0/24"
  gateway_ip = "192.168.0.1"
  vpc_id     = huaweicloud_vpc.demo.id
}

resource "huaweicloud_networking_secgroup" "demo" {
  name = "bgd-demo-sg"
}

resource "huaweicloud_rds_instance" "mysql" {
  name                = "bgd-demo-mysql"
  engine              = "mysql"
  engine_version      = "8.4"
  flavor              = "rds.mysql.s3.large.2.ha" # explicit billable spec (gate C9)
  vpc_id              = huaweicloud_vpc.demo.id
  subnet_id           = huaweicloud_vpc_subnet.demo.id
  security_group_id   = huaweicloud_networking_secgroup.demo.id
  storage_type        = "CLOUDSSD"
  storage_size        = 100 # explicit, GB
  password            = var.db_password
  ha_replication_mode = "semisync"

  # password is mutable at runtime (console / API); let the runtime own it so
  # a later apply does not silently reset it (gate C10).
  lifecycle {
    ignore_changes = [password]
  }
}

output "mysql_endpoint" {
  value = huaweicloud_rds_instance.mysql.private_ips
}
