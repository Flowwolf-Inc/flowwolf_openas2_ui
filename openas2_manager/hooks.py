app_name = "openas2_manager"
app_title = "OpenAS2 Manager"
app_publisher = "Lakshana"
app_description = "Central OpenAS2 Management Web UI for Shipper, Broker, and Carrier TMS"
app_email = "lakshanavm2005@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "openas2_manager",
		"title": "EDI AS2",
		"route": "/app/openas2-dashboard",
		"has_permission": "openas2_manager.boot.has_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = [
	"/assets/openas2_manager/css/openas2_dashboard.css",
	"/assets/openas2_manager/css/openas2_partnership_ui.css",
	"/assets/openas2_manager/css/openas2_assistant.css?v=20261009stack",
]
# Shared OA2 layout (theme toggle, full-bleed width/height). Scoped to OA2 routes only.
app_include_js = [
	"/assets/openas2_manager/js/openas2_layout.js?v=20261028strip-lists",
	"/assets/openas2_manager/js/openas2_provision.js",
	"/assets/openas2_manager/js/openas2_partnership_ui.js",
	"/assets/openas2_manager/js/openas2_assistant.js?v=20261009stack",
	"/assets/openas2_manager/js/openas2_assistant_boot.js?v=20261009stack",
]

# include js, css files in header of web template
# web_include_css = "/assets/openas2_manager/css/openas2_manager.css"
# web_include_js = "/assets/openas2_manager/js/openas2_manager.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "openas2_manager/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "openas2_manager/public/icons.svg"

# Home Pages
# ----------

# Desk boot: open AS2 dashboard as home (see boot.py)
boot_session = "openas2_manager.boot.boot_session"
on_session_creation = "openas2_manager.boot.on_session_creation"

# Frappe remaps app route to the module Workspace (/app/openas2-manager).
# Send that URL to the real dashboard Page on full page loads (login).
website_redirects = [
	{
		"source": r"/app/openas2-manager",
		"target": "/app/openas2-dashboard",
		"redirect_http_status": 302,
	},
]

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
# 	"methods": "openas2_manager.utils.jinja_methods",
# 	"filters": "openas2_manager.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "openas2_manager.install.before_install"
# after_install = "openas2_manager.install.after_install"
after_migrate = ["openas2_manager.boot.after_migrate"]

# Uninstallation
# ------------

# before_uninstall = "openas2_manager.uninstall.before_uninstall"
# after_uninstall = "openas2_manager.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "openas2_manager.utils.before_app_install"
# after_app_install = "openas2_manager.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "openas2_manager.utils.before_app_uninstall"
# after_app_uninstall = "openas2_manager.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "openas2_manager.notifications.get_notification_config"

# Awesome Ba
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["openas2_manager.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"OpenAS2 Instance": "openas2_manager.access.openas2_instance_query",
	"OpenAS2 Partnership": "openas2_manager.access.openas2_partnership_query",
	"AS2 Certificate": "openas2_manager.access.as2_certificate_query",
	"AS2 Partner": "openas2_manager.access.as2_partner_query",
	"OpenAS2 Message Log": "openas2_manager.access.openas2_message_log_query",
	"OpenAS2 AI Conversation": "openas2_manager.openas2.assistant_history.conversation_query",
}

has_permission = {
	"OpenAS2 Instance": "openas2_manager.access.openas2_instance_has_permission",
	"OpenAS2 Partnership": "openas2_manager.access.openas2_partnership_has_permission",
	"AS2 Certificate": "openas2_manager.access.as2_certificate_has_permission",
	"AS2 Partner": "openas2_manager.access.as2_partner_has_permission",
	"OpenAS2 Message Log": "openas2_manager.access.openas2_message_log_has_permission",
	"OpenAS2 AI Conversation": "openas2_manager.openas2.assistant_history.conversation_has_permission",
}

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
# 		"on_update": "openas2_manager.utils.update",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	# Message lists read msg_metadata directly. This job does not copy files into Message Log.
	"cron": {
		"*/1 * * * *": [
			"openas2_manager.openas2.monitoring.scheduled_monitoring_sync",
		],
	},
}

# Testing
# -------

# before_tests = "openas2_manager.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "openas2_manager.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "openas2_manager.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["openas2_manager.utils.before_request"]
# after_request = ["openas2_manager.utils.after_request"]

# Job Events
# ----------
# before_job = ["openas2_manager.utils.before_job"]
# after_job = ["openas2_manager.utils.after_job"]

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
# 	"openas2_manager.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
