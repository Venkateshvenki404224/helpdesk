# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, cstr


class HDTelegramUser(Document):
    def before_save(self):
        """Validation and setup before saving"""
        self.set_full_name()
        self.set_first_contact()
        self.validate_telegram_user_id()
    
    def set_full_name(self):
        """Set full name for display"""
        if self.first_name and self.last_name:
            self.full_name = f"{self.first_name} {self.last_name}"
        elif self.first_name:
            self.full_name = self.first_name
        elif self.username:
            self.full_name = self.username
        else:
            self.full_name = f"User {self.telegram_user_id}"
    
    def set_first_contact(self):
        """Set first contact timestamp for new users"""
        if self.is_new():
            self.first_contact = now_datetime()
            self.last_contact = now_datetime()
    
    def validate_telegram_user_id(self):
        """Validate Telegram user ID format"""
        if not self.telegram_user_id:
            frappe.throw(_("Telegram User ID is required"))
        
        # Telegram user IDs are positive integers
        try:
            user_id = int(self.telegram_user_id)
            if user_id <= 0:
                frappe.throw(_("Invalid Telegram User ID"))
        except ValueError:
            frappe.throw(_("Telegram User ID must be a number"))
    
    @frappe.whitelist()
    def create_customer(self):
        """Create HD Customer from Telegram user"""
        if self.customer:
            return {"success": False, "message": _("Customer already exists")}
        
        try:
            customer_doc = frappe.get_doc({
                "doctype": "HD Customer",
                "customer_name": self.full_name or f"Telegram User {self.telegram_user_id}",
                "email": self.email,
                "phone": self.phone_number,
                "source": "Telegram"
            })
            
            customer_doc.insert()
            
            # Link customer to telegram user
            self.customer = customer_doc.name
            self.save()
            
            return {
                "success": True,
                "message": _("Customer created successfully"),
                "customer": customer_doc.name
            }
        
        except Exception as e:
            frappe.log_error("Telegram Customer Creation Error", str(e))
            return {
                "success": False,
                "message": _("Failed to create customer: {0}").format(str(e))
            }
    
    @frappe.whitelist()
    def link_user(self, user_email):
        """Link Telegram user to Frappe User"""
        if not frappe.db.exists("User", user_email):
            frappe.throw(_("User does not exist"))
        
        try:
            self.linked_user = user_email
            self.save()
            
            return {
                "success": True,
                "message": _("User linked successfully")
            }
        
        except Exception as e:
            frappe.log_error("User Linking Error", str(e))
            return {
                "success": False,
                "message": _("Failed to link user: {0}").format(str(e))
            }
    
    def update_last_contact(self):
        """Update last contact timestamp"""
        self.db_set('last_contact', now_datetime())
    
    def increment_message_count(self):
        """Increment total messages sent"""
        self.db_set('total_messages_sent', self.total_messages_sent + 1)
        self.update_last_contact()
    
    def increment_ticket_count(self):
        """Increment total tickets created"""
        self.db_set('total_tickets_created', self.total_tickets_created + 1)
    
    def update_message_id(self, message_id):
        """Update last message ID"""
        self.db_set('last_message_id', cstr(message_id))
    
    @frappe.whitelist()
    def block_user(self, reason=None):
        """Block user from creating tickets"""
        self.is_blocked = 1
        if reason:
            self.add_comment("Info", f"User blocked: {reason}")
        self.save()
        
        return {"success": True, "message": _("User blocked successfully")}
    
    @frappe.whitelist()
    def unblock_user(self):
        """Unblock user"""
        self.is_blocked = 0
        self.add_comment("Info", "User unblocked")
        self.save()
        
        return {"success": True, "message": _("User unblocked successfully")}
    
    def get_display_name(self):
        """Get display name for the user"""
        if self.full_name:
            return self.full_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.telegram_user_id}"


@frappe.whitelist()
def get_or_create_telegram_user(user_data):
    """Get existing or create new Telegram user"""
    telegram_user_id = cstr(user_data.get('id'))
    
    if not telegram_user_id:
        frappe.throw(_("Telegram User ID is required"))
    
    # Check if user exists
    existing_user = frappe.db.get_value(
        "HD Telegram User",
        {"telegram_user_id": telegram_user_id},
        "name"
    )
    
    if existing_user:
        # Update existing user data
        user_doc = frappe.get_doc("HD Telegram User", existing_user)
        user_doc.username = user_data.get('username')
        user_doc.first_name = user_data.get('first_name')
        user_doc.last_name = user_data.get('last_name')
        user_doc.language_code = user_data.get('language_code')
        user_doc.is_premium = user_data.get('is_premium', 0)
        user_doc.update_last_contact()
        user_doc.save(ignore_permissions=True)
        
        return user_doc
    
    else:
        # Create new user
        user_doc = frappe.get_doc({
            "doctype": "HD Telegram User",
            "telegram_user_id": telegram_user_id,
            "username": user_data.get('username'),
            "first_name": user_data.get('first_name'),
            "last_name": user_data.get('last_name'),
            "language_code": user_data.get('language_code'),
            "is_bot": user_data.get('is_bot', 0),
            "is_premium": user_data.get('is_premium', 0)
        })
        
        user_doc.insert(ignore_permissions=True)
        return user_doc


@frappe.whitelist()
def search_telegram_users(query):
    """Search Telegram users by name or username"""
    filters = []
    
    if query:
        filters.append(['first_name', 'like', f'%{query}%'])
        filters.append(['last_name', 'like', f'%{query}%'])
        filters.append(['username', 'like', f'%{query}%'])
        filters.append(['telegram_user_id', 'like', f'%{query}%'])
    
    users = frappe.get_all(
        "HD Telegram User",
        or_filters=filters if filters else None,
        fields=[
            "name", "telegram_user_id", "username", "first_name", "last_name",
            "customer", "is_blocked", "total_tickets_created", "last_contact"
        ],
        limit=50
    )
    
    return users


@frappe.whitelist()
def get_user_tickets(telegram_user_id):
    """Get all tickets created by a Telegram user"""
    telegram_user = frappe.db.get_value(
        "HD Telegram User",
        {"telegram_user_id": telegram_user_id},
        "customer"
    )
    
    if not telegram_user:
        return []
    
    tickets = frappe.get_all(
        "HD Ticket",
        filters={"customer": telegram_user},
        fields=[
            "name", "subject", "status", "priority", "creation",
            "modified", "assigned_to"
        ],
        order_by="creation desc"
    )
    
    return tickets 