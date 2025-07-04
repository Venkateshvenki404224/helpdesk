# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime
from typing import Dict, Any


def handle_start(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /start command - Initialize bot interaction and show welcome message
    
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
        command_doc = params.get("command_doc")
        
        # Create or update telegram user record
        telegram_user = create_or_update_telegram_user(user_data, bot_doc)
        
        # Get available commands for this user
        available_commands = get_user_available_commands(user_data, bot_doc)
        
        # Prepare context for welcome template
        context = {
            "user_name": user_data.get("first_name", "there"),
            "user_username": user_data.get("username", ""),
            "bot_name": bot_doc.bot_name if bot_doc else "Support Bot",
            "company_name": bot_doc.company_name if bot_doc else "Our Company",
            "available_commands": format_commands_for_display(available_commands),
            "commands_count": len(available_commands),
            "timestamp": now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Try to use bot's welcome template first
        if bot_doc and bot_doc.welcome_template:
            try:
                template_doc = frappe.get_doc("HD Bot Response Template", bot_doc.welcome_template)
                if template_doc.is_active:
                    result = template_doc.render(context)
                    return create_success_response(
                        message=result["content"],
                        parse_mode=result.get("parse_mode"),
                        keyboard=result.get("keyboard")
                    )
            except frappe.DoesNotExistError:
                pass
        
        # Use default welcome template
        try:
            default_template = frappe.get_doc("HD Bot Response Template", "welcome_message")
            if default_template.is_active:
                result = default_template.render(context)
                return create_success_response(
                    message=result["content"],
                    parse_mode=result.get("parse_mode"),
                    keyboard=result.get("keyboard")
                )
        except frappe.DoesNotExistError:
            pass
        
        # Fallback welcome message
        welcome_message = f"""👋 Hello {context['user_name']}! Welcome to {context['bot_name']}.

I'm here to help you with support requests. Here are the available commands:

{context['available_commands']}

Just type a command or describe your issue to get started! 🚀"""
        
        return create_success_response(
            message=welcome_message,
            parse_mode="HTML"
        )
    
    except Exception as e:
        frappe.log_error(f"Start command failed: {str(e)}")
        return create_error_response(f"Welcome message failed: {str(e)}")


def create_or_update_telegram_user(user_data: Dict[str, Any], bot_doc=None) -> Any:
    """
    Create or update telegram user record
    
    Args:
        user_data: Telegram user data
        bot_doc: Bot document
        
    Returns:
        HD Telegram User document
    """
    from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
    
    telegram_user = get_or_create_telegram_user(
        telegram_user_id=user_data.get("id"),
        user_data=user_data
    )
    
    # Update user's last interaction
    telegram_user.update_last_contact()
    
    return telegram_user


def get_user_available_commands(user_data: Dict[str, Any], bot_doc=None) -> list:
    """
    Get available commands for user
    
    Args:
        user_data: User data
        bot_doc: Bot document
        
    Returns:
        List of available commands
    """
    try:
        from helpdesk.helpdesk.utils.telegram_command_processor import create_command_processor
        
        processor = create_command_processor(bot_doc.bot_name if bot_doc else None)
        return processor.get_available_commands(user_data)
    
    except Exception as e:
        frappe.log_error(f"Failed to get available commands: {str(e)}")
        # Return basic commands as fallback
        return [
            {"command": "/help", "description": "Show available commands", "icon": "❓"},
            {"command": "/ticket", "description": "Create a support ticket", "icon": "🎫"},
            {"command": "/status", "description": "Check ticket status", "icon": "📋"}
        ]


def format_commands_for_display(commands: list) -> str:
    """
    Format commands list for display
    
    Args:
        commands: List of command dictionaries
        
    Returns:
        Formatted commands string
    """
    if not commands:
        return "No commands available."
    
    formatted = []
    for cmd in commands:
        icon = cmd.get("icon", "")
        command = cmd.get("command", "")
        description = cmd.get("description", "")
        
        line = f"{icon} <b>{command}</b>"
        if description:
            line += f" - {description}"
        
        formatted.append(line)
    
    return "\n".join(formatted)


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