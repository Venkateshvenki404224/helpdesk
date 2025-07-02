# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, cstr, get_datetime


class HDTelegramMessage(Document):
    def before_save(self):
        """Validation and setup before saving"""
        self.set_received_on()
        self.validate_message_data()
    
    def set_received_on(self):
        """Set received timestamp for new messages"""
        if self.is_new() and not self.received_on:
            self.received_on = now_datetime()
    
    def validate_message_data(self):
        """Validate message data"""
        if not self.message_id:
            frappe.throw(_("Message ID is required"))
        
        if not self.telegram_user:
            frappe.throw(_("Telegram User is required"))
        
        if not self.message_type:
            frappe.throw(_("Message Type is required"))
    
    @frappe.whitelist()
    def process_message(self):
        """Process the message and create ticket if needed"""
        if self.is_processed:
            return {"success": False, "message": _("Message already processed")}
        
        try:
            self.processing_status = "Processing"
            self.save()
            
            # Get telegram user
            telegram_user = frappe.get_doc("HD Telegram User", self.telegram_user)
            
            # Check if user is blocked
            if telegram_user.is_blocked:
                self.processing_status = "Skipped"
                self.error_message = "User is blocked"
                self.save()
                return {"success": False, "message": _("User is blocked")}
            
            # Check if auto create tickets is enabled
            if not telegram_user.auto_create_tickets:
                self.processing_status = "Skipped"
                self.error_message = "Auto ticket creation disabled for user"
                self.save()
                return {"success": False, "message": _("Auto ticket creation disabled")}
            
            # Create or update ticket
            result = self.create_or_update_ticket(telegram_user)
            
            if result.get("success"):
                self.is_processed = 1
                self.processing_status = "Completed"
                self.processed_on = now_datetime()
                self.linked_ticket = result.get("ticket_name")
                self.created_ticket = result.get("created_new_ticket", 0)
                self.communication_id = result.get("communication_id")
            else:
                self.processing_status = "Failed"
                self.error_message = result.get("message", "Unknown error")
            
            self.save()
            return result
        
        except Exception as e:
            frappe.log_error("Telegram Message Processing Error", str(e))
            self.processing_status = "Failed"
            self.error_message = str(e)
            self.save()
            return {"success": False, "message": str(e)}
    
    def create_or_update_ticket(self, telegram_user):
        """Create new ticket or update existing ticket"""
        try:
            # Get bot configuration
            bot_doc = frappe.get_doc("HD Telegram Bot", self.telegram_bot)
            
            # Check for existing open ticket for this user
            existing_ticket = self.get_existing_open_ticket(telegram_user)
            
            if existing_ticket:
                # Add message to existing ticket
                return self.add_message_to_ticket(existing_ticket, telegram_user)
            else:
                # Create new ticket
                return self.create_new_ticket(telegram_user, bot_doc)
        
        except Exception as e:
            frappe.log_error("Ticket Creation/Update Error", str(e))
            return {"success": False, "message": str(e)}
    
    def get_existing_open_ticket(self, telegram_user):
        """Get existing open ticket for the user"""
        if not telegram_user.customer:
            return None
        
        # Look for open tickets from last 24 hours
        open_ticket = frappe.db.get_value(
            "HD Ticket",
            {
                "customer": telegram_user.customer,
                "status": ["in", ["Open", "Replied"]],
                "creation": [">=", frappe.utils.add_hours(now_datetime(), -24)]
            },
            "name",
            order_by="creation desc"
        )
        
        return open_ticket
    
    def create_new_ticket(self, telegram_user, bot_doc):
        """Create a new ticket from the message"""
        try:
            # Ensure customer exists
            if not telegram_user.customer:
                customer_result = telegram_user.create_customer()
                if not customer_result.get("success"):
                    return customer_result
            
            # Create ticket subject
            subject = self.generate_ticket_subject()
            
            # Create ticket document
            ticket_doc = frappe.get_doc({
                "doctype": "HD Ticket",
                "subject": subject,
                "customer": telegram_user.customer,
                "description": self.get_message_content(),
                "status": "Open",
                "priority": bot_doc.default_priority or "Medium",
                "assigned_to": bot_doc.default_team,
                "via_customer_portal": 0,
                "contact": telegram_user.customer,
                "custom_source": "Telegram"
            })
            
            ticket_doc.insert()
            
            # Create communication
            communication_doc = self.create_communication(ticket_doc, telegram_user)
            
            # Update statistics
            telegram_user.increment_ticket_count()
            bot_doc.increment_ticket_count()
            
            return {
                "success": True,
                "message": _("New ticket created successfully"),
                "ticket_name": ticket_doc.name,
                "created_new_ticket": 1,
                "communication_id": communication_doc.name if communication_doc else None
            }
        
        except Exception as e:
            frappe.log_error("New Ticket Creation Error", str(e))
            return {"success": False, "message": str(e)}
    
    def add_message_to_ticket(self, ticket_name, telegram_user):
        """Add message to existing ticket"""
        try:
            ticket_doc = frappe.get_doc("HD Ticket", ticket_name)
            
            # Create communication
            communication_doc = self.create_communication(ticket_doc, telegram_user)
            
            # Update ticket status if it was closed
            if ticket_doc.status in ["Closed", "Resolved"]:
                ticket_doc.status = "Open"
                ticket_doc.save()
            
            return {
                "success": True,
                "message": _("Message added to existing ticket"),
                "ticket_name": ticket_name,
                "created_new_ticket": 0,
                "communication_id": communication_doc.name if communication_doc else None
            }
        
        except Exception as e:
            frappe.log_error("Ticket Update Error", str(e))
            return {"success": False, "message": str(e)}
    
    def create_communication(self, ticket_doc, telegram_user):
        """Create communication record for the message"""
        try:
            communication_doc = frappe.get_doc({
                "doctype": "Communication",
                "communication_type": "Communication",
                "communication_medium": "Chat",
                "sent_or_received": "Received",
                "reference_doctype": "HD Ticket",
                "reference_name": ticket_doc.name,
                "subject": f"Telegram message from {telegram_user.get_display_name()}",
                "content": self.get_message_content(),
                "sender": telegram_user.email or f"telegram_user_{telegram_user.telegram_user_id}@telegram.local",
                "sender_full_name": telegram_user.get_display_name(),
                "timeline_hide": 0
            })
            
            communication_doc.insert()
            return communication_doc
        
        except Exception as e:
            frappe.log_error("Communication Creation Error", str(e))
            return None
    
    def generate_ticket_subject(self):
        """Generate appropriate ticket subject"""
        if self.text_content:
            # Use first 50 characters of text as subject
            subject = self.text_content[:50].strip()
            if len(self.text_content) > 50:
                subject += "..."
        elif self.caption:
            subject = self.caption[:50].strip()
            if len(self.caption) > 50:
                subject += "..."
        elif self.media_type:
            subject = f"Telegram {self.media_type.title()}"
        else:
            subject = f"Telegram Message #{self.message_id}"
        
        return subject or "Telegram Support Request"
    
    def get_message_content(self):
        """Get formatted message content for ticket"""
        content_parts = []
        
        if self.text_content:
            content_parts.append(self.text_content)
        
        if self.caption:
            content_parts.append(f"Caption: {self.caption}")
        
        if self.media_type:
            content_parts.append(f"[{self.media_type.title()} attachment]")
        
        if self.file_id:
            content_parts.append(f"File ID: {self.file_id}")
        
        return "\n\n".join(content_parts) or "[Empty message]"
    
    @frappe.whitelist()
    def reprocess_message(self):
        """Reprocess a failed message"""
        self.is_processed = 0
        self.processing_status = "Pending"
        self.error_message = ""
        self.processed_on = None
        self.save()
        
        return self.process_message()


@frappe.whitelist()
def create_telegram_message(message_data, bot_name):
    """Create HD Telegram Message from webhook data"""
    try:
        # Parse message data
        message = message_data.get("message", {})
        message_id = message.get("message_id")
        user_data = message.get("from", {})
        
        if not message_id or not user_data:
            return {"success": False, "message": "Invalid message data"}
        
        # Get or create telegram user
        from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
        telegram_user = get_or_create_telegram_user(user_data)
        
        # Determine message type and content
        message_type, text_content, media_info = parse_message_content(message)
        
        # Create message document
        message_doc = frappe.get_doc({
            "doctype": "HD Telegram Message",
            "message_id": cstr(message_id),
            "telegram_user": telegram_user.name,
            "telegram_bot": bot_name,
            "message_type": message_type,
            "message_date": get_datetime(message.get("date")),
            "text_content": text_content,
            "caption": message.get("caption"),
            "media_type": media_info.get("media_type"),
            "file_id": media_info.get("file_id"),
            "file_size": media_info.get("file_size"),
            "is_forwarded": bool(message.get("forward_from")),
            "forward_from": message.get("forward_from", {}).get("first_name"),
            "reply_to_message_id": cstr(message.get("reply_to_message", {}).get("message_id", "")),
            "raw_message_data": json.dumps(message_data),
            "processing_status": "Pending"
        })
        
        message_doc.insert()
        
        # Update user statistics
        telegram_user.increment_message_count()
        
        # Process message in background
        frappe.enqueue(
            "helpdesk.helpdesk.doctype.hd_telegram_message.hd_telegram_message.process_message_background",
            message_name=message_doc.name,
            queue="default",
            timeout=300
        )
        
        return {
            "success": True,
            "message": "Message created and queued for processing",
            "message_name": message_doc.name
        }
    
    except Exception as e:
        frappe.log_error("Telegram Message Creation Error", str(e))
        return {"success": False, "message": str(e)}


def parse_message_content(message):
    """Parse message content and determine type"""
    message_type = "text"
    text_content = message.get("text", "")
    media_info = {}
    
    # Check for different media types
    if message.get("photo"):
        message_type = "photo"
        media_info = {
            "media_type": "image",
            "file_id": message["photo"][-1].get("file_id"),  # Get largest photo
            "file_size": message["photo"][-1].get("file_size")
        }
    elif message.get("video"):
        message_type = "video"
        media_info = {
            "media_type": "video",
            "file_id": message["video"].get("file_id"),
            "file_size": message["video"].get("file_size")
        }
    elif message.get("audio"):
        message_type = "audio"
        media_info = {
            "media_type": "audio",
            "file_id": message["audio"].get("file_id"),
            "file_size": message["audio"].get("file_size")
        }
    elif message.get("document"):
        message_type = "document"
        media_info = {
            "media_type": "document",
            "file_id": message["document"].get("file_id"),
            "file_size": message["document"].get("file_size")
        }
    elif message.get("voice"):
        message_type = "voice"
        media_info = {
            "media_type": "voice",
            "file_id": message["voice"].get("file_id"),
            "file_size": message["voice"].get("file_size")
        }
    elif message.get("sticker"):
        message_type = "sticker"
        media_info = {
            "media_type": "sticker",
            "file_id": message["sticker"].get("file_id"),
            "file_size": message["sticker"].get("file_size")
        }
    
    return message_type, text_content, media_info


def process_message_background(message_name):
    """Background job to process message"""
    try:
        message_doc = frappe.get_doc("HD Telegram Message", message_name)
        result = message_doc.process_message()
        
        if not result.get("success"):
            frappe.log_error("Background Message Processing Failed", result.get("message"))
    
    except Exception as e:
        frappe.log_error("Background Processing Error", str(e)) 