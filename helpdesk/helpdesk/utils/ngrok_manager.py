#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ngrok Testing Manager for Helpdesk Telegram Integration

This module provides automated ngrok tunnel management for seamless webhook testing
during development. It handles tunnel creation, webhook updates, and session management.
"""

import os
import sys
import json
import time
import subprocess
import requests
import frappe
from frappe import _
from frappe.utils import now, get_datetime, cstr
from typing import Dict, Any, Optional, Tuple
import platform
import zipfile
import tarfile
from pathlib import Path


class NgrokTestingManager:
    """
    Manages ngrok tunnels for Telegram webhook testing during development.
    
    Features:
    - Support for both ngrok Python API and CLI approaches
    - Automatic ngrok installation and updates
    - Tunnel creation and management 
    - Webhook URL synchronization with Telegram
    - Session tracking and cleanup
    - Cross-platform support (Windows, macOS, Linux)
    - Proper authentication handling
    """
    
    def __init__(self):
        """Initialize the ngrok manager."""
        self.ngrok_path = self._get_ngrok_path()
        self.api_base = "http://localhost:4040/api"
        self.sessions = {}
    
    def _get_ngrok_api_key(self) -> Optional[str]:
        """Get ngrok API key from site config or environment."""
        # Try to get from site config first
        api_key = frappe.conf.get('ngrok_api_key')
        if api_key:
            return api_key
        
        # Try environment variable
        api_key = os.environ.get('NGROK_API_KEY')
        if api_key:
            return api_key
        
        return None
    
    def _get_ngrok_authtoken(self) -> Optional[str]:
        """Get ngrok authtoken from site config or environment."""
        # Try to get from site config first
        authtoken = frappe.conf.get('ngrok_authtoken')
        if authtoken:
            return authtoken
        
        # Try environment variable
        authtoken = os.environ.get('NGROK_AUTHTOKEN')
        if authtoken:
            return authtoken
        
        return None
    

    
    def _get_ngrok_path(self) -> str:
        """Get the ngrok binary path."""
        system = platform.system().lower()
        if system == "windows":
            return os.path.join(frappe.get_site_path(), "private", "ngrok", "ngrok.exe")
        else:
            return os.path.join(frappe.get_site_path(), "private", "ngrok", "ngrok")
    
    def start_testing_session(self, bot_name: str) -> Dict[str, Any]:
        """
        Start a testing session with ngrok tunnel and webhook setup.
        
        Args:
            bot_name: Name of the Telegram bot
            
        Returns:
            Dict containing session start result
        """
        try:
            # Get bot configuration
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
            if not bot_doc.bot_token:
                return {
                    'success': False,
                    'error': 'missing_token',
                    'message': 'Bot token is required for testing'
                }
            
            # Check authentication
            auth_check = self._check_ngrok_auth()
            if not auth_check['success']:
                return auth_check
            
            # Stop any existing session for this bot
            self.stop_testing_session(bot_name)
            
            # Start ngrok tunnel (CLI approach - Python API doesn't support tunnel creation)
            port = bot_doc.ngrok_port or 8000
            
            # Install ngrok if needed
            install_result = self.install_ngrok_if_needed()
            if not install_result:
                return {
                    'success': False,
                    'error': 'ngrok_install_failed',
                    'message': 'Failed to install or setup ngrok'
                }
            
            tunnel_result = self._start_ngrok_tunnel(port)
            
            if not tunnel_result['success']:
                return tunnel_result
            
            tunnel_url = tunnel_result['tunnel_url']
            webhook_url = f"{tunnel_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
            
            # Automatically update Telegram webhook with tunnel URL using new method
            webhook_url = f"{tunnel_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
            webhook_result = bot_doc.update_webhook_secret(new_webhook_url=webhook_url, force_regenerate=True)
            if not webhook_result['success']:
                # Clean up tunnel if webhook update fails
                self._stop_ngrok_tunnel()
                return webhook_result
            
            # Update bot document with tunnel information
            bot_doc.db_set('test_mode_enabled', 1)
            bot_doc.db_set('ngrok_tunnel_url', tunnel_url)
            bot_doc.db_set('testing_status', 'Active - Testing Mode')
            
            # Store session info
            self.sessions[bot_name] = {
                'tunnel_url': tunnel_url,
                'port': port,
                'started_at': frappe.utils.now(),
                'webhook_url': webhook_url
            }
            
            frappe.log_error(
                message=f"Testing session started for bot {bot_name}: {tunnel_url}",
                title="Ngrok Testing Session Started"
            )
            
            return {
                'success': True,
                'message': 'Testing session started successfully',
                'tunnel_url': tunnel_url,
                'webhook_url': webhook_url,
                'port': port,
                'webhook_secret': webhook_result.get('webhook_secret', '')
            }
            
        except Exception as e:
            frappe.log_error(
                message=f"Failed to start testing session: {str(e)}",
                title="Ngrok Testing Session Error"
            )
            return {
                'success': False,
                'error': 'session_start_failed',
                'message': f"Failed to start testing session: {str(e)}"
            }
    
    def _check_ngrok_auth(self) -> Dict[str, Any]:
        """Check if ngrok authentication is properly configured."""
        authtoken = self._get_ngrok_authtoken()
        if not authtoken:
            return {
                'success': False,
                'error': 'missing_authtoken',
                'message': ('Ngrok authtoken is required. Please add "ngrok_authtoken" to your site_config.json '
                          'or set NGROK_AUTHTOKEN environment variable. '
                          'Get your authtoken from: https://dashboard.ngrok.com/get-started/your-authtoken')
            }
        
        return {'success': True}
    
    def _start_tunnel_python_api(self, port: int) -> Dict[str, Any]:
        """
        Note: The ngrok Python API doesn't support creating tunnels directly.
        This method is a placeholder - we'll use CLI approach instead.
        """
        return {
            'success': False,
            'error': 'python_api_not_supported',
            'message': 'The ngrok Python API does not support creating tunnels. Using CLI approach instead.'
        }
    
    def _configure_authtoken(self) -> bool:
        """Configure ngrok authtoken for CLI usage."""
        try:
            authtoken = self._get_ngrok_authtoken()
            if not authtoken:
                return False
            
            # Configure authtoken
            cmd = [self.ngrok_path, "config", "add-authtoken", authtoken]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                frappe.log_error("Ngrok authtoken configured successfully")
                return True
            else:
                frappe.log_error(f"Failed to configure authtoken: {result.stderr}")
                return False
                
        except Exception as e:
            frappe.log_error(f"Error configuring authtoken: {str(e)}")
            return False
    
    def stop_testing_session(self, bot_name: str) -> Dict[str, Any]:
        """
        Stop the testing session and clean up resources.
        
        Args:
            bot_name: Name of the Telegram bot
            
        Returns:
            Dict containing session stop result
        """
        try:
            # Get bot configuration
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
            
            # Stop ngrok tunnel
            self._stop_ngrok_tunnel()
            
            # Remove webhook from Telegram and restore original webhook URL
            if bot_doc.bot_token:
                self._restore_original_webhook(bot_doc)
            
            # Update bot document
            bot_doc.db_set('test_mode_enabled', 0)
            bot_doc.db_set('ngrok_tunnel_url', '')
            bot_doc.db_set('testing_status', 'Inactive')
            
            # Restore original webhook URL
            original_webhook_url = self._get_original_webhook_url(bot_doc)
            bot_doc.db_set('webhook_url', original_webhook_url)
            
            # Clean up session info
            if bot_name in self.sessions:
                del self.sessions[bot_name]
            
            frappe.log_error(
                message=f"Testing session stopped for bot {bot_name}",
                title="Ngrok Testing Session Stopped"
            )
            
            return {
                'success': True,
                'message': 'Testing session stopped successfully'
            }
            
        except Exception as e:
            frappe.log_error(
                message=f"Failed to stop testing session: {str(e)}",
                title="Ngrok Testing Session Error"
            )
            return {
                'success': False,
                'error': 'session_stop_failed',
                'message': f"Failed to stop testing session: {str(e)}"
            }
    
    def _restore_original_webhook(self, bot_doc):
        """Restore the original webhook URL or remove webhook entirely."""
        try:
            import requests
            
            # Get original webhook URL
            original_webhook_url = self._get_original_webhook_url(bot_doc)
            
            if original_webhook_url and not 'ngrok' in original_webhook_url:
                # Restore original webhook
                telegram_api_url = f"https://api.telegram.org/bot{bot_doc.bot_token}/setWebhook"
                payload = {
                    'url': original_webhook_url,
                    'drop_pending_updates': False  # Keep pending updates when restoring
                }
                
                response = requests.post(telegram_api_url, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        frappe.log_error(f"Restored original webhook: {original_webhook_url}", "Webhook Restoration")
                    else:
                        frappe.log_error(f"Failed to restore webhook: {result}", "Webhook Restoration Error")
                else:
                    frappe.log_error(f"HTTP error restoring webhook: {response.text}", "Webhook Restoration Error")
            else:
                # Remove webhook entirely
                telegram_api_url = f"https://api.telegram.org/bot{bot_doc.bot_token}/deleteWebhook"
                payload = {'drop_pending_updates': False}
                
                response = requests.post(telegram_api_url, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('ok'):
                        frappe.log_error("Webhook removed successfully", "Webhook Cleanup")
                    else:
                        frappe.log_error(f"Failed to remove webhook: {result}", "Webhook Cleanup Error")
                else:
                    frappe.log_error(f"HTTP error removing webhook: {response.text}", "Webhook Cleanup Error")
                    
        except Exception as e:
            frappe.log_error(f"Error restoring webhook: {str(e)}", "Webhook Restoration Error")
    
    def _get_original_webhook_url(self, bot_doc):
        """Get the original webhook URL for production use."""
        try:
            from frappe.utils import get_site_url
            site_url = get_site_url(frappe.local.site)
            return f"{site_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
        except Exception:
            return None
    
    def get_tunnel_status(self, bot_name: str) -> Dict[str, Any]:
        """
        Get the current status of the testing tunnel.
        
        Args:
            bot_name: Name of the Telegram bot
            
        Returns:
            Dict containing tunnel status information
        """
        try:
            if bot_name not in self.sessions:
                return {
                    'success': False,
                    'status': 'inactive',
                    'message': 'No active testing session'
                }
            
            # Check if ngrok is still running
            try:
                response = requests.get(f"{self.api_base}/tunnels", timeout=5)
                if response.status_code == 200:
                    tunnels = response.json().get('tunnels', [])
                    if tunnels:
                        session_info = self.sessions[bot_name]
                        return {
                            'success': True,
                            'status': 'active',
                            'tunnel_url': session_info['tunnel_url'],
                            'webhook_url': session_info['webhook_url'],
                            'port': session_info['port'],
                            'started_at': session_info['started_at']
                        }
            except requests.RequestException:
                pass
            
            # If we reach here, ngrok is not running
            self._cleanup_inactive_session(bot_name)
            return {
                'success': False,
                'status': 'inactive',
                'message': 'Ngrok tunnel is not active'
            }
            
        except Exception as e:
            return {
                'success': False,
                'status': 'error',
                'message': f"Error checking tunnel status: {str(e)}"
            }
    
    def install_ngrok_if_needed(self) -> bool:
        """
        Install ngrok CLI if it's not already installed.
        
        Returns:
            bool: True if ngrok is available, False otherwise
        """
        try:
            # Check if ngrok is already installed
            if os.path.exists(self.ngrok_path):
                # Test if it's working
                try:
                    subprocess.run([self.ngrok_path, "version"], 
                                 capture_output=True, timeout=10, check=True)
                    return True
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    # Existing installation is broken, remove it
                    os.remove(self.ngrok_path)
            
            # Download and install ngrok CLI
            return self._download_and_install_ngrok()
            
        except Exception as e:
            frappe.log_error(f"Error installing ngrok: {str(e)}")
            return False
    

    
    def update_telegram_webhook(self, bot_token: str, tunnel_url: str, bot_name: str) -> Dict[str, Any]:
        """
        Update the Telegram webhook URL with the ngrok tunnel.
        
        Args:
            bot_token: Telegram bot token
            tunnel_url: Ngrok tunnel URL
            bot_name: Name of the bot for webhook endpoint
            
        Returns:
            Dict containing webhook update result
        """
        try:
            webhook_url = f"{tunnel_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
            
            # Update webhook via Telegram API
            telegram_api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
            payload = {
                'url': webhook_url,
                'drop_pending_updates': True  # Clear any pending updates
            }
            
            response = requests.post(telegram_api_url, data=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return {
                        'success': True,
                        'message': 'Webhook updated successfully',
                        'webhook_url': webhook_url
                    }
                else:
                    return {
                        'success': False,
                        'error': 'telegram_api_error',
                        'message': f"Telegram API error: {result.get('description', 'Unknown error')}"
                    }
            else:
                return {
                    'success': False,
                    'error': 'http_error',
                    'message': f"HTTP error {response.status_code}: {response.text}"
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'error': 'network_error',
                'message': f"Network error updating webhook: {str(e)}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': 'webhook_update_failed',
                'message': f"Failed to update webhook: {str(e)}"
            }
    
    def _start_ngrok_tunnel(self, port: int) -> Dict[str, Any]:
        """Start ngrok tunnel on specified port using CLI."""
        try:
            # Configure authtoken before starting tunnel
            if not self._configure_authtoken():
                return {
                    'success': False,
                    'error': 'authtoken_config_failed',
                    'message': ('Failed to configure ngrok authtoken. Please ensure your authtoken is valid. '
                              'Get your authtoken from: https://dashboard.ngrok.com/get-started/your-authtoken')
                }
            
            # Kill any existing ngrok processes
            self._stop_ngrok_tunnel()
            
            # Start ngrok in background
            cmd = [self.ngrok_path, "http", str(port), "--log", "stdout"]
            
            # Start process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait a moment for ngrok to start
            time.sleep(3)
            
            # Check if process is still running
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                return {
                    'success': False,
                    'error': 'ngrok_failed_to_start',
                    'message': f"Ngrok failed to start: {stderr}"
                }
            
            # Get tunnel URL from ngrok API
            tunnel_url = self._get_tunnel_url()
            if not tunnel_url:
                self._stop_ngrok_tunnel()
                return {
                    'success': False,
                    'error': 'tunnel_url_not_found',
                    'message': 'Could not retrieve tunnel URL from ngrok'
                }
            
            return {
                'success': True,
                'tunnel_url': tunnel_url,
                'process': process
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': 'tunnel_start_failed',
                'message': f"Failed to start tunnel: {str(e)}"
            }
    
    def _stop_ngrok_tunnel(self):
        """Stop any running ngrok tunnels."""
        try:
            # Kill CLI processes
            system = platform.system().lower()
            if system == "windows":
                subprocess.run(["taskkill", "/f", "/im", "ngrok.exe"], 
                             capture_output=True)
            else:
                subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)
            
            # Wait a moment for cleanup
            time.sleep(1)
            
        except Exception as e:
            frappe.log_error(f"Error stopping ngrok: {str(e)}")
    
    def _get_tunnel_url(self) -> Optional[str]:
        """Get the tunnel URL from ngrok API."""
        try:
            for _ in range(10):  # Try for up to 10 seconds
                try:
                    response = requests.get(f"{self.api_base}/tunnels", timeout=2)
                    if response.status_code == 200:
                        data = response.json()
                        tunnels = data.get('tunnels', [])
                        for tunnel in tunnels:
                            if tunnel.get('proto') == 'https':
                                return tunnel.get('public_url')
                except requests.RequestException:
                    pass
                time.sleep(1)
            return None
        except Exception:
            return None
    
    def _download_and_install_ngrok(self) -> bool:
        """Download and install ngrok binary."""
        try:
            # Create ngrok directory
            ngrok_dir = os.path.dirname(self.ngrok_path)
            os.makedirs(ngrok_dir, exist_ok=True)
            
            # Determine download URL based on platform
            system = platform.system().lower()
            machine = platform.machine().lower()
            
            if system == "windows":
                if "64" in machine or "x86_64" in machine or "amd64" in machine:
                    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
                else:
                    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-386.zip"
                is_zip = True
            elif system == "darwin":  # macOS
                if "arm" in machine or "aarch64" in machine:
                    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.tgz"
                else:
                    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.tgz"
                is_zip = False
            else:  # Linux
                if "arm" in machine or "aarch64" in machine:
                    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz"
                elif "386" in machine or "i686" in machine:
                    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-386.tgz"
                else:
                    download_url = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz"
                is_zip = False
            
            # Download ngrok
            frappe.log_error(f"Downloading ngrok from: {download_url}")
            response = requests.get(download_url, timeout=300)  # 5 minutes timeout
            response.raise_for_status()
            
            # Save to temp file
            temp_file = os.path.join(ngrok_dir, "ngrok_temp")
            with open(temp_file, 'wb') as f:
                f.write(response.content)
            
            # Extract archive
            if is_zip:
                with zipfile.ZipFile(temp_file, 'r') as zip_ref:
                    zip_ref.extractall(ngrok_dir)
            else:
                with tarfile.open(temp_file, 'r:gz') as tar_ref:
                    tar_ref.extractall(ngrok_dir)
            
            # Remove temp file
            os.remove(temp_file)
            
            # Make executable on Unix systems
            if system != "windows":
                os.chmod(self.ngrok_path, 0o755)
            
            # Test installation
            try:
                subprocess.run([self.ngrok_path, "version"], 
                             capture_output=True, timeout=10, check=True)
                frappe.log_error("Ngrok installed successfully")
                return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                frappe.log_error("Ngrok installation test failed")
                return False
                
        except Exception as e:
            frappe.log_error(f"Error downloading/installing ngrok: {str(e)}")
            return False
    
    def _remove_telegram_webhook(self, bot_token: str):
        """Remove webhook from Telegram (sets webhook to empty)."""
        try:
            telegram_api_url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
            payload = {'drop_pending_updates': True}
            requests.post(telegram_api_url, data=payload, timeout=30)
        except Exception as e:
            frappe.log_error(f"Error removing webhook: {str(e)}")
    
    def _cleanup_inactive_session(self, bot_name: str):
        """Clean up session data for inactive tunnel."""
        try:
            if bot_name in self.sessions:
                del self.sessions[bot_name]
            
            # Update bot document
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
            bot_doc.db_set('test_mode_enabled', 0)
            bot_doc.db_set('ngrok_tunnel_url', '')
            bot_doc.db_set('testing_status', 'Inactive - Tunnel Disconnected')
            
        except Exception as e:
            frappe.log_error(f"Error cleaning up session: {str(e)}")

    @frappe.whitelist()
    def get_configuration_guide(self) -> Dict[str, Any]:
        """
        Get configuration guide for setting up ngrok authentication.
        
        Returns:
            Dict containing setup instructions
        """
        return {
            'success': True,
            'message': 'Ngrok Configuration Guide',
            'instructions': {
                'step_1': {
                    'title': '1. Create Ngrok Account',
                    'description': 'Sign up for a free ngrok account',
                    'url': 'https://dashboard.ngrok.com/signup'
                },
                'step_2': {
                    'title': '2. Get Your Authtoken/API Key',
                    'description': 'Get your authtoken or API key from the dashboard',
                    'url': 'https://dashboard.ngrok.com/get-started/your-authtoken'
                },
                'step_3': {
                    'title': '3. Configure Authentication',
                    'description': 'Add your authtoken to Frappe configuration',
                    'options': [
                        {
                            'method': 'Site Config (Recommended)',
                            'config': {
                                'site_config.json': '"ngrok_authtoken": "your_authtoken_here"'
                            }
                        },
                        {
                            'method': 'Environment Variable',
                            'config': {
                                'environment': 'export NGROK_AUTHTOKEN=your_authtoken_here'
                            }
                        }
                    ]
                },
                'step_4': {
                    'title': '4. Test Configuration',
                    'description': 'Click "Start Testing Session" to test your setup'
                }
            },
            'current_status': {
                'authtoken_configured': bool(self._get_ngrok_authtoken()),
                'cli_installed': os.path.exists(self.ngrok_path)
            }
        }
    
    def _setup_telegram_webhook_with_tunnel(self, bot_doc, tunnel_url: str) -> Dict[str, Any]:
        """
        Configure Telegram webhook with the ngrok tunnel URL.
        
        Args:
            bot_doc: HD Telegram Bot document
            tunnel_url: Ngrok tunnel URL
            
        Returns:
            Dict containing webhook setup result
        """
        try:
            import secrets
            import requests
            
            webhook_secret = secrets.token_urlsafe(32)
            webhook_url = f"{tunnel_url}/api/method/helpdesk.www.telegram.webhook.handle_webhook"
            
            # Call Telegram setWebhook API
            telegram_api_url = f"https://api.telegram.org/bot{bot_doc.bot_token}/setWebhook"
            payload = {
                'url': webhook_url,
                'secret_token': webhook_secret,
                'allowed_updates': ['message', 'callback_query'],
                'drop_pending_updates': True
            }
            
            frappe.log_error(f"Setting Telegram webhook - URL: {telegram_api_url}, Payload: {payload}", "Ngrok Webhook Setup")
            
            response = requests.post(telegram_api_url, json=payload, timeout=30)
            
            frappe.log_error(f"Telegram webhook response - Status: {response.status_code}, Content: {response.text}", "Ngrok Webhook Response")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    return {
                        'success': True,
                        'message': 'Webhook configured successfully with Telegram',
                        'webhook_url': webhook_url,
                        'webhook_secret': webhook_secret,
                        'telegram_response': result
                    }
                else:
                    error_msg = result.get('description', 'Unknown error from Telegram API')
                    return {
                        'success': False,
                        'error': 'telegram_api_error',
                        'message': f"Telegram API error: {error_msg}",
                        'telegram_response': result
                    }
            else:
                return {
                    'success': False,
                    'error': 'http_error',
                    'message': f"HTTP error {response.status_code}: {response.text}",
                    'response_text': response.text
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'error': 'network_error',
                'message': f"Network error configuring webhook: {str(e)}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': 'webhook_setup_failed',
                'message': f"Failed to configure webhook: {str(e)}"
            }




# Frappe API endpoints for frontend integration

@frappe.whitelist()
def start_testing_session(bot_name: str):
    """API endpoint to start testing session."""
    try:
        manager = NgrokTestingManager()
        result = manager.start_testing_session(bot_name)
        return result
    except Exception as e:
        frappe.log_error(f"API error starting testing session: {str(e)}")
        return {
            'success': False,
            'error': 'api_error',
            'message': f"API error: {str(e)}"
        }

@frappe.whitelist()
def stop_testing_session(bot_name: str):
    """API endpoint to stop testing session."""
    try:
        manager = NgrokTestingManager()
        result = manager.stop_testing_session(bot_name)
        return result
    except Exception as e:
        frappe.log_error(f"API error stopping testing session: {str(e)}")
        return {
            'success': False,
            'error': 'api_error',
            'message': f"API error: {str(e)}"
        }

@frappe.whitelist()
def get_tunnel_status(bot_name: str):
    """API endpoint to get tunnel status."""
    try:
        manager = NgrokTestingManager()
        result = manager.get_tunnel_status(bot_name)
        return result
    except Exception as e:
        frappe.log_error(f"API error getting tunnel status: {str(e)}")
        return {
            'success': False,
            'error': 'api_error',
            'message': f"API error: {str(e)}"
        }

@frappe.whitelist()
def get_configuration_guide():
    """API endpoint to get ngrok configuration guide."""
    try:
        manager = NgrokTestingManager()
        result = manager.get_configuration_guide()
        return result
    except Exception as e:
        frappe.log_error(f"Error getting configuration guide: {str(e)}")
        return {
            'success': False,
            'error': 'guide_error',
            'message': f"Error getting configuration guide: {str(e)}"
        }

@frappe.whitelist()
def check_ngrok_status():
    """API endpoint to check ngrok configuration status."""
    try:
        manager = NgrokTestingManager()
        return {
            'success': True,
            'status': {
                'authtoken_configured': bool(manager._get_ngrok_authtoken()),
                'cli_installed': os.path.exists(manager.ngrok_path),
                'authentication_configured': manager._check_ngrok_auth()['success']
            }
        }
    except Exception as e:
        frappe.log_error(f"Error checking ngrok status: {str(e)}")
        return {
            'success': False,
            'error': 'status_check_error',
            'message': f"Error checking ngrok status: {str(e)}"
        } 