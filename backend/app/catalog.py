"""Static catalogues: software catalogue and the whitelist of safe automations."""
import re

SOFTWARE_CATALOGUE = [
    {"id": "SW001", "name": "Visual Studio Code", "version": "1.95", "category": "Development",
     "aliases": ["visual studio code", "vs code", "vscode"]},
    {"id": "SW002", "name": "Google Chrome", "version": "130", "category": "Browsers",
     "aliases": ["google chrome", "chrome"]},
    {"id": "SW003", "name": "Slack", "version": "4.40", "category": "Collaboration",
     "aliases": ["slack"]},
    {"id": "SW004", "name": "Zoom", "version": "6.2", "category": "Collaboration",
     "aliases": ["zoom"]},
    {"id": "SW005", "name": "Microsoft Teams", "version": "24", "category": "Collaboration",
     "aliases": ["microsoft teams", "ms teams", "teams"]},
    {"id": "SW006", "name": "Python 3.12", "version": "3.12", "category": "Development",
     "aliases": ["python"]},
    {"id": "SW007", "name": "Git", "version": "2.47", "category": "Development",
     "aliases": ["git"]},
    {"id": "SW008", "name": "Postman", "version": "11", "category": "Development",
     "aliases": ["postman"]},
    {"id": "SW009", "name": "Docker Desktop", "version": "4.35", "category": "Development",
     "aliases": ["docker desktop", "docker"]},
    {"id": "SW010", "name": "7-Zip", "version": "24.08", "category": "Utilities",
     "aliases": ["7-zip", "7zip"]},
]


def find_software(text: str):
    """Return the catalogue entry mentioned in `text`, or None. Longest alias wins."""
    t = text.lower()
    best, best_len = None, 0
    for item in SOFTWARE_CATALOGUE:
        for alias in item["aliases"]:
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", t) and len(alias) > best_len:
                best, best_len = item, len(alias)
    return best


# Only these actions may ever run without a human. Each maps to a mock API.
AUTOMATIONS = {
    "password_reset": {
        "label": "Password reset",
        "patterns": [
            r"password.*(expire|reset|forgot|change)",
            r"(expire|forgot|forget|reset).*password",
        ],
        "category": "Access", "subcategory": "Password / Account",
        "assignment_group": "Identity & Access",
        "kb_query": "password reset expired password",
        "safe": True,
    },
    "account_unlock": {
        "label": "Account unlock",
        "patterns": [r"account.*lock", r"locked out", r"\bunlock\b", r"lock.*account"],
        "category": "Access", "subcategory": "Password / Account",
        "assignment_group": "Identity & Access",
        "kb_query": "account locked unlock",
        "safe": True,
    },
    "clear_cache": {
        "label": "Clear application cache",
        "patterns": [r"clear.*cache", r"cache.*(clear|full|corrupt)"],
        "category": "Software", "subcategory": "Application",
        "assignment_group": "Service Desk",
        "kb_query": "clear cache application performance",
        "safe": True,
    },
    "restart_outlook": {
        "label": "Restart Outlook",
        "patterns": [r"outlook.*(frozen|hang|hung|not responding|stuck)", r"restart outlook"],
        "category": "Email", "subcategory": "Outlook",
        "assignment_group": "Messaging Support",
        "kb_query": "outlook not responding restart",
        "safe": True,
    },
    "vpn_status_check": {
        "label": "VPN status check",
        "patterns": [r"vpn status", r"is (the )?vpn (down|up|working)"],
        "category": "Network", "subcategory": "VPN",
        "assignment_group": "Network Support",
        "kb_query": "vpn troubleshooting status",
        "safe": True,
    },
}


def detect_automation(text: str):
    t = text.lower()
    for key, meta in AUTOMATIONS.items():
        if any(re.search(p, t) for p in meta["patterns"]):
            return key
    return None
