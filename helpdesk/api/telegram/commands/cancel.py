# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from typing import Dict, Any


def handle_cancel(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /cancel command - Cancel current operation
    
    Args:
        params: Dictionary containing user_data, message_data, bot_doc, etc.
    
    Returns:
        Dict containing response data
    """
    try:
        user_data = params.get("user_data", {})
        
        # Clear any active conversations or states
        clear_user_state(user_data)
        
        cancel_message = """❌ <b>Operation Cancelled</b>

Any ongoing operation has been cancelled.

You can now:
• Use /help to see available commands
• Use /ticket to create a new support ticket
• Use /status to check your tickets"""
        
        return create_success_response(
            message=cancel_message,
            parse_mode="HTML"
        )
    
    except Exception as e:
        frappe.log_error(f"Cancel command failed: {str(e)}")
        return create_error_response(f"Cancel operation failed: {str(e)}")


def clear_user_state(user_data: Dict[str, Any]):
    """
    Clear user's conversation state and any pending operations
    
    Args:
        user_data: User data
    """
    try:
        telegram_user_id = user_data.get("id")
        if not telegram_user_id:
            return
        
        # Clear any conversation state in database
        # This could be expanded to clear session data, conversation flows, etc.
        frappe.cache().delete_value(f"telegram_conversation_{telegram_user_id}")
        frappe.cache().delete_value(f"telegram_state_{telegram_user_id}")
        
        frappe.logger().info(f"Cleared state for telegram user {telegram_user_id}")
    
    except Exception as e:
        frappe.log_error(f"Failed to clear user state: {str(e)}")


def create_success_response(message: str, parse_mode: str = None, keyboard: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create success response"""
    response = {
        "success": True,
        "message": message,
        "response_type": "text"
    }
    
    if parse_mode:
        response["parse_mode"] = parse_mode
    
    if keyboard:
        response["keyboard"] = keyboard
    
    return response


def create_error_response(error_message: str) -> Dict[str, Any]:
    """Create error response"""
    return {
        "success": False,
        "message": f"❌ {error_message}",
        "response_type": "text"
    } 