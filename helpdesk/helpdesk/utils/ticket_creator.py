#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Ticket Creation Engine for Helpdesk Integration

This module provides functionality to create helpdesk tickets from Telegram messages,
including subject generation, priority assignment, team routing, and attachment processing.
"""

import os
import mimetypes
from typing import Dict, Any, Optional, List, Tuple
import frappe
from frappe import _
from frappe.utils import (
    now, get_datetime, cstr, cint, flt,
    get_files_path, random_string
)
from frappe.core.doctype.file.file import create_new_folder

from helpdesk.helpdesk.utils.message_parser import TelegramMessageParser
from helpdesk.helpdesk.utils.user_mapper import TelegramUserMapper
from helpdesk.helpdesk.utils.telegram_client import TelegramBotClient


class TelegramTicketCreator:
    """
    Creates helpdesk tickets from Telegram messages with full processing workflow.
    
    Handles:
    - Ticket creation from parsed messages
    - Subject generation and priority assignment
    - Team and agent assignment
    - Attachment processing and file uploads
    - Communication creation
    - Notification and confirmation
    """
    
    def __init__(self):
        """Initialize the ticket creator."""
        self.settings = self._get_creator_settings()
        self.message_parser = TelegramMessageParser()
        self.user_mapper = TelegramUserMapper()
    
    def _get_creator_settings(self) -> Dict[str, Any]:
        """Get ticket creator settings from system configuration."""
        try:
            settings = frappe.get_single('HD Telegram Bot')
            return {
                'default_team': getattr(settings, 'default_team', None),
                'auto_assign_agent': getattr(settings, 'auto_assign_agent', 0),
                'default_priority': getattr(settings, 'default_priority', 'Medium'),
                'default_ticket_type': getattr(settings, 'default_ticket_type', None),
                'enable_attachments': getattr(settings, 'enable_attachments', 1),
                'max_attachments': getattr(settings, 'max_attachments', 5),
                'attachment_folder': getattr(settings, 'attachment_folder', 'Telegram Attachments'),
                'send_confirmation': getattr(settings, 'send_confirmation', 1),
                'subject_max_length': getattr(settings, 'subject_max_length', 100),
                'priority_keywords': self._parse_priority_keywords(getattr(settings, 'priority_keywords', '')),
                'team_routing_rules': self._parse_team_routing(getattr(settings, 'team_routing_rules', '')),
            }
        except Exception:
            # Default settings if no bot configured
            return {
                'default_team': None,
                'auto_assign_agent': False,
                'default_priority': 'Medium',
                'default_ticket_type': None,
                'enable_attachments': True,
                'max_attachments': 5,
                'attachment_folder': 'Telegram Attachments',
                'send_confirmation': True,
                'subject_max_length': 100,
                'priority_keywords': {},
                'team_routing_rules': [],
            }
    
    def _parse_priority_keywords(self, priority_keywords_str: str) -> Dict[str, str]:
        """Parse priority keywords from settings."""
        try:
            keywords = {}
            if priority_keywords_str:
                for line in priority_keywords_str.split('\n'):
                    if ':' in line:
                        priority, words = line.split(':', 1)
                        keywords[priority.strip()] = [w.strip().lower() for w in words.split(',')]
            return keywords
        except Exception:
            return {}
    
    def _parse_team_routing(self, team_routing_str: str) -> List[Dict[str, Any]]:
        """Parse team routing rules from settings."""
        try:
            rules = []
            if team_routing_str:
                for line in team_routing_str.split('\n'):
                    if ':' in line:
                        condition, team = line.split(':', 1)
                        rules.append({
                            'condition': condition.strip().lower(),
                            'team': team.strip()
                        })
            return rules
        except Exception:
            return []
    
    def create_ticket_from_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a helpdesk ticket from a Telegram message.
        
        Args:
            message_data: Raw Telegram message data
            
        Returns:
            Dict containing ticket creation result
        """
        try:
            # Parse the message
            parsed_message = self.message_parser.parse_message(message_data)
            if not parsed_message['is_valid']:
                return {
                    'success': False,
                    'error': 'invalid_message',
                    'message': 'Message parsing failed',
                    'details': parsed_message['validation_errors']
                }
            
            # Resolve the user
            telegram_user_data = message_data.get('from', {})
            user_resolution = self.user_mapper.resolve_user(telegram_user_data, message_data)
            
            if not user_resolution['success']:
                return {
                    'success': False,
                    'error': user_resolution.get('error', 'user_resolution_failed'),
                    'message': user_resolution.get('message', 'Failed to resolve user'),
                    'telegram_user': user_resolution.get('telegram_user'),
                    'verification_required': user_resolution.get('verification_required', False)
                }
            
            # Create the ticket
            ticket_result = self._create_ticket(parsed_message, user_resolution)
            
            if ticket_result['success']:
                # Log the message
                self._log_telegram_message(
                    parsed_message, 
                    user_resolution, 
                    ticket_result['ticket']
                )
                
                # Send confirmation if enabled
                if self.settings['send_confirmation']:
                    self._send_ticket_confirmation(
                        message_data.get('chat', {}).get('id'),
                        ticket_result['ticket'],
                        user_resolution.get('telegram_user')
                    )
            
            return ticket_result
            
        except Exception as e:
            frappe.log_error(
                message=f"Failed to create ticket from Telegram message: {str(e)}",
                title="Telegram Ticket Creation Error"
            )
            return {
                'success': False,
                'error': 'creation_failed',
                'message': f"Ticket creation failed: {str(e)}"
            }
    
    def _create_ticket(self, parsed_message: Dict[str, Any], user_resolution: Dict[str, Any]) -> Dict[str, Any]:
        """Create the actual HD Ticket document."""
        try:
            # Generate ticket data
            ticket_data = self._prepare_ticket_data(parsed_message, user_resolution)
            
            # Create the ticket
            ticket = frappe.get_doc({
                'doctype': 'HD Ticket',
                **ticket_data
            })
            
            ticket.insert(ignore_permissions=True)
            
            # Process attachments if any
            if parsed_message.get('attachments') and self.settings['enable_attachments']:
                self._process_attachments(ticket.name, parsed_message['attachments'])
            
            # Create initial communication
            self._create_initial_communication(ticket.name, parsed_message, user_resolution)
            
            frappe.db.commit()
            
            return {
                'success': True,
                'ticket': ticket.name,
                'ticket_id': ticket.name,
                'subject': ticket.subject,
                'status': ticket.status,
                'priority': ticket.priority
            }
            
        except Exception as e:
            frappe.log_error(f"Error creating ticket: {str(e)}")
            return {
                'success': False,
                'error': 'ticket_creation_failed',
                'message': f"Failed to create ticket: {str(e)}"
            }
    
    def _prepare_ticket_data(self, parsed_message: Dict[str, Any], user_resolution: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare ticket data from parsed message and user resolution."""
        # Generate subject
        subject = self._generate_subject(parsed_message)
        
        # Determine priority
        priority = self._determine_priority(parsed_message)
        
        # Determine team assignment
        team = self._determine_team(parsed_message)
        
        # Prepare description
        description = self._prepare_description(parsed_message)
        
        ticket_data = {
            'subject': subject,
            'description': description,
            'status': 'Open',
            'priority': priority,
            'customer': user_resolution.get('customer'),
            'contact': user_resolution.get('contact'),
            'source': 'Telegram',
            'ticket_type': self.settings.get('default_ticket_type'),
        }
        
        # Add team if determined
        if team:
            ticket_data['team'] = team
            
            # Auto-assign agent if enabled
            if self.settings['auto_assign_agent']:
                agent = self._get_available_agent(team)
                if agent:
                    ticket_data['agent_group'] = agent
        
        return ticket_data
    
    def _generate_subject(self, parsed_message: Dict[str, Any]) -> str:
        """Generate appropriate subject for the ticket."""
        return TelegramMessageParser.extract_ticket_subject(
            parsed_message, 
            self.settings['subject_max_length']
        )
    
    def _determine_priority(self, parsed_message: Dict[str, Any]) -> str:
        """Determine ticket priority based on message content."""
        if not parsed_message.get('text_content'):
            return self.settings['default_priority']
        
        text = parsed_message['text_content']['raw_text'].lower()
        
        # Check priority keywords
        for priority, keywords in self.settings['priority_keywords'].items():
            for keyword in keywords:
                if keyword in text:
                    return priority
        
        # Check for urgency indicators
        urgent_words = ['urgent', 'emergency', 'critical', 'asap', 'immediately', 'broken', 'down', 'error']
        if any(word in text for word in urgent_words):
            return 'High'
        
        return self.settings['default_priority']
    
    def _determine_team(self, parsed_message: Dict[str, Any]) -> Optional[str]:
        """Determine team assignment based on routing rules."""
        if not parsed_message.get('text_content'):
            return self.settings.get('default_team')
        
        text = parsed_message['text_content']['raw_text'].lower()
        
        # Apply routing rules
        for rule in self.settings['team_routing_rules']:
            if rule['condition'] in text:
                return rule['team']
        
        return self.settings.get('default_team')
    
    def _prepare_description(self, parsed_message: Dict[str, Any]) -> str:
        """Prepare ticket description from parsed message."""
        description_parts = []
        
        # Add text content
        if parsed_message.get('text_content'):
            text_content = parsed_message['text_content']['formatted_text']
            description_parts.append(text_content)
        
        # Add media description
        if parsed_message.get('media_content'):
            media = parsed_message['media_content']
            media_type = media.get('type', 'media')
            
            if media_type == 'photo':
                description_parts.append(f"📷 Photo attached")
                if media.get('caption'):
                    description_parts.append(f"Caption: {media['caption']}")
            
            elif media_type == 'document':
                filename = media.get('file_name', 'document')
                description_parts.append(f"📎 Document attached: {filename}")
                if media.get('caption'):
                    description_parts.append(f"Caption: {media['caption']}")
            
            elif media_type == 'voice':
                duration = media.get('duration', 0)
                description_parts.append(f"🎤 Voice message ({duration}s)")
                if media.get('caption'):
                    description_parts.append(f"Caption: {media['caption']}")
            
            elif media_type == 'video':
                duration = media.get('duration', 0)
                description_parts.append(f"🎥 Video attached ({duration}s)")
                if media.get('caption'):
                    description_parts.append(f"Caption: {media['caption']}")
            
            elif media_type == 'location':
                lat = media.get('latitude')
                lon = media.get('longitude')
                description_parts.append(f"📍 Location shared: {lat}, {lon}")
            
            elif media_type == 'contact':
                name = f"{media.get('first_name', '')} {media.get('last_name', '')}".strip()
                phone = media.get('phone_number', '')
                description_parts.append(f"👤 Contact shared: {name} ({phone})")
        
        # Add extracted entities
        if parsed_message.get('entities'):
            entities = parsed_message['entities']
            if entities.get('urls'):
                description_parts.append(f"🔗 URLs: {', '.join(entities['urls'][:3])}")
            if entities.get('emails'):
                description_parts.append(f"📧 Emails: {', '.join(entities['emails'][:3])}")
            if entities.get('phones'):
                description_parts.append(f"📞 Phones: {', '.join(entities['phones'][:3])}")
        
        # Add Telegram metadata
        description_parts.append("---")
        description_parts.append(f"**Source:** Telegram")
        description_parts.append(f"**Message ID:** {parsed_message.get('message_id')}")
        description_parts.append(f"**Chat ID:** {parsed_message.get('chat_id')}")
        
        return "\n\n".join(description_parts)
    
    def _get_available_agent(self, team: str) -> Optional[str]:
        """Get an available agent from the specified team."""
        try:
            # This is a basic round-robin assignment
            # In production, you might want more sophisticated logic
            agents = frappe.db.sql("""
                SELECT user
                FROM `tabHD Team Member`
                WHERE parent = %s
                ORDER BY RAND()
                LIMIT 1
            """, (team,), as_dict=True)
            
            return agents[0]['user'] if agents else None
            
        except Exception as e:
            frappe.log_error(f"Error getting available agent: {str(e)}")
            return None
    
    def _process_attachments(self, ticket_name: str, attachments: List[Dict[str, Any]]):
        """Process and download attachments for the ticket."""
        try:
            if len(attachments) > self.settings['max_attachments']:
                attachments = attachments[:self.settings['max_attachments']]
            
            # Create attachment folder if needed
            self._ensure_attachment_folder()
            
            for attachment in attachments:
                try:
                    self._download_and_attach_file(ticket_name, attachment)
                except Exception as e:
                    frappe.log_error(f"Error processing attachment: {str(e)}")
                    # Continue with other attachments
            
        except Exception as e:
            frappe.log_error(f"Error processing attachments: {str(e)}")
    
    def _ensure_attachment_folder(self):
        """Ensure the attachment folder exists."""
        try:
            folder_name = self.settings['attachment_folder']
            
            # Check if folder exists
            if not frappe.db.exists('File', {'file_name': folder_name, 'is_folder': 1}):
                create_new_folder(folder_name, 'Home')
                
        except Exception as e:
            frappe.log_error(f"Error creating attachment folder: {str(e)}")
    
    def _download_and_attach_file(self, ticket_name: str, attachment: Dict[str, Any]):
        """Download file from Telegram and attach to ticket."""
        try:
            # Get bot client
            bot_client = self._get_bot_client()
            if not bot_client:
                return
            
            # Download file from Telegram
            file_id = attachment.get('file_id')
            if not file_id:
                return
            
            # Get file info from Telegram
            file_info = bot_client.get_file(file_id)
            if not file_info or not file_info.get('file_path'):
                return
            
            # Download file content
            file_content = bot_client.download_file(file_info['file_path'])
            if not file_content:
                return
            
            # Prepare file data
            filename = attachment.get('filename', f"telegram_file_{file_id}")
            mime_type = attachment.get('mime_type', 'application/octet-stream')
            
            # Create file document
            file_doc = frappe.get_doc({
                'doctype': 'File',
                'file_name': filename,
                'content': file_content,
                'decode': False,
                'is_private': 1,
                'folder': f'Home/{self.settings["attachment_folder"]}',
                'attached_to_doctype': 'HD Ticket',
                'attached_to_name': ticket_name
            })
            
            file_doc.save(ignore_permissions=True)
            
        except Exception as e:
            frappe.log_error(f"Error downloading and attaching file: {str(e)}")
    
    def _get_bot_client(self) -> Optional[TelegramBotClient]:
        """Get configured Telegram bot client."""
        try:
            bot_settings = frappe.get_single('HD Telegram Bot')
            if bot_settings and bot_settings.bot_token:
                return TelegramBotClient(bot_settings.bot_token)
        except Exception:
            pass
        return None
    
    def _create_initial_communication(self, ticket_name: str, parsed_message: Dict[str, Any], user_resolution: Dict[str, Any]):
        """Create initial communication record for the ticket."""
        try:
            communication_content = self._prepare_communication_content(parsed_message)
            
            communication = frappe.get_doc({
                'doctype': 'Communication',
                'communication_type': 'Communication',
                'communication_medium': 'Telegram',
                'sent_or_received': 'Received',
                'reference_doctype': 'HD Ticket',
                'reference_name': ticket_name,
                'subject': f"Telegram Message - Ticket {ticket_name}",
                'content': communication_content,
                'sender': user_resolution.get('contact'),
                'timeline_hide': 0
            })
            
            communication.insert(ignore_permissions=True)
            
        except Exception as e:
            frappe.log_error(f"Error creating initial communication: {str(e)}")
    
    def _prepare_communication_content(self, parsed_message: Dict[str, Any]) -> str:
        """Prepare communication content from parsed message."""
        if parsed_message.get('text_content'):
            return parsed_message['text_content']['formatted_text']
        elif parsed_message.get('media_content'):
            media = parsed_message['media_content']
            media_type = media.get('type', 'media')
            
            if media_type == 'photo':
                return f"📷 Photo message{': ' + media.get('caption', '') if media.get('caption') else ''}"
            elif media_type == 'document':
                filename = media.get('file_name', 'document')
                return f"📎 Document: {filename}{': ' + media.get('caption', '') if media.get('caption') else ''}"
            elif media_type == 'voice':
                duration = media.get('duration', 0)
                return f"🎤 Voice message ({duration}s)"
            elif media_type == 'video':
                duration = media.get('duration', 0)
                return f"🎥 Video message ({duration}s){': ' + media.get('caption', '') if media.get('caption') else ''}"
            else:
                return f"{media_type.title()} message"
        else:
            return "Message from Telegram"
    
    def _log_telegram_message(self, parsed_message: Dict[str, Any], user_resolution: Dict[str, Any], ticket_name: str):
        """Log the Telegram message in HD Telegram Message."""
        try:
            telegram_message = frappe.get_doc({
                'doctype': 'HD Telegram Message',
                'telegram_message_id': parsed_message.get('message_id'),
                'telegram_user': user_resolution.get('telegram_user'),
                'chat_id': parsed_message.get('chat_id'),
                'message_type': parsed_message.get('message_type'),
                'content': parsed_message.get('text_content', {}).get('raw_text', ''),
                'media_info': str(parsed_message.get('media_content', {})) if parsed_message.get('media_content') else '',
                'ticket': ticket_name,
                'processing_status': 'Processed',
                'received_at': now(),
                'processed_at': now()
            })
            
            telegram_message.insert(ignore_permissions=True)
            
        except Exception as e:
            frappe.log_error(f"Error logging Telegram message: {str(e)}")
    
    def _send_ticket_confirmation(self, chat_id: int, ticket_name: str, telegram_user_name: str):
        """Send ticket creation confirmation to user."""
        try:
            bot_client = self._get_bot_client()
            if not bot_client:
                return
            
            # Get ticket details
            ticket = frappe.get_doc('HD Ticket', ticket_name)
            
            # Prepare confirmation message
            message = self._prepare_confirmation_message(ticket, telegram_user_name)
            
            # Send message
            bot_client.send_message(str(chat_id), message)
            
        except Exception as e:
            frappe.log_error(f"Error sending ticket confirmation: {str(e)}")
    
    def _prepare_confirmation_message(self, ticket, telegram_user_name: str) -> str:
        """Prepare ticket creation confirmation message."""
        try:
            # Get user language
            language = 'en'  # Default
            if telegram_user_name:
                try:
                    tg_user = frappe.get_doc('HD Telegram User', telegram_user_name)
                    language = tg_user.language_code or 'en'
                except Exception:
                    pass
            
            # Prepare message based on language
            if language.startswith('es'):
                message = f"""
✅ **Ticket Creado**

🎫 **Número:** {ticket.name}
📝 **Asunto:** {ticket.subject}
⚡ **Prioridad:** {ticket.priority}
📊 **Estado:** {ticket.status}

Nuestro equipo revisará tu solicitud y te responderá pronto.

Para consultar el estado de tu ticket, usa: `/status {ticket.name}`
            """
            elif language.startswith('fr'):
                message = f"""
✅ **Ticket Créé**

🎫 **Numéro:** {ticket.name}
📝 **Sujet:** {ticket.subject}
⚡ **Priorité:** {ticket.priority}
📊 **Statut:** {ticket.status}

Notre équipe examinera votre demande et vous répondra bientôt.

Pour vérifier le statut de votre ticket, utilisez: `/status {ticket.name}`
            """
            else:  # English default
                message = f"""
✅ **Ticket Created**

🎫 **Number:** {ticket.name}
📝 **Subject:** {ticket.subject}
⚡ **Priority:** {ticket.priority}
📊 **Status:** {ticket.status}

Our team will review your request and respond soon.

To check your ticket status, use: `/status {ticket.name}`
            """
            
            return message.strip()
            
        except Exception as e:
            frappe.log_error(f"Error preparing confirmation message: {str(e)}")
            return "✅ Your ticket has been created successfully!"


# Helper functions for external use

def create_ticket_from_telegram_message(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to create a ticket from a Telegram message.
    
    Args:
        message_data: Raw Telegram message data
        
    Returns:
        Ticket creation result
    """
    creator = TelegramTicketCreator()
    return creator.create_ticket_from_message(message_data)


def process_telegram_message_background(message_data: Dict[str, Any]):
    """
    Background job function to process Telegram messages.
    
    Args:
        message_data: Raw Telegram message data
    """
    try:
        result = create_ticket_from_telegram_message(message_data)
        
        if not result['success']:
            frappe.log_error(
                message=f"Failed to process Telegram message: {result.get('message', 'Unknown error')}",
                title="Telegram Message Processing Failed"
            )
        else:
            frappe.logger().info(f"Successfully created ticket {result['ticket']} from Telegram message")
            
    except Exception as e:
        frappe.log_error(
            message=f"Error in background processing: {str(e)}",
            title="Telegram Background Processing Error"
        ) 