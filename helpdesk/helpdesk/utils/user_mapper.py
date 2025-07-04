#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram User Mapper for Helpdesk Integration

This module provides functionality to map Telegram users to Helpdesk customers,
including automatic contact creation, phone verification, and customer linking.
"""

import re
import frappe
from frappe import _
from frappe.utils import (
    now, get_datetime, cstr, cint, 
    validate_email_address, random_string
)
from typing import Dict, Any, Optional, Tuple, List

class TelegramUserMapper:
    """
    Maps Telegram users to Helpdesk customers with automatic contact creation.
    
    Handles:
    - Customer identification and linking
    - Automatic contact creation
    - Phone number verification workflow
    - User registration and onboarding
    - Customer data synchronization
    """
    
    def __init__(self):
        """Initialize the user mapper."""
        self.settings = self._get_mapper_settings()
    
    def _get_mapper_settings(self) -> Dict[str, Any]:
        """Get mapper settings from system configuration."""
        try:
            settings = frappe.get_single('HD Telegram Bot')
            return {
                'auto_create_customers': getattr(settings, 'auto_create_customers', 1),
                'require_phone_verification': getattr(settings, 'require_phone_verification', 0),
                'auto_link_by_phone': getattr(settings, 'auto_link_by_phone', 1),
                'auto_link_by_email': getattr(settings, 'auto_link_by_email', 1),
                'default_customer_group': getattr(settings, 'default_customer_group', 'Individual'),
                'default_territory': getattr(settings, 'default_territory', 'All Territories'),
                'verification_code_expiry': getattr(settings, 'verification_code_expiry', 300),  # 5 minutes
            }
        except Exception:
            # Default settings if no bot configured
            return {
                'auto_create_customers': True,
                'require_phone_verification': False,
                'auto_link_by_phone': True,
                'auto_link_by_email': True,
                'default_customer_group': 'Individual',
                'default_territory': 'All Territories',
                'verification_code_expiry': 300,
            }
    
    def resolve_user(self, telegram_user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Resolve a Telegram user to a Helpdesk customer.
        
        Args:
            telegram_user_data: Telegram user information from message
            message_data: Optional full message data for context
            
        Returns:
            Dict containing resolution result with customer and contact info
        """
        try:
            telegram_user_id = str(telegram_user_data.get('id', ''))
            if not telegram_user_id:
                return self._create_error_result("No Telegram user ID provided")
            
            # Check if we already have this Telegram user mapped
            existing_mapping = self._get_existing_telegram_user(telegram_user_id)
            if existing_mapping:
                return self._resolve_existing_user(existing_mapping, telegram_user_data)
            
            # Try to find customer by phone or email if available
            auto_linked_customer = self._try_auto_link_customer(telegram_user_data, message_data)
            if auto_linked_customer:
                return self._create_mapping_for_existing_customer(
                    auto_linked_customer, telegram_user_data
                )
            
            # Create new customer if auto-creation is enabled
            if self.settings['auto_create_customers']:
                return self._create_new_customer_mapping(telegram_user_data, message_data)
            else:
                return self._create_unverified_mapping(telegram_user_data)
                
        except Exception as e:
            frappe.log_error(
                message=f"Failed to resolve Telegram user: {str(e)}",
                title="Telegram User Resolution Error"
            )
            return self._create_error_result(f"User resolution failed: {str(e)}")
    
    def _get_existing_telegram_user(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """Get existing HD Telegram User record."""
        try:
            telegram_user = frappe.get_doc('HD Telegram User', {
                'telegram_user_id': telegram_user_id
            })
            return telegram_user.as_dict() if telegram_user else None
        except frappe.DoesNotExistError:
            return None
        except Exception as e:
            frappe.log_error(f"Error fetching Telegram user: {str(e)}")
            return None
    
    def _resolve_existing_user(self, existing_mapping: Dict[str, Any], telegram_user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve user with existing mapping."""
        try:
            # Update user profile if needed
            self._update_telegram_user_profile(existing_mapping['name'], telegram_user_data)
            
            # Check if user is blocked
            if existing_mapping.get('is_blocked'):
                return {
                    'success': False,
                    'error': 'blocked_user',
                    'message': 'User is blocked from creating tickets',
                    'telegram_user': existing_mapping['name'],
                    'customer': existing_mapping.get('customer'),
                    'contact': existing_mapping.get('contact')
                }
            
            # Check verification status
            if self.settings['require_phone_verification'] and not existing_mapping.get('is_verified'):
                return {
                    'success': False,
                    'error': 'verification_required',
                    'message': 'Phone verification required',
                    'telegram_user': existing_mapping['name'],
                    'verification_required': True
                }
            
            return {
                'success': True,
                'telegram_user': existing_mapping['name'],
                'customer': existing_mapping.get('customer'),
                'contact': existing_mapping.get('contact'),
                'is_new': False
            }
            
        except Exception as e:
            frappe.log_error(f"Error resolving existing user: {str(e)}")
            return self._create_error_result("Failed to resolve existing user")
    
    def _try_auto_link_customer(self, telegram_user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> Optional[str]:
        """Try to automatically link to existing customer by phone or email."""
        if not (self.settings['auto_link_by_phone'] or self.settings['auto_link_by_email']):
            return None
        
        # Extract contact information
        phone_number = self._extract_phone_number(telegram_user_data, message_data)
        email = self._extract_email(telegram_user_data, message_data)
        
        # Try linking by phone
        if phone_number and self.settings['auto_link_by_phone']:
            customer = self._find_customer_by_phone(phone_number)
            if customer:
                return customer
        
        # Try linking by email  
        if email and self.settings['auto_link_by_email']:
            customer = self._find_customer_by_email(email)
            if customer:
                return customer
        
        return None
    
    def _extract_phone_number(self, telegram_user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> Optional[str]:
        """Extract phone number from Telegram user data or message content."""
        # Check if user shared their phone with the bot
        if message_data and 'contact' in message_data:
            contact = message_data['contact']
            if contact.get('user_id') == telegram_user_data.get('id'):
                return contact.get('phone_number')
        
        # Look for phone in message text
        if message_data and 'text' in message_data:
            text = message_data['text']
            phone_pattern = re.compile(r'[\+]?[1-9]?[0-9]{7,15}')
            phones = phone_pattern.findall(text)
            if phones:
                return phones[0]  # Return first found phone
        
        return None
    
    def _extract_email(self, telegram_user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> Optional[str]:
        """Extract email from message content."""
        if not message_data or 'text' not in message_data:
            return None
        
        text = message_data['text']
        email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        emails = email_pattern.findall(text)
        
        if emails:
            # Validate the email
            try:
                validate_email_address(emails[0])
                return emails[0]
            except Exception:
                pass
        
        return None
    
    def _find_customer_by_phone(self, phone_number: str) -> Optional[str]:
        """Find customer by phone number."""
        try:
            # Clean phone number
            clean_phone = re.sub(r'[^\d+]', '', phone_number)
            
            # Search in Contact doctype first
            contacts = frappe.db.sql("""
                SELECT DISTINCT c.name as contact_name, dl.link_name as customer_name
                FROM `tabContact` c
                LEFT JOIN `tabDynamic Link` dl ON dl.parent = c.name 
                    AND dl.link_doctype = 'HD Customer'
                WHERE (c.phone = %s OR c.mobile_no = %s)
                    AND c.disabled = 0
                LIMIT 1
            """, (clean_phone, clean_phone), as_dict=True)
            
            if contacts and contacts[0].customer_name:
                return contacts[0].customer_name
            
            # Search in HD Customer records
            customers = frappe.db.sql("""
                SELECT name FROM `tabHD Customer`
                WHERE name = %s OR customer_name LIKE %s
                LIMIT 1
            """, (clean_phone, f"%{clean_phone}%"), as_dict=True)
            
            return customers[0].name if customers else None
            
        except Exception as e:
            frappe.log_error(f"Error finding customer by phone: {str(e)}")
            return None
    
    def _find_customer_by_email(self, email: str) -> Optional[str]:
        """Find customer by email address."""
        try:
            # Search in Contact doctype first
            contacts = frappe.db.sql("""
                SELECT DISTINCT c.name as contact_name, dl.link_name as customer_name
                FROM `tabContact` c
                LEFT JOIN `tabDynamic Link` dl ON dl.parent = c.name 
                    AND dl.link_doctype = 'HD Customer'
                WHERE c.email_id = %s AND c.disabled = 0
                LIMIT 1
            """, (email,), as_dict=True)
            
            if contacts and contacts[0].customer_name:
                return contacts[0].customer_name
            
            # Search in HD Customer doctype by name/customer_name
            customers = frappe.db.sql("""
                SELECT name FROM `tabHD Customer`
                WHERE customer_name LIKE %s
                LIMIT 1
            """, (f"%{email}%",), as_dict=True)
            
            return customers[0].name if customers else None
            
        except Exception as e:
            frappe.log_error(f"Error finding customer by email: {str(e)}")
            return None
    
    def _create_mapping_for_existing_customer(self, customer_name: str, telegram_user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Telegram user mapping for existing customer."""
        try:
            # Get or create contact for this customer
            contact_name = self._get_or_create_contact_for_customer(customer_name, telegram_user_data)
            
            # Create HD Telegram User record
            telegram_user = frappe.get_doc({
                'doctype': 'HD Telegram User',
                'telegram_user_id': telegram_user_data.get('id'),
                'first_name': telegram_user_data.get('first_name', ''),
                'last_name': telegram_user_data.get('last_name', ''),
                'username': telegram_user_data.get('username', ''),
                'language_code': telegram_user_data.get('language_code', 'en'),
                'customer': customer_name,
                'contact': contact_name,
                'is_verified': True,  # Auto-verified since linked to existing customer
                'verification_method': 'auto_linked',
                'joined_at': now()
            })
            
            telegram_user.insert(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                'success': True,
                'telegram_user': telegram_user.name,
                'customer': customer_name,
                'contact': contact_name,
                'is_new': True,
                'auto_linked': True
            }
            
        except Exception as e:
            frappe.log_error(f"Error creating mapping for existing customer: {str(e)}")
            return self._create_error_result("Failed to create customer mapping")
    
    def _create_new_customer_mapping(self, telegram_user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create new customer and mapping."""
        try:
            # Generate customer name
            customer_name = self._generate_customer_name(telegram_user_data)
            
            # Create HD Customer (Helpdesk Customer)
            customer = frappe.get_doc({
                'doctype': 'HD Customer',
                'customer_name': customer_name
            })
            
            customer.insert(ignore_permissions=True)
            
            # Create Contact
            contact_name = self._create_contact_for_customer(customer.name, telegram_user_data, message_data)
            
            # Determine verification status
            is_verified = not self.settings['require_phone_verification']
            verification_method = 'auto_created' if is_verified else 'pending'
            
            # Create HD Telegram User record
            telegram_user = frappe.get_doc({
                'doctype': 'HD Telegram User',
                'telegram_user_id': telegram_user_data.get('id'),
                'first_name': telegram_user_data.get('first_name', ''),
                'last_name': telegram_user_data.get('last_name', ''),
                'username': telegram_user_data.get('username', ''),
                'language_code': telegram_user_data.get('language_code', 'en'),
                'customer': customer.name,
                'contact': contact_name,
                'is_verified': is_verified,
                'verification_method': verification_method,
                'joined_at': now()
            })
            
            telegram_user.insert(ignore_permissions=True)
            frappe.db.commit()
            
            result = {
                'success': True,
                'telegram_user': telegram_user.name,
                'customer': customer.name,
                'contact': contact_name,
                'is_new': True,
                'customer_created': True
            }
            
            if not is_verified:
                result['verification_required'] = True
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Error creating new customer mapping: {str(e)}")
            return self._create_error_result("Failed to create new customer")
    
    def _create_unverified_mapping(self, telegram_user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create unverified mapping when auto-creation is disabled."""
        try:
            # Create HD Telegram User record without customer link
            telegram_user = frappe.get_doc({
                'doctype': 'HD Telegram User',
                'telegram_user_id': telegram_user_data.get('id'),
                'first_name': telegram_user_data.get('first_name', ''),
                'last_name': telegram_user_data.get('last_name', ''),
                'username': telegram_user_data.get('username', ''),
                'language_code': telegram_user_data.get('language_code', 'en'),
                'is_verified': False,
                'verification_method': 'pending_admin',
                'joined_at': now()
            })
            
            telegram_user.insert(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                'success': False,
                'error': 'verification_required',
                'message': 'Manual verification required by administrator',
                'telegram_user': telegram_user.name,
                'verification_required': True,
                'admin_verification_required': True
            }
            
        except Exception as e:
            frappe.log_error(f"Error creating unverified mapping: {str(e)}")
            return self._create_error_result("Failed to create user record")
    
    def _get_or_create_contact_for_customer(self, customer_name: str, telegram_user_data: Dict[str, Any]) -> str:
        """Get existing contact or create new one for customer."""
        try:
            # Try to find existing contact for this customer
            existing_contacts = frappe.db.sql("""
                SELECT c.name
                FROM `tabContact` c
                INNER JOIN `tabDynamic Link` dl ON dl.parent = c.name
                WHERE dl.link_doctype = 'Customer' 
                    AND dl.link_name = %s
                    AND c.disabled = 0
                ORDER BY c.creation DESC
                LIMIT 1
            """, (customer_name,), as_dict=True)
            
            if existing_contacts:
                return existing_contacts[0].name
            
            # Create new contact
            return self._create_contact_for_customer(customer_name, telegram_user_data)
            
        except Exception as e:
            frappe.log_error(f"Error getting/creating contact: {str(e)}")
            raise
    
    def _create_contact_for_customer(self, customer_name: str, telegram_user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> str:
        """Create new contact for customer."""
        try:
            contact_name = self._generate_contact_name(telegram_user_data)
            phone_number = self._extract_phone_number(telegram_user_data, message_data)
            email = self._extract_email(telegram_user_data, message_data)
            
            contact = frappe.get_doc({
                'doctype': 'Contact',
                'first_name': telegram_user_data.get('first_name', 'Telegram'),
                'last_name': telegram_user_data.get('last_name', 'User'),
                'mobile_no': phone_number,
                'email_id': email,
                'links': [{
                    'link_doctype': 'HD Customer',
                    'link_name': customer_name
                }]
            })
            
            contact.insert(ignore_permissions=True)
            return contact.name
            
        except Exception as e:
            frappe.log_error(f"Error creating contact: {str(e)}")
            raise
    
    def _generate_customer_name(self, telegram_user_data: Dict[str, Any]) -> str:
        """Generate a unique customer name."""
        first_name = telegram_user_data.get('first_name', '')
        last_name = telegram_user_data.get('last_name', '')
        username = telegram_user_data.get('username', '')
        telegram_id = telegram_user_data.get('id', '')
        
        # Build base name
        if first_name and last_name:
            base_name = f"{first_name} {last_name}"
        elif first_name:
            base_name = first_name
        elif username:
            base_name = f"@{username}"
        else:
            base_name = f"Telegram User {telegram_id}"
        
        # Ensure uniqueness
        return self._ensure_unique_name('HD Customer', base_name)
    
    def _generate_contact_name(self, telegram_user_data: Dict[str, Any]) -> str:
        """Generate contact name (Frappe auto-generates, but this is for reference)."""
        first_name = telegram_user_data.get('first_name', 'Telegram')
        last_name = telegram_user_data.get('last_name', 'User')
        return f"{first_name} {last_name}".strip()
    
    def _ensure_unique_name(self, doctype: str, base_name: str) -> str:
        """Ensure the name is unique by appending numbers if needed."""
        name = base_name
        counter = 1
        
        while frappe.db.exists(doctype, name):
            name = f"{base_name} {counter}"
            counter += 1
        
        return name
    
    def _update_telegram_user_profile(self, telegram_user_name: str, telegram_user_data: Dict[str, Any]):
        """Update Telegram user profile with latest data."""
        try:
            telegram_user = frappe.get_doc('HD Telegram User', telegram_user_name)
            
            # Update fields that might change
            telegram_user.first_name = telegram_user_data.get('first_name', telegram_user.first_name)
            telegram_user.last_name = telegram_user_data.get('last_name', telegram_user.last_name)
            telegram_user.username = telegram_user_data.get('username', telegram_user.username)
            telegram_user.language_code = telegram_user_data.get('language_code', telegram_user.language_code)
            telegram_user.last_seen = now()
            
            telegram_user.save(ignore_permissions=True)
            
        except Exception as e:
            frappe.log_error(f"Error updating Telegram user profile: {str(e)}")
    
    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error result."""
        return {
            'success': False,
            'error': 'resolution_failed',
            'message': error_message
        }
    
    def verify_phone_number(self, telegram_user_name: str, phone_number: str) -> Dict[str, Any]:
        """
        Start phone number verification process.
        
        Args:
            telegram_user_name: HD Telegram User record name
            phone_number: Phone number to verify
            
        Returns:
            Dict containing verification result
        """
        try:
            # Generate verification code
            verification_code = random_string(6).upper()
            
            # Store verification data
            frappe.db.set_value(
                'HD Telegram User', 
                telegram_user_name,
                {
                    'verification_code': verification_code,
                    'verification_phone': phone_number,
                    'verification_code_sent': now(),
                    'verification_attempts': 0
                }
            )
            
            # Here you would integrate with SMS service
            # For now, we'll just log the code
            frappe.log_error(
                message=f"Verification code for {phone_number}: {verification_code}",
                title="Telegram Phone Verification"
            )
            
            return {
                'success': True,
                'message': f'Verification code sent to {phone_number}',
                'verification_code': verification_code  # Remove in production
            }
            
        except Exception as e:
            frappe.log_error(f"Error sending verification code: {str(e)}")
            return {
                'success': False,
                'error': 'verification_failed',
                'message': 'Failed to send verification code'
            }
    
    def confirm_phone_verification(self, telegram_user_name: str, verification_code: str) -> Dict[str, Any]:
        """
        Confirm phone number verification.
        
        Args:
            telegram_user_name: HD Telegram User record name
            verification_code: Code entered by user
            
        Returns:
            Dict containing confirmation result
        """
        try:
            telegram_user = frappe.get_doc('HD Telegram User', telegram_user_name)
            
            # Check if verification is still valid
            if not telegram_user.verification_code:
                return {
                    'success': False,
                    'error': 'no_verification_pending',
                    'message': 'No verification code pending'
                }
            
            # Check expiry
            if telegram_user.verification_code_sent:
                import datetime
                sent_time = get_datetime(telegram_user.verification_code_sent)
                expiry_time = sent_time + datetime.timedelta(seconds=self.settings['verification_code_expiry'])
                
                if get_datetime() > expiry_time:
                    return {
                        'success': False,
                        'error': 'verification_expired',
                        'message': 'Verification code has expired'
                    }
            
            # Check attempts
            if telegram_user.verification_attempts >= 3:
                return {
                    'success': False,
                    'error': 'too_many_attempts',
                    'message': 'Too many verification attempts'
                }
            
            # Verify code
            if telegram_user.verification_code.upper() != verification_code.upper():
                # Increment attempts
                telegram_user.verification_attempts += 1
                telegram_user.save(ignore_permissions=True)
                
                return {
                    'success': False,
                    'error': 'invalid_code',
                    'message': 'Invalid verification code',
                    'attempts_remaining': 3 - telegram_user.verification_attempts
                }
            
            # Success - mark as verified
            telegram_user.is_verified = True
            telegram_user.verification_method = 'phone_verified'
            telegram_user.verified_at = now()
            telegram_user.verification_code = ''
            telegram_user.verification_phone = ''
            telegram_user.verification_code_sent = None
            telegram_user.verification_attempts = 0
            
            # Update contact with verified phone
            if telegram_user.contact and telegram_user.verification_phone:
                frappe.db.set_value(
                    'Contact',
                    telegram_user.contact,
                    'mobile_no',
                    telegram_user.verification_phone
                )
            
            telegram_user.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                'success': True,
                'message': 'Phone number verified successfully'
            }
            
        except Exception as e:
            frappe.log_error(f"Error confirming phone verification: {str(e)}")
            return {
                'success': False,
                'error': 'verification_failed',
                'message': 'Failed to verify phone number'
            }


# Helper functions for external use

def resolve_telegram_user(telegram_user_data: Dict[str, Any], message_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Convenience function to resolve a Telegram user.
    
    Args:
        telegram_user_data: Telegram user information
        message_data: Optional full message data
        
    Returns:
        Resolution result
    """
    mapper = TelegramUserMapper()
    return mapper.resolve_user(telegram_user_data, message_data)


def get_customer_for_telegram_user(telegram_user_id: int) -> Optional[str]:
    """
    Get customer name for a Telegram user ID.
    
    Args:
        telegram_user_id: Telegram user ID
        
    Returns:
        Customer name if found, None otherwise
    """
    try:
        result = frappe.db.get_value(
            'HD Telegram User',
            {'telegram_user_id': telegram_user_id},
            'customer'
        )
        return result
    except Exception:
        return None


def is_telegram_user_verified(telegram_user_id: int) -> bool:
    """
    Check if a Telegram user is verified.
    
    Args:
        telegram_user_id: Telegram user ID
        
    Returns:
        True if verified, False otherwise
    """
    try:
        result = frappe.db.get_value(
            'HD Telegram User',
            {'telegram_user_id': telegram_user_id},
            'is_verified'
        )
        return bool(result)
    except Exception:
        return False 