#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Command Handler for Helpdesk Integration

This module provides command handling functionality for Telegram bot commands,
including help system, user state management, and multi-language support.
"""

import re
from typing import Dict, Any, Optional, List, Tuple, Callable
import frappe
from frappe import _
from frappe.utils import now, get_datetime, cstr, cint

from helpdesk.helpdesk.utils.user_mapper import TelegramUserMapper
from helpdesk.helpdesk.utils.telegram_client import TelegramBotClient


class TelegramCommandHandler:
    """
    Handles Telegram bot commands with multi-language support and state management.
    
    Supports:
    - /start - Welcome and onboarding
    - /help - Context-aware help system  
    - /status - Ticket status queries
    - /mytickets - User ticket history
    - /cancel - Cancel current operation
    - /settings - User preferences
    """
    
    def __init__(self):
        """Initialize the command handler."""
        self.settings = self._get_handler_settings()
        self.user_mapper = TelegramUserMapper()
        self.commands = self._register_commands()
    
    def _get_handler_settings(self) -> Dict[str, Any]:
        """Get command handler settings from system configuration."""
        try:
            settings = frappe.get_single('HD Telegram Bot')
            return {
                'default_language': getattr(settings, 'default_language', 'en'),
                'support_languages': getattr(settings, 'support_languages', 'en,es,fr').split(','),
                'welcome_message': getattr(settings, 'welcome_message', ''),
                'help_message': getattr(settings, 'help_message', ''),
                'company_name': getattr(settings, 'company_name', 'Helpdesk'),
                'support_hours': getattr(settings, 'support_hours', '24/7'),
                'response_time': getattr(settings, 'response_time', '2-4 hours'),
                'enable_user_states': getattr(settings, 'enable_user_states', 1),
                'max_tickets_per_page': getattr(settings, 'max_tickets_per_page', 5),
            }
        except Exception:
            # Default settings if no bot configured
            return {
                'default_language': 'en',
                'support_languages': ['en'],
                'welcome_message': '',
                'help_message': '',
                'company_name': 'Helpdesk',
                'support_hours': '24/7',
                'response_time': '2-4 hours',
                'enable_user_states': True,
                'max_tickets_per_page': 5,
            }
    
    def _register_commands(self) -> Dict[str, Callable]:
        """Register available commands with their handlers."""
        return {
            'start': self.handle_start_command,
            'help': self.handle_help_command,
            'status': self.handle_status_command,
            'mytickets': self.handle_mytickets_command,
            'cancel': self.handle_cancel_command,
            'settings': self.handle_settings_command,
            'verify': self.handle_verify_command,
            'language': self.handle_language_command,
        }
    
    def handle_command(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming command message.
        
        Args:
            message_data: Telegram message data
            
        Returns:
            Dict containing command handling result
        """
        try:
            # Extract command and parameters
            text = message_data.get('text', '')
            command_info = self._parse_command(text)
            
            if not command_info:
                return {
                    'success': False,
                    'error': 'invalid_command',
                    'message': 'Invalid command format'
                }
            
            command = command_info['command']
            parameters = command_info['parameters']
            
            # Get user information
            telegram_user_data = message_data.get('from', {})
            user_context = self._get_user_context(telegram_user_data)
            
            # Check if command exists
            if command not in self.commands:
                return self._handle_unknown_command(command, user_context, message_data)
            
            # Execute command
            return self.commands[command](
                parameters=parameters,
                user_context=user_context,
                message_data=message_data
            )
            
        except Exception as e:
            frappe.log_error(
                message=f"Failed to handle Telegram command: {str(e)}",
                title="Telegram Command Handler Error"
            )
            return {
                'success': False,
                'error': 'command_failed',
                'message': 'Command execution failed'
            }
    
    def _parse_command(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse command text to extract command and parameters."""
        if not text.startswith('/'):
            return None
        
        # Remove the leading slash
        text = text[1:]
        
        # Split command and parameters
        parts = text.split(' ', 1)
        command = parts[0].lower()
        parameters = parts[1] if len(parts) > 1 else ''
        
        # Remove bot username if present (e.g., /start@botname)
        if '@' in command:
            command = command.split('@')[0]
        
        return {
            'command': command,
            'parameters': parameters.strip()
        }
    
    def _get_user_context(self, telegram_user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Get user context including language, state, and preferences."""
        telegram_user_id = telegram_user_data.get('id')
        
        try:
            # Try to get existing user record
            telegram_user = frappe.get_doc('HD Telegram User', {
                'telegram_user_id': telegram_user_id
            })
            
            return {
                'telegram_user_id': telegram_user_id,
                'telegram_user_name': telegram_user.name,
                'language': telegram_user.language_code or self.settings['default_language'],
                'is_verified': telegram_user.is_verified,
                'customer': telegram_user.customer,
                'contact': telegram_user.contact,
                'current_state': getattr(telegram_user, 'current_state', 'idle'),
                'state_data': getattr(telegram_user, 'state_data', {}),
                'first_name': telegram_user.first_name,
                'is_new_user': False
            }
            
        except frappe.DoesNotExistError:
            # New user
            language = telegram_user_data.get('language_code', self.settings['default_language'])
            return {
                'telegram_user_id': telegram_user_id,
                'telegram_user_name': None,
                'language': language,
                'is_verified': False,
                'customer': None,
                'contact': None,
                'current_state': 'new',
                'state_data': {},
                'first_name': telegram_user_data.get('first_name', 'User'),
                'is_new_user': True
            }
        except Exception as e:
            frappe.log_error(f"Error getting user context: {str(e)}")
            return {
                'telegram_user_id': telegram_user_id,
                'language': self.settings['default_language'],
                'is_verified': False,
                'is_new_user': True,
                'first_name': telegram_user_data.get('first_name', 'User')
            }
    
    def handle_start_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /start command - welcome and onboarding."""
        try:
            language = user_context.get('language', 'en')
            first_name = user_context.get('first_name', 'User')
            
            if user_context.get('is_new_user'):
                # New user onboarding
                message = self._get_welcome_message(language, first_name, is_new=True)
                
                # Create user record if auto-creation is enabled
                if self.user_mapper.settings.get('auto_create_customers'):
                    telegram_user_data = message_data.get('from', {})
                    self.user_mapper.resolve_user(telegram_user_data, message_data)
            else:
                # Returning user
                message = self._get_welcome_message(language, first_name, is_new=False)
            
            return {
                'success': True,
                'message': message,
                'parse_mode': 'Markdown'
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling start command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def handle_help_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /help command - context-aware help system."""
        try:
            language = user_context.get('language', 'en')
            current_state = user_context.get('current_state', 'idle')
            
            if parameters:
                # Specific help topic requested
                message = self._get_topic_help(parameters, language)
            else:
                # General help based on user state
                message = self._get_contextual_help(current_state, language, user_context)
            
            return {
                'success': True,
                'message': message,
                'parse_mode': 'Markdown'
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling help command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def handle_status_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /status command - ticket status queries."""
        try:
            language = user_context.get('language', 'en')
            
            if not user_context.get('is_verified'):
                return {
                    'success': False,
                    'message': self._get_text('verification_required', language),
                    'verification_required': True
                }
            
            if not parameters:
                return {
                    'success': False,
                    'message': self._get_text('status_usage', language),
                    'parse_mode': 'Markdown'
                }
            
            # Extract ticket number
            ticket_number = parameters.strip()
            
            # Get ticket information
            ticket_info = self._get_ticket_status(ticket_number, user_context)
            
            if not ticket_info:
                return {
                    'success': False,
                    'message': self._get_text('ticket_not_found', language).format(ticket=ticket_number)
                }
            
            # Format status message
            message = self._format_ticket_status(ticket_info, language)
            
            return {
                'success': True,
                'message': message,
                'parse_mode': 'Markdown'
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling status command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def handle_mytickets_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /mytickets command - user ticket history."""
        try:
            language = user_context.get('language', 'en')
            
            if not user_context.get('is_verified'):
                return {
                    'success': False,
                    'message': self._get_text('verification_required', language),
                    'verification_required': True
                }
            
            # Parse parameters for filtering
            filter_params = self._parse_ticket_filters(parameters)
            
            # Get user tickets
            tickets = self._get_user_tickets(user_context, filter_params)
            
            if not tickets:
                return {
                    'success': True,
                    'message': self._get_text('no_tickets_found', language)
                }
            
            # Format ticket list
            message = self._format_ticket_list(tickets, language, filter_params)
            
            return {
                'success': True,
                'message': message,
                'parse_mode': 'Markdown'
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling mytickets command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def handle_cancel_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /cancel command - cancel current operation."""
        try:
            language = user_context.get('language', 'en')
            
            # Clear user state if any
            if user_context.get('telegram_user_name'):
                self._set_user_state(user_context['telegram_user_name'], 'idle', {})
            
            return {
                'success': True,
                'message': self._get_text('operation_cancelled', language)
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling cancel command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def handle_settings_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /settings command - user preferences."""
        try:
            language = user_context.get('language', 'en')
            
            if parameters:
                # Handle specific setting change
                return self._handle_setting_change(parameters, user_context)
            else:
                # Show current settings
                message = self._get_user_settings(user_context, language)
                
                return {
                    'success': True,
                    'message': message,
                    'parse_mode': 'Markdown'
                }
            
        except Exception as e:
            frappe.log_error(f"Error handling settings command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def handle_verify_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /verify command - phone verification."""
        try:
            language = user_context.get('language', 'en')
            
            if not user_context.get('telegram_user_name'):
                return {
                    'success': False,
                    'message': self._get_text('user_not_registered', language)
                }
            
            if user_context.get('is_verified'):
                return {
                    'success': True,
                    'message': self._get_text('already_verified', language)
                }
            
            if not parameters:
                # Start verification process
                return self._start_phone_verification(user_context, language)
            else:
                # Confirm verification code
                return self._confirm_phone_verification(parameters, user_context, language)
            
        except Exception as e:
            frappe.log_error(f"Error handling verify command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def handle_language_command(self, parameters: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /language command - change user language."""
        try:
            current_language = user_context.get('language', 'en')
            
            if not parameters:
                # Show available languages
                message = self._get_available_languages(current_language)
                return {
                    'success': True,
                    'message': message,
                    'parse_mode': 'Markdown'
                }
            
            # Set new language
            new_language = parameters.strip().lower()
            
            if new_language not in self.settings['support_languages']:
                return {
                    'success': False,
                    'message': self._get_text('unsupported_language', current_language)
                }
            
            # Update user language
            if user_context.get('telegram_user_name'):
                frappe.db.set_value(
                    'HD Telegram User',
                    user_context['telegram_user_name'],
                    'language_code',
                    new_language
                )
                frappe.db.commit()
            
            return {
                'success': True,
                'message': self._get_text('language_changed', new_language)
            }
            
        except Exception as e:
            frappe.log_error(f"Error handling language command: {str(e)}")
            return self._get_error_response(user_context.get('language', 'en'))
    
    def _handle_unknown_command(self, command: str, user_context: Dict[str, Any], message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle unknown command with helpful suggestions."""
        language = user_context.get('language', 'en')
        
        # Suggest similar commands
        suggestions = self._get_command_suggestions(command)
        
        message = self._get_text('unknown_command', language).format(command=command)
        
        if suggestions:
            message += "\n\n" + self._get_text('did_you_mean', language) + "\n"
            for suggestion in suggestions:
                message += f"• /{suggestion}\n"
        
        message += "\n" + self._get_text('use_help_command', language)
        
        return {
            'success': False,
            'message': message,
            'parse_mode': 'Markdown'
        }
    
    def _get_welcome_message(self, language: str, first_name: str, is_new: bool) -> str:
        """Get welcome message based on user status."""
        company_name = self.settings.get('company_name', 'Helpdesk')
        
        if self.settings.get('welcome_message'):
            # Custom welcome message
            base_message = self.settings['welcome_message']
        else:
            # Default welcome message
            if is_new:
                base_message = self._get_text('welcome_new_user', language)
            else:
                base_message = self._get_text('welcome_returning_user', language)
        
        # Replace placeholders
        message = base_message.format(
            first_name=first_name,
            company_name=company_name,
            support_hours=self.settings.get('support_hours', '24/7'),
            response_time=self.settings.get('response_time', '2-4 hours')
        )
        
        # Add available commands
        message += "\n\n" + self._get_text('available_commands', language) + "\n"
        message += "• /help - " + self._get_text('help_description', language) + "\n"
        message += "• /status <ticket> - " + self._get_text('status_description', language) + "\n"
        message += "• /mytickets - " + self._get_text('mytickets_description', language) + "\n"
        
        return message
    
    def _get_contextual_help(self, current_state: str, language: str, user_context: Dict[str, Any]) -> str:
        """Get context-aware help message."""
        if self.settings.get('help_message'):
            # Custom help message
            base_message = self.settings['help_message']
        else:
            # Default help message
            base_message = self._get_text('general_help', language)
        
        # Add state-specific help
        if current_state == 'verification_pending':
            base_message += "\n\n" + self._get_text('verification_help', language)
        elif current_state == 'ticket_creation':
            base_message += "\n\n" + self._get_text('ticket_creation_help', language)
        
        # Add command list
        base_message += "\n\n" + self._get_text('available_commands', language) + "\n"
        
        commands_help = {
            'help': self._get_text('help_description', language),
            'status': self._get_text('status_description', language),
            'mytickets': self._get_text('mytickets_description', language),
            'cancel': self._get_text('cancel_description', language),
            'settings': self._get_text('settings_description', language),
        }
        
        if not user_context.get('is_verified'):
            commands_help['verify'] = self._get_text('verify_description', language)
        
        for command, description in commands_help.items():
            base_message += f"• /{command} - {description}\n"
        
        return base_message
    
    def _get_topic_help(self, topic: str, language: str) -> str:
        """Get help for specific topic."""
        topic = topic.lower()
        
        help_topics = {
            'tickets': self._get_text('tickets_help', language),
            'status': self._get_text('status_help', language),
            'verification': self._get_text('verification_help', language),
            'settings': self._get_text('settings_help', language),
            'commands': self._get_text('commands_help', language),
        }
        
        return help_topics.get(topic, self._get_text('topic_not_found', language).format(topic=topic))
    
    def _get_ticket_status(self, ticket_number: str, user_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get ticket status information."""
        try:
            customer = user_context.get('customer')
            if not customer:
                return None
            
            # Check if ticket belongs to user's customer
            ticket = frappe.db.sql("""
                SELECT name, subject, status, priority, creation, 
                       modified, owner, agent_group
                FROM `tabHD Ticket`
                WHERE name = %s AND customer = %s
                LIMIT 1
            """, (ticket_number, customer), as_dict=True)
            
            return ticket[0] if ticket else None
            
        except Exception as e:
            frappe.log_error(f"Error getting ticket status: {str(e)}")
            return None
    
    def _format_ticket_status(self, ticket_info: Dict[str, Any], language: str) -> str:
        """Format ticket status message."""
        status_icons = {
            'Open': '🔓',
            'Replied': '💬', 
            'Resolved': '✅',
            'Closed': '🔒'
        }
        
        priority_icons = {
            'Low': '🟢',
            'Medium': '🟡',
            'High': '🔴',
            'Urgent': '🚨'
        }
        
        status_icon = status_icons.get(ticket_info['status'], '📋')
        priority_icon = priority_icons.get(ticket_info['priority'], '⚪')
        
        message = f"""
{status_icon} **{self._get_text('ticket_status', language)}**

🎫 **{self._get_text('ticket_number', language)}:** {ticket_info['name']}
📝 **{self._get_text('subject', language)}:** {ticket_info['subject']}
📊 **{self._get_text('status', language)}:** {ticket_info['status']}
{priority_icon} **{self._get_text('priority', language)}:** {ticket_info['priority']}
📅 **{self._get_text('created', language)}:** {ticket_info['creation'].strftime('%Y-%m-%d %H:%M')}
🕐 **{self._get_text('last_update', language)}:** {ticket_info['modified'].strftime('%Y-%m-%d %H:%M')}
        """
        
        if ticket_info.get('agent_group'):
            message += f"\n👤 **{self._get_text('assigned_to', language)}:** {ticket_info['agent_group']}"
        
        return message.strip()
    
    def _parse_ticket_filters(self, parameters: str) -> Dict[str, Any]:
        """Parse ticket filter parameters."""
        filters = {
            'status': None,
            'priority': None,
            'limit': self.settings['max_tickets_per_page'],
            'offset': 0
        }
        
        if not parameters:
            return filters
        
        # Parse parameters
        parts = parameters.lower().split()
        
        for part in parts:
            if part in ['open', 'replied', 'resolved', 'closed']:
                filters['status'] = part.title()
            elif part in ['low', 'medium', 'high', 'urgent']:
                filters['priority'] = part.title()
            elif part.startswith('page:'):
                try:
                    page = int(part.split(':')[1])
                    filters['offset'] = (page - 1) * filters['limit']
                except:
                    pass
        
        return filters
    
    def _get_user_tickets(self, user_context: Dict[str, Any], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get user tickets with filters."""
        try:
            customer = user_context.get('customer')
            if not customer:
                return []
            
            # Build query
            conditions = ["customer = %s"]
            values = [customer]
            
            if filters.get('status'):
                conditions.append("status = %s")
                values.append(filters['status'])
            
            if filters.get('priority'):
                conditions.append("priority = %s")
                values.append(filters['priority'])
            
            where_clause = " AND ".join(conditions)
            
            tickets = frappe.db.sql(f"""
                SELECT name, subject, status, priority, creation, modified
                FROM `tabHD Ticket`
                WHERE {where_clause}
                ORDER BY creation DESC
                LIMIT %s OFFSET %s
            """, values + [filters['limit'], filters['offset']], as_dict=True)
            
            return tickets
            
        except Exception as e:
            frappe.log_error(f"Error getting user tickets: {str(e)}")
            return []
    
    def _format_ticket_list(self, tickets: List[Dict[str, Any]], language: str, filters: Dict[str, Any]) -> str:
        """Format ticket list message."""
        header = f"🎫 **{self._get_text('your_tickets', language)}**"
        
        if filters.get('status') or filters.get('priority'):
            filter_parts = []
            if filters.get('status'):
                filter_parts.append(f"{self._get_text('status', language)}: {filters['status']}")
            if filters.get('priority'):
                filter_parts.append(f"{self._get_text('priority', language)}: {filters['priority']}")
            header += f" ({', '.join(filter_parts)})"
        
        message = header + "\n\n"
        
        status_icons = {'Open': '🔓', 'Replied': '💬', 'Resolved': '✅', 'Closed': '🔒'}
        priority_icons = {'Low': '🟢', 'Medium': '🟡', 'High': '🔴', 'Urgent': '🚨'}
        
        for i, ticket in enumerate(tickets, 1):
            status_icon = status_icons.get(ticket['status'], '📋')
            priority_icon = priority_icons.get(ticket['priority'], '⚪')
            
            subject = ticket['subject'][:50] + "..." if len(ticket['subject']) > 50 else ticket['subject']
            
            message += f"""
{i}. {status_icon} **{ticket['name']}**
   📝 {subject}
   {priority_icon} {ticket['priority']} • 📅 {ticket['creation'].strftime('%m/%d')}
   `/status {ticket['name']}`

"""
        
        # Add navigation help
        if len(tickets) == filters['limit']:
            page_num = (filters['offset'] // filters['limit']) + 1
            message += f"\n📄 {self._get_text('page', language)} {page_num}"
            message += f"\n{self._get_text('next_page_help', language).format(page=page_num + 1)}"
        
        return message.strip()
    
    def _start_phone_verification(self, user_context: Dict[str, Any], language: str) -> Dict[str, Any]:
        """Start phone verification process."""
        message = self._get_text('phone_verification_start', language)
        
        # Set user state to verification pending
        if user_context.get('telegram_user_name'):
            self._set_user_state(
                user_context['telegram_user_name'], 
                'verification_pending', 
                {'step': 'phone_input'}
            )
        
        return {
            'success': True,
            'message': message,
            'state_change': True
        }
    
    def _confirm_phone_verification(self, verification_code: str, user_context: Dict[str, Any], language: str) -> Dict[str, Any]:
        """Confirm phone verification with code."""
        if not user_context.get('telegram_user_name'):
            return {
                'success': False,
                'message': self._get_text('user_not_registered', language)
            }
        
        result = self.user_mapper.confirm_phone_verification(
            user_context['telegram_user_name'],
            verification_code
        )
        
        if result['success']:
            # Clear verification state
            self._set_user_state(user_context['telegram_user_name'], 'idle', {})
            
            return {
                'success': True,
                'message': self._get_text('verification_success', language)
            }
        else:
            error_key = result.get('error', 'verification_failed')
            message = self._get_text(f'verification_error_{error_key}', language)
            
            return {
                'success': False,
                'message': message
            }
    
    def _handle_setting_change(self, setting_param: str, user_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user setting changes."""
        language = user_context.get('language', 'en')
        
        # Parse setting parameter
        if '=' in setting_param:
            setting, value = setting_param.split('=', 1)
            setting = setting.strip().lower()
            value = value.strip()
            
            # Handle specific settings
            if setting == 'language':
                return self.handle_language_command(value, user_context, {})
            else:
                return {
                    'success': False,
                    'message': self._get_text('unknown_setting', language).format(setting=setting)
                }
        else:
            return {
                'success': False,
                'message': self._get_text('settings_usage', language)
            }
    
    def _get_user_settings(self, user_context: Dict[str, Any], language: str) -> str:
        """Get current user settings display."""
        message = f"⚙️ **{self._get_text('your_settings', language)}**\n\n"
        
        # Language setting
        current_lang = user_context.get('language', 'en')
        lang_name = self._get_language_name(current_lang, language)
        message += f"🌐 **{self._get_text('language', language)}:** {lang_name}\n"
        
        # Verification status
        verified_status = self._get_text('verified', language) if user_context.get('is_verified') else self._get_text('not_verified', language)
        message += f"✅ **{self._get_text('verification_status', language)}:** {verified_status}\n"
        
        # Add settings help
        message += f"\n{self._get_text('settings_help', language)}"
        
        return message
    
    def _get_available_languages(self, current_language: str) -> str:
        """Get available languages message."""
        message = f"🌐 **{self._get_text('available_languages', current_language)}**\n\n"
        
        for lang_code in self.settings['support_languages']:
            lang_name = self._get_language_name(lang_code, current_language)
            current_marker = " ✅" if lang_code == current_language else ""
            message += f"• {lang_name} (`{lang_code}`){current_marker}\n"
        
        message += f"\n{self._get_text('language_usage', current_language)}"
        
        return message
    
    def _get_language_name(self, lang_code: str, display_language: str) -> str:
        """Get language name in specified display language."""
        language_names = {
            'en': {'en': 'English', 'es': 'Spanish', 'fr': 'French'},
            'es': {'en': 'Inglés', 'es': 'Español', 'fr': 'Francés'},
            'fr': {'en': 'Anglais', 'es': 'Espagnol', 'fr': 'Français'}
        }
        
        names = language_names.get(display_language, language_names['en'])
        return names.get(lang_code, lang_code.upper())
    
    def _set_user_state(self, telegram_user_name: str, state: str, state_data: Dict[str, Any]):
        """Set user state for conversation management."""
        try:
            if self.settings['enable_user_states']:
                frappe.db.set_value(
                    'HD Telegram User',
                    telegram_user_name,
                    {
                        'current_state': state,
                        'state_data': str(state_data) if state_data else ''
                    }
                )
                frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Error setting user state: {str(e)}")
    
    def _get_command_suggestions(self, command: str) -> List[str]:
        """Get command suggestions for unknown commands."""
        available_commands = list(self.commands.keys())
        suggestions = []
        
        # Simple fuzzy matching
        for cmd in available_commands:
            if command in cmd or cmd in command:
                suggestions.append(cmd)
        
        return suggestions[:3]  # Limit to 3 suggestions
    
    def _get_error_response(self, language: str) -> Dict[str, Any]:
        """Get standardized error response."""
        return {
            'success': False,
            'message': self._get_text('command_error', language)
        }
    
    def _get_text(self, key: str, language: str) -> str:
        """Get localized text for given key and language."""
        # This is a simplified implementation
        # In production, you'd want to use a proper localization system
        
        texts = {
            'en': {
                'welcome_new_user': "👋 Welcome to {company_name} Support, {first_name}!\n\nI'm here to help you create and manage support tickets. Simply send me a message describing your issue and I'll create a ticket for you.\n\n🕒 Support Hours: {support_hours}\n⏱️ Response Time: {response_time}",
                'welcome_returning_user': "👋 Welcome back, {first_name}!\n\nI'm ready to help with your support needs.",
                'general_help': "🤖 **{company_name} Support Bot Help**\n\nI can help you:\n• Create support tickets by sending messages\n• Check ticket status\n• View your ticket history\n• Manage your preferences",
                'verification_required': "⚠️ Phone verification required to access this feature. Use /verify to start verification.",
                'status_usage': "📋 **Usage:** `/status <ticket_number>`\n\nExample: `/status TICK-001`",
                'ticket_not_found': "❌ Ticket `{ticket}` not found or doesn't belong to you.",
                'no_tickets_found': "📋 No tickets found matching your criteria.",
                'operation_cancelled': "✅ Current operation cancelled.",
                'unknown_command': "❓ Unknown command: `/{command}`",
                'did_you_mean': "Did you mean:",
                'use_help_command': "Use /help for available commands.",
                'available_commands': "**Available Commands:**",
                'help_description': "Show this help message",
                'status_description': "Check ticket status",
                'mytickets_description': "View your tickets",
                'cancel_description': "Cancel current operation",
                'settings_description': "Manage preferences",
                'verify_description': "Verify phone number",
                'command_error': "❌ An error occurred while processing your command.",
                'ticket_status': "Ticket Status",
                'ticket_number': "Number",
                'subject': "Subject",
                'status': "Status", 
                'priority': "Priority",
                'created': "Created",
                'last_update': "Last Update",
                'assigned_to': "Assigned To",
                'your_tickets': "Your Tickets",
                'page': "Page",
                'next_page_help': "Use `/mytickets page:{page}` for next page",
                'phone_verification_start': "📱 **Phone Verification**\n\nPlease share your phone number by:\n1. Using the 'Share Contact' button below, or\n2. Sending your phone number as a message\n\nThis helps us verify your identity and link your account.",
                'verification_success': "✅ Phone number verified successfully!",
                'verification_error_invalid_code': "❌ Invalid verification code. Please try again.",
                'verification_error_verification_expired': "⏰ Verification code has expired. Please request a new one.",
                'verification_error_too_many_attempts': "🚫 Too many verification attempts. Please try again later.",
                'user_not_registered': "❌ User not registered. Use /start to begin.",
                'already_verified': "✅ Your phone number is already verified.",
                'your_settings': "Your Settings",
                'language': "Language",
                'verification_status': "Verification Status",
                'verified': "Verified",
                'not_verified': "Not Verified", 
                'settings_help': "To change settings, use: `/settings <setting>=<value>`\nExample: `/settings language=es`",
                'available_languages': "Available Languages",
                'language_usage': "To change language, use: `/language <code>`",
                'language_changed': "✅ Language changed successfully!",
                'unsupported_language': "❌ Language not supported.",
                'unknown_setting': "❌ Unknown setting: {setting}",
                'settings_usage': "⚙️ **Settings Usage:**\n\n`/settings language=<code>` - Change language\n\nExample: `/settings language=es`"
            },
            'es': {
                'welcome_new_user': "👋 ¡Bienvenido al Soporte de {company_name}, {first_name}!\n\nEstoy aquí para ayudarte a crear y gestionar tickets de soporte. Simplemente envíame un mensaje describiendo tu problema y crearé un ticket para ti.\n\n🕒 Horario de Soporte: {support_hours}\n⏱️ Tiempo de Respuesta: {response_time}",
                'welcome_returning_user': "👋 ¡Bienvenido de nuevo, {first_name}!\n\nEstoy listo para ayudar con tus necesidades de soporte.",
                'general_help': "🤖 **Ayuda del Bot de Soporte de {company_name}**\n\nPuedo ayudarte a:\n• Crear tickets de soporte enviando mensajes\n• Verificar el estado de tickets\n• Ver tu historial de tickets\n• Gestionar tus preferencias",
                'verification_required': "⚠️ Se requiere verificación telefónica para acceder a esta función. Usa /verify para comenzar la verificación.",
                'status_usage': "📋 **Uso:** `/status <número_ticket>`\n\nEjemplo: `/status TICK-001`",
                'ticket_not_found': "❌ Ticket `{ticket}` no encontrado o no te pertenece.",
                'no_tickets_found': "📋 No se encontraron tickets que coincidan con tus criterios.",
                'operation_cancelled': "✅ Operación actual cancelada.",
                'command_error': "❌ Ocurrió un error al procesar tu comando.",
                'language_changed': "✅ ¡Idioma cambiado exitosamente!",
                'unsupported_language': "❌ Idioma no soportado."
            },
            'fr': {
                'welcome_new_user': "👋 Bienvenue au Support {company_name}, {first_name}!\n\nJe suis là pour vous aider à créer et gérer des tickets de support. Envoyez-moi simplement un message décrivant votre problème et je créerai un ticket pour vous.\n\n🕒 Heures de Support: {support_hours}\n⏱️ Temps de Réponse: {response_time}",
                'welcome_returning_user': "👋 Bon retour, {first_name}!\n\nJe suis prêt à vous aider avec vos besoins de support.",
                'general_help': "🤖 **Aide du Bot de Support {company_name}**\n\nJe peux vous aider à:\n• Créer des tickets de support en envoyant des messages\n• Vérifier le statut des tickets\n• Voir votre historique de tickets\n• Gérer vos préférences",
                'verification_required': "⚠️ Vérification téléphonique requise pour accéder à cette fonction. Utilisez /verify pour commencer la vérification.",
                'status_usage': "📋 **Usage:** `/status <numéro_ticket>`\n\nExemple: `/status TICK-001`",
                'ticket_not_found': "❌ Ticket `{ticket}` non trouvé ou ne vous appartient pas.",
                'no_tickets_found': "📋 Aucun ticket trouvé correspondant à vos critères.",
                'operation_cancelled': "✅ Opération actuelle annulée.",
                'command_error': "❌ Une erreur s'est produite lors du traitement de votre commande.",
                'language_changed': "✅ Langue changée avec succès!",
                'unsupported_language': "❌ Langue non supportée."
            }
        }
        
        # Get text for language, fallback to English
        lang_texts = texts.get(language, texts['en'])
        return lang_texts.get(key, texts['en'].get(key, f"[{key}]"))


# Helper functions for external use

def handle_telegram_command(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to handle Telegram commands.
    
    Args:
        message_data: Telegram message data
        
    Returns:
        Command handling result
    """
    handler = TelegramCommandHandler()
    return handler.handle_command(message_data)


def is_command_message(text: str) -> bool:
    """
    Check if message text is a command.
    
    Args:
        text: Message text
        
    Returns:
        True if text is a command, False otherwise
    """
    return text.strip().startswith('/') if text else False 