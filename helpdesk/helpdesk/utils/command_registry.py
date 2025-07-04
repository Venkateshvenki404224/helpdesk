# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
import importlib
import inspect
from frappe import _
from frappe.utils import now_datetime
from typing import Dict, Any, List, Optional, Callable
import os
import pkgutil


class CommandRegistry:
    """
    Registry system for managing Telegram bot commands.
    Handles dynamic loading, registration, and execution of command functions.
    """
    
    def __init__(self):
        """Initialize the command registry"""
        self.registered_commands = {}
        self.function_cache = {}
        self.module_cache = {}
        self.auto_discovery_paths = [
            "helpdesk.api.telegram.commands",
            "helpdesk.helpdesk.commands"
        ]
    
    def register_command(self, command_name: str, function_path: str, 
                        metadata: Dict[str, Any] = None) -> bool:
        """
        Register a command with its function path
        
        Args:
            command_name: Command name (e.g., "/start")
            function_path: Python function path
            metadata: Additional command metadata
            
        Returns:
            True if registration successful, False otherwise
        """
        try:
            # Validate function path
            if not self.validate_function_path(function_path):
                frappe.log_error(f"Invalid function path for command {command_name}: {function_path}")
                return False
            
            # Store command registration
            self.registered_commands[command_name] = {
                "function_path": function_path,
                "metadata": metadata or {},
                "registered_at": now_datetime(),
                "last_used": None,
                "usage_count": 0
            }
            
            # Clear cache for this command if it exists
            if command_name in self.function_cache:
                del self.function_cache[command_name]
            
            frappe.logger().info(f"Registered command: {command_name} -> {function_path}")
            return True
        
        except Exception as e:
            frappe.log_error(f"Command registration failed for {command_name}: {str(e)}")
            return False
    
    def unregister_command(self, command_name: str) -> bool:
        """
        Unregister a command
        
        Args:
            command_name: Command name to unregister
            
        Returns:
            True if unregistration successful, False otherwise
        """
        try:
            if command_name in self.registered_commands:
                del self.registered_commands[command_name]
            
            if command_name in self.function_cache:
                del self.function_cache[command_name]
            
            frappe.logger().info(f"Unregistered command: {command_name}")
            return True
        
        except Exception as e:
            frappe.log_error(f"Command unregistration failed for {command_name}: {str(e)}")
            return False
    
    def get_command_function(self, command_name: str) -> Optional[Callable]:
        """
        Get command function by name
        
        Args:
            command_name: Command name
            
        Returns:
            Command function or None
        """
        try:
            # Check cache first
            if command_name in self.function_cache:
                return self.function_cache[command_name]
            
            # Get command registration
            if command_name not in self.registered_commands:
                # Try to auto-discover from database
                self.sync_from_database()
                
                if command_name not in self.registered_commands:
                    return None
            
            registration = self.registered_commands[command_name]
            function_path = registration["function_path"]
            
            # Load function
            function = self.load_function(function_path)
            
            if function:
                # Cache the function
                self.function_cache[command_name] = function
                
                # Update usage statistics
                registration["last_used"] = now_datetime()
                registration["usage_count"] += 1
            
            return function
        
        except Exception as e:
            frappe.log_error(f"Failed to get command function for {command_name}: {str(e)}")
            return None
    
    def load_function(self, function_path: str) -> Optional[Callable]:
        """
        Load function from path
        
        Args:
            function_path: Python function path (module.function)
            
        Returns:
            Function object or None
        """
        try:
            # Split path into module and function
            if '.' not in function_path:
                raise ValueError("Invalid function path format")
            
            module_path, function_name = function_path.rsplit('.', 1)
            
            # Load module
            module = self.get_module(module_path)
            
            if not module:
                return None
            
            # Get function from module
            if not hasattr(module, function_name):
                frappe.log_error(f"Function '{function_name}' not found in module '{module_path}'")
                return None
            
            function = getattr(module, function_name)
            
            # Validate function
            if not self.validate_function(function):
                frappe.log_error(f"Invalid function signature: {function_path}")
                return None
            
            return function
        
        except Exception as e:
            frappe.log_error(f"Function loading failed for {function_path}: {str(e)}")
            return None
    
    def get_module(self, module_path: str):
        """
        Get module with caching
        
        Args:
            module_path: Python module path
            
        Returns:
            Module object or None
        """
        try:
            # Check cache first
            if module_path in self.module_cache:
                return self.module_cache[module_path]
            
            # Import module
            module = importlib.import_module(module_path)
            
            # Cache module
            self.module_cache[module_path] = module
            
            return module
        
        except ImportError as e:
            frappe.log_error(f"Module import failed for {module_path}: {str(e)}")
            return None
    
    def validate_function_path(self, function_path: str) -> bool:
        """
        Validate function path format
        
        Args:
            function_path: Function path to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if not function_path or '.' not in function_path:
                return False
            
            parts = function_path.split('.')
            
            # Must have at least module.function
            if len(parts) < 2:
                return False
            
            # Check for valid Python identifiers
            for part in parts:
                if not part.isidentifier():
                    return False
            
            return True
        
        except Exception:
            return False
    
    def validate_function(self, function: Callable) -> bool:
        """
        Validate function signature for command handlers
        
        Args:
            function: Function to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Check if function is callable
            if not callable(function):
                return False
            
            # Get function signature
            sig = inspect.signature(function)
            params = list(sig.parameters.keys())
            
            # Command functions should accept a parameters dict
            # We're flexible about the exact signature
            return len(params) >= 1
        
        except Exception:
            return False
    
    def sync_from_database(self) -> int:
        """
        Sync command registrations from database
        
        Returns:
            Number of commands synced
        """
        try:
            # Get all active commands from database
            commands = frappe.get_all(
                "HD Telegram Command",
                filters={"is_active": 1},
                fields=["command_name", "function_path", "description", "command_type", "category"]
            )
            
            synced_count = 0
            
            for cmd in commands:
                command_name = cmd.command_name
                function_path = cmd.function_path
                
                # Register command if not already registered or if path changed
                if (command_name not in self.registered_commands or 
                    self.registered_commands[command_name]["function_path"] != function_path):
                    
                    metadata = {
                        "description": cmd.description,
                        "command_type": cmd.command_type,
                        "category": cmd.category,
                        "source": "database"
                    }
                    
                    if self.register_command(command_name, function_path, metadata):
                        synced_count += 1
            
            frappe.logger().info(f"Synced {synced_count} commands from database")
            return synced_count
        
        except Exception as e:
            frappe.log_error(f"Database sync failed: {str(e)}")
            return 0
    
    def auto_discover_commands(self) -> int:
        """
        Auto-discover command functions from specified paths
        
        Returns:
            Number of commands discovered
        """
        discovered_count = 0
        
        for path in self.auto_discovery_paths:
            try:
                discovered_count += self.discover_commands_in_path(path)
            except Exception as e:
                frappe.log_error(f"Auto-discovery failed for path {path}: {str(e)}")
        
        return discovered_count
    
    def discover_commands_in_path(self, module_path: str) -> int:
        """
        Discover commands in a specific module path
        
        Args:
            module_path: Module path to search
            
        Returns:
            Number of commands discovered
        """
        try:
            discovered_count = 0
            
            # Try to import the main module
            try:
                module = importlib.import_module(module_path)
            except ImportError:
                return 0
            
            # Get module directory
            if hasattr(module, '__path__'):
                # This is a package, iterate through submodules
                for importer, modname, ispkg in pkgutil.iter_modules(module.__path__, module.__name__ + "."):
                    try:
                        submodule = importlib.import_module(modname)
                        discovered_count += self.discover_commands_in_module(submodule, modname)
                    except Exception as e:
                        frappe.log_error(f"Failed to discover commands in {modname}: {str(e)}")
            else:
                # Single module
                discovered_count += self.discover_commands_in_module(module, module_path)
            
            return discovered_count
        
        except Exception as e:
            frappe.log_error(f"Path discovery failed for {module_path}: {str(e)}")
            return 0
    
    def discover_commands_in_module(self, module, module_path: str) -> int:
        """
        Discover command functions in a module
        
        Args:
            module: Module object
            module_path: Module path string
            
        Returns:
            Number of commands discovered
        """
        discovered_count = 0
        
        try:
            # Look for functions that follow command naming conventions
            for name in dir(module):
                obj = getattr(module, name)
                
                # Check if it's a function
                if not inspect.isfunction(obj):
                    continue
                
                # Check if it follows command naming convention
                if name.startswith('handle_') and self.validate_function(obj):
                    # Extract command name from function name
                    command_name = '/' + name[7:]  # Remove 'handle_' prefix
                    
                    function_path = f"{module_path}.{name}"
                    
                    # Register if not already registered
                    if command_name not in self.registered_commands:
                        metadata = {
                            "description": f"Auto-discovered command from {module_path}",
                            "command_type": "Custom",
                            "category": "Auto-discovered",
                            "source": "auto_discovery"
                        }
                        
                        if self.register_command(command_name, function_path, metadata):
                            discovered_count += 1
        
        except Exception as e:
            frappe.log_error(f"Module discovery failed for {module_path}: {str(e)}")
        
        return discovered_count
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """
        Get registry statistics
        
        Returns:
            Statistics dictionary
        """
        return {
            "total_commands": len(self.registered_commands),
            "cached_functions": len(self.function_cache),
            "cached_modules": len(self.module_cache),
            "auto_discovery_paths": self.auto_discovery_paths,
            "commands": list(self.registered_commands.keys())
        }
    
    def clear_cache(self):
        """Clear all caches"""
        self.function_cache.clear()
        self.module_cache.clear()
        frappe.logger().info("Command registry cache cleared")
    
    def reload_command(self, command_name: str) -> bool:
        """
        Reload a specific command
        
        Args:
            command_name: Command to reload
            
        Returns:
            True if reload successful, False otherwise
        """
        try:
            # Clear caches for this command
            if command_name in self.function_cache:
                del self.function_cache[command_name]
            
            if command_name in self.registered_commands:
                function_path = self.registered_commands[command_name]["function_path"]
                module_path = function_path.rsplit('.', 1)[0]
                
                # Clear module cache
                if module_path in self.module_cache:
                    del self.module_cache[module_path]
                    
                    # Reload module
                    module = importlib.import_module(module_path)
                    importlib.reload(module)
                    self.module_cache[module_path] = module
            
            frappe.logger().info(f"Reloaded command: {command_name}")
            return True
        
        except Exception as e:
            frappe.log_error(f"Command reload failed for {command_name}: {str(e)}")
            return False


# Global registry instance
_registry = None


def get_command_registry() -> CommandRegistry:
    """
    Get global command registry instance
    
    Returns:
        CommandRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
        # Auto-sync from database on first access
        _registry.sync_from_database()
    return _registry


# Helper functions for external use
@frappe.whitelist()
def register_command(command_name: str, function_path: str, metadata: Dict[str, Any] = None) -> bool:
    """Register a command in the global registry"""
    registry = get_command_registry()
    return registry.register_command(command_name, function_path, metadata)


@frappe.whitelist()
def execute_command(command_name: str, params: Dict[str, Any]) -> Any:
    """Execute a command using the registry"""
    registry = get_command_registry()
    function = registry.get_command_function(command_name)
    
    if not function:
        frappe.throw(_("Command '{0}' not found or not registered").format(command_name))
    
    return function(params)


@frappe.whitelist()
def sync_commands_from_database() -> int:
    """Sync commands from database to registry"""
    registry = get_command_registry()
    return registry.sync_from_database()


@frappe.whitelist()
def auto_discover_commands() -> int:
    """Auto-discover commands from code"""
    registry = get_command_registry()
    return registry.auto_discover_commands()


@frappe.whitelist()
def get_registry_info() -> Dict[str, Any]:
    """Get registry information"""
    registry = get_command_registry()
    return registry.get_registry_stats()


@frappe.whitelist()
def clear_command_cache():
    """Clear command registry cache"""
    registry = get_command_registry()
    registry.clear_cache()


@frappe.whitelist()
def reload_command_registry():
    """Reload the entire command registry"""
    global _registry
    _registry = None
    registry = get_command_registry()
    return registry.get_registry_stats() 