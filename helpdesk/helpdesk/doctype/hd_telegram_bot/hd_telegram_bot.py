# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_site_url, now_datetime


class HDTelegramBot(Document):
    def before_save(self):
        """Validation and setup before saving the document"""
        self.validate_bot_token()
        self.set_webhook_url()
        self.set_created_on()
    
    def validate_bot_token(self):
        """Validate bot token format and connectivity"""
        if not self.bot_token:
            return
        
        # Basic token format validation (should be like: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11)
        token_parts = self.bot_token.split(':')
        if len(token_parts) != 2:
            frappe.throw(_("Invalid bot token format. Token should be in format 'bot_id:auth_token'"))
        
        bot_id, auth_token = token_parts
        if not bot_id.isdigit() or len(auth_token) < 35:
            frappe.throw(_("Invalid bot token format"))
    
    def set_webhook_url(self):
        """Set the webhook URL based on site URL"""
        if not self.webhook_url:
            site_url = get_site_url(frappe.local.site)
            self.webhook_url = f"{site_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
    
    def set_created_on(self):
        """Set created_on timestamp for new documents"""
        if self.is_new():
            self.created_on = now_datetime()
    
    @frappe.whitelist()
    def test_bot_connection(self):
        """Test bot connectivity with Telegram API"""
        if not self.bot_token:
            frappe.throw(_("Bot token is required"))
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    return {
                        'success': True,
                        'message': _("Bot connection successful"),
                        'bot_info': bot_info.get('result', {})
                    }
            
            return {
                'success': False,
                'message': _("Failed to connect to Telegram API"),
                'error': response.text
            }
        
        except requests.RequestException as e:
            return {
                'success': False,
                'message': _("Connection error"),
                'error': str(e)
            }
    
    @frappe.whitelist()
    def setup_webhook(self):
        """Setup webhook with Telegram"""
        if not self.bot_token or not self.webhook_url:
            frappe.throw(_("Bot token and webhook URL are required"))
        
        try:
            # Generate webhook secret for security
            import secrets
            webhook_secret = secrets.token_urlsafe(32)
            
            url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
            payload = {
                'url': self.webhook_url,
                'secret_token': webhook_secret,
                'allowed_updates': ['message', 'callback_query'],
                'drop_pending_updates': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    # Save webhook secret and setup time
                    self.webhook_secret = webhook_secret
                    self.last_webhook_setup = now_datetime()
                    self.save()
                    
                    return {
                        'success': True,
                        'message': _("Webhook setup successful"),
                        'webhook_info': result.get('result', {})
                    }
            
            return {
                'success': False,
                'message': _("Failed to setup webhook"),
                'error': response.text
            }
        
        except Exception as e:
            frappe.log_error("Telegram Webhook Setup Error", str(e))
            return {
                'success': False,
                'message': _("Webhook setup error"),
                'error': str(e)
            }
    
    @frappe.whitelist()
    def remove_webhook(self):
        """Remove webhook from Telegram"""
        if not self.bot_token:
            frappe.throw(_("Bot token is required"))
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/deleteWebhook"
            response = requests.post(url, json={'drop_pending_updates': True}, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    # Clear webhook secret
                    self.webhook_secret = ""
                    self.save()
                    
                    return {
                        'success': True,
                        'message': _("Webhook removed successfully")
                    }
            
            return {
                'success': False,
                'message': _("Failed to remove webhook"),
                'error': response.text
            }
        
        except Exception as e:
            frappe.log_error("Telegram Webhook Removal Error", str(e))
            return {
                'success': False,
                'message': _("Webhook removal error"),
                'error': str(e)
            }
    
    @frappe.whitelist()
    def get_webhook_info(self):
        """Get current webhook information from Telegram"""
        if not self.bot_token:
            frappe.throw(_("Bot token is required"))
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getWebhookInfo"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return {
                        'success': True,
                        'webhook_info': result.get('result', {})
                    }
            
            return {
                'success': False,
                'message': _("Failed to get webhook info"),
                'error': response.text
            }
        
        except Exception as e:
            return {
                'success': False,
                'message': _("Error getting webhook info"),
                'error': str(e)
            }
    
    def increment_message_count(self):
        """Increment the total message count"""
        self.db_set('total_messages_received', self.total_messages_received + 1)
        self.db_set('last_message_received', now_datetime())
    
    def increment_ticket_count(self):
        """Increment the total ticket count"""
        self.db_set('total_tickets_created', self.total_tickets_created + 1)
    
    def is_rate_limited(self, user_id):
        """Check if user is rate limited"""
        if not self.rate_limit_per_hour:
            return False
        
        # Use Redis cache for rate limiting
        cache_key = f"telegram_rate_limit:{self.name}:{user_id}"
        current_count = frappe.cache().get(cache_key) or 0
        
        return current_count >= self.rate_limit_per_hour
    
    def increment_rate_limit(self, user_id):
        """Increment rate limit counter for user"""
        cache_key = f"telegram_rate_limit:{self.name}:{user_id}"
        current_count = frappe.cache().get(cache_key) or 0
        frappe.cache().set(cache_key, current_count + 1, expires_in_sec=3600)


@frappe.whitelist()
def get_active_bot():
    """Get the active telegram bot"""
    bot = frappe.db.get_value(
        "HD Telegram Bot", 
        {"is_active": 1}, 
        ["name", "bot_name", "bot_token", "default_team", "default_priority", "auto_acknowledge", "enable_status_commands"],
        as_dict=True
    )
    return bot


@frappe.whitelist()
def validate_bot_token(token):
    """Validate bot token format"""
    if not token:
        return {"valid": False, "message": "Token is required"}
    
    token_parts = token.split(':')
    if len(token_parts) != 2:
        return {"valid": False, "message": "Invalid token format"}
    
    bot_id, auth_token = token_parts
    if not bot_id.isdigit() or len(auth_token) < 35:
        return {"valid": False, "message": "Invalid token format"}
    
    return {"valid": True, "message": "Token format is valid"} 