# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime
from typing import Dict, Any


def handle_help(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle /help command - Show available commands and their usage
    
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
        bot_doc = params.get("bot_doc")
        command_args = params.get("command_args", [])
        
        # Check if user wants help for a specific command
        if command_args:
            return handle_specific_command_help(command_args[0], user_data, bot_doc)
        
        # Get available commands for this user
        available_commands = get_user_available_commands(user_data, bot_doc)
        
        # Group commands by category
        categorized_commands = group_commands_by_category(available_commands)
        
        # Prepare context for help template
        context = {
            "user_name": user_data.get("first_name", "there"),
            "bot_name": bot_doc.bot_name if bot_doc else "Support Bot",
            "company_name": bot_doc.company_name if bot_doc else "Our Company",
            "commands_list": format_categorized_commands(categorized_commands),
            "total_commands": len(available_commands),
            "categories": list(categorized_commands.keys()),
            "timestamp": now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Try to use bot's help template first
        if bot_doc and bot_doc.help_template:
            try:
                template_doc = frappe.get_doc("HD Bot Response Template", bot_doc.help_template)
                if template_doc.is_active:
                    result = template_doc.render(context)
                    return create_success_response(
                        message=result["content"],
                        parse_mode=result.get("parse_mode"),
                        keyboard=result.get("keyboard")
                    )
            except frappe.DoesNotExistError:
                pass
        
        # Use default help template
        try:
            default_template = frappe.get_doc("HD Bot Response Template", "help_message")
            if default_template.is_active:
                result = default_template.render(context)
                return create_success_response(
                    message=result["content"],
                    parse_mode=result.get("parse_mode"),
                    keyboard=result.get("keyboard")
                )
        except frappe.DoesNotExistError:
            pass
        
        # Fallback help message
        help_message = f"""📋 <b>Available Commands for {context['bot_name']}:</b>

{context['commands_list']}

💡 <i>Tip: You can also just describe your problem and I'll help you create a support ticket!</i>

Use <code>/help [command]</code> for detailed help on a specific command."""
        
        return create_success_response(
            message=help_message,
            parse_mode="HTML"
        )
    
    except Exception as e:
        frappe.log_error(f"Help command failed: {str(e)}")
        return create_error_response(f"Help command failed: {str(e)}")


def handle_specific_command_help(command_name: str, user_data: Dict[str, Any], bot_doc=None) -> Dict[str, Any]:
    """
    Handle help for a specific command
    
    Args:
        command_name: Name of the command to get help for
        user_data: User data
        bot_doc: Bot document
        
    Returns:
        Dict containing response data
    """
    try:
        # Ensure command starts with /
        if not command_name.startswith('/'):
            command_name = '/' + command_name
        
        # Get command information
        try:
            command_doc = frappe.get_doc("HD Telegram Command", command_name)
        except frappe.DoesNotExistError:
            return create_error_response(f"Command '{command_name}' not found.")
        
        # Check if user has access to this command
        processor = get_command_processor(bot_doc)
        if processor:
            command_config = processor.get_command_config(command_name)
            if not command_config or not processor.check_command_permissions(command_config, user_data):
                return create_error_response(f"You don't have access to the '{command_name}' command.")
        
        # Format command help
        help_text = f"""📖 <b>Help for {command_name}</b>

<b>Description:</b> {command_doc.description}

<b>Category:</b> {command_doc.category}
<b>Type:</b> {command_doc.command_type}"""
        
        if command_doc.help_text:
            help_text += f"\n\n<b>Usage:</b> {command_doc.help_text}"
        
        if command_doc.parameters_schema:
            try:
                import json
                schema = json.loads(command_doc.parameters_schema) if isinstance(command_doc.parameters_schema, str) else command_doc.parameters_schema
                if schema and 'parameters' in schema:
                    help_text += "\n\n<b>Parameters:</b>"
                    for param in schema['parameters']:
                        help_text += f"\n• {param.get('name', 'unknown')}: {param.get('description', 'No description')}"
            except:
                pass
        
        return create_success_response(
            message=help_text,
            parse_mode="HTML"
        )
    
    except Exception as e:
        frappe.log_error(f"Specific command help failed: {str(e)}")
        return create_error_response(f"Failed to get help for '{command_name}': {str(e)}")


def get_user_available_commands(user_data: Dict[str, Any], bot_doc=None) -> list:
    """Get available commands for user"""
    try:
        processor = get_command_processor(bot_doc)
        if processor:
            return processor.get_available_commands(user_data)
    except Exception as e:
        frappe.log_error(f"Failed to get available commands: {str(e)}")
    
    # Return basic commands as fallback
    return [
        {"command": "/start", "description": "Get started with the bot", "icon": "🚀", "category": "General"},
        {"command": "/help", "description": "Show this help message", "icon": "❓", "category": "General"},
        {"command": "/ticket", "description": "Create a support ticket", "icon": "🎫", "category": "Support"},
        {"command": "/status", "description": "Check ticket status", "icon": "📋", "category": "Support"}
    ]


def get_command_processor(bot_doc=None):
    """Get command processor instance"""
    try:
        from helpdesk.helpdesk.utils.telegram_command_processor import create_command_processor
        return create_command_processor(bot_doc.bot_name if bot_doc else None)
    except Exception as e:
        frappe.log_error(f"Failed to create command processor: {str(e)}")
        return None


def group_commands_by_category(commands: list) -> Dict[str, list]:
    """
    Group commands by category
    
    Args:
        commands: List of command dictionaries
        
    Returns:
        Dict with categories as keys and command lists as values
    """
    categorized = {}
    
    for cmd in commands:
        category = cmd.get("category", "General")
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(cmd)
    
    # Sort commands within each category by sort_order
    for category in categorized:
        categorized[category].sort(key=lambda x: x.get("sort_order", 10))
    
    return categorized


def format_categorized_commands(categorized_commands: Dict[str, list]) -> str:
    """
    Format categorized commands for display
    
    Args:
        categorized_commands: Dict of categorized commands
        
    Returns:
        Formatted commands string
    """
    if not categorized_commands:
        return "No commands available."
    
    formatted = []
    
    # Sort categories
    sorted_categories = sorted(categorized_commands.keys())
    
    for category in sorted_categories:
        commands = categorized_commands[category]
        
        # Add category header if more than one category
        if len(categorized_commands) > 1:
            formatted.append(f"\n<b>{category}:</b>")
        
        # Add commands in this category
        for cmd in commands:
            icon = cmd.get("icon", "")
            command = cmd.get("command", "")
            description = cmd.get("description", "")
            
            line = f"{icon} <code>{command}</code>"
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