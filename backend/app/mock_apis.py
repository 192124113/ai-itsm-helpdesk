"""Mock enterprise systems used by the self-heal and provisioning agents.

In production these functions would call Active Directory / Entra ID, an endpoint-management
tool (Intune, SCCM) and a software-deployment system. Each returns a result dict and never
raises, so the agent can always validate and audit the outcome.
"""
import uuid

from .db import get_db, now_iso


def get_user(user_id: str):
    return get_db().users.find_one({"user_id": user_id}, {"_id": 0})


def diagnose(key: str, user: dict):
    """Return (action_needed, human-readable finding)."""
    name = user["name"]
    if key == "password_reset":
        if user.get("password_expired"):
            return True, f"Directory shows {name}'s password is EXPIRED."
        return True, f"{name}'s password is not flagged as expired; proceeding with the requested reset."
    if key == "account_unlock":
        if user.get("locked"):
            return True, f"Directory shows {name}'s account is LOCKED after repeated failed sign-ins."
        return False, f"{name}'s account is not locked, so no unlock is needed."
    if key == "clear_cache":
        return True, "Endpoint agent reports 1.8 GB of application cache on the device."
    if key == "restart_outlook":
        return True, "Endpoint agent reports the Outlook process is not responding."
    if key == "vpn_status_check":
        return True, "Querying VPN gateway health for the user's region."
    return False, "No diagnostic available."


def execute(key: str, user_id: str) -> dict:
    users = get_db().users
    if key == "password_reset":
        users.update_one({"user_id": user_id}, {"$set": {"password_expired": False, "password_last_set": now_iso()}})
        return {"success": True, "api_call": f"POST /mock/directory/users/{user_id}/password-reset",
                "message": "Password reset. A temporary password was sent to the registered mobile number."}
    if key == "account_unlock":
        users.update_one({"user_id": user_id}, {"$set": {"locked": False}})
        return {"success": True, "api_call": f"POST /mock/directory/users/{user_id}/unlock",
                "message": "Account unlocked."}
    if key == "clear_cache":
        return {"success": True, "api_call": f"POST /mock/endpoint/{user_id}/clear-cache",
                "message": "Application cache cleared (1.8 GB freed)."}
    if key == "restart_outlook":
        return {"success": True, "api_call": f"POST /mock/endpoint/{user_id}/restart-app?name=outlook",
                "message": "Outlook restarted remotely."}
    if key == "vpn_status_check":
        return {"success": True, "api_call": "GET /mock/vpn/gateway/status",
                "message": "VPN gateway is ONLINE (primary and backup)."}
    return {"success": False, "api_call": "n/a", "message": f"Unknown automation '{key}'."}


def validate(key: str, user_id: str):
    """Independently re-check the system state. Returns (ok, message)."""
    user = get_user(user_id) or {}
    if key == "password_reset":
        ok = not user.get("password_expired", True)
        return ok, "Directory confirms the password is no longer expired." if ok else "Password still expired."
    if key == "account_unlock":
        ok = not user.get("locked", True)
        return ok, "Directory confirms the account is unlocked." if ok else "Account is still locked."
    if key == "clear_cache":
        return True, "Endpoint agent confirms cache size is now 0 MB."
    if key == "restart_outlook":
        return True, "Endpoint agent confirms Outlook is running and responding."
    if key == "vpn_status_check":
        return True, "Gateway health check returned HTTP 200."
    return False, "Nothing to validate."


def start_provisioning(software: dict, user: dict) -> dict:
    """Pretend to push an install job to the deployment system."""
    return {
        "job_id": "PRV-" + uuid.uuid4().hex[:8].upper(),
        "state": "Provisioning",
        "api_call": "POST /mock/provisioning/jobs",
        "target": f"{user['user_id']}-laptop",
        "package": f"{software['name']} {software['version']}",
    }
