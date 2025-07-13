# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime
from typing import Dict, Any


def handle_ticket(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /ticket command - Create a new support ticket
    
    Args:
        params: Dictionary containing:
            - user_data: Telegram user information
            - message_data: Telegram message data
            - bot_doc: HD Telegram Bot document
            - command_doc: HD Telegram Command document
            - command_args: List of command arguments
            - mapping: Bot command mapping (if any)
    
    Returns:
        Dict containing response data
    """
    try:
        user_data = params.get("user_data", {})
        message_data = params.get("message_data", {})
        bot_doc = params.get("bot_doc")
        command_args = params.get("command_args", [])
        
        # Get or create telegram user
        telegram_user = get_or_create_telegram_user(user_data)
        
        # Extract ticket description from command arguments
        ticket_description = " ".join(command_args) if command_args else None
        
        if not ticket_description:
            # If no description provided, guide user to provide one
            return create_guidance_response()
        
        # Create the ticket
        ticket_doc = create_support_ticket(
            telegram_user=telegram_user,
            description=ticket_description,
            bot_doc=bot_doc,
            message_data=message_data
        )
        
        if not ticket_doc:
            return create_error_response("Failed to create ticket. Please try again.")
        
        # Prepare context for success template
        context = {
            "user_name": user_data.get("first_name", "there"),
            "ticket_id": ticket_doc.name,
            "ticket_subject": ticket_doc.subject,
            "ticket_status": ticket_doc.status,
            "ticket_priority": ticket_doc.priority,
            "created_time": ticket_doc.creation.strftime("%Y-%m-%d %H:%M:%S"),
            "bot_name": bot_doc.bot_name if bot_doc else "Support Bot"
        }
        
        # Try to use ticket creation template
        try:
            template_doc = frappe.get_doc("HD Bot Response Template", "ticket_created")
            if template_doc.is_active:
                result = template_doc.render(context)
                return create_success_response(
                    message=result["content"],
                    parse_mode=result.get("parse_mode"),
                    keyboard=result.get("keyboard")
                )
        except frappe.DoesNotExistError:
            pass
        
        # Fallback success message
        success_message = f"""✅ <b>Ticket Created Successfully!</b>

🎫 <b>Ticket ID:</b> <code>{context['ticket_id']}</code>
📝 <b>Subject:</b> {context['ticket_subject']}
📊 <b>Status:</b> {context['ticket_status']}
⚡ <b>Priority:</b> {context['ticket_priority']}
⏰ <b>Created:</b> {context['created_time']}

Our support team will respond soon. You can check the status anytime with /status."""
        
        return create_success_response(
            message=success_message,
            parse_mode="HTML"
        )
    
    except Exception as e:
        frappe.log_error(f"Ticket command failed: {str(e)}")
        return create_error_response(f"Failed to create ticket: {str(e)}")


def create_guidance_response() -> Dict[str, Any]:
    """Create guidance response for ticket creation"""
    guidance_message = """🎫 <b>Create a Support Ticket</b>

To create a new ticket, please describe your issue:

<code>/ticket Your problem description here</code>

<b>Examples:</b>
• <code>/ticket I can't log into my account</code>
• <code>/ticket Website is loading slowly</code>
• <code>/ticket Need help with billing</code>

💡 <i>The more details you provide, the better we can help you!</i>"""
    
    return create_success_response(
        message=guidance_message,
        parse_mode="HTML"
    )


def get_or_create_telegram_user(user_data: Dict[str, Any]):
    """Get or create telegram user"""
    try:
        from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
        return get_or_create_telegram_user(user_data)
    except Exception as e:
        frappe.log_error(f"Failed to get/create telegram user: {str(e)}")
        return None


def create_support_ticket(telegram_user, description: str, bot_doc=None, message_data=None) -> Any:
    """
    Create a support ticket
    
    Args:
        telegram_user: HD Telegram User document
        description: Ticket description
        bot_doc: Bot document
        message_data: Message data
        
    Returns:
        HD Ticket document or None
    """
    try:
        # Prepare ticket data
        ticket_data = {
            "doctype": "HD Ticket",
            "subject": generate_ticket_subject(description),
            "description": description,
            "status": "Open",
            "contact": telegram_user.contact if hasattr(telegram_user, 'contact') else None,
            "raised_by": telegram_user.frappe_user if hasattr(telegram_user, 'frappe_user') else None,
            "via_customer_portal": 0
        }
        
        # Add bot-specific settings
        if bot_doc:
            if bot_doc.default_team:
                ticket_data["team"] = bot_doc.default_team
            if bot_doc.default_priority:
                ticket_data["priority"] = bot_doc.default_priority
            if bot_doc.company_name:
                ticket_data["company"] = bot_doc.company_name
        
        # Create ticket document
        ticket_doc = frappe.get_doc(ticket_data)
        ticket_doc.insert(ignore_permissions=True)
        
        # Create communication record
        create_ticket_communication(ticket_doc, telegram_user, description, message_data)
        
        # Update statistics
        if bot_doc:
            bot_doc.db_set('total_tickets_created', (bot_doc.total_tickets_created or 0) + 1)
        
        return ticket_doc
    
    except Exception as e:
        frappe.log_error(f"Ticket creation failed: {str(e)}")
        return None


def generate_ticket_subject(description: str) -> str:
    """
    Generate ticket subject from description
    
    Args:
        description: Ticket description
        
    Returns:
        Generated subject
    """
    # Truncate description to create subject
    subject = description[:50] + "..." if len(description) > 50 else description
    
    # Clean up subject
    subject = subject.replace('\n', ' ').replace('\r', ' ')
    subject = ' '.join(subject.split())  # Remove extra whitespace
    
    return subject


def create_ticket_communication(ticket_doc, telegram_user, content: str, message_data=None):
    """Create communication record for the ticket"""
    try:
        communication_data = {
            "doctype": "HD Ticket Communication",
            "reference_name": ticket_doc.name,
            "reference_doctype": "HD Ticket",
            "content": content,
            "communication_type": "Comment",
            "sent_or_received": "Received",
            "communication_medium": "Telegram"
        }
        
        # Add user information
        if telegram_user:
            if hasattr(telegram_user, 'contact'):
                communication_data["contact"] = telegram_user.contact
            if hasattr(telegram_user, 'frappe_user'):
                communication_data["user"] = telegram_user.frappe_user
        
        # Add message metadata
        if message_data:
            communication_data["message_id"] = str(message_data.get("message_id", ""))
            communication_data["chat_id"] = str(message_data.get("chat", {}).get("id", ""))
        
        comm_doc = frappe.get_doc(communication_data)
        comm_doc.insert(ignore_permissions=True)
        
        return comm_doc
    
    except Exception as e:
        frappe.log_error(f"Communication creation failed: {str(e)}")
        return None


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