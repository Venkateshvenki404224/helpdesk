# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
import re
from frappe import _
from frappe.utils import now_datetime, cstr
from typing import Dict, Any, List, Optional, Union
import importlib


class TelegramCommandProcessor:
    """
    Core command processor for Telegram bot interactions.
    Handles command routing, execution, and response generation.
    """
    
    def __init__(self, bot_doc=None):
        """
        Initialize the command processor
        
        Args:
            bot_doc: HD Telegram Bot document instance
        """
        self.bot_doc = bot_doc
        self.command_cache = {}
        self.response_manager = None
        
        # Load response manager if needed
        if bot_doc:
            from helpdesk.helpdesk.utils.bot_response_manager import BotResponseManager
            self.response_manager = BotResponseManager(bot_doc)
    
    def process_message(self, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming message and route to appropriate handler
        
        Args:
            message_data: Telegram message data
            user_data: User information
            
        Returns:
            Dict containing response data and execution results
        """
        try:
            message_text = message_data.get("text", "").strip()
            
            # Check if message is a command
            if self.is_command(message_text):
                return self.process_command(message_data, user_data)
            else:
                # Handle non-command messages
                return self.process_non_command_message(message_data, user_data)
        
        except Exception as e:
            frappe.log_error(f"Message processing failed: {str(e)}")
            return self.create_error_response(str(e))
    
    def is_command(self, message_text: str) -> bool:
        """Check if message text is a command"""
        return message_text.startswith("/") and len(message_text) > 1
    
    def process_command(self, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a command message
        
        Args:
            message_data: Telegram message data
            user_data: User information
            
        Returns:
            Dict containing command execution results
        """
        try:
            command_text = message_data.get("text", "").strip()
            command_name = self.extract_command_name(command_text) #e.g /start -> start
            command_args = self.extract_command_args(command_text) #e.g /start 123 -> 123
            
            # Get command configuration
            command_config = self.get_command_config(command_name)
            
            if not command_config:
                return self.handle_unknown_command(command_name, user_data)
            
            # Check permissions and access levels
            if not self.check_command_permissions(command_config, user_data):
                return self.create_permission_denied_response(command_name)
            
            # Execute command
            return self.execute_command(command_config, message_data, user_data, command_args)
        
        except Exception as e:
            frappe.log_error(f"Command processing failed: {str(e)}")
            return self.create_error_response(str(e))
    
    def extract_command_name(self, command_text: str) -> str:
        """Extract command name from message text"""
        # Handle commands like "/start@botname" or "/start"
        command_part = command_text.split()[0] if command_text else ""
        command_name = command_part.split("@")[0] if "@" in command_part else command_part
        return command_name.lower()
    
    def extract_command_args(self, command_text: str) -> List[str]:
        """Extract command arguments from message text"""
        parts = command_text.split()
        return parts[1:] if len(parts) > 1 else []
    
    def get_command_config(self, command_name: str) -> Optional[Dict[str, Any]]:
        """
        Get command configuration from bot mapping or global commands
        
        Args:
            command_name: Command name (e.g., "/start")
            
        Returns:
            Command configuration dict or None
        """
        # Check cache first
        if command_name in self.command_cache:
            return self.command_cache[command_name]
        
        command_config = None
        
        # First check bot-specific command mappings
        if self.bot_doc and self.bot_doc.command_mappings:
            for mapping in self.bot_doc.command_mappings:
                if mapping.is_active and mapping.command == command_name:
                    command_doc = frappe.get_doc("HD Telegram Command", mapping.command)
                    command_config = {
                        "command_doc": command_doc,
                        "mapping": mapping,
                        "is_global": False
                    }
                    break
        
        # If not found in bot mappings, check global commands
        if not command_config and (not self.bot_doc or self.bot_doc.enable_global_commands):
            try:
                command_doc = frappe.get_doc("HD Telegram Command", command_name)
                if command_doc.is_active and command_doc.is_global:
                    command_config = {
                        "command_doc": command_doc,
                        "mapping": None,
                        "is_global": True
                    }
            except frappe.DoesNotExistError:
                pass
        
        # Cache the result
        if command_config:
            self.command_cache[command_name] = command_config
        
        return command_config
    
    def check_command_permissions(self, command_config: Dict[str, Any], user_data: Dict[str, Any]) -> bool:
        """
        Check if user has permission to execute command
        
        Args:
            command_config: Command configuration
            user_data: User information
            
        Returns:
            True if user has permission, False otherwise
        """
        command_doc = command_config["command_doc"]
        mapping = command_config.get("mapping")
        
        # Get user access level (default to Public)
        user_access_level = user_data.get("access_level", "Public")
        
        # Use mapping access level override if available
        required_access_level = None
        if mapping and mapping.access_level:
            required_access_level = mapping.access_level
        else:
            required_access_level = command_doc.access_level
        
        # Check access level
        if not self.check_access_level(user_access_level, required_access_level):
            return False
        
        # Check role-based permissions
        user_roles = user_data.get("roles", [])
        if not command_doc.check_permissions(user_roles):
            return False
        
        return True
    
    def check_access_level(self, user_level: str, required_level: str) -> bool:
        """Check if user meets minimum access level requirement"""
        access_levels = {
            "Public": 0,
            "Verified": 1,
            "Registered": 2,
            "Admin": 3
        }
        
        user_level_value = access_levels.get(user_level, 0)
        required_level_value = access_levels.get(required_level, 0)
        
        return user_level_value >= required_level_value
    
    def execute_command(self, command_config: Dict[str, Any], message_data: Dict[str, Any], 
                       user_data: Dict[str, Any], command_args: List[str]) -> Dict[str, Any]:
        """
        Execute a command with the given configuration
        
        Args:
            command_config: Command configuration
            message_data: Telegram message data
            user_data: User information
            command_args: Command arguments
            
        Returns:
            Dict containing execution results
        """
        try:
            command_doc = command_config["command_doc"]
            mapping = command_config.get("mapping")
            
            # Load command function
            function = self.load_command_function(command_doc)
            
            # Prepare function parameters
            params = {
                "user_data": user_data,
                "message_data": message_data,
                "bot_doc": self.bot_doc,
                "command_doc": command_doc,
                "command_args": command_args,
                "mapping": mapping
            }
            
            # Execute function
            result = function(params)
            
            # Process response through response manager
            if self.response_manager and isinstance(result, dict):
                return self.response_manager.process_command_response(result, command_doc, mapping)
            
            return result
        
        except Exception as e:
            frappe.log_error(f"Command execution failed for {command_doc.command_name}: {str(e)}")
            return self.create_error_response(str(e))
    
    def load_command_function(self, command_doc):
        """Load and return the command function"""
        try:
            function_path = command_doc.function_path
            module_path, function_name = function_path.rsplit('.', 1)
            
            # Import module
            module = importlib.import_module(module_path)
            
            # Get function
            function = getattr(module, function_name)
            
            return function
        
        except Exception as e:
            frappe.throw(_("Failed to load command function: {0}").format(str(e)))
    
    def handle_unknown_command(self, command_name: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle unknown or unavailable commands"""
        # Get available commands for help
        available_commands = self.get_available_commands(user_data)
        
        if self.response_manager:
            return self.response_manager.render_template(
                "command_not_found",
                {
                    "command_name": command_name,
                    "available_commands": self.format_commands_list(available_commands)
                }
            )
        
        # Fallback response
        return {
            "success": False,
            "message": f"Unknown command: {command_name}. Use /help to see available commands.",
            "response_type": "text"
        }
    
    def process_non_command_message(self, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process non-command messages (regular text, files, etc.)
        
        Args:
            message_data: Telegram message data
            user_data: User information
            
        Returns:
            Dict containing processing results
        """
        try:
            # For first-time users, show welcome message
            if self.is_first_time_user(user_data):
                return self.handle_welcome_message(user_data)
            
            # Default handling - suggest ticket creation
            return self.handle_default_message(message_data, user_data)
        
        except Exception as e:
            frappe.log_error(f"Non-command message processing failed: {str(e)}")
            return self.create_error_response(str(e))
    
    def is_first_time_user(self, user_data: Dict[str, Any]) -> bool:
        """Check if this is the user's first interaction"""
        telegram_user_id = user_data.get("id")
        if not telegram_user_id:
            return True
        
        # Check if user exists in database
        existing_user = frappe.db.exists("HD Telegram User", {"telegram_user_id": telegram_user_id})
        return not existing_user
    
    def handle_welcome_message(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle welcome message for first-time users"""
        if self.response_manager:
            # Get available commands
            available_commands = self.get_available_commands(user_data)
            
            context = {
                "user_name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip() or "there",
                "bot_name": self.bot_doc.bot_name if self.bot_doc else "Support Bot",
                "available_commands": self.format_commands_list(available_commands)
            }
            
            return self.response_manager.render_template("welcome_message", context)
        
        # Fallback response
        return {
            "success": True,
            "message": f"Welcome {user_data.get('first_name', 'there')}! Send /help to see available commands.",
            "response_type": "text"
        }
    
    def handle_default_message(self, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle default message processing"""
        return {
            "success": True,
            "message": "I received your message. Use /ticket to create a support ticket or /help for available commands.",
            "response_type": "text"
        }
    
    def get_available_commands(self, user_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get list of available commands for user"""
        commands = []
        
        # Get bot-specific commands
        if self.bot_doc and self.bot_doc.command_mappings:
            for mapping in self.bot_doc.command_mappings:
                if mapping.is_active:
                    try:
                        command_doc = frappe.get_doc("HD Telegram Command", mapping.command)
                        if self.check_command_permissions({"command_doc": command_doc, "mapping": mapping}, user_data):
                            commands.append({
                                "command": command_doc.command_name,
                                "description": command_doc.description,
                                "icon": command_doc.icon or "",
                                "sort_order": mapping.sort_order or command_doc.sort_order
                            })
                    except frappe.DoesNotExistError:
                        continue
        
        # Get global commands if enabled
        if not self.bot_doc or self.bot_doc.enable_global_commands:
            global_commands = frappe.get_all(
                "HD Telegram Command",
                filters={"is_active": 1, "is_global": 1},
                fields=["command_name", "description", "icon", "sort_order"]
            )
            
            for cmd in global_commands:
                try:
                    command_doc = frappe.get_doc("HD Telegram Command", cmd.command_name)
                    if self.check_command_permissions({"command_doc": command_doc, "mapping": None}, user_data):
                        commands.append({
                            "command": cmd.command_name,
                            "description": cmd.description,
                            "icon": cmd.icon or "",
                            "sort_order": cmd.sort_order
                        })
                except frappe.DoesNotExistError:
                    continue
        
        # Sort commands by sort_order
        commands.sort(key=lambda x: x.get("sort_order", 10))
        
        return commands
    
    def format_commands_list(self, commands: List[Dict[str, Any]]) -> str:
        """Format commands list for display"""
        formatted = []
        
        for cmd in commands:
            icon = cmd.get("icon", "")
            command = cmd.get("command", "")
            description = cmd.get("description", "")
            
            formatted.append(f"{icon} {command} - {description}")
        
        return "\n".join(formatted)
    
    def create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        if self.response_manager:
            return self.response_manager.render_template(
                "error_message",
                {"error_details": error_message}
            )
        
        return {
            "success": False,
            "message": f"Error: {error_message}",
            "response_type": "text"
        }
    
    def create_permission_denied_response(self, command_name: str) -> Dict[str, Any]:
        """Create permission denied response"""
        return {
            "success": False,
            "message": f"You don't have permission to use the {command_name} command.",
            "response_type": "text"
        }
    
    def clear_command_cache(self):
        """Clear command configuration cache"""
        self.command_cache.clear()


# Factory function for creating command processor instances
def create_command_processor(bot_name: str = None) -> TelegramCommandProcessor:
    """
    Create a command processor instance
    
    Args:
        bot_name: Name of the bot to create processor for
        
    Returns:
        TelegramCommandProcessor instance
    """
    bot_doc = None
    if bot_name:
        try:
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        except frappe.DoesNotExistError:
            frappe.throw(_("Bot '{0}' not found").format(bot_name))
    
    return TelegramCommandProcessor(bot_doc)


# Helper function for processing messages
@frappe.whitelist()
def process_telegram_message(bot_name: str, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a Telegram message using the command processor
    
    Args:
        bot_name: Name of the bot
        message_data: Telegram message data
        user_data: User information
        
    Returns:
        Processing results
    """
    processor = create_command_processor(bot_name)
    return processor.process_message(message_data, user_data) 