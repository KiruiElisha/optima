# Copyright (c) 2024, Ronoh and contributors
# For license information, please see license.txt
import frappe
from frappe import _
import pymssql
from frappe.utils import cint
from frappe.model.document import Document


class OptimaSettings(Document):
	def validate(self):
		# Ensure port is numeric
		if not self.port.isdigit():
			frappe.throw("Port must be a valid number")

	def get_connection(self, with_database=True):
		"""Get MSSQL connection for Optima."""
		if not self.enabled:
			frappe.throw(_("Optima Integration is not enabled"))
		
		try:
			connection_params = {
				'server': self.server_ip,
				'port': cint(self.port),
				'user': self.username,
				'password': self.get_password('password')
			}
			
			# Only include database if with_database is True and database_name is set
			if with_database and self.database_name:
				connection_params['database'] = self.database_name
			
			conn = pymssql.connect(**connection_params)
			return conn
		except Exception as e:
			frappe.log_error(f"Optima Connection Error: {str(e)}", "Optima Integration")
			
			frappe.throw(_("Could not connect to Optima database. Please check settings and try again."))

	@frappe.whitelist()
	def test_connection(self):
		"""Test connection to Optima database."""
		try:
			# First test without database
			conn = self.get_connection(with_database=False)
			cursor = conn.cursor()
			cursor.execute("SELECT @@VERSION")
			version = cursor.fetchone()
			
			# If database name is provided, try to use it
			database_msg = ""
			if self.database_name:
				try:
					cursor.execute(f"USE {self.database_name}")
					database_msg = f"\nSuccessfully connected to database: {self.database_name}"
				except Exception as e:
					database_msg = f"\nWarning: Could not connect to database '{self.database_name}': {str(e)}"
			
			cursor.close()
			conn.close()
			
			return {
				"success": True,
				"message": f"Successfully connected to SQL Server.\nSQL Server Version: {version[0]}{database_msg}"
			}
		except Exception as e:
			return {
				"success": False,
				"message": f"Connection failed: {str(e)}"
			}

	@frappe.whitelist()
	def get_databases(self):
		"""Get list of available databases."""
		try:
			conn = self.get_connection(with_database=False)
			cursor = conn.cursor()
			cursor.execute("""
				SELECT name 
				FROM sys.databases 
				WHERE database_id > 4  -- Exclude system databases
				ORDER BY name
			""")
			databases = [row[0] for row in cursor.fetchall()]
			cursor.close()
			conn.close()
			
			return {
				"success": True,
				"databases": databases
			}
		except Exception as e:
			return {
				"success": False,
				"message": f"Failed to fetch databases: {str(e)}"
			}

	@frappe.whitelist()
	def get_tables(self, database):
		"""Get list of tables in specified database."""
		try:
			conn = self.get_connection(with_database=False)
			cursor = conn.cursor()
			cursor.execute(f"USE {database}")
			cursor.execute("""
				SELECT TABLE_NAME 
				FROM INFORMATION_SCHEMA.TABLES 
				WHERE TABLE_TYPE = 'BASE TABLE'
				ORDER BY TABLE_NAME
			""")
			tables = [row[0] for row in cursor.fetchall()]
			cursor.close()
			conn.close()
			
			return {
				"success": True,
				"tables": tables
			}
		except Exception as e:
			return {
				"success": False,
				"message": f"Failed to fetch tables: {str(e)}"
			}

	@frappe.whitelist()
	def get_table_fields(self, database, table):
		"""Get field information for a specific table."""
		try:
			conn = self.get_connection(with_database=False)
			cursor = conn.cursor()
			cursor.execute(f"USE {database}")
			cursor.execute("""
				SELECT 
					c.name AS column_name,
					t.name AS data_type,
					c.is_nullable,
					CASE WHEN i.index_id IS NOT NULL AND i.is_primary_key = 1 
						THEN 1 ELSE 0 END AS is_primary_key
				FROM sys.columns c
				INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
				LEFT JOIN sys.index_columns ic ON ic.object_id = c.object_id 
					AND ic.column_id = c.column_id
				LEFT JOIN sys.indexes i ON ic.object_id = i.object_id 
					AND ic.index_id = i.index_id
				WHERE c.object_id = OBJECT_ID(%s)
				ORDER BY c.column_id
			""", (table,))
			
			fields = [
				{
					'name': row[0],
					'type': row[1],
					'is_nullable': bool(row[2]),
					'is_primary_key': bool(row[3])
				}
				for row in cursor.fetchall()
			]
			
			cursor.close()
			conn.close()
			
			return {
				"success": True,
				"fields": fields
			}
		except Exception as e:
			return {
				"success": False,
				"message": f"Failed to fetch table fields: {str(e)}"
			}
