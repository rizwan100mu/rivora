# Single Rivora app — employee source already merged

This is the merged Rivora server app, version 2.0.3. Install only `rivora`; the employee-service backend is bundled in this repository. See README.md for current GitHub checkout instructions and SERVER_UPDATE_2.0.3.md for an existing Rivora update. Historical package examples below refer to the earlier 2.0.2 delivery.

Verified contents:296/296 files from the original employee-service bundle are accounted for inside the Rivora source;63 app-owned DocTypes already have Rivora names in their JSON/controller files before installation. Original business controllers, helpers, fixtures, hooks and scheduled jobs are bundled. All renamed schema uses the Rivora module. Root pyproject.toml registers only rivora. ERPNext and HRMS remain platform dependencies. Original copyright/license notices are retained.

Examples: Employee Self Service Settings -> Rivora Settings; ESS Post -> Rivora Post; ESS Documents -> Rivora Documents; ESS Notification Log -> Rivora Notification Log. The complete source mapping and file audit are included. Standard ERPNext/HRMS DocTypes are unchanged. The historical upstream source version2.2.5 is provenance only; installed Rivora reports2.0.2.

Your supplied `bench --site all list-apps` output contains neither ESS nor Rivora. Use the fresh single-app install path for erp.local. The installer still checks for any legacy app/schema before writing and backs up first.

## On your Ubuntu bench

Extract `Rivora-2.0.2-Single-App.zip` so its outer rivora directory is `/home/frappe/frappe-bench/apps/rivora`. The pyproject.toml and install_local.py files must sit directly in apps/rivora, alongside the inner rivora Python folder. Keep a copy of your previous source folder before replacing it. No original ESS checkout is needed.

Then run:

```bash
cd ~/frappe-bench
python3 apps/rivora/install_local.py --bench "$PWD" --site erp.local
bench --site erp.local list-apps
```

The site should list rivora2.0.2 after a successful installation. Send the first error if it stops; do not work around installer errors by uninstalling other apps. Python dependencies may need downloads, but no ESS repository is fetched.

The combined source ZIP also includes the Rivora mobile project3.0.1/build39 with its employee source modules. It does not require another mobile repository. This packaging audit does not establish full live workflow acceptance. No remote server was changed here. The existing Rivora mobile APK remains unchanged; Firebase push still needs configuration for com.rivora.workforce.mobile.
