# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
import importlib
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr


class HDTelegramCommand(Document):
    def validate(self):
        """Validate command configuration"""
        self.validate_command_name()
        self.validate_function_path()
        self.validate_json_fields()
        self.validate_permissions()
    
    def validate_command_name(self):
        """Validate command name format"""
        if not self.command_name:
            frappe.throw(_("Command Name is required"))
        
        # Ensure command starts with /
        if not self.command_name.startswith('/'):
            self.command_name = f"/{self.command_name}"
        
        # Check for valid characters
        if not all(c.isalnum() or c in ['/', '_', '-'] for c in self.command_name):
            frappe.throw(_("Command name can only contain letters, numbers, underscores, and hyphens"))
    
    def validate_function_path(self):
        """Validate that the function path is accessible"""
        if not self.function_path:
            frappe.throw(_("Function Path is required"))
        
        try:
            # Try to import the function to validate it exists
            module_path, function_name = self.function_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            if not hasattr(module, function_name):
                frappe.throw(_("Function '{0}' not found in module '{1}'").format(function_name, module_path))
        except (ImportError, ValueError) as e:
            frappe.throw(_("Invalid function path: {0}").format(str(e)))
    
    def validate_json_fields(self):
        """Validate JSON field formats"""
        json_fields = ['parameters_schema', 'response_templates', 'keyboard_layout']
        
        for field in json_fields:
            value = getattr(self, field, None)
            if value:
                try:
                    if isinstance(value, str):
                        json.loads(value)
                except json.JSONDecodeError:
                    frappe.throw(_("Invalid JSON format in field '{0}'").format(field))
    
    def validate_permissions(self):
        """Validate permission settings"""
        if self.permissions:
            # Validate that all mentioned roles exist
            roles = [role.strip() for role in self.permissions.split(',')]
            for role in roles:
                if role and not frappe.db.exists('Role', role):
                    frappe.throw(_("Role '{0}' does not exist").format(role))
    
    @frappe.whitelist()
    def test_command(self, test_data=None):
        """Test command execution with sample data"""
        try:
            # Load the function
            function = self.load_function()
            
            # Prepare test data
            if not test_data:
                test_data = {
                    "user_data": {
                        "id": "123456789",
                        "first_name": "Test",
                        "username": "testuser"
                    },
                    "message_data": {
                        "text": self.command_name,
                        "chat": {"id": "123456789"}
                    },
                    "bot_doc": None
                }
            
            # Execute function
            result = function(test_data)
            
            return {
                "success": True,
                "message": "Command tested successfully",
                "result": result
            }
        
        except Exception as e:
            frappe.log_error(f"Command test failed for {self.command_name}: {str(e)}")
            return {
                "success": False,
                "message": str(e)
            }
    
    def load_function(self):
        """Load and return the command function"""
        try:
            module_path, function_name = self.function_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            return getattr(module, function_name)
        except Exception as e:
            frappe.throw(_("Failed to load function: {0}").format(str(e)))
    
    def get_response_template(self, template_type="success"):
        """Get response template by type"""
        if self.response_templates:
            templates = json.loads(self.response_templates) if isinstance(self.response_templates, str) else self.response_templates
            return templates.get(template_type, "")
        return ""
    
    def get_keyboard_layout(self):
        """Get keyboard layout configuration"""
        if self.keyboard_layout:
            return json.loads(self.keyboard_layout) if isinstance(self.keyboard_layout, str) else self.keyboard_layout
        return None
    
    def check_permissions(self, user_roles):
        """Check if user has permission to use this command"""
        if not self.permissions:
            return True  # No restrictions
        
        required_roles = [role.strip() for role in self.permissions.split(',')]
        return any(role in user_roles for role in required_roles)
    
    def check_access_level(self, user_access_level):
        """Check if user meets minimum access level"""
        access_levels = {
            "Public": 0,
            "Verified": 1, 
            "Registered": 2,
            "Admin": 3
        }
        
        required_level = access_levels.get(self.access_level, 0)
        user_level = access_levels.get(user_access_level, 0)
        
        return user_level >= required_level


@frappe.whitelist()
def get_available_commands(bot_name=None, user_access_level="Public", user_roles=None):
    """Get list of available commands for a bot and user"""
    filters = {
        "is_active": 1
    }
    
    # Get commands either global or specific to bot
    if bot_name:
        # Check if bot has specific command mappings
        bot_commands = frappe.get_all(
            "HD Bot Command Mapping",
            filters={"parent": bot_name, "is_active": 1},
            fields=["command"]
        )
        
        if bot_commands:
            command_names = [cmd["command"] for cmd in bot_commands]
            filters["name"] = ["in", command_names]
        else:
            filters["is_global"] = 1
    else:
        filters["is_global"] = 1
    
    commands = frappe.get_all(
        "HD Telegram Command",
        filters=filters,
        fields=["*"],
        order_by="sort_order asc"
    )
    
    # Filter by user permissions and access level
    filtered_commands = []
    user_roles = user_roles or []
    
    for cmd in commands:
        command_doc = frappe.get_doc("HD Telegram Command", cmd.name)
        
        # Check access level
        if not command_doc.check_access_level(user_access_level):
            continue
        
        # Check permissions
        if not command_doc.check_permissions(user_roles):
            continue
        
        filtered_commands.append(cmd)
    
    return filtered_commands


@frappe.whitelist()
def execute_command(command_name, user_data, message_data, bot_doc=None):
    """Execute a command with the given parameters"""
    try:
        # Get command configuration
        command_doc = frappe.get_doc("HD Telegram Command", command_name)
        
        if not command_doc.is_active:
            return {
                "success": False,
                "message": "Command is not active"
            }
        
        # Load and execute function
        function = command_doc.load_function()
        
        # Prepare function parameters
        params = {
            "user_data": user_data,
            "message_data": message_data,
            "bot_doc": bot_doc,
            "command_doc": command_doc
        }
        
        # Execute with timeout handling
        result = function(params)
        
        return {
            "success": True,
            "result": result,
            "command_doc": command_doc
        }
    
    except Exception as e:
        frappe.log_error(f"Command execution failed for {command_name}: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def create_default_commands():
    """Create default system commands"""
    default_commands = [
        {
            "command_name": "/start",
            "display_name": "Start",
            "description": "Initialize bot interaction and show welcome message",
            "function_path": "helpdesk.api.telegram.commands.start.handle_start",
            "command_type": "Built-in",
            "category": "General",
            "icon": "🚀",
            "help_text": "Get started with the bot",
            "sort_order": 1
        },
        {
            "command_name": "/help",
            "display_name": "Help",
            "description": "Show available commands and their usage",
            "function_path": "helpdesk.api.telegram.commands.help.handle_help",
            "command_type": "Built-in",
            "category": "General",
            "icon": "❓",
            "help_text": "Show all available commands",
            "sort_order": 2
        },
        {
            "command_name": "/status",
            "display_name": "Status", 
            "description": "Check status of your tickets",
            "function_path": "helpdesk.api.telegram.commands.status.handle_status",
            "command_type": "Built-in",
            "category": "Ticketing",
            "icon": "📋",
            "help_text": "Check your ticket status",
            "sort_order": 3
        },
        {
            "command_name": "/ticket",
            "display_name": "New Ticket",
            "description": "Create a new support ticket",
            "function_path": "helpdesk.api.telegram.commands.ticket.handle_ticket",
            "command_type": "Built-in", 
            "category": "Ticketing",
            "icon": "🎫",
            "help_text": "Create a new support ticket",
            "sort_order": 4
        },
        {
            "command_name": "/cancel",
            "display_name": "Cancel",
            "description": "Cancel current operation",
            "function_path": "helpdesk.api.telegram.commands.cancel.handle_cancel",
            "command_type": "Built-in",
            "category": "General", 
            "icon": "❌",
            "help_text": "Cancel current operation",
            "sort_order": 5
        }
    ]
    
    created_commands = []
    
    for cmd_data in default_commands:
        if not frappe.db.exists("HD Telegram Command", cmd_data["command_name"]):
            command_doc = frappe.get_doc({
                "doctype": "HD Telegram Command",
                **cmd_data
            })
            command_doc.insert()
            created_commands.append(cmd_data["command_name"])
    
    return {
        "success": True,
        "message": f"Created {len(created_commands)} default commands",
        "commands": created_commands
    } 