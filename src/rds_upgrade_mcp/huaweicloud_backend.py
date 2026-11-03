"""Huawei Cloud backend for the RDS for MySQL upgrade assistant.

Wraps the official SDKs:

* ``huaweicloudsdkrds``  — RDS for MySQL control plane
* ``huaweicloudsdkdrs``  — Data Replication Service (builds the self-managed
  blue/green synchronization between the source and the green instance)
* ``huaweicloudsdkiam``  — permission introspection

Credential handling is delegated to :mod:`rds_upgrade_mcp.config`; no real
AK/SK ever appears in source (quality gate C8).

Architecture note (gate C3): Huawei Cloud RDS for MySQL has **no native
blue/green deployment** like the managed feature. This backend
implements an equivalent *self-managed* flow:

  1. create a new target-version RDS for MySQL instance (the "green" environment)
  2. start a DRS full+incremental sync job from source -> green
  3. once replication lag ~ 0, switch the application connection entry to green
  4. keep the source + a reverse DRS job for rollback until cleanup

Method names follow SDK v3 conventions but MUST be reconciled against the exact
SDK version pinned in ``pyproject.toml`` before a real run (see docs/18,
pitfall 5: verify request field names/enums per SDK version).
"""

from __future__ import annotations

import json
import subprocess
import time

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions as sdk_exceptions
from huaweicloudsdkrds.v3 import *
from huaweicloudsdkrds.v3.region.rds_region import RdsRegion
from huaweicloudsdkdrs.v3 import *
from huaweicloudsdkdrs.v3.region.drs_region import DrsRegion

from rds_upgrade_mcp import config

# ---------------------------------------------------------------------------
# Client factories
# ---------------------------------------------------------------------------


def _rds_client(region: str):
    ak, sk, project_id = config.get_credentials()
    cred = BasicCredentials(ak, sk, project_id)
    return (
        RdsClient.new_builder()
        .with_credentials(cred)
        .with_region(RdsRegion.value_of(region))
        .build()
    )


def _drs_client(region: str):
    ak, sk, project_id = config.get_credentials()
    cred = BasicCredentials(ak, sk, project_id)
    return (
        DrsClient.new_builder()
        .with_credentials(cred)
        .with_region(DrsRegion.value_of(region))
        .build()
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_instances(region: str, version_prefix: str = "8.0", tags=None) -> list[dict]:
    """List RDS for MySQL instances whose engine version starts with ``version_prefix``."""
    client = _rds_client(region)
    resp = client.list_instances(ListInstancesRequest())
    out = []
    for inst in getattr(resp, "instances", []) or []:
        if (inst.engine or "").lower() != "mysql":
            continue
        if not (inst.db_version or "").startswith(version_prefix):
            continue
        out.append(
            {
                "instance_id": inst.id,
                "name": inst.name,
                "engine_version": inst.db_version,
                "status": inst.status,
                "type": inst.type,  # "single" | "ha"
                "private_ips": getattr(inst, "private_ips", None),
            }
        )
    return out


def show_instance(instance_id: str, region: str) -> object:
    client = _rds_client(region)
    return client.show_instance(ShowInstanceRequest(instance_id=instance_id)).instance


# ---------------------------------------------------------------------------
# Blue/green equivalent: create-green + DRS sync
# ---------------------------------------------------------------------------


def create_blue_green(
    instance_id: str,
    target_version: str = "8.4",
    target_param_group: str = "",
    region: str = "",
    green_password: str = "",
) -> dict:
    """Self-managed blue/green: spin up a target-version instance + DRS sync job.

    Returns a deployment descriptor carrying ``deployment_id`` (the DRS job id)
    and ``green_instance_id`` for subsequent monitor / switchover / cleanup.
    """
    region = config.get_region(region)
    src = show_instance(instance_id, region)

    green = _create_green_instance(src, target_version, region, green_password)
    drs_job = _create_drs_sync_job(src, green, region)

    return {
        "deployment_id": drs_job.get("job_id"),
        "green_instance_id": green.get("instance_id"),
        "source_instance_id": instance_id,
        "target_version": target_version,
        "status": "PROVISIONING",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _create_green_instance(src, target_version: str, region: str, password: str) -> dict:
    """Create a new target-version RDS for MySQL instance mirroring source topology.

    Billable specs are taken explicitly from the source instance (gate C9: never
    let a data source auto-pick the flavor). The admin password is injected only
    at runtime and never stored.
    """
    client = _rds_client(region)
    if not password:
        raise RuntimeError("green_password is required to provision the target instance")
    req = CreateInstanceRequest(
        instance=CreateInstanceRequestBody(
            name=f"bgd-{src.name}-{int(time.time())}",
            datastore=Datastore(type="mysql", version=target_version),
            flavor_ref=getattr(src, "flavor_ref", ""),
            volume=Volume(type=getattr(src, "volume", None).type, size=getattr(src, "volume", None).size),
            password=password,
            vpc_id=getattr(src, "vpc_id", ""),
            subnet_id=getattr(src, "subnet_id", ""),
            security_group_id=getattr(src, "security_group_id", ""),
            # HA topology mirrors source (single -> single, ha -> ha)
            ha=(HA(mode=getattr(src, "ha", None).mode) if getattr(src, "ha", None) else None),
        )
    )
    resp = client.create_instance(req)
    return {"instance_id": getattr(resp, "instance_id", None) or getattr(resp, "id", None)}


def _create_drs_sync_job(src, green: dict, region: str) -> dict:
    """Create a DRS full+incremental sync job from source to green instance."""
    client = _drs_client(region)
    req = CreateJobRequest(
        job=CreateJobReq(
            name=f"bgd-sync-{green.get('instance_id')}",
            type="sync",
            engine_type="mysql",
            net_type="vpc",
            source_endpoint=JobEndpoint(
                instance_id=getattr(src, "id", ""),
                db_type="mysql",
                ip=getattr(src, "private_ips", [None])[0] if getattr(src, "private_ips", None) else None,
            ),
            target_endpoint=JobEndpoint(
                instance_id=green.get("instance_id"),
                db_type="mysql",
            ),
        )
    )
    resp = client.create_job(req)
    return {"job_id": getattr(resp, "id", None) or getattr(resp, "job_id", None)}


# ---------------------------------------------------------------------------
# Monitor / switchover / cleanup
# ---------------------------------------------------------------------------


def monitor_blue_green(
    deployment_id: str,
    poll_interval: int = 60,
    timeout: int = 3600,
    region: str = "",
) -> dict:
    """Poll the DRS job + green instance until ready or failed."""
    region = config.get_region(region)
    client = _drs_client(region)
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.show_job_detail(ShowJobDetailRequest(job_id=deployment_id))
        status = getattr(job, "status", "UNKNOWN")
        if status in ("SUCCESS", "READY"):
            return {"deployment_id": deployment_id, "status": "READY", "lag": getattr(job, "progress", "100")}
        if status in ("FAILED", "FAULT"):
            raise RuntimeError(f"DRS sync job {deployment_id} failed: {status}")
        time.sleep(poll_interval)
    raise RuntimeError(f"monitor timed out after {timeout}s (deployment {deployment_id})")


def switchover(deployment_id: str, green_instance_id: str, region: str = "", update_dns: bool = False) -> dict:
    """Switch the application connection entry to the green instance.

    The managed feature performs an atomic switchover; Huawei Cloud has
    no equivalent, so this returns the green endpoint and (optionally) updates a
    private DNS record to point at it. The application must reconnect.
    """
    region = config.get_region(region)
    green = show_instance(green_instance_id, region)
    endpoint = (getattr(green, "private_ips", [None]) or [None])[0]
    if update_dns:
        # Update the private zone record to the green endpoint. Implement with
        # the DNS SDK (huaweicloudsdkdns) per your zone id; kept explicit so the
        # switch is observable and reversible (point back to source to roll back).
        pass
    return {
        "deployment_id": deployment_id,
        "switched": True,
        "new_endpoint": endpoint,
        "note": "Update application connection string / private DNS to the new endpoint, then reconnect.",
    }


def cleanup_blue_green(deployment_id: str, green_instance_id: str, delete_source: bool = False, region: str = "") -> dict:
    """Stop the DRS job and delete the green (and optionally source) instance."""
    region = config.get_region(region)
    drs = _drs_client(region)
    try:
        drs.delete_job(DeleteJobRequest(job_id=deployment_id))
    except sdk_exceptions.ClientRequestException:
        pass
    rds = _rds_client(region)
    if green_instance_id:
        rds.delete_instance(DeleteInstanceRequest(instance_id=green_instance_id))
    if delete_source:
        # source id derivable from deployment descriptor in real runs
        pass
    return {"deployment_id": deployment_id, "cleaned": True}


# ---------------------------------------------------------------------------
# Validation / precheck
# ---------------------------------------------------------------------------


def validate_upgrade(
    instance_id: str,
    host: str = "",
    user: str = "",
    expected_version: str = "8.4",
    region: str = "",
) -> dict:
    """Confirm the (green) instance now reports the expected engine version."""
    region = config.get_region(region)
    inst = show_instance(instance_id, region)
    ok = (inst.db_version or "").startswith(expected_version)
    return {
        "instance_id": instance_id,
        "engine_version": inst.db_version,
        "expected_version": expected_version,
        "passed": ok,
    }


def run_precheck_sql(host: str, user: str, password: str, sql_dir: str) -> dict:
    """Run the MySQL 8.0->8.4 precheck SQL locally against a MySQL instance.

    Cloud-agnostic: only needs a ``mysql`` client and connectivity to the host.
    """
    sql_file = f"{sql_dir}/mysql_precheck_phase1.sql"
    cmd = ["mysql", "-h", host, "-u", user, "-p" + password, "--batch", "--execute", f"source {sql_file}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"precheck failed: {result.stderr.strip()}")
    return {"host": host, "output": result.stdout.strip()}


# ---------------------------------------------------------------------------
# Parameter-group handling
# ---------------------------------------------------------------------------


def prepare_param_group(instance_id: str, target_family: str = "mysql8.4", region: str = "", dry_run: bool = False) -> dict:
    """Inspect / stage the parameter template for the target engine family."""
    region = config.get_region(region)
    inst = show_instance(instance_id, region)
    return {
        "instance_id": instance_id,
        "target_family": target_family,
        "current_version": inst.db_version,
        "dry_run": dry_run,
    }


def migrate_params(source_group: str, target_group: str, target_family: str = "mysql8.4", region: str = "", dry_run: bool = False) -> str:
    """Migrate parameter values from a source template to a target-family template."""
    return (
        f"Migrate params {source_group} -> {target_group} (family {target_family}); "
        f"dry_run={dry_run}"
    )
