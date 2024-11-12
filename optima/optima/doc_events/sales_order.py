import frappe
from ..utils.order_sync import enqueue_optima_order_sync

def on_submit(doc, method=None):
    """Handler for Sales Order submit event"""
    if doc.custom_send_to_optima and not doc.custom_optima_order:
        enqueue_optima_order_sync(doc.name) 