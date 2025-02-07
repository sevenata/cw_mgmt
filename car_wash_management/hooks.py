app_name = "car_wash_management"
app_title = "Car Wash Management"
app_publisher = "Rifat"
app_description = "Car wash management description"
app_email = "jum.rifm@gmail.com"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/car_wash_management/css/car_wash_management.css"
# app_include_js = "/assets/car_wash_management/js/car_wash_management.js"

# include js, css files in header of web template
# web_include_css = "/assets/car_wash_management/css/car_wash_management.css"
# web_include_js = "/assets/car_wash_management/js/car_wash_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "car_wash_management/public/scss/website"

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
# app_include_icons = "car_wash_management/public/icons.svg"

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
# 	"methods": "car_wash_management.utils.jinja_methods",
# 	"filters": "car_wash_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "car_wash_management.install.before_install"
# after_install = "car_wash_management.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "car_wash_management.uninstall.before_uninstall"
# after_uninstall = "car_wash_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "car_wash_management.utils.before_app_install"
# after_app_install = "car_wash_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "car_wash_management.utils.before_app_uninstall"
# after_app_uninstall = "car_wash_management.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "car_wash_management.notifications.get_notification_config"

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

doc_events = {
	# "Car wash booking": {
	# 	"on_update": "car_wash_management.car_wash_management.doctype.car_wash_availability.car_wash_availability.update_cars_in_queue"
	# }
	# "*": {
	# 	"on_update": "method",
	# 	"on_cancel": "method",
	# 	"on_trash": "method"
	# }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"car_wash_management.tasks.all"
# 	],
# 	"daily": [
# 		"car_wash_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"car_wash_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"car_wash_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"car_wash_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "car_wash_management.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service.get_random": "car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service.get_random",
	"car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service.get_services_with_prices": "car_wash_management.car_wash_management.doctype.car_wash_service.car_wash_service.get_services_with_prices"
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "car_wash_management.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["car_wash_management.utils.before_request"]
# after_request = ["car_wash_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["car_wash_management.utils.before_job"]
# after_job = ["car_wash_management.utils.after_job"]

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
# 	"car_wash_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
	# 	{
	# 		"doctype": "Car make"
	# 	},
	# 	{
	# 		"doctype": "Car model"
	# 	},
	# 	{
	# 		"doctype": "Car model synonym"
	# 	},
	{
		"doctype": "City"
	},
	{
		"doctype": "Shift Type"
	},
	# {
	# 	"doctype": "Work Shift Schedule"
	# },
	# {
	# 	"doctype": "Worker Check In"
	# },
	{
		"doctype": "Workflow"
	},
	{
		"doctype": "Workflow State"
	},
	{
		"doctype": "Workflow Action"
	},
	# 	{
	# 		"doctype": "User",
	# "filters": [
	#             # Filter users whose role_profiles include the desired role profile
	#             ["role_profiles", "in", [["role_profile", "in", ["Car Wash Worker Role Profile"]]]]
	#         ]
	# 		# "filters": [
	# 		# 	["role_profile_name", "in",
	# 		# 	 ["Car Wash Cashier Role Profile", "Car Wash Administrator Role Profile",
	# 		# 	  "Car Wash Worker Role Profile"]]
	# 		# ]
	# 	},
	{
		"doctype": "Role",
		"filters": [
			["name", "in", ["Car Wash Cashier", "Car Wash Administrator", "Car Wash Worker"]]
		]
	},
		{
			"doctype": "Role Profile",
			"filters": [
				["name", "in", ["Car Wash Cashier Role Profile", "Car Wash Administrator Role Profile",
								"Car Wash Worker Role Profile"]]
			]
		},
		{
        		"doctype": "Custom DocPerm",
        		"filters": [
                			["role", "in", ["Car Wash Cashier", "Car Wash Administrator", "Car Wash Worker"]]
                		]
        	}
]
