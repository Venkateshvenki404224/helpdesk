# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, cstr, get_datetime
from datetime import datetime
from helpdesk.helpdesk.utils.json_utils import safe_serialize_response


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
            self.save(ignore_permissions=True)
            
            # Get telegram user
            telegram_user = frappe.get_doc("HD Telegram User", self.telegram_user)
            
            # Check if user is blocked
            if telegram_user.is_blocked:
                self.processing_status = "Skipped"
                self.error_message = "User is blocked"
                self.save(ignore_permissions=True)
                return {"success": False, "message": _("User is blocked")}
            
            # Check if auto create tickets is enabled
            if not telegram_user.auto_create_tickets:
                self.processing_status = "Skipped"
                self.error_message = "Auto ticket creation disabled for user"
                self.save(ignore_permissions=True)
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
            
            self.save(ignore_permissions=True)
            return result
        
        except Exception as e:
            frappe.log_error("Telegram Message Processing Error", str(e))
            self.processing_status = "Failed"
            self.error_message = str(e)
            self.save(ignore_permissions=True)
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
            
            ticket_doc.insert(ignore_permissions=True)
            
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
                ticket_doc.save(ignore_permissions=True)
            
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
            
            communication_doc.insert(ignore_permissions=True)
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
        self.save(ignore_permissions=True)
        
        return self.process_message()
    
    # ============ CONVERSATION MANAGEMENT METHODS ============
    
    @frappe.whitelist()
    def start_conversation(self, category=None):
        """Start a new conversation flow"""
        try:
            # Generate conversation group ID
            if not self.conversation_group_id:
                self.conversation_group_id = self.generate_conversation_group_id(category)
            
            # Set conversation state
            self.conversation_state = "waiting_for_problem"
            self.is_conversation_starter = 1
            self.awaiting_response = 1
            self.conversation_category = category or "General Inquiry"
            
            # Initialize context
            context = {
                "started_at": now_datetime().isoformat(),
                "category": category,
                "step": 1,
                "collected_info": {}
            }
            self.conversation_context = json.dumps(context)
            
            self.save(ignore_permissions=True)
            
            return {
                "success": True,
                "conversation_group_id": self.conversation_group_id,
                "next_prompt": self.get_next_prompt()
            }
            
        except Exception as e:
            frappe.log_error(f"Error starting conversation: {str(e)}")
            return {"success": False, "message": str(e)}
    
    @frappe.whitelist()
    def update_conversation_state(self, new_state, context_update=None):
        """Update conversation state and context"""
        try:
            self.conversation_state = new_state
            
            # Update context if provided
            if context_update:
                existing_context = self.get_conversation_context()
                existing_context.update(context_update)
                self.conversation_context = json.dumps(existing_context)
            
            # Update awaiting status based on state
            if new_state in ["waiting_for_problem", "waiting_for_details", "waiting_for_priority"]:
                self.awaiting_response = 1
            else:
                self.awaiting_response = 0
            
            self.save(ignore_permissions=True)
            
            return {
                "success": True,
                "state": new_state,
                "next_prompt": self.get_next_prompt()
            }
            
        except Exception as e:
            frappe.log_error(f"Error updating conversation state: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def get_conversation_context(self):
        """Get conversation context as dictionary"""
        try:
            return json.loads(self.conversation_context) if self.conversation_context else {}
        except:
            return {}
    
    def set_conversation_context(self, context_dict):
        """Set conversation context from dictionary"""
        self.conversation_context = json.dumps(context_dict)
    
    def generate_conversation_group_id(self, category=None):
        """Generate unique conversation group ID"""
        import uuid
        timestamp = now_datetime().strftime("%Y%m%d")
        category_prefix = (category or "GEN")[:3].upper()
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"CONV-{category_prefix}-{timestamp}-{unique_id}"
    
    def get_next_prompt(self):
        """Get next prompt based on conversation state"""
        state_prompts = {
            "waiting_for_problem": "🤔 **What do you need help with today?**\n\nPlease describe your problem or question in detail.",
            "waiting_for_details": "📝 **Can you provide more details?**\n\nAny additional information would help us assist you better.",
            "waiting_for_priority": "⚡ **How urgent is this issue?**\n\nReply with:\n• **High** - Urgent/Critical\n• **Medium** - Normal priority\n• **Low** - When convenient",
            "collecting_info": "ℹ️ **Any additional information you'd like to add?**",
            "ready_for_ticket": "✅ **Perfect! Creating your support ticket now...**",
            "ticket_created": "🎫 **Ticket created successfully!**"
        }
        return state_prompts.get(self.conversation_state, "👋 Hello! How can I help you today?")
    
    @frappe.whitelist()
    def get_conversation_summary(self):
        """Get conversation summary for ticket creation"""
        try:
            context = self.get_conversation_context()
            
            # Get all messages in this conversation group
            related_messages = frappe.get_all(
                "HD Telegram Message",
                filters={
                    "conversation_group_id": self.conversation_group_id,
                    "telegram_user": self.telegram_user
                },
                fields=["text_content", "message_date", "conversation_state"],
                order_by="message_date asc"
            )
            
            # Compile conversation summary
            summary = {
                "conversation_group_id": self.conversation_group_id,
                "category": self.conversation_category,
                "problem_description": context.get("collected_info", {}).get("problem_description", ""),
                "additional_details": context.get("collected_info", {}).get("additional_details", ""),
                "priority": context.get("collected_info", {}).get("priority", "Medium"),
                "all_messages": [msg["text_content"] for msg in related_messages if msg["text_content"]],
                "message_count": len(related_messages),
                "started_at": context.get("started_at"),
                "telegram_user": self.telegram_user,
                "chat_id": frappe.get_value("HD Telegram User", self.telegram_user, "telegram_user_id")
            }
            
            return summary
            
        except Exception as e:
            frappe.log_error(f"Error getting conversation summary: {str(e)}")
            return {}
    
    @frappe.whitelist()
    def complete_conversation(self, ticket_id=None):
        """Mark conversation as completed"""
        try:
            self.conversation_state = "ticket_created"
            self.awaiting_response = 0
            
            if ticket_id:
                self.linked_ticket = ticket_id
                self.created_ticket = 1
            
            # Update context
            context = self.get_conversation_context()
            context["completed_at"] = now_datetime().isoformat()
            context["ticket_id"] = ticket_id
            self.conversation_context = json.dumps(context)
            
            self.save(ignore_permissions=True)
            
            return {"success": True, "message": "Conversation completed"}
            
        except Exception as e:
            frappe.log_error(f"Error completing conversation: {str(e)}")
            return {"success": False, "message": str(e)}


@frappe.whitelist()
def create_telegram_message(message_data, bot_name_or_doc):
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
        
        # Convert large integers to strings before storing raw data
        safe_message_data = safe_serialize_response(message_data)
        
        # Get bot document name
        if hasattr(bot_name_or_doc, 'name'):
            # It's a bot document
            bot_doc_name = bot_name_or_doc.name
        else:
            # It's a bot name string, find the document
            bot_doc = frappe.get_value("HD Telegram Bot", {"bot_name": bot_name_or_doc}, "name")
            if not bot_doc:
                return {"success": False, "message": f"Could not find Telegram Bot: {bot_name_or_doc}"}
            bot_doc_name = bot_doc
        
        # Create message document
        message_doc = frappe.get_doc({
            "doctype": "HD Telegram Message",
            "message_id": cstr(message_id),
            "telegram_user": telegram_user.name,
            "telegram_bot": bot_doc_name,
            "message_type": message_type,
            "message_date": datetime.fromtimestamp(message.get("date")) if message.get("date") else now_datetime(),
            "text_content": text_content,
            "caption": message.get("caption"),
            "media_type": media_info.get("media_type"),
            "file_id": media_info.get("file_id"),
            "file_size": media_info.get("file_size"),
            "is_forwarded": bool(message.get("forward_from")),
            "forward_from": message.get("forward_from", {}).get("first_name"),
            "reply_to_message_id": cstr(message.get("reply_to_message", {}).get("message_id", "")),
            "raw_message_data": json.dumps(safe_message_data),
            "processing_status": "Pending"
        })
        
        message_doc.insert(ignore_permissions=True)
        
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


# ============ CONVERSATION UTILITY FUNCTIONS ============

@frappe.whitelist()
def get_active_conversation(telegram_user_id, category=None):
    """Get active conversation for a user in specific category"""
    try:
        # Get HD Telegram User
        telegram_user = frappe.db.get_value(
            "HD Telegram User", 
            {"telegram_user_id": cstr(telegram_user_id)}, 
            "name"
        )
        
        if not telegram_user:
            return None
        
        # Build filters
        filters = {
            "telegram_user": telegram_user,
            "awaiting_response": 1,
            "conversation_state": ["not in", ["idle", "ticket_created"]]
        }
        
        # Add category filter if specified
        if category:
            filters["conversation_category"] = category
        
        # Find active conversation
        conversation = frappe.db.get_value(
            "HD Telegram Message",
            filters,
            ["name", "conversation_group_id", "conversation_state", "conversation_category", 
             "conversation_context", "awaiting_response"],
            as_dict=True,
            order_by="message_date desc"
        )
        
        return conversation
        
    except Exception as e:
        frappe.log_error(f"Error getting active conversation: {str(e)}")
        return None


@frappe.whitelist()
def start_new_conversation(telegram_user_id, initial_message, category=None, bot_doc=None):
    """Start a new conversation for a user"""
    try:
        frappe.logger().debug(f"start_new_conversation called with user_id: {telegram_user_id}, category: {category}")
        
        # Get or create telegram user
        from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
        telegram_user = get_or_create_telegram_user(initial_message.get('from', {}))
        frappe.logger().debug(f"Telegram user: {telegram_user.name if telegram_user else 'None'}")
        
        # Create message document
        bot_name = bot_doc.bot_name if bot_doc else "n8n Builder"  # Fallback
        frappe.logger().debug(f"Creating message with bot_name: {bot_name}")
        message_doc = create_telegram_message({"message": initial_message}, bot_name)
        frappe.logger().debug(f"create_telegram_message result: {message_doc}")
        
        if message_doc.get("success"):
            message_name = message_doc.get("message_name")
            msg_doc = frappe.get_doc("HD Telegram Message", message_name)
            
            # Start conversation
            result = msg_doc.start_conversation(category)
            frappe.logger().debug(f"start_conversation result: {result}")
            
            return {
                "success": True,
                "message_name": message_name,
                "conversation_result": result
            }
        else:
            frappe.logger().error(f"create_telegram_message failed: {message_doc}")
            return message_doc
        
    except Exception as e:
        frappe.log_error(f"Error starting new conversation: {str(e)}")
        return {"success": False, "message": str(e)}


@frappe.whitelist() 
def get_user_conversations(telegram_user_id, limit=5):
    """Get recent conversations for a user"""
    try:
        # Get HD Telegram User
        telegram_user = frappe.db.get_value(
            "HD Telegram User", 
            {"telegram_user_id": cstr(telegram_user_id)}, 
            "name"
        )
        
        if not telegram_user:
            return []
        
        # Get conversation starters (unique conversations)
        conversations = frappe.get_all(
            "HD Telegram Message",
            filters={
                "telegram_user": telegram_user,
                "is_conversation_starter": 1
            },
            fields=[
                "conversation_group_id", "conversation_category", "conversation_state",
                "message_date", "linked_ticket", "conversation_context"
            ],
            order_by="message_date desc",
            limit=limit
        )
        
        return conversations
        
    except Exception as e:
        frappe.log_error(f"Error getting user conversations: {str(e)}")
        return []


@frappe.whitelist()
def create_ticket_from_conversation(conversation_group_id):
    """Create ticket from a completed conversation"""
    try:
        # Get conversation starter message
        starter_message = frappe.get_value(
            "HD Telegram Message",
            {
                "conversation_group_id": conversation_group_id,
                "is_conversation_starter": 1
            },
            "name"
        )
        
        if not starter_message:
            return {"success": False, "message": "Conversation not found"}
        
        msg_doc = frappe.get_doc("HD Telegram Message", starter_message)
        conversation_summary = msg_doc.get_conversation_summary()
        
        # Create ticket with conversation context
        ticket_data = {
            "doctype": "HD Ticket",
            "subject": conversation_summary.get("problem_description", "Support Request")[:100],
            "description": format_conversation_for_ticket(conversation_summary),
            "status": "Open",
            "priority": conversation_summary.get("priority", "Medium"),
            "customer": frappe.get_value("HD Telegram User", msg_doc.telegram_user, "customer"),
            "source": "Telegram",
            "ticket_type": conversation_summary.get("category"),
            "custom_conversation_id": conversation_group_id
        }
        
        # Create ticket
        ticket = frappe.get_doc(ticket_data)
        ticket.insert()
        
        # Mark conversation as completed
        msg_doc.complete_conversation(ticket.name)
        
        # Update all messages in conversation
        frappe.db.sql("""
            UPDATE `tabHD Telegram Message`
            SET linked_ticket = %s, conversation_state = 'ticket_created'
            WHERE conversation_group_id = %s
        """, (ticket.name, conversation_group_id))
        
        frappe.db.commit()
        
        return {
            "success": True,
            "ticket": ticket.name,
            "ticket_id": ticket.name,
            "subject": ticket.subject
        }
        
    except Exception as e:
        frappe.log_error(f"Error creating ticket from conversation: {str(e)}")
        return {"success": False, "message": str(e)}


def format_conversation_for_ticket(conversation_summary):
    """Format conversation summary into ticket description"""
    description_parts = []
    
    # Add problem description
    if conversation_summary.get("problem_description"):
        description_parts.append(f"**Problem Description:**\n{conversation_summary['problem_description']}")
    
    # Add additional details
    if conversation_summary.get("additional_details"):
        description_parts.append(f"**Additional Details:**\n{conversation_summary['additional_details']}")
    
    # Add conversation messages
    if conversation_summary.get("all_messages"):
        description_parts.append("**Conversation History:**")
        for i, message in enumerate(conversation_summary["all_messages"], 1):
            if message.strip():
                description_parts.append(f"{i}. {message}")
    
    # Add metadata
    description_parts.append("---")
    description_parts.append(f"**Source:** Telegram Conversation")
    description_parts.append(f"**Category:** {conversation_summary.get('category', 'General')}")
    description_parts.append(f"**Conversation ID:** {conversation_summary.get('conversation_group_id')}")
    description_parts.append(f"**Messages:** {conversation_summary.get('message_count', 0)}")
    
    return "\n\n".join(description_parts) 