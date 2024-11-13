import frappe
from frappe import _
from frappe.utils.background_jobs import enqueue
from .connection import get_optima_connection
import random

@frappe.whitelist()
def enqueue_optima_order_sync(sales_order):
    """Enqueue the Optima order sync process."""
    enqueue(
        method="optima.optima.utils.order_sync.sync_sales_order_to_optima_by_name",
        queue="long",
        timeout=300,
        job_name=f"sync_optima_order_{sales_order}",
        sales_order=sales_order
    )
    
    frappe.msgprint(
        msg=_('Order sync has been queued and will be sent to Optima in the background.'),
        title=_('Order Sync Queued'),
        indicator='blue'
    )

def sync_sales_order_to_optima_by_name(sales_order):
    """Wrapper function to sync sales order by name."""
    doc = frappe.get_doc("Sales Order", sales_order)
    return sync_sales_order_to_optima(doc)

def prepare_order_header(doc, shipping_details):
    """Prepare order header data matching Optima_Orders schema."""
    return {
        "CLIENTE": 1,  # Assuming a default customer ID; replace with actual logic if available
        "NAZIONI_CODICE": None,
        "RIF": doc.name[:12],  # Truncate to 12 characters to match SQL type
        "RIFCLI": doc.po_no or '',
        "DATAORD": doc.transaction_date,
        "DATACONS": doc.delivery_date,
        "DATAINIZIO": doc.transaction_date,
        "DATAFINE": doc.delivery_date,
        "DEF": 'Y',  # Confirmed order
        "NOTES": "Test",  # Default value, can be customized
        "DESCR1_SPED": shipping_details.get("address_line1", "")[:40],
        "DESCR2_SPED": doc.customer_name[:40],
        "INDIRI_SPED": shipping_details.get("address_line1", "")[:64],
        "CAP_SPED": (shipping_details.get("pincode") or "")[:30],
        "LOCALITA_SPED": (shipping_details.get("city") or "")[:30],
        "PROV_SPED": (shipping_details.get("state") or "")[:30],
        "COMMESSA_CLI": doc.name[:50],
        "RIFINTERNO": doc.name[:50],
        "RIFAGENTE": frappe.session.user[:50],
        "DESCR_TIPICAUDOC": 'Sales Order'
    }

def prepare_order_line(idx, item, order_id):
    """Prepare order line data matching Optima_OrderLines schema."""
    return {
        "ID_ORDINI": order_id,
        "RIGA": idx,
        "QTAPZ": item.qty,
        "DESCR_MAT_COMP": item.description[:512] if item.description else item.item_name[:512],
        "COD_ART_CLIENTE": item.item_code[:512],
        "DESCMAT": item.description[:1024] if item.description else item.item_name[:1024],
        "SAGOMA": 'RECT',  # Default rectangle shape
        "CODICE_ANAGRAFICA": item.item_code[:32],
        "CATEGORIE": item.item_group[:255] if item.item_group else '',
        "DIMXPZ": item.get('width', 20),
        "DIMYPZ": item.get('height', 50),
        "ID_UM": 0,  # 0=mm
        "PRODOTTI_CODICE": item.item_code[:32],
        "isrect": 1  # 1=Rectangle, 0=Shaped
    }

def get_next_order_id(cursor):
    """Get the next available order ID from OPTIMA_Orders using SQL Server specific syntax."""
    cursor.execute("""
        DECLARE @NextID int;
        SELECT @NextID = ISNULL(MAX(ID_ORDINI), 0) + 1 FROM OPTIMA_Orders;
        SELECT @NextID as next_id;
    """)
    row = cursor.fetchone()
    return row[0]

def create_optima_order(doc, order_id, header, shipping_details):
    """Create or update Optima Order document."""
    # Check if Optima Order already exists
    optima_order = frappe.get_all(
        "Optima Order", 
        filters={"sales_order": doc.name}, 
        limit=1
    )
    
    order_data = {
        "sales_order": doc.name,
        "customer": doc.customer,
        "customer_reference": doc.po_no or "",
        "order_date": header["DATAORD"],
        "delivery_date": header["DATACONS"],
        "status": "Pending",
        "sync_status": "In Progress",
        "delivery_address": shipping_details.get("address_line1", ""),
        "delivery_city": shipping_details.get("city", ""),
        "delivery_country": shipping_details.get("country", ""),
        "optima_order_id": order_id,
        "internal_reference": doc.name,
        "agent_reference": frappe.session.user,
        "notes": header.get("NOTES", "")
    }

    if optima_order:
        # Update existing order
        existing_order = frappe.get_doc("Optima Order", optima_order[0].name)
        existing_order.update(order_data)
        existing_order.sync_status = "Completed"
        existing_order.save()
        return existing_order
    else:
        # Create new order
        order_data.update({
            "doctype": "Optima Order",
            "items": []
        })
        
        # Add items
        for item in doc.items:
            order_data["items"].append({
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty": item.qty,
                "rate": item.rate,
                "amount": item.amount,
                "description": item.description or item.item_name,
                "optima_sync_status": "Pending"
            })
        
        new_order = frappe.get_doc(order_data)
        new_order.insert(ignore_permissions=True)
        return new_order

def create_sync_log(doc, order_id, status, message=None):
    """Create Optima Sync Log entry."""
    log_data = {
        "doctype": "Optima Sync Log",
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "operation_id": order_id,
        "user": frappe.session.user,
        "status": status,
        "message": message if message else ""
    }
    
    log = frappe.get_doc(log_data)
    log.insert(ignore_permissions=True)
    return log

def sync_sales_order_to_optima(doc):
    """Sync Sales Order to Optima."""
    sync_log = None
    
    with get_optima_connection() as conn:
        try:
            cursor = conn.cursor(as_dict=False)

            # Set transaction isolation level to ensure data consistency
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            
            # Create sync log with "Pending" status
            sync_log = create_sync_log(doc, None, "Pending")
            
            # Fetch shipping address details
            shipping_address = frappe.get_doc("Address", doc.shipping_address_name) if doc.shipping_address_name else None
            shipping_details = {
                "address_line1": shipping_address.address_line1 if shipping_address else "",
                "city": shipping_address.city if shipping_address else "",
                "pincode": shipping_address.pincode if shipping_address else "",
                "state": shipping_address.state if shipping_address else "",
                "country": shipping_address.country if shipping_address else ""
            }

            # Start database transaction
            cursor.execute("BEGIN TRANSACTION")

            # Get next order ID with proper locking
            cursor.execute("""
                DECLARE @NextID int;
                SELECT @NextID = ISNULL(MAX(ID_ORDINI), 1000) + 1 
                FROM dbo.OPTIMA_Orders WITH (TABLOCKX);
                SELECT @NextID as next_id;
            """)
            order_id = cursor.fetchone()[0]

            # Prepare header and insert order header
            header = prepare_order_header(doc, shipping_details)
            cursor.execute("""
                INSERT INTO dbo.OPTIMA_Orders (
                    ID_ORDINI, CLIENTE, NAZIONI_CODICE, RIF, RIFCLI, DATAORD, DATACONS, 
                    DATAINIZIO, DATAFINE, DEF, NOTES, DESCR1_SPED, DESCR2_SPED, 
                    INDIRI_SPED, CAP_SPED, LOCALITA_SPED, PROV_SPED, 
                    COMMESSA_CLI, RIFINTERNO, RIFAGENTE, DESCR_TIPICAUDOC
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                order_id, header["CLIENTE"], header["NAZIONI_CODICE"], header["RIF"], 
                header["RIFCLI"], header["DATAORD"], header["DATACONS"], 
                header["DATAINIZIO"], header["DATAFINE"], header["DEF"], 
                header["NOTES"], header["DESCR1_SPED"], header["DESCR2_SPED"],
                header["INDIRI_SPED"], header["CAP_SPED"], header["LOCALITA_SPED"],
                header["PROV_SPED"], header["COMMESSA_CLI"], header["RIFINTERNO"],
                header["RIFAGENTE"], header["DESCR_TIPICAUDOC"]
            ))

            # Insert order lines
            for idx, item in enumerate(doc.items, 1):
                line = prepare_order_line(idx, item, order_id)
                cursor.execute("""
                    INSERT INTO dbo.OPTIMA_OrderLines (
                        ID_ORDINI, RIGA, QTAPZ, DESCR_MAT_COMP, COD_ART_CLIENTE,
                        DESCMAT, SAGOMA, CODICE_ANAGRAFICA, CATEGORIE, DIMXPZ,
                        DIMYPZ, ID_UM, PRODOTTI_CODICE, isrect
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    line["ID_ORDINI"], line["RIGA"], line["QTAPZ"],
                    line["DESCR_MAT_COMP"], line["COD_ART_CLIENTE"],
                    line["DESCMAT"], line["SAGOMA"], line["CODICE_ANAGRAFICA"],
                    line["CATEGORIE"], line["DIMXPZ"], line["DIMYPZ"],
                    line["ID_UM"], line["PRODOTTI_CODICE"], line["isrect"]
                ))

            # Verify the records were inserted
            cursor.execute("SELECT COUNT(*) FROM dbo.OPTIMA_Orders WHERE ID_ORDINI = %s", (order_id,))
            if cursor.fetchone()[0] == 0:
                raise Exception("Order header was not persisted properly")

            cursor.execute("SELECT COUNT(*) FROM dbo.OPTIMA_OrderLines WHERE ID_ORDINI = %s", (order_id,))
            if cursor.fetchone()[0] != len(doc.items):
                raise Exception("Order lines were not persisted properly")

            # Commit the transaction
            conn.commit()

            # Create/Update Optima Order document
            optima_order = create_optima_order(doc, order_id, header, shipping_details)

            # Update sync log with success status
            sync_log.operation_id = order_id
            sync_log.status = "Completed"
            sync_log.save()

            # Update ERPNext status
            frappe.db.set_value('Sales Order', doc.name, {
                'custom_optima_sync_status': 'Completed',
                'custom_optima_order': order_id
            })
            frappe.db.commit()

            return {"success": True, "order_id": order_id, "optima_order": optima_order.name}

        except Exception as e:
            if conn:
                conn.rollback()
            
            error_message = str(e)
            
            if sync_log:
                sync_log.status = "Failed"
                sync_log.message = error_message
                sync_log.save()
            else:
                create_sync_log(doc, None, "Failed", error_message)
            
            # Update Optima Order if it exists
            existing_order = frappe.get_all(
                "Optima Order",
                filters={"sales_order": doc.name},
                limit=1
            )
            if existing_order:
                frappe.db.set_value('Optima Order', existing_order[0].name, {
                    'status': 'Failed',
                    'sync_status': 'Failed',
                    'sync_message': error_message
                })
            
            # Update Sales Order
            frappe.db.set_value('Sales Order', doc.name, {
                'custom_optima_sync_status': 'Failed',
                'custom_optima_sync_error': error_message
            })
            frappe.db.commit()

            raise

