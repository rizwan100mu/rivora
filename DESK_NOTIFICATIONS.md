# Rivora Server 2.0.9 ? ERPNext Desk notifications

Use ERPNext **Notification** rules with channel **System** for any standard or custom DocType. ERPNext controls events, conditions, recipients and saved Desk Notification Log entries; Rivora forwards these saved alerts to registered phones. Standard assignment logs are forwarded too. Phone push preferences, Firebase configuration and existing recipient/document scope checks remain in force.

Removed active duplicate paths: Rivora Notification document-event engine, mobile new-entry engine, mobile-only ToDo engine and duplicate comment hook. Old queued jobs for those engines safely do nothing. Remaining employee event producers save standard Notification Log entries. The historical Rivora Notification Log no longer calls the vendor relay.

## Existing-site upgrade

1. Back up the site database/files and installed Rivora source.
2. Review enabled **Rivora Notification** rules and the old Mobile Settings new-entry selections. Recreate required behavior in ERPNext **Notification**, channel **System**, with the appropriate DocType, event, condition and recipients. Review scheduled employee reminders too. Existing custom rules are not automatically converted: employee-field recipient rules require mapping to the corresponding User field or site logic.
3. Test the replacement rules on staging before deploying this source. This release stops executing old custom rules; installing without replacements can stop alerts that only those rules generated.
4. Replace the existing `apps/rivora` source with the `rivora/` folder from the ZIP. Keep site configuration and Firebase credentials. Do not install a second app or uninstall Rivora.
5. From the bench directory run `bench --site YOUR_SITE migrate`, `bench build --app rivora`, `bench --site YOUR_SITE clear-cache`, then `bench restart` for your deployment.
6. Create an assigned ToDo and trigger a System Notification on a business/custom DocType. Check the intended recipient's Desk bell first, then phone delivery; confirm no duplicate mobile-only alert. Check disabled recipients and phone push off.

Old DocTypes and saved records are retained for compatibility/history; old notification settings are hidden. Do not delete tables or DocTypes blindly. Mobile history still includes historical Rivora logs. No APK update is required.

Validation: 177 backend unit tests passed (mocked Frappe). Live ERPNext migration, actual Desk events and physical-phone delivery still require staging acceptance. This package has not been deployed to your server.
