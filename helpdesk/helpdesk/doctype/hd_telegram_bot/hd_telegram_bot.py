# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_site_url, now_datetime
from helpdesk.helpdesk.utils.json_utils import safe_serialize_response, format_telegram_id


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
        # Validate bot_id format without converting to integer to avoid overflow
        if not bot_id.isdigit() or len(bot_id) < 3 or len(auth_token) < 35:
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
                    # Convert large integers to strings to prevent serialization errors
                    safe_bot_info = safe_serialize_response(bot_info.get('result', {}))
                    return {
                        'success': True,
                        'message': _("Bot connection successful"),
                        'bot_info': safe_bot_info
                    }
            
            return safe_serialize_response({
                'success': False,
                'message': _("Failed to connect to Telegram API"),
                'error': response.text
            })
        
        except requests.RequestException as e:
            return safe_serialize_response({
                'success': False,
                'message': _("Connection error"),
                'error': str(e)
            })
    
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
            
            # Log the request for debugging
            frappe.log_error(f"Setting webhook - URL: {url}, Payload: {payload}", "Webhook Setup Debug")
            
            response = requests.post(url, json=payload, timeout=30)
            
            # Log the response for debugging
            frappe.log_error(f"Webhook response - Status: {response.status_code}, Content: {response.text}", "Webhook Setup Response")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    # Save webhook secret and setup time
                    self.webhook_secret = webhook_secret
                    self.last_webhook_setup = now_datetime()
                    self.save()
                    
                    # Convert large integers to strings to prevent serialization errors
                    safe_webhook_info = safe_serialize_response(result.get('result', {}))
                    return {
                        'success': True,
                        'message': _("Webhook setup successful"),
                        'webhook_info': safe_webhook_info
                    }
                else:
                    # Telegram API returned error
                    error_msg = result.get('description', 'Unknown error from Telegram API')
                    frappe.log_error(f"Telegram API error: {error_msg}", "Webhook Setup Error")
                    return safe_serialize_response({
                        'success': False,
                        'message': _("Telegram API error: {0}").format(error_msg),
                        'error': result
                    })
            else:
                # HTTP error
                frappe.log_error(f"HTTP error {response.status_code}: {response.text}", "Webhook Setup HTTP Error")
                return safe_serialize_response({
                    'success': False,
                    'message': _("HTTP error {0}: {1}").format(response.status_code, response.text),
                    'error': response.text
                })
        
        except requests.RequestException as e:
            frappe.log_error(f"Network error during webhook setup: {str(e)}", "Webhook Setup Network Error")
            return safe_serialize_response({
                'success': False,
                'message': _("Network error: {0}").format(str(e)),
                'error': str(e)
            })
        except Exception as e:
            frappe.log_error(f"Unexpected error during webhook setup: {str(e)}", "Webhook Setup Error")
            return safe_serialize_response({
                'success': False,
                'message': _("Webhook setup error: {0}").format(str(e)),
                'error': str(e)
            })
    
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
                    
                    return safe_serialize_response({
                        'success': True,
                        'message': _("Webhook removed successfully")
                    })
            
            return safe_serialize_response({
                'success': False,
                'message': _("Failed to remove webhook"),
                'error': response.text
            })
        
        except Exception as e:
            frappe.log_error("Telegram Webhook Removal Error", str(e))
            return safe_serialize_response({
                'success': False,
                'message': _("Webhook removal error"),
                'error': str(e)
            })
    
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
                    # Convert large integers to strings to prevent serialization errors
                    safe_webhook_info = safe_serialize_response(result.get('result', {}))
                    return {
                        'success': True,
                        'webhook_info': safe_webhook_info
                    }
            
            return safe_serialize_response({
                'success': False,
                'message': _("Failed to get webhook info"),
                'error': response.text
            })
        
        except Exception as e:
            return safe_serialize_response({
                'success': False,
                'message': _("Error getting webhook info"),
                'error': str(e)
            })
    
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
    def start_testing_session(self):
        """Start ngrok testing session for development"""
        try:
            from helpdesk.helpdesk.utils.ngrok_manager import NgrokTestingManager
            
            manager = NgrokTestingManager()
            result = manager.start_testing_session(self.name)
            
            if result.get('success'):
                frappe.msgprint(
                    msg=_(f"Ngrok tunnel created successfully!<br><br>"
                          f"<strong>Tunnel URL:</strong> {result.get('tunnel_url')}<br>"
                          f"<strong>Webhook URL:</strong> {result.get('webhook_url')}<br>"
                          f"<strong>Port:</strong> {result.get('port')}<br><br>"
                          f"You can now test your bot with this tunnel."),
                    title=_('Testing Session Started'),
                    indicator='green'
                )
            else:
                frappe.msgprint(
                    msg=_(f"Failed to start testing session: {result.get('message')}"),
                    title=_('Testing Session Failed'),
                    indicator='red'
                )
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Error starting testing session: {str(e)}")
            frappe.msgprint(
                msg=_(f"Error starting testing session: {str(e)}"),
                title=_('Error'),
                indicator='red'
            )
            return safe_serialize_response({
                'success': False,
                'error': 'session_start_error',
                'message': str(e)
            })
    
    @frappe.whitelist()
    def stop_testing_session(self):
        """Stop ngrok testing session"""
        try:
            from helpdesk.helpdesk.utils.ngrok_manager import NgrokTestingManager
            
            manager = NgrokTestingManager()
            result = manager.stop_testing_session(self.name)
            
            if result.get('success'):
                frappe.msgprint(
                    msg=_("Testing session stopped successfully. Ngrok tunnel has been closed."),
                    title=_('Testing Session Stopped'),
                    indicator='green'
                )
            else:
                frappe.msgprint(
                    msg=_(f"Failed to stop testing session: {result.get('message')}"),
                    title=_('Error Stopping Session'),
                    indicator='orange'
                )
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Error stopping testing session: {str(e)}")
            frappe.msgprint(
                msg=_(f"Error stopping testing session: {str(e)}"),
                title=_('Error'),
                indicator='red'
            )
            return safe_serialize_response({
                'success': False,
                'error': 'session_stop_error',
                'message': str(e)
            })
    
    @frappe.whitelist()
    def get_testing_status(self):
        """Get current testing session status"""
        try:
            from helpdesk.helpdesk.utils.ngrok_manager import NgrokTestingManager
            
            manager = NgrokTestingManager()
            result = manager.get_tunnel_status(self.name)
            
            return result
            
        except Exception as e:
            frappe.log_error(f"Error getting testing status: {str(e)}")
            return safe_serialize_response({
                'success': False,
                'error': 'status_check_error',
                'message': str(e)
            })
    
    @frappe.whitelist()
    def send_test_message(self, chat_id, message=None):
        """Send a test message to verify bot functionality"""
        if not self.bot_token:
            frappe.throw(_("Bot token is required"))
        
        if not chat_id:
            frappe.throw(_("Chat ID is required"))
        
        try:
            import requests
            
            # Default test message
            if not message:
                message = f"🤖 Test message from {self.bot_name}\n\n" \
                         f"✅ Bot is working correctly!\n" \
                         f"📅 Sent at: {frappe.utils.now()}\n" \
                         f"🔗 Webhook: {'Active' if self.test_mode_enabled else 'Production'}"
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': str(chat_id),
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return safe_serialize_response({
                        'success': True,
                        'message': _("Test message sent successfully"),
                        'telegram_response': result.get('result', {})
                    })
            
            return safe_serialize_response({
                'success': False,
                'message': _("Failed to send test message"),
                'error': response.text
            })
        
        except requests.RequestException as e:
            return safe_serialize_response({
                'success': False,
                'message': _("Network error sending test message"),
                'error': str(e)
            })
        except Exception as e:
            frappe.log_error("Test Message Send Error", str(e))
            return safe_serialize_response({
                'success': False,
                'message': _("Error sending test message"),
                'error': str(e)
            })
    
    @frappe.whitelist()
    def get_recent_chats(self):
        """Get recent chat updates to help find chat IDs for testing"""
        if not self.bot_token:
            frappe.throw(_("Bot token is required"))
        
        try:
            import requests
            
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {
                'limit': 10,  # Get last 10 updates
                'timeout': 5
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    updates = result.get('result', [])
                    
                    # Extract unique chats
                    chats = {}
                    for update in updates:
                        if 'message' in update:
                            chat = update['message'].get('chat', {})
                            chat_id = chat.get('id')
                            if chat_id:
                                chats[str(chat_id)] = {
                                    'chat_id': str(chat_id),
                                    'type': chat.get('type', 'unknown'),
                                    'title': chat.get('title', ''),
                                    'first_name': chat.get('first_name', ''),
                                    'last_name': chat.get('last_name', ''),
                                    'username': chat.get('username', ''),
                                    'last_message_date': update['message'].get('date', 0)
                                }
                    
                    return safe_serialize_response({
                        'success': True,
                        'chats': list(chats.values()),
                        'total_updates': len(updates)
                    })
            
            return safe_serialize_response({
                'success': False,
                'message': _("Failed to get recent chats"),
                'error': response.text
            })
        
        except requests.RequestException as e:
            return safe_serialize_response({
                'success': False,
                'message': _("Network error getting recent chats"),
                'error': str(e)
            })
        except Exception as e:
            frappe.log_error("Get Recent Chats Error", str(e))
            return safe_serialize_response({
                'success': False,
                'message': _("Error getting recent chats"),
                'error': str(e)
            })
    
    @frappe.whitelist()
    def update_webhook_secret(self, new_webhook_url=None, force_regenerate=False):
        """
        Update webhook secret and URL when testing mode changes or tunnels regenerate.
        
        Args:
            new_webhook_url: New webhook URL (for testing mode)
            force_regenerate: Force regeneration of webhook secret
            
        Returns:
            Dict containing update result with new secret
        """
        if not self.bot_token:
            frappe.throw(_("Bot token is required"))
        
        try:
            import secrets
            import requests
            
            # Generate new webhook secret
            new_webhook_secret = secrets.token_urlsafe(32)
            
            # Determine webhook URL
            if new_webhook_url:
                webhook_url = new_webhook_url
            elif self.test_mode_enabled and self.ngrok_tunnel_url:
                webhook_url = f"{self.ngrok_tunnel_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
            else:
                webhook_url = self.webhook_url or f"{frappe.utils.get_site_url()}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
            
            # Update Telegram webhook
            telegram_api_url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
            payload = {
                'url': webhook_url,
                'secret_token': new_webhook_secret,
                'allowed_updates': ['message', 'callback_query'],
                'drop_pending_updates': True
            }
            
            frappe.log_error(f"Updating webhook secret - URL: {telegram_api_url}, Webhook: {webhook_url}", "Webhook Secret Update")
            
            response = requests.post(telegram_api_url, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    # Update database with new secret and URL
                    self.db_set('webhook_secret', new_webhook_secret)
                    self.db_set('webhook_url', webhook_url)
                    self.db_set('last_webhook_setup', frappe.utils.now_datetime())
                    
                    frappe.log_error(f"Webhook secret updated successfully - New secret: {new_webhook_secret[:8]}****", "Webhook Secret Update Success")
                    
                    return safe_serialize_response({
                        'success': True,
                        'message': _("Webhook secret updated successfully"),
                        'webhook_url': webhook_url,
                        'webhook_secret': new_webhook_secret,
                        'telegram_response': result
                    })
                else:
                    error_msg = result.get('description', 'Unknown error from Telegram API')
                    frappe.log_error(f"Telegram API error updating webhook: {error_msg}", "Webhook Secret Update Error")
                    return safe_serialize_response({
                        'success': False,
                        'message': f"Telegram API error: {error_msg}",
                        'error': result
                    })
            else:
                frappe.log_error(f"HTTP error updating webhook: {response.status_code} - {response.text}", "Webhook Secret Update HTTP Error")
                return safe_serialize_response({
                    'success': False,
                    'message': f"HTTP error {response.status_code}: {response.text}",
                    'error': response.text
                })
                
        except requests.RequestException as e:
            frappe.log_error(f"Network error updating webhook secret: {str(e)}", "Webhook Secret Update Network Error")
            return safe_serialize_response({
                'success': False,
                'message': f"Network error: {str(e)}",
                'error': str(e)
            })
        except Exception as e:
            frappe.log_error(f"Unexpected error updating webhook secret: {str(e)}", "Webhook Secret Update Error")
            return safe_serialize_response({
                'success': False,
                'message': f"Failed to update webhook secret: {str(e)}",
                'error': str(e)
            })
    
    @frappe.whitelist()
    def refresh_testing_webhook(self):
        """
        Refresh webhook configuration for active testing session.
        Call this when bench restarts or tunnel URL changes.
        
        Returns:
            Dict containing refresh result
        """
        try:
            if not self.test_mode_enabled:
                return safe_serialize_response({
                    'success': False,
                    'message': _("Testing mode is not enabled")
                })
            
            if not self.ngrok_tunnel_url:
                return safe_serialize_response({
                    'success': False,
                    'message': _("No ngrok tunnel URL found")
                })
            
            # Update webhook with current tunnel URL
            webhook_url = f"{self.ngrok_tunnel_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
            result = self.update_webhook_secret(new_webhook_url=webhook_url, force_regenerate=True)
            
            if result.get('success'):
                # Update testing status
                self.db_set('testing_status', 'Active - Webhook Refreshed')
                
                frappe.log_error(f"Testing webhook refreshed for bot {self.bot_name}", "Testing Webhook Refresh")
                
                return safe_serialize_response({
                    'success': True,
                    'message': _("Testing webhook refreshed successfully"),
                    'webhook_url': result.get('webhook_url'),
                    'webhook_secret': result.get('webhook_secret')
                })
            else:
                return result
                
        except Exception as e:
            frappe.log_error(f"Error refreshing testing webhook: {str(e)}", "Testing Webhook Refresh Error")
            return safe_serialize_response({
                'success': False,
                'message': f"Failed to refresh testing webhook: {str(e)}",
                'error': str(e)
            })


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
        return safe_serialize_response({"valid": False, "message": "Token is required"})
    
    token_parts = token.split(':')
    if len(token_parts) != 2:
        return safe_serialize_response({"valid": False, "message": "Invalid token format"})
    
    bot_id, auth_token = token_parts
    # Validate bot_id format without converting to integer to avoid overflow
    if not bot_id.isdigit() or len(bot_id) < 3 or len(auth_token) < 35:
        return safe_serialize_response({"valid": False, "message": "Invalid token format"})
    
    return safe_serialize_response({"valid": True, "message": "Token format is valid"}) 