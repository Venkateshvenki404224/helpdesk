# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def create_telegram_indexes():
    """Create database indexes for Telegram integration"""
    try:
        indexes = [
            # HD Telegram Bot indexes
            {
                "doctype": "HD Telegram Bot",
                "fields": ["webhook_secret", "is_active"],
                "name": "telegram_bot_webhook_active"
            },
            {
                "doctype": "HD Telegram Bot",
                "fields": ["is_active", "bot_name"],
                "name": "telegram_bot_active_name"
            },
            
            # HD Telegram User indexes
            {
                "doctype": "HD Telegram User",
                "fields": ["telegram_user_id"],
                "name": "telegram_user_id_idx",
                "unique": True
            },
            {
                "doctype": "HD Telegram User",
                "fields": ["customer", "is_blocked"],
                "name": "telegram_user_customer_blocked"
            },
            {
                "doctype": "HD Telegram User",
                "fields": ["is_blocked", "auto_create_tickets"],
                "name": "telegram_user_blocked_auto"
            },
            {
                "doctype": "HD Telegram User",
                "fields": ["last_contact"],
                "name": "telegram_user_last_contact"
            },
            
            # HD Telegram Message indexes
            {
                "doctype": "HD Telegram Message",
                "fields": ["message_id", "telegram_bot"],
                "name": "telegram_message_id_bot"
            },
            {
                "doctype": "HD Telegram Message",
                "fields": ["telegram_user", "received_on"],
                "name": "telegram_message_user_received"
            },
            {
                "doctype": "HD Telegram Message",
                "fields": ["processing_status", "received_on"],
                "name": "telegram_message_status_received"
            },
            {
                "doctype": "HD Telegram Message",
                "fields": ["is_processed", "processing_status"],
                "name": "telegram_message_processed_status"
            },
            {
                "doctype": "HD Telegram Message",
                "fields": ["linked_ticket"],
                "name": "telegram_message_ticket"
            },
            {
                "doctype": "HD Telegram Message",
                "fields": ["telegram_bot", "received_on"],
                "name": "telegram_message_bot_received"
            },
            
            # HD Ticket indexes for Telegram integration
            {
                "doctype": "HD Ticket",
                "fields": ["customer", "status", "creation"],
                "name": "ticket_customer_status_creation"
            }
        ]
        
        created_count = 0
        failed_count = 0
        
        for index_config in indexes:
            try:
                result = create_index_if_not_exists(index_config)
                if result:
                    created_count += 1
                    frappe.logger().info(f"Created index: {index_config['name']}")
            except Exception as e:
                failed_count += 1
                frappe.log_error(f"Index Creation Failed: {index_config['name']}", str(e))
        
        frappe.logger().info(f"Telegram indexes: {created_count} created, {failed_count} failed")
        
        return {
            "success": True,
            "created": created_count,
            "failed": failed_count,
            "message": f"Index creation completed: {created_count} created, {failed_count} failed"
        }
    
    except Exception as e:
        frappe.log_error("Telegram Index Creation Error", str(e))
        return {"success": False, "error": str(e)}


def create_index_if_not_exists(index_config):
    """Create database index if it doesn't exist"""
    try:
        doctype = index_config["doctype"]
        fields = index_config["fields"]
        index_name = index_config["name"]
        unique = index_config.get("unique", False)
        
        # Get table name
        table_name = f"tab{doctype}"
        
        # Check if index already exists
        if index_exists(table_name, index_name):
            return False  # Index already exists
        
        # Build index creation SQL
        fields_str = ", ".join([f"`{field}`" for field in fields])
        unique_keyword = "UNIQUE" if unique else ""
        
        sql = f"""
        CREATE {unique_keyword} INDEX `{index_name}` 
        ON `{table_name}` ({fields_str})
        """
        
        frappe.db.sql(sql)
        frappe.db.commit()
        
        return True
    
    except Exception as e:
        frappe.log_error(f"Index Creation Error: {index_config.get('name', 'unknown')}", str(e))
        return False


def index_exists(table_name, index_name):
    """Check if index exists on table"""
    try:
        result = frappe.db.sql(f"""
        SHOW INDEX FROM `{table_name}` 
        WHERE Key_name = %s
        """, (index_name,))
        
        return len(result) > 0
    
    except Exception:
        return False


@frappe.whitelist()
def optimize_telegram_tables():
    """Optimize Telegram-related tables for better performance"""
    try:
        tables = [
            "tabHD Telegram Bot",
            "tabHD Telegram User", 
            "tabHD Telegram Message"
        ]
        
        optimized_count = 0
        
        for table in tables:
            try:
                frappe.db.sql(f"OPTIMIZE TABLE `{table}`")
                optimized_count += 1
                frappe.logger().info(f"Optimized table: {table}")
            except Exception as e:
                frappe.log_error(f"Table Optimization Failed: {table}", str(e))
        
        frappe.db.commit()
        
        return {
            "success": True,
            "optimized": optimized_count,
            "message": f"Optimized {optimized_count} tables"
        }
    
    except Exception as e:
        frappe.log_error("Table Optimization Error", str(e))
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def analyze_telegram_table_stats():
    """Analyze table statistics for Telegram tables"""
    try:
        tables_info = []
        
        tables = [
            "tabHD Telegram Bot",
            "tabHD Telegram User",
            "tabHD Telegram Message"
        ]
        
        for table in tables:
            try:
                # Get table status
                status_result = frappe.db.sql(f"""
                SHOW TABLE STATUS LIKE '{table}'
                """, as_dict=True)
                
                if status_result:
                    status = status_result[0]
                    
                    # Get index information
                    index_result = frappe.db.sql(f"""
                    SHOW INDEX FROM `{table}`
                    """, as_dict=True)
                    
                    tables_info.append({
                        "table_name": table,
                        "rows": status.get("Rows", 0),
                        "data_length": status.get("Data_length", 0),
                        "index_length": status.get("Index_length", 0),
                        "auto_increment": status.get("Auto_increment"),
                        "indexes": len(index_result),
                        "engine": status.get("Engine")
                    })
            
            except Exception as e:
                frappe.log_error(f"Table Analysis Failed: {table}", str(e))
        
        return {
            "success": True,
            "tables": tables_info,
            "total_tables": len(tables_info)
        }
    
    except Exception as e:
        frappe.log_error("Table Analysis Error", str(e))
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_telegram_query_performance():
    """Get performance statistics for common Telegram queries"""
    try:
        # Common queries and their performance
        queries = [
            {
                "name": "Find user by telegram_user_id",
                "sql": """
                SELECT COUNT(*) FROM `tabHD Telegram User` 
                WHERE telegram_user_id = '123456789'
                """,
                "expected_index": "telegram_user_id_idx"
            },
            {
                "name": "Get pending messages",
                "sql": """
                SELECT COUNT(*) FROM `tabHD Telegram Message` 
                WHERE processing_status = 'Pending' 
                ORDER BY received_on
                """,
                "expected_index": "telegram_message_status_received"
            },
            {
                "name": "Get user messages",
                "sql": """
                SELECT COUNT(*) FROM `tabHD Telegram Message` 
                WHERE telegram_user = 'TG-USER-001' 
                ORDER BY received_on DESC
                """,
                "expected_index": "telegram_message_user_received"
            },
            {
                "name": "Get active bot by webhook",
                "sql": """
                SELECT COUNT(*) FROM `tabHD Telegram Bot` 
                WHERE webhook_secret = 'secret123' AND is_active = 1
                """,
                "expected_index": "telegram_bot_webhook_active"
            }
        ]
        
        performance_results = []
        
        for query in queries:
            try:
                # Explain the query
                explain_sql = f"EXPLAIN {query['sql']}"
                explain_result = frappe.db.sql(explain_sql, as_dict=True)
                
                # Measure execution time
                import time
                start_time = time.time()
                frappe.db.sql(query['sql'])
                execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                
                performance_results.append({
                    "query_name": query["name"],
                    "execution_time_ms": round(execution_time, 2),
                    "explain_info": explain_result,
                    "expected_index": query.get("expected_index"),
                    "using_index": any(
                        result.get("key") == query.get("expected_index") 
                        for result in explain_result
                    ) if explain_result else False
                })
            
            except Exception as e:
                performance_results.append({
                    "query_name": query["name"],
                    "error": str(e)
                })
        
        return {
            "success": True,
            "performance_results": performance_results
        }
    
    except Exception as e:
        frappe.log_error("Query Performance Analysis Error", str(e))
        return {"success": False, "error": str(e)}


def setup_telegram_database_optimization():
    """Complete database optimization setup for Telegram integration"""
    try:
        results = {}
        
        # Step 1: Create indexes
        frappe.logger().info("Creating Telegram database indexes...")
        index_result = create_telegram_indexes()
        results["indexes"] = index_result
        
        # Step 2: Optimize tables
        frappe.logger().info("Optimizing Telegram tables...")
        optimize_result = optimize_telegram_tables()
        results["optimization"] = optimize_result
        
        # Step 3: Analyze tables
        frappe.logger().info("Analyzing table statistics...")
        analysis_result = analyze_telegram_table_stats()
        results["analysis"] = analysis_result
        
        frappe.logger().info("Telegram database optimization completed")
        
        return {
            "success": True,
            "message": "Database optimization completed successfully",
            "results": results
        }
    
    except Exception as e:
        frappe.log_error("Database Optimization Setup Error", str(e))
        return {"success": False, "error": str(e)} 