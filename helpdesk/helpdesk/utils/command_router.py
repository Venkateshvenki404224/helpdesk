# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import json
import re
from frappe import _
from frappe.utils import now_datetime, cstr
from typing import Dict, Any, List, Optional, Union, Callable
import importlib


class CommandRouter:
    """
    Advanced command router for Telegram bot interactions.
    Provides modular routing capabilities with middleware support and flexible command mapping.
    """
    
    def __init__(self, bot_doc=None):
        """
        Initialize the command router
        
        Args:
            bot_doc: HD Telegram Bot document instance
        """
        self.bot_doc = bot_doc
        self.routes = {}
        self.middleware_stack = []
        self.fallback_handlers = []
        self.route_cache = {}
        self.command_processor = None
        
        # Initialize command processor
        self._initialize_command_processor()
        
        # Load default routes
        self._load_default_routes()
    
    def _initialize_command_processor(self):
        """Initialize the underlying command processor"""
        try:
            from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor
            self.command_processor = TelegramCommandProcessor(self.bot_doc)
        except Exception as e:
            frappe.log_error(f"Failed to initialize command processor: {str(e)}")
    
    def _load_default_routes(self):
        """Load default command routes from configuration"""
        try:
            # Load bot-specific routes
            if self.bot_doc and self.bot_doc.command_mappings:
                for mapping in self.bot_doc.command_mappings:
                    if mapping.is_active:
                        self._register_bot_command_route(mapping)
            
            # Load global routes if enabled
            if not self.bot_doc or self.bot_doc.enable_global_commands:
                self._load_global_routes()
                
        except Exception as e:
            frappe.log_error(f"Failed to load default routes: {str(e)}")
    
    def _register_bot_command_route(self, mapping):
        """Register a bot-specific command route"""
        try:
            command_doc = frappe.get_doc("HD Telegram Command", mapping.command)
            
            route_config = {
                "handler": command_doc.function_path,
                "command_doc": command_doc,
                "mapping": mapping,
                "access_level": mapping.access_level or command_doc.access_level,
                "is_global": False,
                "middleware": self._get_command_middleware(command_doc),
                "rate_limit": command_doc.rate_limit_per_user,
                "timeout": command_doc.timeout_seconds
            }
            
            self.routes[mapping.command] = route_config
            
        except Exception as e:
            frappe.log_error(f"Failed to register bot command route {mapping.command}: {str(e)}")
    
    def _load_global_routes(self):
        """Load global command routes"""
        try:
            global_commands = frappe.get_all(
                "HD Telegram Command",
                filters={"is_active": 1, "is_global": 1},
                fields=["name", "command_name", "function_path", "access_level", "rate_limit_per_user", "timeout_seconds"]
            )
            
            for cmd in global_commands:
                if cmd.command_name not in self.routes:  # Don't override bot-specific routes
                    command_doc = frappe.get_doc("HD Telegram Command", cmd.name)
                    
                    route_config = {
                        "handler": cmd.function_path,
                        "command_doc": command_doc,
                        "mapping": None,
                        "access_level": cmd.access_level,
                        "is_global": True,
                        "middleware": self._get_command_middleware(command_doc),
                        "rate_limit": cmd.rate_limit_per_user,
                        "timeout": cmd.timeout_seconds
                    }
                    
                    self.routes[cmd.command_name] = route_config
                    
        except Exception as e:
            frappe.log_error(f"Failed to load global routes: {str(e)}")
    
    def _get_command_middleware(self, command_doc):
        """Get middleware for a command"""
        middleware = []
        
        # Add rate limiting middleware if configured
        if command_doc.rate_limit_per_user:
            middleware.append("rate_limit")
        
        # Add permission checking middleware
        middleware.append("permission_check")
        
        # Add logging middleware
        middleware.append("logging")
        
        # Add custom middleware from command configuration
        if hasattr(command_doc, 'middleware_list') and command_doc.middleware_list:
            middleware.extend(command_doc.middleware_list.split(','))
        
        return middleware
    
    def route_message(self, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route incoming message to appropriate handler
        
        Args:
            message_data: Telegram message data
            user_data: User information
            
        Returns:
            Dict containing routing and execution results
        """
        try:
            # Extract message details
            message_text = message_data.get("text", "").strip()
            
            # Check if message is a command
            if self.is_command(message_text):
                return self.route_command(message_data, user_data)
            else:
                return self.route_non_command(message_data, user_data)
                
        except Exception as e:
            frappe.log_error(f"Message routing failed: {str(e)}")
            return self._create_error_response(str(e))
    
    def is_command(self, message_text: str) -> bool:
        """Check if message text is a command"""
        return message_text.startswith("/") and len(message_text) > 1
    
    def route_command(self, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route command message to appropriate handler
        
        Args:
            message_data: Telegram message data
            user_data: User information
            
        Returns:
            Dict containing command execution results
        """
        try:
            command_text = message_data.get("text", "").strip()
            command_name = self._extract_command_name(command_text)
            command_args = self._extract_command_args(command_text)
            
            # Get route configuration
            route_config = self.get_route_config(command_name)
            
            if not route_config:
                return self._handle_unknown_command(command_name, user_data)
            
            # Execute middleware stack
            middleware_result = self._execute_middleware(route_config, message_data, user_data, command_args)
            if not middleware_result.get("success"):
                return middleware_result
            
            # Execute command handler
            return self._execute_command_handler(route_config, message_data, user_data, command_args)
            
        except Exception as e:
            frappe.log_error(f"Command routing failed: {str(e)}")
            return self._create_error_response(str(e))
    
    def route_non_command(self, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route non-command message to appropriate handler
        
        Args:
            message_data: Telegram message data
            user_data: User information
            
        Returns:
            Dict containing processing results
        """
        try:
            # Check for custom non-command handlers
            for handler in self.fallback_handlers:
                try:
                    result = handler(message_data, user_data, self.bot_doc)
                    if result and result.get("handled"):
                        return result
                except Exception as e:
                    frappe.log_error(f"Fallback handler error: {str(e)}")
                    continue
            
            # Use command processor for default non-command handling
            if self.command_processor:
                return self.command_processor.process_non_command_message(message_data, user_data)
            
            # Final fallback
            return self._create_default_response(user_data)
            
        except Exception as e:
            frappe.log_error(f"Non-command routing failed: {str(e)}")
            return self._create_error_response(str(e))
    
    def get_route_config(self, command_name: str) -> Optional[Dict[str, Any]]:
        """
        Get route configuration for a command
        
        Args:
            command_name: Command name (e.g., "/start")
            
        Returns:
            Route configuration dict or None
        """
        # Check cache first
        if command_name in self.route_cache:
            return self.route_cache[command_name]
        
        # Get from routes
        route_config = self.routes.get(command_name)
        
        # Cache the result
        if route_config:
            self.route_cache[command_name] = route_config
        
        return route_config
    
    def _execute_middleware(self, route_config: Dict[str, Any], message_data: Dict[str, Any], 
                           user_data: Dict[str, Any], command_args: List[str]) -> Dict[str, Any]:
        """
        Execute middleware stack for a route
        
        Args:
            route_config: Route configuration
            message_data: Telegram message data
            user_data: User information
            command_args: Command arguments
            
        Returns:
            Dict containing middleware execution results
        """
        try:
            middleware_list = route_config.get("middleware", [])
            
            for middleware_name in middleware_list:
                middleware_result = self._execute_single_middleware(
                    middleware_name, route_config, message_data, user_data, command_args
                )
                
                if not middleware_result.get("success"):
                    return middleware_result
            
            return {"success": True, "message": "Middleware executed successfully"}
            
        except Exception as e:
            frappe.log_error(f"Middleware execution failed: {str(e)}")
            return {"success": False, "message": f"Middleware error: {str(e)}"}
    
    def _execute_single_middleware(self, middleware_name: str, route_config: Dict[str, Any], 
                                  message_data: Dict[str, Any], user_data: Dict[str, Any], 
                                  command_args: List[str]) -> Dict[str, Any]:
        """Execute a single middleware"""
        try:
            if middleware_name == "rate_limit":
                return self._rate_limit_middleware(route_config, user_data)
            elif middleware_name == "permission_check":
                return self._permission_check_middleware(route_config, user_data)
            elif middleware_name == "logging":
                return self._logging_middleware(route_config, message_data, user_data)
            else:
                # Try to load custom middleware
                return self._load_custom_middleware(middleware_name, route_config, message_data, user_data, command_args)
                
        except Exception as e:
            frappe.log_error(f"Single middleware execution failed for {middleware_name}: {str(e)}")
            return {"success": False, "message": f"Middleware {middleware_name} failed"}
    
    def _rate_limit_middleware(self, route_config: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Rate limiting middleware"""
        try:
            rate_limit = route_config.get("rate_limit")
            if not rate_limit:
                return {"success": True}
            
            user_id = user_data.get("id")
            if not user_id:
                return {"success": True}
            
            # Check rate limit using bot's rate limiting system
            if self.bot_doc and hasattr(self.bot_doc, 'is_rate_limited'):
                if self.bot_doc.is_rate_limited(user_id):
                    return {
                        "success": False,
                        "message": "Rate limit exceeded. Please try again later.",
                        "error_type": "rate_limit"
                    }
            
            return {"success": True}
            
        except Exception as e:
            frappe.log_error(f"Rate limit middleware error: {str(e)}")
            return {"success": True}  # Don't block on middleware errors
    
    def _permission_check_middleware(self, route_config: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Permission checking middleware"""
        try:
            # Use command processor's permission checking
            if self.command_processor:
                command_config = {
                    "command_doc": route_config.get("command_doc"),
                    "mapping": route_config.get("mapping")
                }
                
                if not self.command_processor.check_command_permissions(command_config, user_data):
                    return {
                        "success": False,
                        "message": "You don't have permission to use this command.",
                        "error_type": "permission_denied"
                    }
            
            return {"success": True}
            
        except Exception as e:
            frappe.log_error(f"Permission check middleware error: {str(e)}")
            return {"success": True}  # Don't block on middleware errors
    
    def _logging_middleware(self, route_config: Dict[str, Any], message_data: Dict[str, Any], 
                           user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Logging middleware"""
        try:
            command_name = route_config.get("command_doc", {}).get("command_name", "unknown")
            user_id = user_data.get("id", "unknown")
            
            frappe.logger().info(f"Command execution: {command_name} by user {user_id}")
            
            return {"success": True}
            
        except Exception as e:
            frappe.log_error(f"Logging middleware error: {str(e)}")
            return {"success": True}  # Don't block on middleware errors
    
    def _load_custom_middleware(self, middleware_name: str, route_config: Dict[str, Any], 
                               message_data: Dict[str, Any], user_data: Dict[str, Any], 
                               command_args: List[str]) -> Dict[str, Any]:
        """Load and execute custom middleware"""
        try:
            # Try to load custom middleware from configured paths
            middleware_paths = [
                f"helpdesk.middleware.{middleware_name}",
                f"helpdesk.helpdesk.middleware.{middleware_name}"
            ]
            
            for path in middleware_paths:
                try:
                    module = importlib.import_module(path)
                    middleware_func = getattr(module, 'execute_middleware')
                    
                    return middleware_func(route_config, message_data, user_data, command_args)
                    
                except (ImportError, AttributeError):
                    continue
            
            # If no custom middleware found, just continue
            return {"success": True}
            
        except Exception as e:
            frappe.log_error(f"Custom middleware loading failed for {middleware_name}: {str(e)}")
            return {"success": True}  # Don't block on middleware errors
    
    def _execute_command_handler(self, route_config: Dict[str, Any], message_data: Dict[str, Any], 
                                user_data: Dict[str, Any], command_args: List[str]) -> Dict[str, Any]:
        """
        Execute the command handler function
        
        Args:
            route_config: Route configuration
            message_data: Telegram message data
            user_data: User information
            command_args: Command arguments
            
        Returns:
            Dict containing command execution results
        """
        try:
            # Use command processor's execution if available
            if self.command_processor:
                command_config = {
                    "command_doc": route_config.get("command_doc"),
                    "mapping": route_config.get("mapping")
                }
                
                return self.command_processor.execute_command(
                    command_config, message_data, user_data, command_args
                )
            
            # Fallback to direct execution
            return self._direct_command_execution(route_config, message_data, user_data, command_args)
            
        except Exception as e:
            frappe.log_error(f"Command handler execution failed: {str(e)}")
            return self._create_error_response(str(e))
    
    def _direct_command_execution(self, route_config: Dict[str, Any], message_data: Dict[str, Any], 
                                 user_data: Dict[str, Any], command_args: List[str]) -> Dict[str, Any]:
        """Direct command execution without command processor"""
        try:
            handler_path = route_config.get("handler")
            command_doc = route_config.get("command_doc")
            mapping = route_config.get("mapping")
            
            # Load function
            module_path, function_name = handler_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            function = getattr(module, function_name)
            
            # Prepare parameters
            params = {
                "user_data": user_data,
                "message_data": message_data,
                "bot_doc": self.bot_doc,
                "command_doc": command_doc,
                "command_args": command_args,
                "mapping": mapping
            }
            
            # Execute function
            return function(params)
            
        except Exception as e:
            frappe.log_error(f"Direct command execution failed: {str(e)}")
            return self._create_error_response(str(e))
    
    def _extract_command_name(self, command_text: str) -> str:
        """Extract command name from message text"""
        command_part = command_text.split()[0] if command_text else ""
        command_name = command_part.split("@")[0] if "@" in command_part else command_part
        return command_name.lower()
    
    def _extract_command_args(self, command_text: str) -> List[str]:
        """Extract command arguments from message text"""
        parts = command_text.split()
        return parts[1:] if len(parts) > 1 else []
    
    def _handle_unknown_command(self, command_name: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle unknown or unavailable commands"""
        try:
            # Use command processor if available
            if self.command_processor:
                return self.command_processor.handle_unknown_command(command_name, user_data)
            
            # Fallback response
            available_commands = self.get_available_commands(user_data)
            commands_list = self._format_commands_list(available_commands)
            
            return {
                "success": False,
                "message": f"Unknown command: {command_name}\n\nAvailable commands:\n{commands_list}",
                "error_type": "unknown_command"
            }
            
        except Exception as e:
            frappe.log_error(f"Unknown command handling failed: {str(e)}")
            return self._create_error_response("Command not found")
    
    def get_available_commands(self, user_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get list of available commands for user"""
        try:
            # Use command processor if available
            if self.command_processor:
                return self.command_processor.get_available_commands(user_data)
            
            # Fallback: return configured routes
            available_commands = []
            for command_name, route_config in self.routes.items():
                try:
                    # Simple permission check
                    command_doc = route_config.get("command_doc")
                    if command_doc:
                        available_commands.append({
                            "command": command_name,
                            "description": command_doc.description,
                            "icon": command_doc.icon or "",
                            "sort_order": command_doc.sort_order or 10
                        })
                except Exception:
                    continue
            
            # Sort by sort_order
            available_commands.sort(key=lambda x: x.get("sort_order", 10))
            
            return available_commands
            
        except Exception as e:
            frappe.log_error(f"Get available commands failed: {str(e)}")
            return []
    
    def _format_commands_list(self, commands: List[Dict[str, Any]]) -> str:
        """Format commands list for display"""
        if not commands:
            return "No commands available"
        
        formatted = []
        for cmd in commands:
            icon = cmd.get("icon", "")
            command = cmd.get("command", "")
            description = cmd.get("description", "")
            formatted.append(f"{icon} {command} - {description}")
        
        return "\n".join(formatted)
    
    def add_middleware(self, middleware_name: str, middleware_func: Callable) -> None:
        """
        Add custom middleware to the router
        
        Args:
            middleware_name: Name of the middleware
            middleware_func: Middleware function
        """
        self.middleware_stack.append({
            "name": middleware_name,
            "function": middleware_func
        })
    
    def add_fallback_handler(self, handler_func: Callable) -> None:
        """
        Add fallback handler for non-command messages
        
        Args:
            handler_func: Handler function
        """
        self.fallback_handlers.append(handler_func)
    
    def register_route(self, command_name: str, handler_path: str, **options) -> None:
        """
        Register a custom route
        
        Args:
            command_name: Command name
            handler_path: Handler function path
            **options: Additional route options
        """
        route_config = {
            "handler": handler_path,
            "middleware": options.get("middleware", []),
            "access_level": options.get("access_level", "Public"),
            "rate_limit": options.get("rate_limit"),
            "timeout": options.get("timeout"),
            "is_custom": True
        }
        
        self.routes[command_name] = route_config
        
        # Clear cache
        if command_name in self.route_cache:
            del self.route_cache[command_name]
    
    def unregister_route(self, command_name: str) -> None:
        """
        Unregister a route
        
        Args:
            command_name: Command name to unregister
        """
        if command_name in self.routes:
            del self.routes[command_name]
        
        if command_name in self.route_cache:
            del self.route_cache[command_name]
    
    def reload_routes(self) -> None:
        """Reload all routes from configuration"""
        self.routes.clear()
        self.route_cache.clear()
        self._load_default_routes()
    
    def get_route_stats(self) -> Dict[str, Any]:
        """Get routing statistics"""
        return {
            "total_routes": len(self.routes),
            "middleware_count": len(self.middleware_stack),
            "fallback_handlers": len(self.fallback_handlers),
            "cached_routes": len(self.route_cache),
            "routes": list(self.routes.keys())
        }
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            "success": False,
            "message": error_message,
            "error_type": "routing_error"
        }
    
    def _create_default_response(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create default response for non-command messages"""
        user_name = user_data.get("first_name", "there")
        
        return {
            "success": True,
            "message": f"Hello {user_name}! I received your message. Use /help to see available commands or /ticket to create a support request.",
            "response_type": "default"
        }


# Factory function for creating router instances
def create_command_router(bot_name: str = None) -> CommandRouter:
    """
    Create a command router instance
    
    Args:
        bot_name: Name of the bot to create router for
        
    Returns:
        CommandRouter instance
    """
    bot_doc = None
    if bot_name:
        try:
            bot_doc = frappe.get_doc("HD Telegram Bot", bot_name)
        except frappe.DoesNotExistError:
            frappe.throw(_("Bot '{0}' not found").format(bot_name))
    
    return CommandRouter(bot_doc)


# API endpoints
@frappe.whitelist()
def route_telegram_message(bot_name: str, message_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route a Telegram message using the command router
    
    Args:
        bot_name: Name of the bot
        message_data: Telegram message data
        user_data: User information
        
    Returns:
        Routing and execution results
    """
    try:
        router = create_command_router(bot_name)
        return router.route_message(message_data, user_data)
    except Exception as e:
        frappe.log_error(f"Message routing API error: {str(e)}")
        return {
            "success": False,
            "message": f"Routing failed: {str(e)}"
        }


@frappe.whitelist()
def get_router_stats(bot_name: str = None) -> Dict[str, Any]:
    """
    Get routing statistics for a bot
    
    Args:
        bot_name: Name of the bot
        
    Returns:
        Router statistics
    """
    try:
        router = create_command_router(bot_name)
        return router.get_route_stats()
    except Exception as e:
        frappe.log_error(f"Router stats API error: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to get stats: {str(e)}"
        }


@frappe.whitelist()
def reload_bot_routes(bot_name: str) -> Dict[str, Any]:
    """
    Reload routes for a bot
    
    Args:
        bot_name: Name of the bot
        
    Returns:
        Reload results
    """
    try:
        router = create_command_router(bot_name)
        router.reload_routes()
        
        return {
            "success": True,
            "message": "Routes reloaded successfully",
            "stats": router.get_route_stats()
        }
    except Exception as e:
        frappe.log_error(f"Route reload API error: {str(e)}")
        return {
            "success": False,
            "message": f"Reload failed: {str(e)}"
        } 