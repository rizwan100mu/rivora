# Rivora server 2.0.8: mobile assignment notifications

Prepared locally. Not installed on your server. Keep mobile Rivora 3.0.10; no new APK is needed.

## Behavior

- A new or reassigned open ToDo notifies only its current Allocated To user, for every linked DocType.
- The mobile alert is saved in Rivora Mobile Notification, then delivered to that user's registered Rivora phones. Current allocation and read permission are checked again before delivery.
- An unallocated ToDo never falls back to notifying its creator.
- Standard Frappe Notification Log records are preserved. Rivora does not forward a second copy of standard Assignment logs to phone push; the dedicated ToDo hook provides the mobile alert.
- Enable/disable phone delivery in Rivora mobile Settings > Phone push alerts. This is per phone; in-app history remains available. No new server-side enable/disable setting is added.
- No ERPNext or Frappe core files, standard notification preferences, or existing notification rules are changed. Previously deleted standard logs are not reconstructed.
- Optional New Entry Notifications are separate from assignment alerts; they are not required for this flow.

## Update an installed Rivora 2.0.7

Use the patch only against the unmodified 2.0.7 release. Run as the bench owner. Replace your-site-name and /path/to with real values. Do not uninstall Rivora or replace site_config.json.

```bash
cd ~/frappe-bench
bench version
bench --site your-site-name backup --with-files
cd apps/rivora
git status --short
git apply --check /path/to/Rivora-2.0.7-to-2.0.8.patch
```

Stop if local customizations exist or the check fails; do not force the patch. The check is read-only. Once clean and checked:

```bash
git diff > /path/to/rivora-before-2.0.8.diff
git apply /path/to/Rivora-2.0.7-to-2.0.8.patch
cd ~/frappe-bench
bench --site your-site-name migrate
bench --site your-site-name clear-cache
bench restart
bench version
```

Migration and restart reload Rivora code and worker hooks; no ERPNext/Frappe core upgrade is requested. Use your deployment's normal process-manager restart if bench restart is unavailable.

## Earlier or customized Rivora versions

Rivora-Server-2.0.8-full.zip contains the full merged Rivora app source. Compare with the installed app and preserve customizations before upgrading. It includes the dedicated mobile notification DocType and hooks needed on earlier merged 2.0.x releases; copying api.py alone is insufficient. Extract to a separate directory for review, back up the site and current apps/rivora source, deploy the reviewed Rivora app contents only, then migrate, clear cache and restart. Do not apply this merged package to legacy employee_self_service/rizora_workforce installations without reviewing their app ownership/migration requirements.

## Acceptance

1. Sign into Rivora as user A and enable Phone push alerts. Confirm Test server push reaches the phone.
2. User B assigns a document (any DocType) to A. Verify the resulting ToDo is Open and Allocated To A.
3. Only A receives the assignment push. B and another manager must not receive it merely because they created or can read the document.
4. Repeat with Rivora in the background. The short queue worker must be running.
5. Turn Phone push alerts off on A's phone. A new assignment must not display a push on that phone. Other enabled phones belonging to A retain their own setting.
6. Turn it on again and repeat a new assignment. Reassign to user C and verify a stale pending job cannot notify A.
7. Standard ERPNext/Frappe notification logs retain their normal behavior. Phone opt-out does not disable Desk notifications or erase in-app history.

200 mocked server tests passed and mobile push registration/opt-out tests passed. Live-server and real-phone assignment acceptance remain pending. Firebase acceptance alone does not prove Android displayed a popup.
