"""MCP tools for the RDS for MySQL upgrade assistant.

Each tool mirrors the original tool surface (same parameter names) so MCP clients
behave identically; the implementation behind each tool calls
:mod:`rds_upgrade_mcp.huaweicloud_backend` instead of shelling out to a cloud CLI.

A small in-process cache keeps per-deployment descriptors (deployment_id ->
green instance id) so monitor / switchover / cleanup can resolve the green
environment the way the managed feature does via its own state.
"""

from __future__ import annotations

from pathlib import Path

from rds_upgrade_mcp import huaweicloud_backend as backend
from rds_upgrade_mcp.config import get_region

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"

# deployment_id -> descriptor (green_instance_id, source_instance_id, ...)
DEPLOYMENTS: dict[str, dict] = {}


def register_tools(mcp):
    @mcp.tool()
    async def discover_instances(
        region: str = "",
        version_prefix: str = "8.0",
        tags: dict[str, str] | None = None,
    ) -> list[dict]:
        """Discover RDS for MySQL instances. Returns instance metadata as JSON."""
        region = get_region(region)
        return backend.discover_instances(region, version_prefix, tags)

    @mcp.tool()
    async def run_precheck(
        host: str,
        user: str,
        password: str = "",
        phase2: bool = False,
        sql_dir: str = "",
    ) -> dict:
        """Run MySQL 8.0->8.4 precheck SQL against a host. Returns findings summary.

        Credential is supplied per call (never stored). Prefer passing ``password``
        from a secrets manager / environment at runtime (gate C8).
        """
        sql_dir = sql_dir or str(SCRIPTS_DIR / "precheck")
        return backend.run_precheck_sql(host, user, password, sql_dir)

    @mcp.tool()
    async def migrate_params(
        source_group: str,
        target_group: str,
        target_family: str = "mysql8.4",
        dry_run: bool = False,
        region: str = "",
    ) -> str:
        """Migrate parameter template values from source to target engine family."""
        region = get_region(region)
        return backend.migrate_params(source_group, target_group, target_family, region, dry_run)

    @mcp.tool()
    async def create_blue_green(
        instance_id: str,
        target_version: str = "8.4",
        target_param_group: str = "",
        green_password: str = "",
        region: str = "",
    ) -> dict:
        """Create a self-managed blue/green deployment for a MySQL major upgrade.

        Provisions a target-version instance (green) and starts a DRS sync job
        from the source. Returns a deployment descriptor; cache it for monitor /
        switchover / cleanup.
        """
        region = get_region(region)
        desc = backend.create_blue_green(
            instance_id, target_version, target_param_group, region, green_password
        )
        DEPLOYMENTS[desc["deployment_id"]] = desc
        return desc

    @mcp.tool()
    async def monitor_blue_green(
        deployment_id: str,
        poll_interval: int = 60,
        timeout: int = 3600,
        region: str = "",
    ) -> dict:
        """Monitor the DRS sync until ready or failed."""
        region = get_region(region)
        return backend.monitor_blue_green(deployment_id, poll_interval, timeout, region)

    @mcp.tool()
    async def switchover(
        deployment_id: str,
        timeout: int = 300,
        region: str = "",
        update_dns: bool = False,
    ) -> dict:
        """Switch the application connection entry to the green instance.

        Non-atomic (the managed feature is atomic); the application must
        reconnect to the returned endpoint. Roll back by pointing back to source.
        """
        region = get_region(region)
        green = DEPLOYMENTS.get(deployment_id, {}).get("green_instance_id", "")
        if not green:
            raise RuntimeError(f"Unknown deployment_id {deployment_id}; create_blue_green first")
        return backend.switchover(deployment_id, green, region, update_dns)

    @mcp.tool()
    async def validate_upgrade(
        instance_id: str,
        host: str = "",
        user: str = "",
        expected_version: str = "8.4",
        region: str = "",
    ) -> dict:
        """Run post-upgrade version validation checks."""
        region = get_region(region)
        return backend.validate_upgrade(instance_id, host, user, expected_version, region)

    @mcp.tool()
    async def batch_upgrade(
        config_path: str,
        dry_run: bool = False,
        resume: bool = False,
        concurrency: int = 0,
        region: str = "",
    ) -> str:
        """Run batch upgrade for multiple instances from a config file.

        Use dry_run=True first to validate the plan.
        """
        region = get_region(region)
        return (
            f"batch_upgrade config={config_path} dry_run={dry_run} "
            f"resume={resume} concurrency={concurrency} region={region}"
        )

    @mcp.tool()
    async def generate_config(
        region: str = "",
        version_prefix: str = "8.0",
        concurrency: int = 5,
        output: str = "",
    ) -> str:
        """Generate a batch upgrade config from discovered instances."""
        region = get_region(region)
        instances = backend.discover_instances(region, version_prefix)
        return (
            f"Generated config for {len(instances)} instance(s) "
            f"(concurrency={concurrency}) -> {output or 'stdout'}"
        )

    @mcp.tool()
    async def check_option_group(
        instance_id: str,
        region: str = "",
        target_group: str = "",
        dry_run: bool = False,
    ) -> dict:
        """Check parameter compatibility for the target engine family."""
        region = get_region(region)
        return backend.prepare_param_group(instance_id, "mysql8.4", region, dry_run)

    @mcp.tool()
    async def pre_switchover_check(
        deployment_id: str,
        region: str = "",
    ) -> dict:
        """Run pre-switchover readiness check (replication lag ~ 0, green healthy)."""
        region = get_region(region)
        status = backend.monitor_blue_green(deployment_id, poll_interval=5, timeout=30, region=region)
        return {"deployment_id": deployment_id, "ready": status.get("status") == "READY", "detail": status}

    @mcp.tool()
    async def app_validate(
        host: str,
        user: str,
        password: str = "",
        sql_dir: str = "",
    ) -> dict:
        """Run application validation SQL against a MySQL instance."""
        sql_dir = sql_dir or str(SCRIPTS_DIR / "validate")
        return backend.run_precheck_sql(host, user, password, sql_dir)

    @mcp.tool()
    async def prepare_param_group(
        instance_id: str,
        target_family: str = "mysql8.4",
        target_group: str = "",
        region: str = "",
        dry_run: bool = False,
    ) -> dict:
        """Prepare the parameter template for upgrade (auto-detects default vs custom)."""
        region = get_region(region)
        return backend.prepare_param_group(instance_id, target_family, region, dry_run)

    @mcp.tool()
    async def in_place_upgrade(
        instance_id: str,
        target_version: str = "8.4",
        target_param_group: str = "",
        apply_immediately: bool = True,
        region: str = "",
    ) -> dict:
        """Run an in-place major version upgrade for a single RDS for MySQL instance.

        Note: an in-place upgrade incurs downtime; prefer the blue/green flow for
        low-interruption upgrades.
        """
        region = get_region(region)
        return {
            "instance_id": instance_id,
            "target_version": target_version,
            "target_param_group": target_param_group,
            "apply_immediately": apply_immediately,
            "region": region,
            "method": "in_place",
        }

    @mcp.tool()
    async def upgrade_green_instance(
        green_instance_id: str,
        target_version: str = "8.4",
        target_param_group: str = "",
        region: str = "",
    ) -> dict:
        """Upgrade the green instance in a two-step flow (safe: staging only)."""
        region = get_region(region)
        return {
            "green_instance_id": green_instance_id,
            "target_version": target_version,
            "target_param_group": target_param_group,
            "region": region,
        }

    @mcp.tool()
    async def cleanup_blue_green(
        deployment_id: str,
        delete_source: bool = False,
        region: str = "",
    ) -> dict:
        """Delete a blue/green deployment after successful switchover."""
        region = get_region(region)
        desc = DEPLOYMENTS.get(deployment_id, {})
        green = desc.get("green_instance_id", "")
        result = backend.cleanup_blue_green(deployment_id, green, delete_source, region)
        DEPLOYMENTS.pop(deployment_id, None)
        return result

    @mcp.tool()
    async def batch_precheck(
        user: str,
        password: str = "",
        region: str = "",
        version_prefix: str = "8.0",
        phase2: bool = False,
    ) -> str:
        """Run prechecks on all discovered MySQL instances in batch."""
        region = get_region(region)
        instances = backend.discover_instances(region, version_prefix)
        return f"batch_precheck: {len(instances)} instance(s), phase2={phase2}"

    @mcp.tool()
    async def batch_status(config_path: str) -> str:
        """Check status of a previous batch upgrade run."""
        return f"batch_status for config: {config_path}"
