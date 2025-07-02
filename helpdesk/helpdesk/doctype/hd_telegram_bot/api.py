# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def create_telegram_bot(bot_name, bot_token, default_team=None, default_priority=None):
    """Create a new Telegram bot configuration"""
    
    # Validate input
    if not bot_name or not bot_token:
        frappe.throw(_("Bot name and token are required"))
    
    # Check if bot already exists
    if frappe.db.exists("HD Telegram Bot", {"bot_name": bot_name}):
        frappe.throw(_("Bot with this name already exists"))
    
    try:
        # Create bot document
        bot_doc = frappe.get_doc({
            "doctype": "HD Telegram Bot",
            "bot_name": bot_name,
            "bot_token": bot_token,
            "default_team": default_team,
            "default_priority": default_priority,
            "is_active": 1
        })
        
        bot_doc.insert()
        
        return {
            "success": True,
            "message": _("Telegram bot created successfully"),
            "bot_name": bot_doc.name
        }
    
    except Exception as e:
        frappe.log_error("Telegram Bot Creation Error", str(e))
        frappe.throw(_("Failed to create Telegram bot: {0}").format(str(e)))


@frappe.whitelist()
def update_bot_status(bot_name, is_active):
    """Update bot active status"""
    
    if not frappe.db.exists("HD Telegram Bot", bot_name):
        frappe.throw(_("Bot not found"))
    
    try:
        bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        bot_doc.is_active = is_active
        bot_doc.save()
        
        return {
            "success": True,
            "message": _("Bot status updated successfully")
        }
    
    except Exception as e:
        frappe.log_error("Bot Status Update Error", str(e))
        frappe.throw(_("Failed to update bot status: {0}").format(str(e)))


@frappe.whitelist()
def get_bot_statistics(bot_name=None):
    """Get statistics for all bots or specific bot"""
    
    filters = {}
    if bot_name:
        filters["name"] = bot_name
    
    try:
        bots = frappe.get_all(
            "HD Telegram Bot",
            filters=filters,
            fields=[
                "name", "bot_name", "is_active", "total_messages_received",
                "total_tickets_created", "last_message_received", "created_on"
            ]
        )
        
        return {
            "success": True,
            "data": bots
        }
    
    except Exception as e:
        frappe.log_error("Bot Statistics Error", str(e))
        return {
            "success": False,
            "message": _("Failed to get bot statistics: {0}").format(str(e))
        }


@frappe.whitelist()
def test_all_bots():
    """Test connectivity for all active bots"""
    
    try:
        active_bots = frappe.get_all(
            "HD Telegram Bot",
            filters={"is_active": 1},
            fields=["name", "bot_name"]
        )
        
        results = []
        for bot in active_bots:
            bot_doc = frappe.get_doc("HD Telegram Bot", bot.name)
            test_result = bot_doc.test_bot_connection()
            results.append({
                "bot_name": bot.bot_name,
                "status": "success" if test_result.get("success") else "failed",
                "message": test_result.get("message")
            })
        
        return {
            "success": True,
            "results": results
        }
    
    except Exception as e:
        frappe.log_error("Bot Testing Error", str(e))
        return {
            "success": False,
            "message": _("Failed to test bots: {0}").format(str(e))
        } 