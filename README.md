# Rivora

Rivora 2.0.7 is one Frappe application containing employee self-service workflows and native mobile integration for ERPNext and HRMS. ESS controllers, APIs, hooks, scheduled jobs, settings, fixtures and schemas are bundled under the Rivora namespace. No separate ESS repository is required. The Android app is distributed separately.

## Installation

Run as the bench owner. ERPNext and HRMS must be installed on the target site. Replace `your-site-name` with the site folder name. Use a staging clone before production deployment.

```bash
cd ~/frappe-bench
bench --site your-site-name backup --with-files
bench get-app https://github.com/rizwan100mu/rivora --branch main
bench --site your-site-name install-app rivora
bench --site your-site-name migrate
bench build --app rivora
bench --site your-site-name clear-cache
bench restart
bench --site your-site-name list-apps
```

Run commands one at a time and stop at the first error. Existing separate ESS/Rizora apps require a reviewed ownership and data migration. Do not uninstall them or delete their records to bypass installation safeguards.

The repository root is the Bench app root: `pyproject.toml`, `install_local.py` and the inner `rivora/` package belong directly in `apps/rivora`.

## Mobile access

Open **Rivora Mobile Settings → Mobile Home Dashboard → User Type Workspace Access**. Each User Type row has an **Allowed DocTypes** selection. Click **Select DocTypes**, choose multiple DocTypes, apply and save. Matching users see those readable DocTypes as workspace cards on Home. Select only ToDo to hide Leave Request; select additional DocTypes to show their workspaces. Existing rows start with ToDo. An explicit empty selection shows no workspaces; users with no matching row retain the full dashboard. This visibility setting does not grant document permissions.

## Firebase setup

Sign in as Administrator or System Manager and open **Rivora Mobile Settings** at `/app/rivora-mobile-settings`.

1. Save any pending settings.
2. Click **Upload Firebase JSON**.
3. Select the Firebase Admin service-account JSON for project **rizora-5a6e6**.
4. Run **Server push test** in the mobile app.

The key is encrypted in the site database, never saved as a public attachment or committed to Git. The page displays the configured project. Uploaded credentials take precedence over the optional `rivora_firebase_credentials` site-config path. The phone's `google-services.json` is a different file. Keep the site encryption key with protected database backups.

## ToDo notifications

New and reassigned open ToDos notify their current assignee by default, without enabling ERPNext personal notifications or adding ToDo to a new-entry list. The app-only alert is stored in Rivora Mobile Notification and queued after commit to registered phones for the current `allocated_to` account. The phone popup shows the ToDo description and, when present, its linked DocType and document ID; it does not show the ToDo ID. It does not create an ERPNext Notification Log or depend on ERPNext notification preferences. The current mobile app stores phone tokens in **Rivora Mobile Device**; **Rivora Employee Device Info** is a legacy token store. Read permission, an enabled account, running background workers, a registered phone and valid Firebase authorization are required.

Users can disable delivery to their phone through **Phone push alerts** in Rivora mobile Settings. Android notification permission is required. Mobile 3.0.9 requests notification permission when no preference has been saved; saved opt-outs remain off. Other document entry alerts use the selected DocTypes and recipients in Rivora Mobile Settings.

The native mobile client supports the supplied ToDo field rules and browser decoration compatibility. QR leave decisions use the ERPNext browser workflow.

## Existing installations

Back up before applying repository updates. For an installed app, preserve any local customizations, then align the app checkout to this fresh `main` history and migrate:

```bash
cd ~/frappe-bench/apps/rivora
git status --short
git fetch upstream main
git checkout -B main upstream/main
cd ~/frappe-bench
bench setup requirements
bench --site your-site-name migrate
bench build --app rivora
bench --site your-site-name clear-cache
bench restart
```

Run each command individually and stop if `git status --short` shows local changes; back them up first. Do not repeat `get-app` for an already installed app.

## Verification and licensing

Local checks use mocked server and mobile environments. Actual Firebase delivery, phone behavior, site permissions, scripts and workflows require acceptance on the target site. Original notices and licenses are retained in `THIRD_PARTY_NOTICES.md` and `LICENSES/`.
