#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Interactive Flow Handler for Telegram Helpdesk Integration

This module coordinates conversation flows, manages state transitions, and handles
interactive dialogue between users and the support bot before ticket creation.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cstr
from typing import Dict, Any, Optional, List
import re


class InteractiveFlowHandler:
    """
    Handles interactive conversation flows for Telegram support.
    
    Features:
    - Multi-step conversation management
    - Category-based conversation routing
    - Context-aware response generation
    - Intelligent state transitions
    - Multiple concurrent conversations per user
    """
    
    def __init__(self):
        """Initialize the flow handler"""
        self.categories = [
            "Technical Support", "Billing", "Account Issues", 
            "Feature Request", "General Inquiry", "Bug Report", "Other"
        ]
        self.max_conversations_per_user = 5
    
    def handle_incoming_message(self, message_data: Dict[str, Any], bot_doc) -> Dict[str, Any]:
        """
        Main entry point for handling incoming messages.
        
        Args:
            message_data: Raw Telegram message data
            bot_doc: HD Telegram Bot document
            
        Returns:
            Dict with processing result and response
        """
        try:
            user_data = message_data.get("from", {})
            user_id = cstr(user_data.get("id"))
            message_text = message_data.get("text", "").strip()
            
            frappe.logger().info(f"🔄 Interactive Flow Handler processing message from user {user_id}")
            frappe.logger().debug(f"Bot doc: {bot_doc.name if bot_doc else 'None'}")
            
            # Handle bot commands first
            if message_text.startswith("/"):
                frappe.logger().info(f"🔧 Handling command: {message_text}")
                return self._handle_command(message_data, bot_doc)
            
            # Check for active conversations
            frappe.logger().debug("🔍 Checking for active conversations...")
            active_conversation = self._get_active_conversation(user_id)
            
            if active_conversation:
                # Continue existing conversation
                frappe.logger().info(f"📝 Continuing conversation {active_conversation['conversation_group_id']}")
                return self._continue_conversation(message_data, active_conversation, bot_doc)
            else:
                # Start new conversation
                frappe.logger().info(f"🆕 Starting new conversation for user {user_id}")
                return self._start_new_conversation(message_data, bot_doc)
        
        except Exception as e:
            frappe.log_error(f"Interactive Flow Handler Error: {str(e)}")
            return {
                "success": False,
                "error": "flow_handler_error",
                "message": str(e)
            }
    
    def _handle_command(self, message_data: Dict[str, Any], bot_doc) -> Dict[str, Any]:
        """Handle bot commands"""
        try:
            from helpdesk.helpdesk.utils.command_handler import handle_telegram_command
            return handle_telegram_command(message_data)
        except Exception as e:
            frappe.log_error(f"Command handling error: {str(e)}")
            return {"success": False, "message": "Command processing failed"}
    
    def _get_active_conversation(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get active conversation for user"""
        try:
            from helpdesk.helpdesk.doctype.hd_telegram_message.hd_telegram_message import get_active_conversation
            return get_active_conversation(user_id)
        except Exception as e:
            frappe.log_error(f"Error getting active conversation: {str(e)}")
            return None
    
    def _start_new_conversation(self, message_data: Dict[str, Any], bot_doc) -> Dict[str, Any]:
        """Start a new conversation flow"""
        try:
            user_data = message_data.get("from", {})
            user_id = cstr(user_data.get("id"))
            message_text = message_data.get("text", "").strip()
            
            frappe.logger().debug(f"Starting new conversation for user {user_id} with text: '{message_text}'")
            
            # Detect category from message
            detected_category = self._detect_category(message_text)
            frappe.logger().debug(f"Detected category: {detected_category}")
            
            # Create message and start conversation
            from helpdesk.helpdesk.doctype.hd_telegram_message.hd_telegram_message import start_new_conversation
            frappe.logger().debug(f"Calling start_new_conversation with bot_doc: {bot_doc.name if bot_doc else 'None'}")
            result = start_new_conversation(user_id, message_data, detected_category, bot_doc)
            
            frappe.logger().debug(f"start_new_conversation result: {result}")
            
            if result.get("success"):
                conversation_result = result.get("conversation_result", {})
                
                # Generate welcome response
                response = self._generate_welcome_response(detected_category, message_text)
                
                return {
                    "success": True,
                    "response_message": response,
                    "conversation_started": True,
                    "conversation_group_id": conversation_result.get("conversation_group_id"),
                    "next_state": "waiting_for_problem",
                    "parse_mode": "Markdown"
                }
            else:
                frappe.logger().error(f"start_new_conversation failed: {result}")
                return result
        
        except Exception as e:
            frappe.log_error(f"Error starting new conversation: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def _continue_conversation(self, message_data: Dict[str, Any], active_conversation: Dict[str, Any], bot_doc) -> Dict[str, Any]:
        """Continue an existing conversation"""
        try:
            user_id = cstr(message_data.get("from", {}).get("id"))
            message_text = message_data.get("text", "").strip()
            current_state = active_conversation.get("conversation_state")
            
            frappe.logger().info(f"📝 Continuing conversation in state: {current_state}")
            
            # Store the new message
            message_result = self._store_conversation_message(message_data, active_conversation)
            
            if not message_result.get("success"):
                return message_result
            
            # Process based on current state
            return self._process_conversation_state(
                message_text, 
                active_conversation, 
                message_result.get("message_doc"),
                bot_doc
            )
        
        except Exception as e:
            frappe.log_error(f"Error continuing conversation: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def _store_conversation_message(self, message_data: Dict[str, Any], active_conversation: Dict[str, Any]) -> Dict[str, Any]:
        """Store incoming message in conversation"""
        try:
            # Create message document
            from helpdesk.helpdesk.doctype.hd_telegram_message.hd_telegram_message import create_telegram_message
            
            message_result = create_telegram_message({"message": message_data}, bot_doc.bot_name)
            
            if message_result.get("success"):
                # Update message with conversation context
                message_doc = frappe.get_doc("HD Telegram Message", message_result.get("message_name"))
                message_doc.conversation_group_id = active_conversation.get("conversation_group_id")
                message_doc.conversation_state = active_conversation.get("conversation_state")
                message_doc.conversation_category = active_conversation.get("conversation_category")
                message_doc.save(ignore_permissions=True)
                
                return {
                    "success": True,
                    "message_doc": message_doc
                }
            else:
                return message_result
        
        except Exception as e:
            frappe.log_error(f"Error storing conversation message: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def _process_conversation_state(self, message_text: str, active_conversation: Dict[str, Any], 
                                  message_doc, bot_doc) -> Dict[str, Any]:
        """Process message based on conversation state"""
        current_state = active_conversation.get("conversation_state")
        
        state_handlers = {
            "waiting_for_problem": self._handle_problem_description,
            "waiting_for_details": self._handle_additional_details,
            "waiting_for_priority": self._handle_priority_selection,
            "collecting_info": self._handle_info_collection,
            "ready_for_ticket": self._handle_ticket_creation
        }
        
        handler = state_handlers.get(current_state, self._handle_unknown_state)
        return handler(message_text, active_conversation, message_doc, bot_doc)
    
    def _handle_problem_description(self, message_text: str, active_conversation: Dict[str, Any], 
                                  message_doc, bot_doc) -> Dict[str, Any]:
        """Handle problem description input"""
        try:
            # Store problem description
            context_update = {
                "collected_info": {
                    "problem_description": message_text,
                    "problem_timestamp": now_datetime().isoformat()
                }
            }
            
            # Update conversation state
            message_doc.update_conversation_state("waiting_for_details", context_update)
            
            # Generate response
            response = (
                f"✅ **Got it!** I understand you're having issues with: *{message_text[:100]}{'...' if len(message_text) > 100 else ''}*\n\n"
                f"📝 **Can you provide any additional details?**\n\n"
                f"For example:\n"
                f"• When did this start happening?\n"
                f"• What steps led to this issue?\n"
                f"• Any error messages you've seen?\n\n"
                f"*Or type 'skip' if you don't have more details.*"
            )
            
            return {
                "success": True,
                "response_message": response,
                "next_state": "waiting_for_details",
                "parse_mode": "Markdown"
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling problem description: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def _handle_additional_details(self, message_text: str, active_conversation: Dict[str, Any], 
                                 message_doc, bot_doc) -> Dict[str, Any]:
        """Handle additional details input"""
        try:
            # Get existing context
            existing_context = message_doc.get_conversation_context()
            
            # Store additional details
            if message_text.lower() != "skip":
                existing_context["collected_info"]["additional_details"] = message_text
            
            # Update conversation state
            message_doc.update_conversation_state("waiting_for_priority", {"collected_info": existing_context["collected_info"]})
            
            # Generate priority selection response
            response = (
                f"📋 **Perfect!** Now let's prioritize your request.\n\n"
                f"⚡ **How urgent is this issue?**\n\n"
                f"Please choose:\n"
                f"• **High** - Urgent/Critical (system down, blocking work)\n"
                f"• **Medium** - Normal priority (can work around it)\n"
                f"• **Low** - When convenient (nice to have)\n\n"
                f"*Just reply with: High, Medium, or Low*"
            )
            
            return {
                "success": True,
                "response_message": response,
                "next_state": "waiting_for_priority",
                "parse_mode": "Markdown"
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling additional details: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def _handle_priority_selection(self, message_text: str, active_conversation: Dict[str, Any], 
                                 message_doc, bot_doc) -> Dict[str, Any]:
        """Handle priority selection"""
        try:
            # Parse priority
            priority = self._parse_priority(message_text)
            
            # Get existing context
            existing_context = message_doc.get_conversation_context()
            existing_context["collected_info"]["priority"] = priority
            
            # Update conversation state
            message_doc.update_conversation_state("ready_for_ticket", {"collected_info": existing_context["collected_info"]})
            
            # Create ticket
            return self._create_ticket_from_conversation(active_conversation, message_doc, bot_doc)
            
        except Exception as e:
            frappe.log_error(f"Error handling priority selection: {str(e)}")
            return {"success": False, "message": str(e)}
    
    def _handle_info_collection(self, message_text: str, active_conversation: Dict[str, Any], 
                              message_doc, bot_doc) -> Dict[str, Any]:
        """Handle additional info collection"""
        # This can be extended for more complex flows
        return self._handle_additional_details(message_text, active_conversation, message_doc, bot_doc)
    
    def _handle_ticket_creation(self, message_text: str, active_conversation: Dict[str, Any], 
                              message_doc, bot_doc) -> Dict[str, Any]:
        """Handle ticket creation state"""
        return self._create_ticket_from_conversation(active_conversation, message_doc, bot_doc)
    
    def _handle_unknown_state(self, message_text: str, active_conversation: Dict[str, Any], 
                            message_doc, bot_doc) -> Dict[str, Any]:
        """Handle unknown conversation state"""
        response = (
            "🤔 I'm not sure how to help with that right now.\n\n"
            "Let me start fresh - what can I help you with today?"
        )
        
        # Reset conversation
        message_doc.update_conversation_state("waiting_for_problem")
        
        return {
            "success": True,
            "response_message": response,
            "next_state": "waiting_for_problem"
        }
    
    def _create_ticket_from_conversation(self, active_conversation: Dict[str, Any], 
                                       message_doc, bot_doc) -> Dict[str, Any]:
        """Create ticket from conversation"""
        try:
            conversation_group_id = active_conversation.get("conversation_group_id")
            
            # Create ticket
            from helpdesk.helpdesk.doctype.hd_telegram_message.hd_telegram_message import create_ticket_from_conversation
            ticket_result = create_ticket_from_conversation(conversation_group_id)
            
            if ticket_result.get("success"):
                ticket_id = ticket_result.get("ticket")
                
                # Generate success response
                response = (
                    f"🎫 **Ticket Created Successfully!**\n\n"
                    f"📝 **Ticket ID:** {ticket_id}\n"
                    f"📋 **Subject:** {ticket_result.get('subject', 'Support Request')}\n"
                    f"⚡ **Priority:** {message_doc.get_conversation_context().get('collected_info', {}).get('priority', 'Medium')}\n\n"
                    f"✅ Our support team will review your request and respond soon.\n\n"
                    f"💬 You can check your ticket status anytime by typing `/status {ticket_id}`\n\n"
                    f"🆕 Need help with something else? Just send me a new message!"
                )
                
                return {
                    "success": True,
                    "response_message": response,
                    "ticket_created": True,
                    "ticket_id": ticket_id,
                    "conversation_completed": True,
                    "parse_mode": "Markdown"
                }
            else:
                # Fallback to old ticket creation method
                return self._fallback_ticket_creation(message_doc, bot_doc)
                
        except Exception as e:
            frappe.log_error(f"Error creating ticket from conversation: {str(e)}")
            return self._fallback_ticket_creation(message_doc, bot_doc)
    
    def _fallback_ticket_creation(self, message_doc, bot_doc) -> Dict[str, Any]:
        """Fallback ticket creation using old method"""
        try:
            from helpdesk.helpdesk.utils.ticket_creator import create_ticket_from_telegram_message
            
            # Get conversation messages
            conversation_summary = message_doc.get_conversation_summary()
            
            # Create a synthetic message for ticket creation
            synthetic_message = {
                "message_id": message_doc.message_id,
                "from": {
                    "id": frappe.get_value("HD Telegram User", message_doc.telegram_user, "telegram_user_id")
                },
                "chat": {"id": conversation_summary.get("chat_id")},
                "date": message_doc.message_date.timestamp(),
                "text": conversation_summary.get("problem_description", "Support request from conversation")
            }
            
            result = create_ticket_from_telegram_message(synthetic_message)
            
            if result.get("success"):
                # Mark conversation as completed
                message_doc.complete_conversation(result.get("ticket"))
                
                response = (
                    f"🎫 **Support Ticket Created!**\n\n"
                    f"📝 **Ticket:** {result.get('ticket')}\n\n"
                    f"Our team will respond soon. Thank you!"
                )
                
                return {
                    "success": True,
                    "response_message": response,
                    "ticket_created": True,
                    "ticket_id": result.get("ticket"),
                    "parse_mode": "Markdown"
                }
            else:
                return result
                
        except Exception as e:
            frappe.log_error(f"Fallback ticket creation failed: {str(e)}")
            return {"success": False, "message": "Failed to create ticket"}
    
    def _detect_category(self, message_text: str) -> str:
        """Detect issue category from message text"""
        category_keywords = {
            "Technical Support": ["error", "bug", "broken", "not working", "issue", "problem", "technical"],
            "Billing": ["payment", "bill", "invoice", "charge", "subscription", "refund", "billing"],
            "Account Issues": ["login", "password", "account", "access", "locked", "forgot", "signin"],
            "Feature Request": ["feature", "enhancement", "request", "suggestion", "improve", "add"],
            "Bug Report": ["bug", "error", "crash", "broken", "malfunction", "defect"],
            "General Inquiry": ["question", "help", "how", "what", "info", "information"]
        }
        
        text_lower = message_text.lower()
        
        for category, keywords in category_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return category
        
        return "General Inquiry"
    
    def _parse_priority(self, message_text: str) -> str:
        """Parse priority from user input"""
        text_lower = message_text.lower().strip()
        
        if any(word in text_lower for word in ["high", "urgent", "critical", "emergency"]):
            return "High"
        elif any(word in text_lower for word in ["low", "minor", "whenever"]):
            return "Low"
        else:
            return "Medium"
    
    def _generate_welcome_response(self, detected_category: str, message_text: str) -> str:
        """Generate welcome response for new conversation"""
        if len(message_text) < 10:
            # Short message - ask for more details
            return (
                f"👋 **Hello!** I'm here to help you with your {detected_category.lower()}.\n\n"
                f"🤔 **What specifically can I help you with today?**\n\n"
                f"Please describe your problem or question in detail so I can create the right support ticket for you."
            )
        else:
            # Longer message - acknowledge and ask for details
            return (
                f"👋 **Hello!** Thanks for reaching out about your {detected_category.lower()}.\n\n"
                f"📝 I see you mentioned: *{message_text[:100]}{'...' if len(message_text) > 100 else ''}*\n\n"
                f"🤔 **Can you tell me more about what you need help with?**\n\n"
                f"The more details you provide, the better I can assist you!"
            )


# Utility functions for external use

def handle_interactive_message(message_data: Dict[str, Any], bot_doc) -> Dict[str, Any]:
    """
    Main function to handle interactive message flow.
    
    Args:
        message_data: Raw Telegram message data
        bot_doc: HD Telegram Bot document
        
    Returns:
        Processing result with response
    """
    handler = InteractiveFlowHandler()
    return handler.handle_incoming_message(message_data, bot_doc)


def get_user_conversation_status(user_id: str) -> Dict[str, Any]:
    """Get current conversation status for a user"""
    try:
        from helpdesk.helpdesk.doctype.hd_telegram_message.hd_telegram_message import get_user_conversations
        conversations = get_user_conversations(user_id, limit=5)
        
        active_conversations = [
            conv for conv in conversations 
            if conv.get("conversation_state") not in ["idle", "ticket_created"]
        ]
        
        return {
            "total_conversations": len(conversations),
            "active_conversations": len(active_conversations),
            "recent_conversations": conversations[:3],
            "can_start_new": len(active_conversations) < 5
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting conversation status: {str(e)}")
        return {"error": str(e)} 