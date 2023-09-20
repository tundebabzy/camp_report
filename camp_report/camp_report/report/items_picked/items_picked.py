# Copyright (c) 2023, tundebabzy@gmail.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.nestedset import get_descendants_of


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date cannot be greater than To Date"))

	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_columns(filters):
	return [
		{
			"label": _("Item Code"),
			"fieldtype": "Link",
			"fieldname": "item_code",
			"options": "Item",
			# "width": 120,
		},
		{"label": _("Item Name"), "fieldtype": "Data", "fieldname": "item_name", "width": 240},
		{"label": _("Quantity"), "fieldtype": "Float", "fieldname": "qty"},
		{
			"label": _("Date"),
			"fieldtype": "Date",
			"fieldname": "modified",
			# "width": 90,
		},
		{
			"label": _("Location"),
			"fieldtype": "Link",
			"fieldname": "warehouse",
			"options": "Warehouse",
			"width": 150,
		},
	]


def get_data(filters):
	from_date = frappe.utils.data.get_datetime_str(frappe.utils.data.add_days(frappe.utils.data.get_datetime(filters.from_date), -1))
	to_date = frappe.utils.data.get_datetime_str(frappe.utils.data.get_datetime(filters.to_date))
	condition = f"where modified > '{from_date}' and modified <= '{to_date}'"
	if filters.get("item_code"):
		condition = f"{condition} and item_code = '{filters.item_code}'"
	return frappe.db.sql(
		f"""select name, item_code, item_name, description, sum(qty) as qty, 
		modified, warehouse from `tabDelivery Note Item`
		{condition} group by item_code""", as_dict=1
	)

	return data
