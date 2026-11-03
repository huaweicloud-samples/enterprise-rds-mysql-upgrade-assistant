"""Configuration and credential loading for the Huawei Cloud RDS upgrade assistant.

Credentials are always read from environment variables and never hardcoded
(see quality gate C8: no real AK/SK may appear in any deliverable).
"""

import os

# Default target region for Huawei Cloud RDS for MySQL.
DEFAULT_REGION = os.environ.get("HW_REGION", "cn-north-4")

# Environment variable names expected to be present at runtime.
ENV_ACCESS_KEY = "HW_ACCESS_KEY"
ENV_SECRET_KEY = "HW_SECRET_KEY"
ENV_PROJECT_ID = "HW_PROJECT_ID"


def get_credentials() -> tuple[str, str, str]:
    """Return (ak, sk, project_id).

    Raises RuntimeError if any required variable is missing, so the caller
    fails fast instead of sending malformed requests.
    """
    ak = os.environ.get(ENV_ACCESS_KEY)
    sk = os.environ.get(ENV_SECRET_KEY)
    project_id = os.environ.get(ENV_PROJECT_ID)
    if not (ak and sk and project_id):
        missing = [
            name
            for name, val in (
                (ENV_ACCESS_KEY, ak),
                (ENV_SECRET_KEY, sk),
                (ENV_PROJECT_ID, project_id),
            )
            if not val
        ]
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Provide them via environment (e.g. export HW_ACCESS_KEY=<HW_ACCESS_KEY>)."
        )
    return ak, sk, project_id


def get_region(region: str = "") -> str:
    return region or DEFAULT_REGION
