# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from frappe.utils import now_datetime, cstr
from typing import Dict, Any, List, Optional, Union


class BotResponseManager:
    """
    Manages bot responses, template rendering, and message formatting.
    Provides centralized response handling for Telegram bot interactions.
    """
    
    def __init__(self, bot_doc=None):
        """
        Initialize the response manager
        
        Args:
            bot_doc: HD Telegram Bot document instance
        """
        self.bot_doc = bot_doc
        self.template_cache = {}
        self.default_templates = {
            "welcome_message": "welcome_message",
            "help_message": "help_message", 
            "error_message": "error_message",
            "command_not_found": "command_not_found",
            "ticket_created": "ticket_created"
        }
    
    def render_template(self, template_key: str, context: Dict[str, Any], 
                       escape_content: bool = True) -> Dict[str, Any]:
        """
        Render a template with given context
        
        Args:
            template_key: Template key or name
            context: Context data for template rendering
            escape_content: Whether to escape content
            
        Returns:
            Dict containing rendered response
        """
        try:
            template_doc = self.get_template(template_key)
            
            if not template_doc:
                return self.create_fallback_response(template_key, context)
            
            # Render template
            result = template_doc.render(context, escape_content)
            
            # Add response metadata
            response = {
                "success": True,
                "message": result["content"],
                "response_type": "text",
                "parse_mode": result.get("parse_mode"),
                "disable_web_page_preview": result.get("disable_web_page_preview", False),
                "keyboard": result.get("keyboard"),
                "template_used": template_doc.template_name
            }
            
            return response
        
        except Exception as e:
            frappe.log_error(f"Template rendering failed for {template_key}: {str(e)}")
            return self.create_fallback_response(template_key, context, str(e))
    
    def get_template(self, template_key: str) -> Optional[Any]:
        """
        Get template document by key
        
        Args:
            template_key: Template key or name
            
        Returns:
            Template document or None
        """
        # Check cache first
        if template_key in self.template_cache:
            return self.template_cache[template_key]
        
        template_doc = None
        
        # Try to get bot-specific template first
        if self.bot_doc:
            template_name = self.get_bot_template_name(template_key)
            if template_name:
                try:
                    template_doc = frappe.get_doc("HD Bot Response Template", template_name)
                    if template_doc.is_active:
                        self.template_cache[template_key] = template_doc
                        return template_doc
                except frappe.DoesNotExistError:
                    pass
        
        # Try to get default template
        if not template_doc and (not self.bot_doc or self.bot_doc.use_default_templates):
            default_template_name = self.default_templates.get(template_key)
            if default_template_name:
                try:
                    template_doc = frappe.get_doc("HD Bot Response Template", default_template_name)
                    if template_doc.is_active:
                        self.template_cache[template_key] = template_doc
                        return template_doc
                except frappe.DoesNotExistError:
                    pass
        
        # Try template key as direct template name
        if not template_doc:
            try:
                template_doc = frappe.get_doc("HD Bot Response Template", template_key)
                if template_doc.is_active:
                    self.template_cache[template_key] = template_doc
                    return template_doc
            except frappe.DoesNotExistError:
                pass
        
        return template_doc
    
    def get_bot_template_name(self, template_key: str) -> Optional[str]:
        """
        Get bot-specific template name for a template key
        
        Args:
            template_key: Template key
            
        Returns:
            Template name or None
        """
        if not self.bot_doc:
            return None
        
        # Map template keys to bot fields
        template_mappings = {
            "welcome_message": self.bot_doc.welcome_template,
            "help_message": self.bot_doc.help_template,
            "error_message": self.bot_doc.error_template
        }
        
        return template_mappings.get(template_key)
    
    def process_command_response(self, command_result: Dict[str, Any], 
                               command_doc: Any, mapping: Any = None) -> Dict[str, Any]:
        """
        Process response from command execution
        
        Args:
            command_result: Result from command execution
            command_doc: Command document
            mapping: Bot command mapping (if any)
            
        Returns:
            Processed response
        """
        try:
            # If command result already has a formatted response, return it
            if isinstance(command_result, dict) and command_result.get("response_type"):
                return command_result
            
            # Check if there's a custom response override
            if mapping and mapping.custom_response_override:
                template_doc = frappe.get_doc("HD Bot Response Template", mapping.custom_response_override)
                if template_doc.is_active:
                    context = self.prepare_command_context(command_result, command_doc)
                    return template_doc.render(context)
            
            # Use command's default response templates
            if command_doc.response_templates:
                templates = json.loads(command_doc.response_templates) if isinstance(command_doc.response_templates, str) else command_doc.response_templates
                
                # Determine which template to use based on result
                template_key = "success" if command_result.get("success") else "error"
                template_content = templates.get(template_key)
                
                if template_content:
                    # Render inline template
                    context = self.prepare_command_context(command_result, command_doc)
                    rendered_content = self.render_inline_template(template_content, context)
                    
                    return {
                        "success": True,
                        "message": rendered_content,
                        "response_type": "text",
                        "parse_mode": command_doc.parse_mode,
                        "keyboard": command_doc.get_keyboard_layout()
                    }
            
            # Fallback to command result as-is
            return command_result
        
        except Exception as e:
            frappe.log_error(f"Command response processing failed: {str(e)}")
            return command_result
    
    def prepare_command_context(self, command_result: Dict[str, Any], command_doc: Any) -> Dict[str, Any]:
        """
        Prepare context for command response templates
        
        Args:
            command_result: Command execution result
            command_doc: Command document
            
        Returns:
            Context dictionary
        """
        context = {
            "command_name": command_doc.command_name,
            "command_display_name": command_doc.display_name,
            "bot_name": self.bot_doc.bot_name if self.bot_doc else "Bot",
            "company_name": self.bot_doc.company_name if self.bot_doc else "Company",
            "result": command_result,
            "timestamp": now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Add command result data to context
        if isinstance(command_result, dict):
            context.update(command_result)
        
        return context
    
    def render_inline_template(self, template_content: str, context: Dict[str, Any]) -> str:
        """
        Render inline template content with context
        
        Args:
            template_content: Template content string
            context: Context data
            
        Returns:
            Rendered content
        """
        try:
            # Simple variable replacement
            import re
            
            def replace_variable(match):
                var_name = match.group(1)
                return str(context.get(var_name, f"{{missing:{var_name}}}"))
            
            # Replace variables in {variable_name} format
            rendered = re.sub(r'\{([^}]+)\}', replace_variable, template_content)
            
            return rendered
        
        except Exception as e:
            frappe.log_error(f"Inline template rendering failed: {str(e)}")
            return template_content
    
    def create_fallback_response(self, template_key: str, context: Dict[str, Any], 
                                error_message: str = None) -> Dict[str, Any]:
        """
        Create fallback response when template is not available
        
        Args:
            template_key: Template key that failed
            context: Context data
            error_message: Error message (if any)
            
        Returns:
            Fallback response
        """
        fallback_messages = {
            "welcome_message": f"Welcome {context.get('user_name', 'there')}! Use /help to see available commands.",
            "help_message": "Here are the available commands:\n\n/help - Show this help\n/start - Get started",
            "error_message": f"An error occurred: {context.get('error_details', 'Unknown error')}",
            "command_not_found": f"Command '{context.get('command_name', 'unknown')}' not found. Use /help for available commands.",
            "ticket_created": f"Ticket created successfully! ID: {context.get('ticket_id', 'N/A')}"
        }
        
        message = fallback_messages.get(template_key, f"Response for {template_key}")
        
        if error_message:
            message += f"\n\nNote: Template error - {error_message}"
        
        return {
            "success": True,
            "message": message,
            "response_type": "text",
            "template_used": "fallback",
            "template_key": template_key
        }
    
    def format_commands_help(self, commands: List[Dict[str, Any]]) -> str:
        """
        Format commands list for help message
        
        Args:
            commands: List of command dictionaries
            
        Returns:
            Formatted commands string
        """
        if not commands:
            return "No commands available."
        
        formatted_commands = []
        
        # Group commands by category
        commands_by_category = {}
        for cmd in commands:
            category = cmd.get("category", "General")
            if category not in commands_by_category:
                commands_by_category[category] = []
            commands_by_category[category].append(cmd)
        
        # Format each category
        for category, category_commands in commands_by_category.items():
            if len(commands_by_category) > 1:
                formatted_commands.append(f"\n<b>{category}</b>:")
            
            for cmd in category_commands:
                icon = cmd.get("icon", "")
                command = cmd.get("command", "")
                description = cmd.get("description", "")
                
                line = f"{icon} {command}"
                if description:
                    line += f" - {description}"
                
                formatted_commands.append(line)
        
        return "\n".join(formatted_commands)
    
    def create_keyboard(self, buttons: List[List[Dict[str, Any]]], 
                       keyboard_type: str = "inline") -> Dict[str, Any]:
        """
        Create keyboard markup for bot responses
        
        Args:
            buttons: Button configuration
            keyboard_type: Type of keyboard (inline, reply, remove)
            
        Returns:
            Keyboard markup
        """
        try:
            if keyboard_type == "inline":
                return {"inline_keyboard": buttons}
            elif keyboard_type == "reply":
                return {"keyboard": buttons, "resize_keyboard": True}
            elif keyboard_type == "remove":
                return {"remove_keyboard": True}
            else:
                return {"inline_keyboard": buttons}
        
        except Exception as e:
            frappe.log_error(f"Keyboard creation failed: {str(e)}")
            return None
    
    def format_ticket_info(self, ticket_doc: Any) -> Dict[str, Any]:
        """
        Format ticket information for display
        
        Args:
            ticket_doc: Ticket document
            
        Returns:
            Formatted ticket information
        """
        try:
            return {
                "ticket_id": ticket_doc.name,
                "ticket_subject": ticket_doc.subject,
                "ticket_status": ticket_doc.status,
                "ticket_priority": ticket_doc.priority,
                "created_on": ticket_doc.creation.strftime("%Y-%m-%d %H:%M:%S"),
                "assigned_to": ticket_doc.assigned_to or "Unassigned"
            }
        
        except Exception as e:
            frappe.log_error(f"Ticket info formatting failed: {str(e)}")
            return {
                "ticket_id": "Unknown",
                "ticket_subject": "Unknown",
                "ticket_status": "Unknown",
                "ticket_priority": "Unknown",
                "created_on": "Unknown",
                "assigned_to": "Unknown"
            }
    
    def clear_template_cache(self):
        """Clear template cache"""
        self.template_cache.clear()
    
    def get_response_stats(self) -> Dict[str, Any]:
        """
        Get response manager statistics
        
        Returns:
            Statistics dictionary
        """
        return {
            "cached_templates": len(self.template_cache),
            "bot_name": self.bot_doc.bot_name if self.bot_doc else None,
            "default_templates": list(self.default_templates.keys())
        }


# Factory function for creating response manager instances
def create_response_manager(bot_name: str = None) -> BotResponseManager:
    """
    Create a response manager instance
    
    Args:
        bot_name: Name of the bot to create manager for
        
    Returns:
        BotResponseManager instance
    """
    bot_doc = None
    if bot_name:
        try:
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        except frappe.DoesNotExistError:
            frappe.throw(_("Bot '{0}' not found").format(bot_name))
    
    return BotResponseManager(bot_doc)


# Helper functions for template rendering
@frappe.whitelist()
def render_bot_template(bot_name: str, template_key: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Render a bot template with context
    
    Args:
        bot_name: Name of the bot
        template_key: Template key
        context: Context data
        
    Returns:
        Rendered response
    """
    response_manager = create_response_manager(bot_name)
    return response_manager.render_template(template_key, context)


@frappe.whitelist()
def format_help_message(bot_name: str, commands: List[Dict[str, Any]]) -> str:
    """
    Format help message for bot
    
    Args:
        bot_name: Name of the bot
        commands: List of commands
        
    Returns:
        Formatted help message
    """
    response_manager = create_response_manager(bot_name)
    return response_manager.format_commands_help(commands) 