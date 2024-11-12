import frappe
from frappe import _
from .connection import get_optima_connection

def sync_invoice_to_optima(doc, method):
    """Sync ERPNext Sales Invoice to Optima."""
    if not frappe.get_single("Optima Settings").enabled:
        return
    
    conn = get_optima_connection()
    cursor = conn.cursor()
    
    try:
        # Get customer mapping
        customer_mapping = frappe.get_all(
            "Optima Customer Mapping",
            filters={"erpnext_customer": doc.customer},
            fields=["optima_customer_code"]
        )
        
        if not customer_mapping:
            frappe.throw(_("Customer mapping not found in Optima"))
        
        # Insert invoice header
        cursor.execute("""
            INSERT INTO SalesInvoices (
                InvoiceNo,
                CustomerCode,
                InvoiceDate,
                TotalAmount
            ) VALUES (%s, %s, %s, %s)
        """, (
            doc.name,
            customer_mapping[0].optima_customer_code,
            doc.posting_date,
            doc.grand_total
        ))
        
        # Insert invoice items
        for item in doc.items:
            item_mapping = frappe.get_all(
                "Optima Item Mapping",
                filters={"erpnext_item_code": item.item_code},
                fields=["optima_item_code"]
            )
            
            if not item_mapping:
                frappe.throw(_("Item mapping not found in Optima for item: {0}").format(item.item_code))
            
            cursor.execute("""
                INSERT INTO SalesInvoiceItems (
                    InvoiceNo,
                    ItemCode,
                    Quantity,
                    UnitPrice,
                    Amount
                ) VALUES (%s, %s, %s, %s, %s)
            """, (
                doc.name,
                item_mapping[0].optima_item_code,
                item.qty,
                item.rate,
                item.amount
            ))
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        frappe.log_error(f"Error syncing invoice to Optima: {str(e)}", "Optima Integration")
        frappe.throw(_("Failed to sync invoice to Optima"))
    finally:
        cursor.close()
        conn.close()

def cancel_invoice_in_optima(doc, method):
    """Cancel invoice in Optima when cancelled in ERPNext."""
    if not frappe.get_single("Optima Settings").enabled:
        return
    
    conn = get_optima_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE SalesInvoices
            SET Status = 'Cancelled'
            WHERE InvoiceNo = %s
        """, (doc.name,))
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        frappe.log_error(f"Error cancelling invoice in Optima: {str(e)}", "Optima Integration")
        frappe.throw(_("Failed to cancel invoice in Optima"))
    finally:
        cursor.close()
        conn.close() 