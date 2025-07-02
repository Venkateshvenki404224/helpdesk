#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Message Parser for Helpdesk Integration

This module provides comprehensive message parsing functionality for Telegram messages,
including text processing, media handling, content extraction, and sanitization.
"""

import re
import html
import mimetypes
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import (
    now, get_datetime, cstr, cint, flt,
    sanitize_html, strip_html_tags, get_url
)

class TelegramMessageParser:
    """
    Parser for Telegram messages with content extraction and validation.
    
    Handles:
    - Text message processing
    - Media message handling (photos, documents, voice, video)
    - URL extraction and validation
    - Content sanitization
    - Message validation
    """
    
    # Supported file types for attachments
    SUPPORTED_IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
    SUPPORTED_DOCUMENT_TYPES = ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx']
    SUPPORTED_AUDIO_TYPES = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac']
    SUPPORTED_VIDEO_TYPES = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']
    
    # Content limits
    MAX_MESSAGE_LENGTH = 4096  # Telegram's limit
    MAX_CAPTION_LENGTH = 1024
    MAX_FILENAME_LENGTH = 255
    
    # Content patterns
    URL_PATTERN = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    PHONE_PATTERN = re.compile(r'[\+]?[1-9]?[0-9]{7,15}')
    
    def __init__(self):
        """Initialize the message parser."""
        self.settings = self._get_parser_settings()
    
    def _get_parser_settings(self) -> Dict[str, Any]:
        """Get parser settings from system configuration."""
        try:
            settings = frappe.get_single('HD Telegram Bot')
            return {
                'max_file_size': getattr(settings, 'max_file_size', 10) * 1024 * 1024,  # MB to bytes
                'allowed_file_types': getattr(settings, 'allowed_file_types', '').split(','),
                'enable_url_preview': getattr(settings, 'enable_url_preview', 1),
                'sanitize_html': getattr(settings, 'sanitize_html', 1),
                'extract_entities': getattr(settings, 'extract_entities', 1),
            }
        except Exception:
            # Default settings if no bot configured
            return {
                'max_file_size': 10 * 1024 * 1024,  # 10MB
                'allowed_file_types': [],
                'enable_url_preview': True,
                'sanitize_html': True,
                'extract_entities': True,
            }
    
    def parse_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a Telegram message and extract relevant information.
        
        Args:
            message_data: Raw Telegram message data
            
        Returns:
            Dict containing parsed message information
        """
        try:
            parsed = {
                'message_id': message_data.get('message_id'),
                'chat_id': message_data.get('chat', {}).get('id'),
                'user_id': message_data.get('from', {}).get('id'),
                'date': message_data.get('date'),
                'message_type': self._determine_message_type(message_data),
                'text_content': None,
                'media_content': None,
                'entities': [],
                'attachments': [],
                'metadata': {},
                'validation_errors': [],
                'is_valid': True
            }
            
            # Parse based on message type
            if parsed['message_type'] == 'text':
                self._parse_text_message(message_data, parsed)
            elif parsed['message_type'] in ['photo', 'document', 'voice', 'video', 'audio']:
                self._parse_media_message(message_data, parsed)
            elif parsed['message_type'] == 'sticker':
                self._parse_sticker_message(message_data, parsed)
            elif parsed['message_type'] == 'location':
                self._parse_location_message(message_data, parsed)
            elif parsed['message_type'] == 'contact':
                self._parse_contact_message(message_data, parsed)
            else:
                self._parse_unsupported_message(message_data, parsed)
            
            # Extract entities if enabled
            if self.settings['extract_entities']:
                self._extract_entities(parsed)
            
            # Validate the parsed content
            self._validate_parsed_content(parsed)
            
            # Add parsing metadata
            parsed['metadata'].update({
                'parsed_at': now(),
                'parser_version': '1.0.0',
                'content_hash': self._generate_content_hash(parsed)
            })
            
            return parsed
            
        except Exception as e:
            frappe.log_error(
                message=f"Failed to parse Telegram message: {str(e)}",
                title="Telegram Message Parser Error"
            )
            return {
                'is_valid': False,
                'validation_errors': [f"Parsing failed: {str(e)}"],
                'message_id': message_data.get('message_id'),
                'chat_id': message_data.get('chat', {}).get('id'),
                'user_id': message_data.get('from', {}).get('id'),
            }
    
    def _determine_message_type(self, message_data: Dict[str, Any]) -> str:
        """Determine the type of message based on its content."""
        if 'text' in message_data:
            return 'text'
        elif 'photo' in message_data:
            return 'photo'
        elif 'document' in message_data:
            return 'document'
        elif 'voice' in message_data:
            return 'voice'
        elif 'video' in message_data:
            return 'video'
        elif 'audio' in message_data:
            return 'audio'
        elif 'sticker' in message_data:
            return 'sticker'
        elif 'location' in message_data:
            return 'location'
        elif 'contact' in message_data:
            return 'contact'
        elif 'poll' in message_data:
            return 'poll'
        elif 'venue' in message_data:
            return 'venue'
        else:
            return 'unknown'
    
    def _parse_text_message(self, message_data: Dict[str, Any], parsed: Dict[str, Any]):
        """Parse text messages with entity extraction."""
        text = message_data.get('text', '')
        
        # Sanitize HTML if enabled
        if self.settings['sanitize_html']:
            text = html.escape(text)
        
        # Extract message entities (mentions, URLs, etc.)
        entities = message_data.get('entities', [])
        formatted_text = self._format_text_with_entities(text, entities)
        
        parsed['text_content'] = {
            'raw_text': text,
            'formatted_text': formatted_text,
            'length': len(text),
            'entities': entities
        }
        
        # Extract URLs for preview
        if self.settings['enable_url_preview']:
            urls = self.URL_PATTERN.findall(text)
            if urls:
                parsed['metadata']['urls'] = urls[:5]  # Limit to 5 URLs
    
    def _parse_media_message(self, message_data: Dict[str, Any], parsed: Dict[str, Any]):
        """Parse media messages (photo, document, video, audio, voice)."""
        message_type = parsed['message_type']
        
        # Get caption if present
        caption = message_data.get('caption', '')
        if caption and self.settings['sanitize_html']:
            caption = html.escape(caption)
        
        # Parse specific media type
        if message_type == 'photo':
            self._parse_photo(message_data, parsed, caption)
        elif message_type == 'document':
            self._parse_document(message_data, parsed, caption)
        elif message_type == 'voice':
            self._parse_voice(message_data, parsed, caption)
        elif message_type == 'video':
            self._parse_video(message_data, parsed, caption)
        elif message_type == 'audio':
            self._parse_audio(message_data, parsed, caption)
        
        # Set text content to caption if present
        if caption:
            parsed['text_content'] = {
                'raw_text': caption,
                'formatted_text': caption,
                'length': len(caption),
                'entities': message_data.get('caption_entities', [])
            }
    
    def _parse_photo(self, message_data: Dict[str, Any], parsed: Dict[str, Any], caption: str):
        """Parse photo messages."""
        photos = message_data.get('photo', [])
        if not photos:
            return
        
        # Get the highest resolution photo
        photo = max(photos, key=lambda p: p.get('width', 0) * p.get('height', 0))
        
        parsed['media_content'] = {
            'type': 'photo',
            'file_id': photo.get('file_id'),
            'file_unique_id': photo.get('file_unique_id'),
            'file_size': photo.get('file_size', 0),
            'width': photo.get('width'),
            'height': photo.get('height'),
            'caption': caption
        }
        
        parsed['attachments'].append({
            'type': 'image',
            'file_id': photo.get('file_id'),
            'mime_type': 'image/jpeg',  # Telegram photos are always JPEG
            'file_size': photo.get('file_size', 0),
            'filename': f"photo_{photo.get('file_unique_id', 'unknown')}.jpg"
        })
    
    def _parse_document(self, message_data: Dict[str, Any], parsed: Dict[str, Any], caption: str):
        """Parse document messages."""
        document = message_data.get('document', {})
        if not document:
            return
        
        filename = document.get('file_name', 'document')
        file_size = document.get('file_size', 0)
        mime_type = document.get('mime_type', 'application/octet-stream')
        
        parsed['media_content'] = {
            'type': 'document',
            'file_id': document.get('file_id'),
            'file_unique_id': document.get('file_unique_id'),
            'file_name': filename,
            'mime_type': mime_type,
            'file_size': file_size,
            'caption': caption
        }
        
        parsed['attachments'].append({
            'type': 'document',
            'file_id': document.get('file_id'),
            'mime_type': mime_type,
            'file_size': file_size,
            'filename': filename
        })
    
    def _parse_voice(self, message_data: Dict[str, Any], parsed: Dict[str, Any], caption: str):
        """Parse voice messages."""
        voice = message_data.get('voice', {})
        if not voice:
            return
        
        duration = voice.get('duration', 0)
        file_size = voice.get('file_size', 0)
        
        parsed['media_content'] = {
            'type': 'voice',
            'file_id': voice.get('file_id'),
            'file_unique_id': voice.get('file_unique_id'),
            'duration': duration,
            'mime_type': voice.get('mime_type', 'audio/ogg'),
            'file_size': file_size,
            'caption': caption
        }
        
        parsed['attachments'].append({
            'type': 'audio',
            'file_id': voice.get('file_id'),
            'mime_type': voice.get('mime_type', 'audio/ogg'),
            'file_size': file_size,
            'filename': f"voice_{voice.get('file_unique_id', 'unknown')}.ogg",
            'duration': duration
        })
    
    def _parse_video(self, message_data: Dict[str, Any], parsed: Dict[str, Any], caption: str):
        """Parse video messages."""
        video = message_data.get('video', {})
        if not video:
            return
        
        parsed['media_content'] = {
            'type': 'video',
            'file_id': video.get('file_id'),
            'file_unique_id': video.get('file_unique_id'),
            'width': video.get('width'),
            'height': video.get('height'),
            'duration': video.get('duration', 0),
            'file_size': video.get('file_size', 0),
            'mime_type': video.get('mime_type', 'video/mp4'),
            'caption': caption
        }
        
        parsed['attachments'].append({
            'type': 'video',
            'file_id': video.get('file_id'),
            'mime_type': video.get('mime_type', 'video/mp4'),
            'file_size': video.get('file_size', 0),
            'filename': f"video_{video.get('file_unique_id', 'unknown')}.mp4",
            'duration': video.get('duration', 0)
        })
    
    def _parse_audio(self, message_data: Dict[str, Any], parsed: Dict[str, Any], caption: str):
        """Parse audio messages."""
        audio = message_data.get('audio', {})
        if not audio:
            return
        
        parsed['media_content'] = {
            'type': 'audio',
            'file_id': audio.get('file_id'),
            'file_unique_id': audio.get('file_unique_id'),
            'duration': audio.get('duration', 0),
            'performer': audio.get('performer'),
            'title': audio.get('title'),
            'file_name': audio.get('file_name'),
            'mime_type': audio.get('mime_type', 'audio/mpeg'),
            'file_size': audio.get('file_size', 0),
            'caption': caption
        }
        
        filename = audio.get('file_name') or f"audio_{audio.get('file_unique_id', 'unknown')}.mp3"
        
        parsed['attachments'].append({
            'type': 'audio',
            'file_id': audio.get('file_id'),
            'mime_type': audio.get('mime_type', 'audio/mpeg'),
            'file_size': audio.get('file_size', 0),
            'filename': filename,
            'duration': audio.get('duration', 0)
        })
    
    def _parse_sticker_message(self, message_data: Dict[str, Any], parsed: Dict[str, Any]):
        """Parse sticker messages."""
        sticker = message_data.get('sticker', {})
        if not sticker:
            return
        
        parsed['media_content'] = {
            'type': 'sticker',
            'file_id': sticker.get('file_id'),
            'file_unique_id': sticker.get('file_unique_id'),
            'width': sticker.get('width'),
            'height': sticker.get('height'),
            'is_animated': sticker.get('is_animated', False),
            'is_video': sticker.get('is_video', False),
            'emoji': sticker.get('emoji'),
            'set_name': sticker.get('set_name'),
            'file_size': sticker.get('file_size', 0)
        }
        
        # Add as text content
        emoji = sticker.get('emoji', '🙂')
        parsed['text_content'] = {
            'raw_text': f"{emoji} (sticker)",
            'formatted_text': f"{emoji} <i>sticker</i>",
            'length': len(emoji) + 10,
            'entities': []
        }
    
    def _parse_location_message(self, message_data: Dict[str, Any], parsed: Dict[str, Any]):
        """Parse location messages."""
        location = message_data.get('location', {})
        if not location:
            return
        
        latitude = location.get('latitude')
        longitude = location.get('longitude')
        
        parsed['media_content'] = {
            'type': 'location',
            'latitude': latitude,
            'longitude': longitude,
            'live_period': location.get('live_period'),
            'heading': location.get('heading'),
            'proximity_alert_radius': location.get('proximity_alert_radius')
        }
        
        # Add as text content
        location_text = f"📍 Location: {latitude}, {longitude}"
        parsed['text_content'] = {
            'raw_text': location_text,
            'formatted_text': location_text,
            'length': len(location_text),
            'entities': []
        }
    
    def _parse_contact_message(self, message_data: Dict[str, Any], parsed: Dict[str, Any]):
        """Parse contact messages."""
        contact = message_data.get('contact', {})
        if not contact:
            return
        
        parsed['media_content'] = {
            'type': 'contact',
            'phone_number': contact.get('phone_number'),
            'first_name': contact.get('first_name'),
            'last_name': contact.get('last_name'),
            'user_id': contact.get('user_id'),
            'vcard': contact.get('vcard')
        }
        
        # Add as text content
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        phone = contact.get('phone_number', '')
        contact_text = f"👤 Contact: {name} ({phone})"
        
        parsed['text_content'] = {
            'raw_text': contact_text,
            'formatted_text': contact_text,
            'length': len(contact_text),
            'entities': []
        }
    
    def _parse_unsupported_message(self, message_data: Dict[str, Any], parsed: Dict[str, Any]):
        """Parse unsupported message types."""
        parsed['text_content'] = {
            'raw_text': '[Unsupported message type]',
            'formatted_text': '<i>[Unsupported message type]</i>',
            'length': 25,
            'entities': []
        }
        
        parsed['validation_errors'].append(
            f"Unsupported message type: {parsed['message_type']}"
        )
    
    def _format_text_with_entities(self, text: str, entities: List[Dict]) -> str:
        """Format text with Telegram entities (bold, italic, links, etc.)."""
        if not entities:
            return text
        
        # Sort entities by offset in reverse order to avoid position shifts
        entities = sorted(entities, key=lambda x: x.get('offset', 0), reverse=True)
        
        formatted_text = text
        for entity in entities:
            entity_type = entity.get('type')
            offset = entity.get('offset', 0)
            length = entity.get('length', 0)
            
            if offset + length > len(formatted_text):
                continue
            
            entity_text = formatted_text[offset:offset + length]
            
            if entity_type == 'bold':
                replacement = f"<b>{entity_text}</b>"
            elif entity_type == 'italic':
                replacement = f"<i>{entity_text}</i>"
            elif entity_type == 'code':
                replacement = f"<code>{entity_text}</code>"
            elif entity_type == 'pre':
                replacement = f"<pre>{entity_text}</pre>"
            elif entity_type == 'url':
                replacement = f'<a href="{entity_text}">{entity_text}</a>'
            elif entity_type == 'text_link':
                url = entity.get('url', entity_text)
                replacement = f'<a href="{url}">{entity_text}</a>'
            elif entity_type == 'mention':
                replacement = f'<a href="https://t.me/{entity_text[1:]}">{entity_text}</a>'
            elif entity_type == 'email':
                replacement = f'<a href="mailto:{entity_text}">{entity_text}</a>'
            elif entity_type == 'phone_number':
                replacement = f'<a href="tel:{entity_text}">{entity_text}</a>'
            else:
                continue  # Unsupported entity type
            
            formatted_text = (
                formatted_text[:offset] + 
                replacement + 
                formatted_text[offset + length:]
            )
        
        return formatted_text
    
    def _extract_entities(self, parsed: Dict[str, Any]):
        """Extract useful entities from the message content."""
        if not parsed.get('text_content'):
            return
        
        text = parsed['text_content']['raw_text']
        entities = {
            'urls': self.URL_PATTERN.findall(text),
            'emails': self.EMAIL_PATTERN.findall(text),
            'phones': self.PHONE_PATTERN.findall(text)
        }
        
        # Remove empty lists
        entities = {k: v for k, v in entities.items() if v}
        
        if entities:
            parsed['entities'] = entities
    
    def _validate_parsed_content(self, parsed: Dict[str, Any]):
        """Validate the parsed content for errors and constraints."""
        errors = []
        
        # Check message length
        if parsed.get('text_content'):
            text_length = parsed['text_content']['length']
            if text_length > self.MAX_MESSAGE_LENGTH:
                errors.append(f"Message too long: {text_length} > {self.MAX_MESSAGE_LENGTH}")
        
        # Check file size limits
        for attachment in parsed.get('attachments', []):
            file_size = attachment.get('file_size', 0)
            if file_size > self.settings['max_file_size']:
                errors.append(
                    f"File too large: {file_size} bytes > {self.settings['max_file_size']} bytes"
                )
            
            # Check file type restrictions
            if self.settings['allowed_file_types']:
                filename = attachment.get('filename', '')
                file_ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
                if file_ext not in self.settings['allowed_file_types']:
                    errors.append(f"File type not allowed: {file_ext}")
        
        # Check for required fields
        required_fields = ['message_id', 'chat_id', 'user_id']
        for field in required_fields:
            if not parsed.get(field):
                errors.append(f"Missing required field: {field}")
        
        parsed['validation_errors'] = errors
        parsed['is_valid'] = len(errors) == 0
    
    def _generate_content_hash(self, parsed: Dict[str, Any]) -> str:
        """Generate a hash of the message content for deduplication."""
        import hashlib
        
        content_parts = []
        
        if parsed.get('text_content'):
            content_parts.append(parsed['text_content']['raw_text'])
        
        if parsed.get('media_content'):
            media = parsed['media_content']
            if 'file_unique_id' in media:
                content_parts.append(media['file_unique_id'])
            elif 'file_id' in media:
                content_parts.append(media['file_id'])
        
        content_string = '|'.join(content_parts)
        return hashlib.md5(content_string.encode()).hexdigest()
    
    @staticmethod
    def extract_ticket_subject(parsed_message: Dict[str, Any], max_length: int = 100) -> str:
        """
        Extract a suitable subject line for a ticket from the parsed message.
        
        Args:
            parsed_message: Parsed message data
            max_length: Maximum length for the subject
            
        Returns:
            Generated subject line
        """
        if not parsed_message.get('text_content'):
            message_type = parsed_message.get('message_type', 'message')
            return f"New {message_type} from Telegram"
        
        text = parsed_message['text_content']['raw_text']
        
        # Clean the text
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Use first line or first sentence as subject
        lines = text.split('\n')
        first_line = lines[0] if lines else text
        
        # If first line is too long, try to find a sentence
        if len(first_line) > max_length:
            sentences = re.split(r'[.!?]+', first_line)
            if sentences and len(sentences[0]) <= max_length:
                first_line = sentences[0]
            else:
                first_line = first_line[:max_length-3] + '...'
        
        # Fallback to truncated text
        if not first_line.strip():
            first_line = text[:max_length-3] + '...' if len(text) > max_length else text
        
        return first_line.strip() or "Message from Telegram"


# Helper functions for external use

def parse_telegram_message(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to parse a Telegram message.
    
    Args:
        message_data: Raw Telegram message data
        
    Returns:
        Parsed message information
    """
    parser = TelegramMessageParser()
    return parser.parse_message(message_data)


def extract_message_subject(message_data: Dict[str, Any], max_length: int = 100) -> str:
    """
    Convenience function to extract a subject from a Telegram message.
    
    Args:
        message_data: Raw Telegram message data or parsed message
        max_length: Maximum length for the subject
        
    Returns:
        Generated subject line
    """
    if 'text_content' in message_data:
        # Already parsed
        return TelegramMessageParser.extract_ticket_subject(message_data, max_length)
    else:
        # Raw message data
        parser = TelegramMessageParser()
        parsed = parser.parse_message(message_data)
        return TelegramMessageParser.extract_ticket_subject(parsed, max_length) 