"""User Type rows select the permitted mobile Home workspaces."""
import json
from pathlib import Path
import frappe

def allowed_doctypes(row):
    raw = row.get('allowed_doctypes')
    if raw is None:
        return [str(row.get('document_type') or 'ToDo').strip()]
    return list(dict.fromkeys(name.strip() for name in str(raw).splitlines() if name.strip()))


def validate_home_rules(settings):
    for row in settings.get('home_rules') or []:
        for name in allowed_doctypes(row):
            if not frappe.db.exists('DocType', name):
                frappe.throw('Select a valid DocType for the mobile Home.')
            meta = frappe.get_meta(name)
            if meta.istable or meta.issingle:
                frappe.throw('Select regular document types for mobile Home workspaces.')

def home_doctypes(user_type, settings):
    current = str(user_type or "").strip().casefold()
    rows = [row for row in settings.get("home_rules") or []
            if current and str(row.get("user_type") or "").strip().casefold() == current]
    if not rows:
        return None
    # Rows created before the DocType column use ToDo until an admin edits them.
    names = list(dict.fromkeys(name for row in rows for name in allowed_doctypes(row)))
    return [name for name in names
            if frappe.db.exists("DocType", name) and frappe.has_permission(name, "read")]


def profile_policy(user_type):
    return {"home_doctypes": home_doctypes(user_type, frappe.get_single("Rivora Mobile Settings")),
            "settings_source": "Rivora Mobile Settings"}


def initialize_home_user_types(legacy_mode=None):
    """Install/one-time migration only; an empty saved list stays empty afterward."""
    settings = frappe.get_single("Rivora Mobile Settings")
    rows = settings.get("home_rules") or []
    old_mode = legacy_mode or settings.get("dashboard_configuration")
    if old_mode == "Repository defaults" or (not old_mode and not rows):
        data = json.loads((Path(__file__).parent / "config/mobile_defaults.json").read_text(encoding="utf-8"))
        names = data["restricted_home_user_types"]
    else:
        # Preserve an administrator's multi-selection, including intentional empties.
        merged = {}
        for row in rows:
            name = str(row.get('user_type') or '').strip()
            if name and frappe.db.exists('User Type', name):
                key = name.casefold()
                merged.setdefault(key, {'user_type': name, 'doctypes': []})
                merged[key]['doctypes'].extend(allowed_doctypes(row))
        selected = [{'user_type': row['user_type'], 'allowed_doctypes': '\n'.join(dict.fromkeys(row['doctypes']))} for row in merged.values()]
        settings.set('home_rules', selected)
        settings.save(ignore_permissions=True)
        return
    selected = []
    seen = set()
    for name in names:
        name = str(name or "").strip()
        key = name.casefold()
        if name and key not in seen and frappe.db.exists("User Type", name):
            seen.add(key)
            selected.append({"user_type": name, "allowed_doctypes": "ToDo"})
    settings.set("home_rules", selected)
    settings.save(ignore_permissions=True)
