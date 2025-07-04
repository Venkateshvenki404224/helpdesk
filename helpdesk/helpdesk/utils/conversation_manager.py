#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Conversation State Manager for Helpdesk Integration

This module manages conversation states, tracks user dialogues, and handles
interactive flows for ticket creation from Telegram messages.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cstr, add_to_date, get_datetime
from typing import Dict, Any, Optional, List
import json
from enum import Enum


class ConversationState(Enum):
    """Conversation state enumeration"""
    IDLE = "idle"                          # User not in conversation
    WAITING_FOR_PROBLEM = "waiting_for_problem"  # Asked what they need help with
    WAITING_FOR_DETAILS = "waiting_for_details"  # Asked for more details
    WAITING_FOR_PRIORITY = "waiting_for_priority"  # Asked about urgency
    CREATING_TICKET = "creating_ticket"    # Processing ticket creation
    TICKET_CREATED = "ticket_created"      # Ticket successfully created


class ConversationStateManager:
    """
    Manages conversation states for Telegram users and handles interactive flows.
    
    Features:
    - Track user conversation states
    - Manage conversation timeouts
    - Handle state transitions
    - Store conversation context and history
    """
    
    def __init__(self):
        """Initialize conversation state manager"""
        self.default_timeout_minutes = 30  # Default conversation timeout
        self.max_messages_per_conversation = 20  # Prevent spam
    
    def get_user_state(self, telegram_user_id: str) -> Dict[str, Any]:
        """
        Get current conversation state for a user.
        
        Args:
            telegram_user_id: Telegram user ID
            
        Returns:
            Dict with state information
        """
        try:
            # Check for active conversation
            conversation = self._get_active_conversation(telegram_user_id)
            
            if conversation:
                return {
                    'state': conversation.get('conversation_state', ConversationState.IDLE.value),
                    'conversation_id': conversation.get('name'),
                    'context': self._parse_conversation_context(conversation.get('context_data', '{}')),
                    'message_count': conversation.get('message_count', 0),
                    'started_at': conversation.get('started_at'),
                    'last_activity': conversation.get('last_activity'),
                    'timeout_at': conversation.get('timeout_at')
                }
            else:
                return {
                    'state': ConversationState.IDLE.value,
                    'conversation_id': None,
                    'context': {},
                    'message_count': 0,
                    'started_at': None,
                    'last_activity': None,
                    'timeout_at': None
                }
        except Exception as e:
            frappe.log_error(f"Error getting user state: {str(e)}")
            return {
                'state': ConversationState.IDLE.value,
                'conversation_id': None,
                'context': {},
                'message_count': 0,
                'started_at': None,
                'last_activity': None,
                'timeout_at': None
            }
    
    def start_conversation(self, telegram_user_id: str, initial_message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start a new conversation for a user.
        
        Args:
            telegram_user_id: Telegram user ID
            initial_message: Initial message that triggered conversation
            
        Returns:
            Dict with conversation start result
        """
        try:
            # Check if user already has active conversation
            existing_state = self.get_user_state(telegram_user_id)
            if existing_state['state'] != ConversationState.IDLE.value:
                # Continue existing conversation
                return self.add_message_to_conversation(
                    existing_state['conversation_id'], 
                    initial_message
                )
            
            # Create new conversation
            conversation_id = self._create_conversation(telegram_user_id, initial_message)
            
            if conversation_id:
                return {
                    'success': True,
                    'conversation_id': conversation_id,
                    'state': ConversationState.WAITING_FOR_PROBLEM.value,
                    'next_prompt': self._get_initial_prompt(telegram_user_id)
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to create conversation'
                }
        
        except Exception as e:
            frappe.log_error(f"Error starting conversation: {str(e)}")
            return {
                'success': False,
                'message': str(e)
            }
    
    def update_conversation_state(self, conversation_id: str, new_state: ConversationState, 
                                context_update: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update conversation state and context.
        
        Args:
            conversation_id: Conversation ID
            new_state: New conversation state
            context_update: Optional context data to merge
            
        Returns:
            Success status
        """
        try:
            conversation = frappe.get_doc("HD Telegram Conversation", conversation_id)
            
            # Update state
            conversation.conversation_state = new_state.value
            conversation.last_activity = now_datetime()
            
            # Update timeout
            conversation.timeout_at = add_to_date(now_datetime(), minutes=self.default_timeout_minutes)
            
            # Update context if provided
            if context_update:
                existing_context = self._parse_conversation_context(conversation.context_data or '{}')
                existing_context.update(context_update)
                conversation.context_data = json.dumps(existing_context)
            
            conversation.save()
            return True
            
        except Exception as e:
            frappe.log_error(f"Error updating conversation state: {str(e)}")
            return False
    
    def add_message_to_conversation(self, conversation_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add a message to an existing conversation.
        
        Args:
            conversation_id: Conversation ID
            message_data: Message data from Telegram
            
        Returns:
            Dict with add message result
        """
        try:
            conversation = frappe.get_doc("HD Telegram Conversation", conversation_id)
            
            # Check if conversation is still active
            if conversation.is_expired or conversation.is_completed:
                return {
                    'success': False,
                    'conversation_expired': True,
                    'message': 'Conversation has expired or completed'
                }
            
            # Check message limit
            if conversation.message_count >= self.max_messages_per_conversation:
                return {
                    'success': False,
                    'message_limit_exceeded': True,
                    'message': 'Too many messages in conversation'
                }
            
            # Update conversation
            conversation.message_count += 1
            conversation.last_activity = now_datetime()
            conversation.timeout_at = add_to_date(now_datetime(), minutes=self.default_timeout_minutes)
            conversation.save()
            
            # Store the message
            message_result = self._store_conversation_message(conversation_id, message_data)
            
            return {
                'success': True,
                'message_stored': message_result,
                'current_state': conversation.conversation_state,
                'message_count': conversation.message_count
            }
            
        except Exception as e:
            frappe.log_error(f"Error adding message to conversation: {str(e)}")
            return {
                'success': False,
                'message': str(e)
            }
    
    def complete_conversation(self, conversation_id: str, ticket_id: Optional[str] = None) -> bool:
        """
        Mark conversation as completed.
        
        Args:
            conversation_id: Conversation ID
            ticket_id: Optional ticket ID if ticket was created
            
        Returns:
            Success status
        """
        try:
            conversation = frappe.get_doc("HD Telegram Conversation", conversation_id)
            
            conversation.is_completed = 1
            conversation.completed_at = now_datetime()
            conversation.conversation_state = ConversationState.TICKET_CREATED.value
            
            if ticket_id:
                conversation.resulting_ticket = ticket_id
            
            conversation.save()
            return True
            
        except Exception as e:
            frappe.log_error(f"Error completing conversation: {str(e)}")
            return False
    
    def expire_conversation(self, conversation_id: str) -> bool:
        """
        Mark conversation as expired.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Success status
        """
        try:
            conversation = frappe.get_doc("HD Telegram Conversation", conversation_id)
            
            conversation.is_expired = 1
            conversation.expired_at = now_datetime()
            conversation.save()
            return True
            
        except Exception as e:
            frappe.log_error(f"Error expiring conversation: {str(e)}")
            return False
    
    def cleanup_expired_conversations(self) -> int:
        """
        Clean up expired conversations.
        
        Returns:
            Number of conversations cleaned up
        """
        try:
            # Find expired conversations
            expired_conversations = frappe.db.sql("""
                SELECT name 
                FROM `tabHD Telegram Conversation`
                WHERE is_expired = 0 
                AND is_completed = 0
                AND timeout_at < %s
            """, (now_datetime(),), as_dict=True)
            
            count = 0
            for conv in expired_conversations:
                if self.expire_conversation(conv['name']):
                    count += 1
            
            return count
            
        except Exception as e:
            frappe.log_error(f"Error cleaning up expired conversations: {str(e)}")
            return 0
    
    def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get conversation summary for ticket creation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Dict with conversation summary
        """
        try:
            conversation = frappe.get_doc("HD Telegram Conversation", conversation_id)
            
            # Get all messages in conversation
            messages = frappe.db.sql("""
                SELECT message_content, message_type, created_on
                FROM `tabHD Telegram Message`
                WHERE conversation_id = %s
                ORDER BY created_on ASC
            """, (conversation_id,), as_dict=True)
            
            # Parse context
            context = self._parse_conversation_context(conversation.context_data or '{}')
            
            # Compile summary
            return {
                'conversation_id': conversation_id,
                'telegram_user': conversation.telegram_user,
                'problem_description': context.get('problem_description', ''),
                'additional_details': context.get('additional_details', ''),
                'urgency_level': context.get('urgency_level', 'medium'),
                'message_count': conversation.message_count,
                'duration_minutes': self._calculate_conversation_duration(conversation),
                'all_messages': messages,
                'started_at': conversation.started_at,
                'context': context
            }
            
        except Exception as e:
            frappe.log_error(f"Error getting conversation summary: {str(e)}")
            return {}
    
    def _get_active_conversation(self, telegram_user_id: str) -> Optional[Dict[str, Any]]:
        """Get active conversation for user"""
        try:
            # Get HD Telegram User
            telegram_user = frappe.db.get_value(
                "HD Telegram User", 
                {"telegram_user_id": cstr(telegram_user_id)}, 
                "name"
            )
            
            if not telegram_user:
                return None
            
            # Find active conversation
            conversation = frappe.db.get_value(
                "HD Telegram Conversation",
                {
                    "telegram_user": telegram_user,
                    "is_completed": 0,
                    "is_expired": 0
                },
                ["name", "conversation_state", "context_data", "message_count", 
                 "started_at", "last_activity", "timeout_at"],
                as_dict=True,
                order_by="started_at desc"
            )
            
            return conversation
            
        except Exception as e:
            frappe.log_error(f"Error getting active conversation: {str(e)}")
            return None
    
    def _create_conversation(self, telegram_user_id: str, initial_message: Dict[str, Any]) -> Optional[str]:
        """Create new conversation record"""
        try:
            # Get or create telegram user
            from helpdesk.helpdesk.doctype.hd_telegram_user.hd_telegram_user import get_or_create_telegram_user
            telegram_user = get_or_create_telegram_user(initial_message.get('from', {}))
            
            # Create conversation
            conversation = frappe.get_doc({
                'doctype': 'HD Telegram Conversation',
                'telegram_user': telegram_user.name,
                'chat_id': cstr(initial_message.get('chat', {}).get('id')),
                'conversation_state': ConversationState.WAITING_FOR_PROBLEM.value,
                'started_at': now_datetime(),
                'last_activity': now_datetime(),
                'timeout_at': add_to_date(now_datetime(), minutes=self.default_timeout_minutes),
                'message_count': 0,
                'context_data': json.dumps({'initial_message_id': initial_message.get('message_id')}),
                'is_completed': 0,
                'is_expired': 0
            })
            
            conversation.insert()
            return conversation.name
            
        except Exception as e:
            frappe.log_error(f"Error creating conversation: {str(e)}")
            return None
    
    def _store_conversation_message(self, conversation_id: str, message_data: Dict[str, Any]) -> bool:
        """Store message in conversation"""
        try:
            # This will be enhanced to use the message storage system
            # For now, just update the conversation with the latest message
            return True
            
        except Exception as e:
            frappe.log_error(f"Error storing conversation message: {str(e)}")
            return False
    
    def _parse_conversation_context(self, context_data: str) -> Dict[str, Any]:
        """Parse conversation context JSON"""
        try:
            return json.loads(context_data) if context_data else {}
        except:
            return {}
    
    def _get_initial_prompt(self, telegram_user_id: str) -> str:
        """Get initial conversation prompt"""
        return ("👋 Hello! I'm here to help you with any technical issues or questions.\n\n"
                "🤔 **What do you need help with today?**\n\n"
                "Please describe your problem or question in detail, and I'll create a support ticket for you.")
    
    def _calculate_conversation_duration(self, conversation) -> int:
        """Calculate conversation duration in minutes"""
        try:
            if conversation.started_at and conversation.last_activity:
                delta = get_datetime(conversation.last_activity) - get_datetime(conversation.started_at)
                return int(delta.total_seconds() / 60)
        except:
            pass
        return 0


# Utility functions for external use

def get_user_conversation_state(telegram_user_id: str) -> Dict[str, Any]:
    """Get current conversation state for a user"""
    manager = ConversationStateManager()
    return manager.get_user_state(telegram_user_id)


def start_user_conversation(telegram_user_id: str, initial_message: Dict[str, Any]) -> Dict[str, Any]:
    """Start conversation for a user"""
    manager = ConversationStateManager()
    return manager.start_conversation(telegram_user_id, initial_message)


def cleanup_expired_conversations():
    """Background job to cleanup expired conversations"""
    manager = ConversationStateManager()
    count = manager.cleanup_expired_conversations()
    frappe.logger().info(f"Cleaned up {count} expired conversations")
    return count 