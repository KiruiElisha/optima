import frappe
from frappe import _
import pymssql
from frappe.utils import cint

def get_optima_settings():
    """Get Optima settings."""
    settings = frappe.get_single("Optima Settings")
    if not settings.enabled:
        frappe.throw(_("Optima Integration is not enabled"))
    return settings

def get_optima_connection():
    """Get MSSQL connection for Optima."""
    settings = get_optima_settings()
    
    try:
        conn = pymssql.connect(
            server=settings.server_ip,
            port=cint(settings.port),
            user=settings.username,
            password=settings.get_password('password'),
            database=settings.database_name
        )
        return conn
    except Exception as e:
        frappe.log_error(f"Optima Connection Error: {str(e)}", "Optima Integration")
        frappe.throw(_("Could not connect to Optima database. Please check settings and try again."))

def test_connection():
    """Test connection to Optima database."""
    try:
        conn = get_optima_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT @@VERSION")
        version = cursor.fetchone()
        cursor.close()
        conn.close()
        return {
            "success": True,
            "message": f"Successfully connected to Optima database.\nSQL Server Version: {version[0]}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}"
        } 