# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime
from typing import Dict, Any


def handle_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /status command - Check status of user's tickets
    
    Args:
        params: Dictionary containing user_data, message_data, bot_doc, etc.
    
    Returns:
        Dict containing response data
    """
    try:
        user_data = params.get("user_data", {})
        command_args = params.get("command_args", [])
        
        # Get telegram user
        telegram_user = get_telegram_user(user_data)
        if not telegram_user:
            return create_error_response("User not found. Please use /start first.")
        
        # Check if specific ticket ID provided
        if command_args:
            ticket_id = command_args[0]
            return get_specific_ticket_status(ticket_id, telegram_user)
        
        # Get user's tickets
        tickets = get_user_tickets(telegram_user)
        
        if not tickets:
            return create_no_tickets_response()
        
        # Format tickets for display
        tickets_display = format_tickets_list(tickets)
        
        status_message = f"""📋 <b>Your Support Tickets</b>

{tickets_display}

💡 Use <code>/status [ticket_id]</code> for detailed information about a specific ticket."""
        
        return create_success_response(
            message=status_message,
            parse_mode="HTML"
        )
    
    except Exception as e:
        frappe.log_error(f"Status command failed: {str(e)}")
        return create_error_response(f"Failed to get ticket status: {str(e)}")


def get_telegram_user(user_data: Dict[str, Any]):
    """Get telegram user record"""
    try:
        telegram_user_id = user_data.get("id")
        if not telegram_user_id:
            return None
        
        return frappe.db.get_value("HD Telegram User", 
                                 {"telegram_user_id": telegram_user_id}, 
                                 "*", as_dict=True)
    except Exception:
        return None


def get_user_tickets(telegram_user):
    """Get tickets for user"""
    try:
        filters = {}
        
        # Filter by contact or raised_by
        if telegram_user.get("contact"):
            filters["contact"] = telegram_user["contact"]
        elif telegram_user.get("frappe_user"):
            filters["raised_by"] = telegram_user["frappe_user"]
        else:
            return []
        
        tickets = frappe.get_all(
            "HD Ticket",
            filters=filters,
            fields=["name", "subject", "status", "priority", "creation", "modified"],
            order_by="creation desc",
            limit=10
        )
        
        return tickets
    
    except Exception as e:
        frappe.log_error(f"Failed to get user tickets: {str(e)}")
        return []


def format_tickets_list(tickets: list) -> str:
    """Format tickets list for display"""
    formatted = []
    
    for i, ticket in enumerate(tickets, 1):
        status_emoji = get_status_emoji(ticket.get("status", ""))
        priority_emoji = get_priority_emoji(ticket.get("priority", ""))
        
        created_date = ticket.get("creation")
        if created_date:
            created_str = created_date.strftime("%Y-%m-%d")
        else:
            created_str = "Unknown"
        
        ticket_line = f"{i}. {status_emoji} <b>{ticket.get('name')}</b>"
        ticket_line += f"\n   📝 {ticket.get('subject', 'No subject')}"
        ticket_line += f"\n   📊 {ticket.get('status', 'Unknown')} {priority_emoji}"
        ticket_line += f"\n   📅 {created_str}\n"
        
        formatted.append(ticket_line)
    
    return "\n".join(formatted)


def get_status_emoji(status: str) -> str:
    """Get emoji for ticket status"""
    status_emojis = {
        "Open": "🟢",
        "Replied": "🔵", 
        "Closed": "🔴",
        "Resolved": "✅",
        "On Hold": "🟡"
    }
    return status_emojis.get(status, "⚪")


def get_priority_emoji(priority: str) -> str:
    """Get emoji for ticket priority"""
    priority_emojis = {
        "Low": "🟢",
        "Medium": "🟡",
        "High": "🟠",
        "Urgent": "🔴"
    }
    return priority_emojis.get(priority, "⚪")


def create_no_tickets_response() -> Dict[str, Any]:
    """Create response for users with no tickets"""
    message = """📋 <b>No Support Tickets</b>

You don't have any support tickets yet.

To create a new ticket, use:
<code>/ticket Your problem description</code>

💡 <i>Example: /ticket I need help with my account</i>"""
    
    return create_success_response(
        message=message,
        parse_mode="HTML"
    )


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