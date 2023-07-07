import frappe
from erpnext.stock.doctype.pick_list.pick_list import map_pl_locations, update_packed_item_details, \
    validate_item_locations
from camp_report.overrides.sales_order import make_delivery_note
from itertools import groupby


def create_dn_with_so(sales_dict, pick_list):
    delivery_note = None

    item_table_mapper = {
        "doctype": "Delivery Note Item",
        "field_map": {
            "rate": "rate",
            "name": "so_detail",
            "parent": "against_sales_order",
            "box": "box"
        },
        "condition": lambda doc: abs(doc.delivered_qty) < abs(doc.qty)
        and doc.delivered_by_supplier != 1,
    }

    for customer in sales_dict:
        for so in sales_dict[customer]:
            delivery_note = None
            delivery_note = make_delivery_note(so, delivery_note, skip_item_mapping=True)
            break
        if delivery_note:
            # map all items of all sales orders of that customer
            for so in sales_dict[customer]:
                map_pl_locations(pick_list, item_table_mapper, delivery_note, so)
            delivery_note.flags.ignore_mandatory = True
            delivery_note.insert()
            update_packed_item_details(pick_list, delivery_note)
            delivery_note.save()

    return delivery_note


def create_dn_wo_so(pick_list):
    delivery_note = frappe.new_doc("Delivery Note")

    item_table_mapper_without_so = {
        "doctype": "Delivery Note Item",
        "field_map": {
            "rate": "rate",
            "name": "name",
            "parent": "",
            "box": "box"
        },
    }
    map_pl_locations(pick_list, item_table_mapper_without_so, delivery_note)
    delivery_note.insert(ignore_mandatory=True)

    return delivery_note



@frappe.whitelist()
def create_delivery_note(source_name, target_doc=None):
    pick_list = frappe.get_doc("Pick List", source_name)
    validate_item_locations(pick_list)
    sales_dict = dict()
    sales_orders = []
    delivery_note = None
    for location in pick_list.locations:
        if location.sales_order:
            sales_orders.append(
                frappe.db.get_value(
                    "Sales Order", location.sales_order, ["customer", "name as sales_order"], as_dict=True
                )
            )

    for customer, rows in groupby(sales_orders, key=lambda so: so["customer"]):
        sales_dict[customer] = {row.sales_order for row in rows}

    if sales_dict:
        delivery_note = create_dn_with_so(sales_dict, pick_list)

    if not all(item.sales_order for item in pick_list.locations):
        delivery_note = create_dn_wo_so(pick_list)

    for dn_item in delivery_note.items:
        for pl_item in pick_list.locations:
            if dn_item.item_code == pl_item.item_code and pl_item.warehouse == dn_item.warehouse:
                dn_item.set('box', pl_item.box)
    delivery_note.save()

    frappe.msgprint(frappe._("Delivery Note(s) created for the Pick List"))
    return delivery_note
