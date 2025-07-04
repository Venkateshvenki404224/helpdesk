# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
import re
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, cstr
from string import Template
import html


class HDBotResponseTemplate(Document):
    def validate(self):
        """Validate template configuration"""
        self.validate_content()
        self.validate_variables()
        self.validate_json_fields()
        self.validate_character_limit()
        self.update_content_preview()
    
    def validate_content(self):
        """Validate template content"""
        if not self.content:
            frappe.throw(_("Template content is required"))
        
        if len(self.content) > (self.character_limit or 4096):
            frappe.throw(_("Template content exceeds character limit of {0}").format(self.character_limit))
    
    def validate_variables(self):
        """Validate variables configuration"""
        if self.variables:
            try:
                variables = json.loads(self.variables) if isinstance(self.variables, str) else self.variables
                
                # Validate variable format
                for var in variables:
                    if not isinstance(var, dict):
                        frappe.throw(_("Each variable must be a dictionary"))
                    
                    required_keys = ['name', 'type', 'description']
                    for key in required_keys:
                        if key not in var:
                            frappe.throw(_("Variable missing required key: {0}").format(key))
            
            except json.JSONDecodeError:
                frappe.throw(_("Invalid JSON format in variables field"))
    
    def validate_json_fields(self):
        """Validate JSON field formats"""
        json_fields = ['variables', 'sample_context', 'keyboard_layout']
        
        for field in json_fields:
            value = getattr(self, field, None)
            if value:
                try:
                    if isinstance(value, str):
                        json.loads(value)
                except json.JSONDecodeError:
                    frappe.throw(_("Invalid JSON format in field '{0}'").format(field))
    
    def validate_character_limit(self):
        """Validate character limit setting"""
        if self.character_limit and self.character_limit > 4096:
            frappe.throw(_("Character limit cannot exceed 4096 (Telegram's limit)"))
    
    def update_content_preview(self):
        """Generate content preview with sample data"""
        try:
            if self.sample_context:
                sample_data = json.loads(self.sample_context) if isinstance(self.sample_context, str) else self.sample_context
                rendered = self.render(sample_data)
                self.content_preview = f'<div style="border: 1px solid #ddd; padding: 10px; background: #f9f9f9;"><pre>{html.escape(rendered["content"])}</pre></div>'
            else:
                self.content_preview = f'<div style="border: 1px solid #ddd; padding: 10px; background: #f9f9f9;"><pre>{html.escape(self.content)}</pre></div>'
        except Exception as e:
            self.content_preview = f'<div style="color: red;">Preview Error: {str(e)}</div>'
    
    @frappe.whitelist()
    def render(self, context_data=None, escape_content=None):
        """Render template with context data"""
        try:
            context = context_data or {}
            content = self.content
            
            # Extract variables from content
            variables = self.extract_variables_from_content()
            
            # Process variables
            for var_name in variables:
                placeholder = "{" + var_name + "}"
                value = context.get(var_name, f"{{missing:{var_name}}}")
                
                # Convert value to string if needed
                if not isinstance(value, str):
                    value = str(value)
                
                # Apply auto-escaping if enabled
                if self.auto_escape and escape_content != False:
                    if self.parse_mode == "HTML":
                        value = html.escape(value)
                    elif self.parse_mode in ["Markdown", "MarkdownV2"]:
                        value = self.escape_markdown(value)
                
                content = content.replace(placeholder, value)
            
            # Track usage
            self.increment_usage()
            
            result = {
                "content": content,
                "parse_mode": self.parse_mode,
                "disable_web_page_preview": self.disable_web_page_preview,
                "keyboard": self.get_keyboard_layout()
            }
            
            return result
        
        except Exception as e:
            frappe.log_error(f"Template rendering failed for {self.template_name}: {str(e)}")
            return {
                "content": f"Error rendering template: {str(e)}",
                "parse_mode": None
            }
    
    def extract_variables_from_content(self):
        """Extract variable names from template content"""
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, self.content)
        return list(set(matches))  # Remove duplicates
    
    def escape_markdown(self, text):
        """Escape special characters for Markdown"""
        special_chars = ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    def get_keyboard_layout(self):
        """Get processed keyboard layout"""
        if not self.keyboard_layout:
            return None
        
        try:
            keyboard = json.loads(self.keyboard_layout) if isinstance(self.keyboard_layout, str) else self.keyboard_layout
            
            if self.keyboard_type == "Inline":
                return {"inline_keyboard": keyboard}
            elif self.keyboard_type == "Reply":
                return {"keyboard": keyboard, "resize_keyboard": True}
            elif self.keyboard_type == "Remove":
                return {"remove_keyboard": True}
            
            return keyboard
        
        except Exception as e:
            frappe.log_error(f"Keyboard layout processing failed: {str(e)}")
            return None
    
    def increment_usage(self):
        """Increment usage counter"""
        try:
            self.db_set('usage_count', (self.usage_count or 0) + 1)
            self.db_set('last_used', now_datetime())
        except Exception:
            pass  # Don't fail template rendering if usage tracking fails
    
    @frappe.whitelist()
    def test_template(self, test_context=None):
        """Test template rendering with provided or sample context"""
        try:
            context = test_context
            
            if not context and self.sample_context:
                context = json.loads(self.sample_context) if isinstance(self.sample_context, str) else self.sample_context
            
            result = self.render(context or {})
            
            return {
                "success": True,
                "rendered_content": result["content"],
                "parse_mode": result["parse_mode"],
                "keyboard": result["keyboard"],
                "context_used": context
            }
        
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }
    
    @frappe.whitelist()
    def duplicate_template(self, new_name=None):
        """Create a copy of this template"""
        try:
            new_template = frappe.copy_doc(self)
            new_template.template_name = new_name or f"{self.template_name}_copy"
            new_template.usage_count = 0
            new_template.last_used = None
            new_template.insert()
            
            return {
                "success": True,
                "message": "Template duplicated successfully",
                "new_template": new_template.name
            }
        
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }


@frappe.whitelist()
def get_templates_by_category(category=None, language="en", is_global=True):
    """Get templates filtered by category and language"""
    filters = {
        "is_active": 1,
        "language": language
    }
    
    if category:
        filters["template_category"] = category
    
    if is_global:
        filters["is_global"] = 1
    
    templates = frappe.get_all(
        "HD Bot Response Template",
        filters=filters,
        fields=["template_name", "template_category", "description", "usage_count"],
        order_by="template_category asc, usage_count desc"
    )
    
    return templates


@frappe.whitelist() 
def render_template(template_name, context_data, escape_content=True):
    """Render a template with context data"""
    try:
        template_doc = frappe.get_doc("HD Bot Response Template", template_name)
        
        if not template_doc.is_active:
            return {
                "success": False,
                "message": "Template is not active"
            }
        
        result = template_doc.render(context_data, escape_content)
        
        return {
            "success": True,
            "result": result
        }
    
    except Exception as e:
        frappe.log_error(f"Template rendering failed: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def create_default_templates():
    """Create default response templates"""
    default_templates = [
        {
            "template_name": "welcome_message",
            "template_category": "Welcome",
            "description": "Default welcome message for new users",
            "content": "👋 Hello {user_name}! Welcome to {bot_name}.\n\nI'm here to help you with support requests. Here are the available commands:\n\n{available_commands}\n\nJust type a command or describe your issue to get started! 🚀",
            "parse_mode": "HTML",
            "variables": json.dumps([
                {"name": "user_name", "type": "string", "description": "User's first name"},
                {"name": "bot_name", "type": "string", "description": "Bot display name"},
                {"name": "available_commands", "type": "string", "description": "List of available commands"}
            ]),
            "sample_context": json.dumps({
                "user_name": "John",
                "bot_name": "Support Bot",
                "available_commands": "/help - Show commands\n/ticket - Create ticket\n/status - Check status"
            })
        },
        {
            "template_name": "help_message",
            "template_category": "Help",
            "description": "Help message showing available commands",
            "content": "📋 <b>Available Commands:</b>\n\n{commands_list}\n\n💡 <i>Tip: You can also just describe your problem and I'll help you create a support ticket!</i>",
            "parse_mode": "HTML",
            "variables": json.dumps([
                {"name": "commands_list", "type": "string", "description": "Formatted list of commands"}
            ]),
            "sample_context": json.dumps({
                "commands_list": "🚀 /start - Get started\n❓ /help - Show this help\n🎫 /ticket - Create new ticket\n📋 /status - Check ticket status"
            })
        },
        {
            "template_name": "error_message",
            "template_category": "Error",
            "description": "Generic error message",
            "content": "❌ <b>Oops! Something went wrong.</b>\n\n{error_details}\n\nPlease try again or contact support if the problem persists.\n\nUse /help to see available commands.",
            "parse_mode": "HTML",
            "variables": json.dumps([
                {"name": "error_details", "type": "string", "description": "Specific error information"}
            ]),
            "sample_context": json.dumps({
                "error_details": "Command not recognized or temporarily unavailable."
            })
        },
        {
            "template_name": "ticket_created",
            "template_category": "Success",
            "description": "Confirmation message for ticket creation",
            "content": "✅ <b>Ticket Created Successfully!</b>\n\n🎫 <b>Ticket ID:</b> {ticket_id}\n📝 <b>Subject:</b> {ticket_subject}\n⏰ <b>Created:</b> {created_time}\n\nOur support team will respond soon. You can check the status anytime with /status.",
            "parse_mode": "HTML",
            "variables": json.dumps([
                {"name": "ticket_id", "type": "string", "description": "Unique ticket identifier"},
                {"name": "ticket_subject", "type": "string", "description": "Ticket subject/title"},
                {"name": "created_time", "type": "string", "description": "Ticket creation timestamp"}
            ]),
            "sample_context": json.dumps({
                "ticket_id": "HD-2024-001",
                "ticket_subject": "Login Issue",
                "created_time": "2024-07-04 17:45:00"
            })
        },
        {
            "template_name": "command_not_found",
            "template_category": "Error",
            "description": "Message for unrecognized commands",
            "content": "❓ I don't recognize the command '{command_name}'.\n\nUse /help to see all available commands, or just describe your issue and I'll help you create a support ticket! 🎫",
            "parse_mode": "HTML",
            "variables": json.dumps([
                {"name": "command_name", "type": "string", "description": "The unrecognized command"}
            ]),
            "sample_context": json.dumps({
                "command_name": "/unknown"
            })
        }
    ]
    
    created_templates = []
    
    for template_data in default_templates:
        if not frappe.db.exists("HD Bot Response Template", template_data["template_name"]):
            template_doc = frappe.get_doc({
                "doctype": "HD Bot Response Template",
                **template_data
            })
            template_doc.insert()
            created_templates.append(template_data["template_name"])
    
    return {
        "success": True,
        "message": f"Created {len(created_templates)} default templates",
        "templates": created_templates
    } 