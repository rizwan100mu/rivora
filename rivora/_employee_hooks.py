app_name = "rivora"
app_title = "Rivora"
app_publisher = "Nesscale Solutions Private Limited"
app_description = "Bundled Rivora employee services"
app_email = "info@nesscale.com"
app_license = "MIT"

# Required applications
required_apps = ["hrms"]

# Includes in <head>
# ------------------

after_install = "rivora.setup.after_install"
after_migrate = "rivora.setup.after_install"


# include js, css files in header of desk.html
# app_include_css = "/assets/rivora/css/rivora.css"
# app_include_js = "/assets/rivora/js/rivora.js"

# include js, css files in header of web template
# web_include_css = "/assets/rivora/css/rivora.css"
# web_include_js = "/assets/rivora/js/rivora.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "employee_self_service/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Employee Checkin": "public/js/employee_checkin.js",
    "Employee": "public/js/employee.js",
}

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "rivora.utils.jinja_methods",
# 	"filters": "rivora.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "rivora.install.before_install"
# after_install = "rivora.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "rivora.uninstall.before_uninstall"
# after_uninstall = "rivora.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "rivora.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
    "*": {
        "after_insert": "rivora.send_notification.notification",
        "on_update": "rivora.send_notification.notification",
        "on_submit": "rivora.send_notification.notification",
        "before_cancel": "rivora.send_notification.notification",
        "after_cancel": "rivora.send_notification.notification",
        "on_change": "rivora.send_notification.notification",
    },
    "Comment": {"after_insert": "rivora.events.after_insert_comment"},
    "Employee Checkin": {
        "after_insert": "rivora.events.set_location_address"
    },
    "Sales Order": {
        "on_submit": "rivora.events.employee_target.create_sales_person_target_log",
        "on_cancel": "rivora.events.employee_target.reverse_sales_person_target_log",
    },
    "Sales Invoice": {
        "on_submit": "rivora.events.employee_target.create_sales_person_target_log",
        "on_cancel": "rivora.events.employee_target.reverse_sales_person_target_log",
    },
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": ["rivora.mobile.employee.daily_rivora_notice_board_event"],
    "cron": {
        "0 9 * * *": ["rivora.background_jobs.process_daily_employee_jobs"],
        "0/5 * * * *": [
            "rivora.background_jobs.reminder_for_checkin",
            "rivora.background_jobs.reminder_for_checkout",
        ],
    },
}

# Testing
# -------

before_tests = "rivora.tests.test_utils.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "rivora.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "rivora.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"rivora.auth.validate"
# ]

jinja = {"methods": ["rivora.utils.strip_and_clean_html"]}

fixtures = [
    # {
    #     "dt": "Rivora Translation",
    # },
    {"dt": "Rivora Notification"},
    {"dt": "Rivora Notification Template"},
]
