import frappe
from frappe import _
from .connection import get_optima_connection

def fetch_optima_items():
    """Fetch items from Optima database."""
    conn = get_optima_connection()
    cursor = conn.cursor(as_dict=True)
    
    try:
        cursor.execute("""
            SELECT 
                ItemCode,
                Description,
                UnitPrice,
                TaxCode
            FROM Items
        """)  # Adjust the query based on actual Optima table structure
        
        items = cursor.fetchall()
        return items
    
    except Exception as e:
        frappe.log_error(f"Error fetching Optima items: {str(e)}", "Optima Integration")
        raise
    finally:
        cursor.close()
        conn.close()

def fetch_optima_customers():
    """Fetch customers from Optima database."""
    conn = get_optima_connection()
    cursor = conn.cursor(as_dict=True)
    
    try:
        cursor.execute("""
            SELECT 
                CustomerCode,
                CustomerName,
                Address1,
                Address2,
                ContactPerson,
                Phone
            FROM Customers
        """)  # Adjust the query based on actual Optima table structure
        
        customers = cursor.fetchall()
        return customers
    
    except Exception as e:
        frappe.log_error(f"Error fetching Optima customers: {str(e)}", "Optima Integration")
        raise
    finally:
        cursor.close()
        conn.close() 