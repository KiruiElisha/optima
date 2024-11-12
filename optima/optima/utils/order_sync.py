import frappe
from frappe import _
from frappe.utils.background_jobs import enqueue
from .connection import get_optima_connection

def get_new_operation_id(cursor):
    """Get new operation ID from Optima"""
    cursor.execute("EXEC OPERATIONS_new @OperationName = 'ERPNext_ORDER_SYNC'")
    return cursor.fetchone()[0]

def enqueue_optima_order_sync(sales_order):
    """Enqueue the Optima order sync process"""
    enqueue(
        method="optima.optima.utils.order_sync.sync_sales_order_to_optima",
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

def get_shipping_details(doc):
    """Get shipping details from Sales Order shipping address"""
    shipping_address = None
    if doc.shipping_address_name:
        shipping_address = frappe.get_doc("Address", doc.shipping_address_name)
    
    return {
        "address": shipping_address.address_line1 if shipping_address else "",
        "city": shipping_address.city if shipping_address else "",
        "pincode": shipping_address.pincode if shipping_address else "",
        "state": shipping_address.state if shipping_address else "",
        "country": shipping_address.country if shipping_address else ""
    }

def sync_sales_order_to_optima(sales_order, method=None):
    """Sync Sales Order to Optima"""
    conn = None
    cursor = None
    optima_order = None
    
    try:
        doc = frappe.get_doc("Sales Order", sales_order)
        shipping_details = get_shipping_details(doc)
        conn = get_optima_connection()
        cursor = conn.cursor()
        
        # First create and insert the Optima Order header
        optima_order = frappe.new_doc("Optima Order")
        optima_order.sales_order = doc.name
        optima_order.status = "Pending"
        optima_order.sync_status = "In Progress"
        optima_order.customer = doc.customer
        optima_order.customer_reference = doc.po_no
        optima_order.order_date = doc.transaction_date
        optima_order.delivery_date = doc.delivery_date
        optima_order.delivery_address = shipping_details["address"]
        optima_order.delivery_city = shipping_details["city"]
        optima_order.delivery_zip = shipping_details["pincode"]
        optima_order.delivery_country = shipping_details["country"]
        
        # Add items before inserting
        for item in doc.items:
            optima_order.append("items", {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty": item.qty,
                "rate": item.rate,
                "amount": item.amount,
                "description": item.description,
                "optima_sync_status": "Pending"
            })
        
        # Insert the document
        optima_order.insert()
        
        # Insert into CONNECTOR_ORDERS.OPTIMA_Orders table
        cursor.execute("""
            INSERT INTO CONNECTOR_ORDERS.OPTIMA_Orders (
                ID_ORDINI,
                CLIENTE,
                RIF,
                RIFCLI,
                DATAORD,
                DATACONS,
                DATAINIZIO,
                DATAFINE,
                DEF,
                NOTES,
                DESCR1_SPED,
                DESCR2_SPED,
                INDIRI_SPED,
                CAP_SPED,
                LOCALITA_SPED,
                PROV_SPED,
                COMMESSA_CLI,
                RIFINTERNO,
                RIFAGENTE,
                statoordine,
                DESCR_TIPICAUDOC
            ) VALUES (
                0,  -- ID_ORDINI (will be auto-generated)
                %s, -- CLIENTE
                %s, -- RIF (Order Number)
                %s, -- RIFCLI (Customer Reference)
                %s, -- DATAORD
                %s, -- DATACONS
                %s, -- DATAINIZIO
                %s, -- DATAFINE
                'Y', -- DEF (Confirmed Order)
                %s, -- NOTES
                %s, -- DESCR1_SPED
                %s, -- DESCR2_SPED
                %s, -- INDIRI_SPED
                %s, -- CAP_SPED
                %s, -- LOCALITA_SPED
                %s, -- PROV_SPED
                %s, -- COMMESSA_CLI
                %s, -- RIFINTERNO
                %s, -- RIFAGENTE
                '1', -- statoordine (1 = to be imported)
                'SALES_ORDER'  -- DESCR_TIPICAUDOC
            )
        """, (
            doc.customer,
            doc.name,
            doc.po_no or '',
            doc.transaction_date,
            doc.delivery_date,
            doc.transaction_date,  # DATAINIZIO - using transaction date
            doc.delivery_date,     # DATAFINE - using delivery date
            doc.po_no or '',
            shipping_details["address"],
            doc.customer_name or '',
            shipping_details["address"],
            shipping_details["pincode"] or '',
            shipping_details["city"] or '',
            shipping_details["country"] or '',
            doc.name,  # COMMESSA_CLI - using sales order name
            doc.name,  # RIFINTERNO - using sales order name
            frappe.session.user  # RIFAGENTE - using current user
        ))
        
        # Get the inserted order ID
        cursor.execute("SELECT SCOPE_IDENTITY()")
        optima_order_id = cursor.fetchone()[0]
        optima_order.optima_order_id = optima_order_id
        
        # Insert items into CONNECTOR_ORDERS.OPTIMA_OrderLines
        for idx, item in enumerate(doc.items, 1):
            cursor.execute("""
                INSERT INTO CONNECTOR_ORDERS.OPTIMA_OrderLines (
                    ID_ORDINI,
                    RIGA,
                    QTAPZ,
                    DESCR_MAT_COMP,
                    COD_ART_CLIENTE,
                    DESCMAT,
                    ID_UM,
                    CODICE_ANAGRAFICA,
                    PRODOTTI_CODICE,
                    DIMXPZ,
                    DIMYPZ,
                    ID_PZ,
                    SAGOMA,
                    CATEGORIE
                ) VALUES (
                    %s, -- ID_ORDINI
                    %s, -- RIGA
                    %s, -- QTAPZ
                    %s, -- DESCR_MAT_COMP
                    %s, -- COD_ART_CLIENTE
                    %s, -- DESCMAT
                    0,  -- ID_UM (0=mm)
                    %s, -- CODICE_ANAGRAFICA
                    %s, -- PRODOTTI_CODICE
                    %s, -- DIMXPZ
                    %s, -- DIMYPZ
                    %s, -- ID_PZ
                    %s, -- SAGOMA
                    %s  -- CATEGORIE
                )
            """, (
                optima_order_id,
                idx,
                item.qty,
                item.description or item.item_name,
                item.item_code,
                item.description or item.item_name,
                item.item_code,
                item.item_code,
                item.width if hasattr(item, 'width') else 0,
                item.height if hasattr(item, 'height') else 0,
                idx,  # Using row index as piece ID
                'RECT',  # Default shape
                item.item_group or ''
            ))
        
        conn.commit()
        
        # Update Optima Order status
        optima_order.status = "Synced"
        optima_order.sync_status = "Completed"
        optima_order.save()
        
        # Update Sales Order using frappe.db to handle submitted doc
        frappe.db.set_value('Sales Order', doc.name, {
            'custom_optima_order': optima_order.name,
            'custom_optima_sync_status': 'Synced'
        })
        frappe.db.commit()
        
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(
            title="Optima Order Sync Error",
            message=f"Error syncing order {sales_order}: {error_msg}"
        )
        
        try:
            # Update Sales Order status using frappe.db
            frappe.db.set_value('Sales Order', doc.name, {
                'custom_optima_sync_status': 'Failed',
                'custom_optima_sync_error': error_msg
            })
            frappe.db.commit()
            
            if optima_order and optima_order.name:
                optima_order.status = "Failed"
                optima_order.sync_status = "Failed"
                optima_order.sync_message = error_msg
                optima_order.save()
        except Exception as update_error:
            frappe.log_error(
                title="Optima Order Status Update Error",
                message=f"Error updating status for {sales_order}: {str(update_error)}"
            )
            
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()