# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from frappe.utils import now_datetime, cstr
from typing import Dict, Any, Optional, List
from datetime import datetime


class WelcomeMessageHandler:
    """
    Handles welcome messages for first-time users with configurable templates.
    Integrates with BotResponseManager for template rendering and user management.
    """
    
    def __init__(self, bot_doc=None):
        """
        Initialize the welcome message handler
        
        Args:
            bot_doc: HD Telegram Bot document instance
        """
        self.bot_doc = bot_doc
        self.response_manager = None
        
        # Initialize response manager if bot document is provided
        if bot_doc:
            from helpdesk.helpdesk.utils.bot_response_manager import BotResponseManager
            self.response_manager = BotResponseManager(bot_doc)
    
    def handle_welcome_message(self, user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Handle welcome message for users
        
        Args:
            user_data: Telegram user information
            message_data: Telegram message data (optional)
            
        Returns:
            Dict containing response data
        """
        try:
            # Check if user is new or returning
            is_new_user = self.is_first_time_user(user_data)
            
            # Create or update user record
            telegram_user = self.create_or_update_user(user_data, is_new_user)
            
            # Generate welcome response
            if is_new_user:
                response = self.generate_new_user_welcome(user_data, telegram_user)
            else:
                response = self.generate_returning_user_welcome(user_data, telegram_user)
            
            # Update user statistics
            if telegram_user:
                self.update_user_welcome_stats(telegram_user, is_new_user)
            
            return response
            
        except Exception as e:
            frappe.log_error(f"Welcome message handler error: {str(e)}")
            return self.generate_fallback_welcome(user_data)
    
    def is_first_time_user(self, user_data: Dict[str, Any]) -> bool:
        """
        Check if this is the user's first interaction with the bot
        
        Args:
            user_data: Telegram user information
            
        Returns:
            True if first-time user, False otherwise
        """
        try:
            telegram_user_id = cstr(user_data.get("id"))
            if not telegram_user_id:
                return True
            
            # Check if user exists in database
            existing_user = frappe.db.exists("HD Telegram User", {"telegram_user_id": telegram_user_id})
            
            if not existing_user:
                return True
            
            # Check if user has been welcomed before
            user_doc = frappe.get_doc("HD Telegram User", {"telegram_user_id": telegram_user_id})
            
            # If user has no first_contact timestamp, they're new
            if not user_doc.first_contact:
                return True
            
            # If user has never sent a message, they're new
            if not user_doc.total_messages_sent:
                return True
            
            return False
            
        except Exception as e:
            frappe.log_error(f"Error checking first-time user: {str(e)}")
            return True  # Default to treating as new user
    
    def create_or_update_user(self, user_data: Dict[str, Any], is_new_user: bool) -> Optional[object]:
        """
        Create new user or update existing user record
        
        Args:
            user_data: Telegram user information
            is_new_user: Whether this is a new user
            
        Returns:
            HD Telegram User document or None
        """
        try:
            from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
            
            # Create or update user
            telegram_user = get_or_create_telegram_user(user_data)
            
            # Set welcome timestamp for new users
            if is_new_user and telegram_user:
                telegram_user.db_set('first_contact', now_datetime())
                telegram_user.db_set('last_contact', now_datetime())
            elif telegram_user:
                telegram_user.db_set('last_contact', now_datetime())
            
            return telegram_user
            
        except Exception as e:
            frappe.log_error(f"Error creating/updating user: {str(e)}")
            return None
    
    def generate_new_user_welcome(self, user_data: Dict[str, Any], telegram_user: Optional[object] = None) -> Dict[str, Any]:
        """
        Generate welcome message for new users
        
        Args:
            user_data: Telegram user information
            telegram_user: HD Telegram User document
            
        Returns:
            Dict containing response data
        """
        try:
            # Prepare context for welcome template
            context = self.prepare_welcome_context(user_data, telegram_user, is_new_user=True)
            
            # Try to use bot's custom welcome template
            if self.bot_doc and self.bot_doc.welcome_template:
                template_response = self.render_custom_welcome_template(context)
                if template_response:
                    return template_response
            
            # Try to use default welcome template
            if self.response_manager:
                template_response = self.response_manager.render_template("welcome_message", context)
                if template_response.get("success"):
                    return {
                        "success": True,
                        "response_message": template_response.get("content"),
                        "parse_mode": template_response.get("parse_mode", "Markdown"),
                        "keyboard": template_response.get("keyboard"),
                        "welcome_sent": True,
                        "is_new_user": True
                    }
            
            # Fallback to hardcoded welcome message
            return self.generate_fallback_new_user_welcome(user_data, context)
            
        except Exception as e:
            frappe.log_error(f"Error generating new user welcome: {str(e)}")
            return self.generate_fallback_welcome(user_data)
    
    def generate_returning_user_welcome(self, user_data: Dict[str, Any], telegram_user: Optional[object] = None) -> Dict[str, Any]:
        """
        Generate welcome message for returning users
        
        Args:
            user_data: Telegram user information
            telegram_user: HD Telegram User document
            
        Returns:
            Dict containing response data
        """
        try:
            # Prepare context for welcome template
            context = self.prepare_welcome_context(user_data, telegram_user, is_new_user=False)
            
            # Try to use bot's custom welcome template for returning users
            if self.bot_doc and hasattr(self.bot_doc, 'returning_user_template') and self.bot_doc.returning_user_template:
                template_response = self.render_custom_template(self.bot_doc.returning_user_template, context)
                if template_response:
                    return template_response
            
            # Use default welcome template with returning user context
            if self.response_manager:
                template_response = self.response_manager.render_template("welcome_message", context)
                if template_response.get("success"):
                    return {
                        "success": True,
                        "response_message": template_response.get("content"),
                        "parse_mode": template_response.get("parse_mode", "Markdown"),
                        "keyboard": template_response.get("keyboard"),
                        "welcome_sent": True,
                        "is_new_user": False
                    }
            
            # Fallback to hardcoded returning user welcome
            return self.generate_fallback_returning_user_welcome(user_data, context)
            
        except Exception as e:
            frappe.log_error(f"Error generating returning user welcome: {str(e)}")
            return self.generate_fallback_welcome(user_data)
    
    def prepare_welcome_context(self, user_data: Dict[str, Any], telegram_user: Optional[object] = None, is_new_user: bool = True) -> Dict[str, Any]:
        """
        Prepare context data for welcome template rendering
        
        Args:
            user_data: Telegram user information
            telegram_user: HD Telegram User document
            is_new_user: Whether this is a new user
            
        Returns:
            Dict containing template context
        """
        try:
            # Get available commands for this user
            available_commands = self.get_user_available_commands(user_data)
            
            # Get user statistics
            user_stats = self.get_user_statistics(telegram_user) if telegram_user else {}
            
            # Prepare context
            context = {
                # User information
                "user_name": user_data.get("first_name", "there"),
                "user_username": user_data.get("username", ""),
                "user_language": user_data.get("language_code", "en"),
                "is_new_user": is_new_user,
                
                # Bot information
                "bot_name": self.bot_doc.bot_name if self.bot_doc else "Support Bot",
                "company_name": self.bot_doc.company_name if self.bot_doc else "Our Company",
                
                # Commands
                "available_commands": self.format_commands_list(available_commands),
                "commands_count": len(available_commands),
                "primary_commands": self.get_primary_commands(available_commands),
                
                # Statistics
                "total_messages": user_stats.get("total_messages", 0),
                "total_tickets": user_stats.get("total_tickets", 0),
                "last_contact": user_stats.get("last_contact"),
                
                # Timestamps
                "current_date": now_datetime().strftime("%Y-%m-%d"),
                "current_time": now_datetime().strftime("%H:%M:%S"),
                "timestamp": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
                
                # Settings
                "enable_help": True,
                "enable_tickets": True,
                "enable_status": True,
                "show_quick_actions": True
            }
            
            return context
            
        except Exception as e:
            frappe.log_error(f"Error preparing welcome context: {str(e)}")
            return {
                "user_name": user_data.get("first_name", "there"),
                "bot_name": "Support Bot",
                "is_new_user": is_new_user
            }
    
    def render_custom_welcome_template(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Render custom welcome template configured in bot settings
        
        Args:
            context: Template context data
            
        Returns:
            Dict containing rendered response or None
        """
        try:
            if not self.bot_doc or not self.bot_doc.welcome_template:
                return None
            
            # Get template document
            template_doc = frappe.get_doc("HD Bot Response Template", self.bot_doc.welcome_template)
            
            if not template_doc.is_active:
                return None
            
            # Render template
            result = template_doc.render(context)
            
            if result.get("success"):
                return {
                    "success": True,
                    "response_message": result.get("content"),
                    "parse_mode": result.get("parse_mode", "Markdown"),
                    "keyboard": result.get("keyboard"),
                    "welcome_sent": True,
                    "template_used": self.bot_doc.welcome_template
                }
            
            return None
            
        except Exception as e:
            frappe.log_error(f"Error rendering custom welcome template: {str(e)}")
            return None
    
    def render_custom_template(self, template_name: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Render a custom template by name
        
        Args:
            template_name: Name of the template
            context: Template context data
            
        Returns:
            Dict containing rendered response or None
        """
        try:
            template_doc = frappe.get_doc("HD Bot Response Template", template_name)
            
            if not template_doc.is_active:
                return None
            
            result = template_doc.render(context)
            
            if result.get("success"):
                return {
                    "success": True,
                    "response_message": result.get("content"),
                    "parse_mode": result.get("parse_mode", "Markdown"),
                    "keyboard": result.get("keyboard"),
                    "welcome_sent": True,
                    "template_used": template_name
                }
            
            return None
            
        except Exception as e:
            frappe.log_error(f"Error rendering custom template {template_name}: {str(e)}")
            return None
    
    def get_user_available_commands(self, user_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get available commands for the user based on their permissions
        
        Args:
            user_data: Telegram user information
            
        Returns:
            List of available commands
        """
        try:
            if not self.bot_doc:
                return self.get_default_commands()
            
            # Get commands mapped to this bot
            bot_commands = frappe.get_all(
                "HD Bot Command Mapping",
                filters={"parent": self.bot_doc.name, "is_active": 1},
                fields=["command", "custom_display_name", "custom_description", "access_level", "sort_order"],
                order_by="sort_order ASC"
            )
            
            # Filter commands based on user access level
            user_access_level = self.get_user_access_level(user_data)
            available_commands = []
            
            for mapping in bot_commands:
                command_doc = frappe.get_doc("HD Telegram Command", mapping.command)
                
                # Check if user has access to this command
                if self.check_command_access(command_doc, user_access_level):
                    available_commands.append({
                        "command": command_doc.command_name,
                        "display_name": mapping.custom_display_name or command_doc.display_name,
                        "description": mapping.custom_description or command_doc.description,
                        "icon": command_doc.icon,
                        "category": command_doc.category,
                        "help_text": command_doc.help_text,
                        "sort_order": mapping.sort_order
                    })
            
            return available_commands
            
        except Exception as e:
            frappe.log_error(f"Error getting user available commands: {str(e)}")
            return self.get_default_commands()
    
    def get_default_commands(self) -> List[Dict[str, Any]]:
        """
        Get default commands when bot configuration is not available
        
        Returns:
            List of default commands
        """
        return [
            {
                "command": "/start",
                "display_name": "Start",
                "description": "Get started with the bot",
                "icon": "🚀",
                "category": "General",
                "help_text": "Initialize bot interaction",
                "sort_order": 1
            },
            {
                "command": "/help",
                "display_name": "Help",
                "description": "Show available commands",
                "icon": "❓",
                "category": "General",
                "help_text": "Get help with bot commands",
                "sort_order": 2
            },
            {
                "command": "/ticket",
                "display_name": "New Ticket",
                "description": "Create a support ticket",
                "icon": "🎫",
                "category": "Support",
                "help_text": "Create a new support ticket",
                "sort_order": 3
            },
            {
                "command": "/status",
                "display_name": "Status",
                "description": "Check ticket status",
                "icon": "📋",
                "category": "Support",
                "help_text": "Check your ticket status",
                "sort_order": 4
            }
        ]
    
    def get_user_access_level(self, user_data: Dict[str, Any]) -> str:
        """
        Get user access level based on their permissions
        
        Args:
            user_data: Telegram user information
            
        Returns:
            User access level string
        """
        try:
            # Default access level
            return "Public"
            
        except Exception:
            return "Public"
    
    def check_command_access(self, command_doc: object, user_access_level: str) -> bool:
        """
        Check if user has access to a command
        
        Args:
            command_doc: HD Telegram Command document
            user_access_level: User's access level
            
        Returns:
            True if user has access, False otherwise
        """
        try:
            # If command has no access restrictions, allow all
            if not command_doc.access_level or command_doc.access_level == "Public":
                return True
            
            # Check access level hierarchy
            access_hierarchy = ["Public", "Registered", "Premium", "Admin"]
            
            user_level_index = access_hierarchy.index(user_access_level) if user_access_level in access_hierarchy else 0
            command_level_index = access_hierarchy.index(command_doc.access_level) if command_doc.access_level in access_hierarchy else 0
            
            return user_level_index >= command_level_index
            
        except Exception:
            return True  # Default to allowing access
    
    def format_commands_list(self, commands: List[Dict[str, Any]]) -> str:
        """
        Format commands list for display in welcome message
        
        Args:
            commands: List of command dictionaries
            
        Returns:
            Formatted commands string
        """
        try:
            if not commands:
                return "No commands available"
            
            # Group commands by category
            categories = {}
            for cmd in commands:
                category = cmd.get("category", "General")
                if category not in categories:
                    categories[category] = []
                categories[category].append(cmd)
            
            # Format each category
            formatted_sections = []
            for category, category_commands in categories.items():
                section = f"**{category}:**\n"
                for cmd in category_commands:
                    icon = cmd.get("icon", "•")
                    command = cmd.get("command", "")
                    description = cmd.get("description", "")
                    section += f"{icon} {command} - {description}\n"
                formatted_sections.append(section)
            
            return "\n".join(formatted_sections)
            
        except Exception as e:
            frappe.log_error(f"Error formatting commands list: {str(e)}")
            return "Use /help to see available commands"
    
    def get_primary_commands(self, commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Get primary commands for quick access
        
        Args:
            commands: List of all commands
            
        Returns:
            List of primary commands
        """
        try:
            # Get top 4 commands by sort order
            sorted_commands = sorted(commands, key=lambda x: x.get("sort_order", 999))
            return sorted_commands[:4]
            
        except Exception:
            return commands[:4] if commands else []
    
    def get_user_statistics(self, telegram_user: Optional[object]) -> Dict[str, Any]:
        """
        Get user statistics for welcome message
        
        Args:
            telegram_user: HD Telegram User document
            
        Returns:
            Dict containing user statistics
        """
        try:
            if not telegram_user:
                return {}
            
            return {
                "total_messages": telegram_user.total_messages_sent or 0,
                "total_tickets": telegram_user.total_tickets_created or 0,
                "last_contact": telegram_user.last_contact,
                "first_contact": telegram_user.first_contact,
                "is_blocked": telegram_user.is_blocked,
                "is_premium": telegram_user.is_premium
            }
            
        except Exception as e:
            frappe.log_error(f"Error getting user statistics: {str(e)}")
            return {}
    
    def update_user_welcome_stats(self, telegram_user: object, is_new_user: bool) -> None:
        """
        Update user statistics after sending welcome message
        
        Args:
            telegram_user: HD Telegram User document
            is_new_user: Whether this is a new user
        """
        try:
            if not telegram_user:
                return
            
            # Update last contact
            telegram_user.db_set('last_contact', now_datetime())
            
            # For new users, set first contact
            if is_new_user:
                telegram_user.db_set('first_contact', now_datetime())
            
            # Increment welcome message count if field exists
            if hasattr(telegram_user, 'welcome_messages_sent'):
                telegram_user.db_set('welcome_messages_sent', (telegram_user.welcome_messages_sent or 0) + 1)
                
        except Exception as e:
            frappe.log_error(f"Error updating user welcome stats: {str(e)}")
    
    def generate_fallback_new_user_welcome(self, user_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate fallback welcome message for new users
        
        Args:
            user_data: Telegram user information
            context: Template context
            
        Returns:
            Dict containing fallback response
        """
        user_name = user_data.get("first_name", "there")
        bot_name = context.get("bot_name", "Support Bot")
        
        message = f"""🎉 Welcome to {bot_name}, {user_name}!

I'm here to help you with your support needs. As a new user, here's what I can do:

🆘 **Support Commands:**
/help - Show all available commands
/ticket - Create a new support ticket
/status - Check your ticket status

💡 **Quick Tips:**
• Type /help to see detailed command information
• Use /ticket to create a support request
• All conversations are secure and confidential

Ready to get started? Type /help to see all available options! 🚀"""
        
        return {
            "success": True,
            "response_message": message,
            "parse_mode": "Markdown",
            "welcome_sent": True,
            "is_new_user": True,
            "fallback_used": True
        }
    
    def generate_fallback_returning_user_welcome(self, user_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate fallback welcome message for returning users
        
        Args:
            user_data: Telegram user information
            context: Template context
            
        Returns:
            Dict containing fallback response
        """
        user_name = user_data.get("first_name", "there")
        bot_name = context.get("bot_name", "Support Bot")
        
        message = f"""👋 Welcome back, {user_name}!

Great to see you again! I'm ready to help with your support needs.

🆘 **Quick Actions:**
/help - Show all available commands
/ticket - Create a new support ticket
/status - Check your ticket status

How can I assist you today? 🤖"""
        
        return {
            "success": True,
            "response_message": message,
            "parse_mode": "Markdown",
            "welcome_sent": True,
            "is_new_user": False,
            "fallback_used": True
        }
    
    def generate_fallback_welcome(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate basic fallback welcome message
        
        Args:
            user_data: Telegram user information
            
        Returns:
            Dict containing basic fallback response
        """
        user_name = user_data.get("first_name", "there")
        
        message = f"""👋 Hello {user_name}!

Welcome to our support bot. I'm here to help you.

Type /help to see available commands or /ticket to create a support request.

Let me know how I can assist you! 🤖"""
        
        return {
            "success": True,
            "response_message": message,
            "parse_mode": "Markdown",
            "welcome_sent": True,
            "fallback_used": True
        }


@frappe.whitelist()
def handle_user_welcome(user_data, bot_doc=None, message_data=None):
    """
    API endpoint to handle user welcome message
    
    Args:
        user_data: Telegram user information
        bot_doc: HD Telegram Bot document
        message_data: Telegram message data (optional)
        
    Returns:
        Dict containing response data
    """
    try:
        # Initialize welcome handler
        welcome_handler = WelcomeMessageHandler(bot_doc)
        
        # Handle welcome message
        result = welcome_handler.handle_welcome_message(user_data, message_data)
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Welcome message API error: {str(e)}")
        return {
            "success": False,
            "message": f"Error handling welcome message: {str(e)}"
        }


@frappe.whitelist()
def check_if_new_user(telegram_user_id):
    """
    Check if a Telegram user is new
    
    Args:
        telegram_user_id: Telegram user ID
        
    Returns:
        Dict containing user status
    """
    try:
        user_data = {"id": telegram_user_id}
        welcome_handler = WelcomeMessageHandler()
        
        is_new = welcome_handler.is_first_time_user(user_data)
        
        return {
            "success": True,
            "is_new_user": is_new
        }
        
    except Exception as e:
        frappe.log_error(f"Error checking new user: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        } 