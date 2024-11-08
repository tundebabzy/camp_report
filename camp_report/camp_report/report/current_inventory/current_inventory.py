# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.utils import flt, today
from pypika.terms import ExistsCriterion

from erpnext.accounts.doctype.pos_invoice.pos_invoice import get_pos_reserved_qty
from erpnext.stock.utils import (
	is_reposting_item_valuation_in_progress,
	update_included_uom_in_report,
)


def execute(filters=None):
	is_reposting_item_valuation_in_progress()
	filters = frappe._dict(filters or {})
	include_uom = filters.get("include_uom")
	columns = get_columns()
	bin_list = get_bin_list(filters)
	item_map = get_item_map(filters.get("item_code"), include_uom)

	warehouse_company = {}
	data = []
	conversion_factors = []
	for bin in bin_list:
		item = item_map.get(bin.item_code)

		if not item:
			# likely an item that has reached its end of life
			continue

		# item = item_map.setdefault(bin.item_code, get_item(bin.item_code))
		company = warehouse_company.setdefault(
			bin.warehouse, frappe.db.get_value("Warehouse", bin.warehouse, "company")
		)

		if filters.brand and filters.brand != item.brand:
			continue

		elif filters.item_group and filters.item_group != item.item_group:
			continue

		elif filters.company and filters.company != company:
			continue

		re_order_level = re_order_qty = 0

		for d in item.get("reorder_levels"):
			if d.warehouse == bin.warehouse:
				re_order_level = d.warehouse_reorder_level
				re_order_qty = d.warehouse_reorder_qty

		shortage_qty = 0
		if (re_order_level or re_order_qty) and re_order_level > bin.projected_qty:
			shortage_qty = re_order_level - flt(bin.projected_qty)

		reserved_qty_for_pos = get_pos_reserved_qty(bin.item_code, bin.warehouse)
		if reserved_qty_for_pos:
			bin.projected_qty -= reserved_qty_for_pos

		if filters.hide and bin.warehouse != item.default_warehouse and bin.projected_qty == 0:
			continue

		data.append(
			[
				item.name,
				item.description,
				bin.warehouse,
				bin.actual_qty,
				bin.reserved_qty,
				bin.projected_qty,
				item.safety_stock,
				flt(item["1_year_average"]),
				item.default_warehouse
			]
		)

		if include_uom:
			conversion_factors.append(item.conversion_factor)

	update_included_uom_in_report(columns, data, include_uom, conversion_factors)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Item Code"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{"label": _("Description"), "fieldname": "description", "width": 200},
		{
			"label": _("Warehouse"),
			"fieldname": "warehouse",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 120,
		},
		{
			"label": _("Actual Qty"),
			"fieldname": "actual_qty",
			"fieldtype": "Float",
			"width": 100,
			"convertible": "qty",
		},
		{
			"label": _("Reserved Qty"),
			"fieldname": "reserved_qty",
			"fieldtype": "Float",
			"width": 140,
			"convertible": "qty",
		},
		{
			"label": _("Available Qty"),
			"fieldname": "projected_qty",
			"fieldtype": "Float",
			"width": 140,
			"convertible": "qty",
		},
		{
			"label": _("Safety Stock"),
			"fieldname": "safety_stock",
			"fieldtype": "Float",
		},
		{
			"label": _("1 Year Average"),
			"fieldname": "1_year_average",
			"fieldtype": "Float"
		}
	]


def get_bin_list(filters):
	bin = frappe.qb.DocType("Bin")
	query = (
		frappe.qb.from_(bin)
		.select(
			bin.item_code,
			bin.warehouse,
			bin.actual_qty,
			bin.planned_qty,
			bin.indented_qty,
			bin.ordered_qty,
			bin.reserved_qty,
			bin.reserved_qty_for_production,
			bin.reserved_qty_for_sub_contract,
			bin.reserved_qty_for_production_plan,
			bin.projected_qty,
		)
		.orderby(bin.item_code, bin.warehouse)
	)

	if filters.item_code:
		query = query.where(bin.item_code == filters.item_code)

	if filters.warehouse:
		warehouse_details = frappe.db.get_value(
			"Warehouse", filters.warehouse, ["lft", "rgt"], as_dict=1
		)

		if warehouse_details:
			wh = frappe.qb.DocType("Warehouse")
			query = query.where(
				ExistsCriterion(
					frappe.qb.from_(wh)
					.select(wh.name)
					.where(
						(wh.lft >= warehouse_details.lft)
						& (wh.rgt <= warehouse_details.rgt)
						& (bin.warehouse == wh.name)
					)
				)
			)

	bin_list = query.run(as_dict=True)

	return bin_list


def get_item_map(item_code, include_uom):
	"""Optimization: get only the item doc and re_order_levels table"""

	bin = frappe.qb.DocType("Bin")
	item = frappe.qb.DocType("Item")

	query = (
		frappe.qb.from_(item)
		.select(item.name, item.item_name, item.description, item.item_group, item.brand, item.stock_uom, item.safety_stock, item["1_year_average"])
		.where(
			(item.is_stock_item == 1)
			& (item.disabled == 0)
			& (
				(item.end_of_life > today()) | (item.end_of_life.isnull()) | (item.end_of_life == "0000-00-00")
			)
			& (ExistsCriterion(frappe.qb.from_(bin).select(bin.name).where(bin.item_code == item.name)))
		)
	)

	if item_code:
		query = query.where(item.item_code == item_code)

	if include_uom:
		ucd = frappe.qb.DocType("UOM Conversion Detail")
		query = query.left_join(ucd).on((ucd.parent == item.name) & (ucd.uom == include_uom))

	items = query.run(as_dict=True)

	ir = frappe.qb.DocType("Item Reorder")
	query = frappe.qb.from_(ir).select("*")

	if item_code:
		query = query.where(ir.parent == item_code)

	reorder_levels = frappe._dict()
	for d in query.run(as_dict=True):
		if d.parent not in reorder_levels:
			reorder_levels[d.parent] = []

		reorder_levels[d.parent].append(d)

	item_map = frappe._dict()
	for item in items:
		item["reorder_levels"] = reorder_levels.get(item.name) or []
		item_map[item.name] = item

	returned_items = []
	for item_name in item_map.keys():
		returned_items.append(item_name)

	item_defaults = frappe.get_all(
		"Item Default", 
		filters={"parent": ["in", returned_items]}, 
		fields=["parent", "default_warehouse"]
	)

	for default in item_defaults:
		item_map.get(default.parent)["default_warehouse"] = default.default_warehouse

	return item_map
