# Telegram Bot System Documentation

## Overview

The Telegram Bot System for Helpdesk is a comprehensive, scalable, and configurable bot framework that replaces hardcoded bot behavior with a plugin-based command system. The system provides template-driven responses, dynamic function loading, comprehensive permission management, and robust error handling.

## Architecture Overview

The system follows a plugin-based architecture with the following key principles:

- **Modular Design**: Commands, templates, and responses are separately configurable
- **Database-Driven**: All configuration stored in Frappe doctypes
- **Scalable**: Support for multiple bots with per-bot customization
- **Template-Based**: Rich template system with variable substitution
- **Permission-Aware**: Comprehensive access control and user management
- **Error Resilient**: Graceful error handling with fallback mechanisms

### System Flow

```
Telegram Webhook → Webhook Handler → Command Router → Command Processor → Response Manager → Telegram API
```

## Core Components

### 1. HD Telegram Bot (Doctype)
**Location**: `helpdesk/helpdesk/doctype/hd_telegram_bot/`

Master configuration for Telegram bots including:
- Bot credentials and webhook settings
- Command mappings and response templates
- Permission settings and rate limiting
- Advanced features (file uploads, conversation tracking)

### 2. HD Telegram Command (Doctype)
**Location**: `helpdesk/helpdesk/doctype/hd_telegram_command/`

Master registry for available commands:
- Command metadata and function mapping
- Permission requirements and access levels
- Response templates and help text
- Usage statistics and validation

### 3. HD Bot Response Template (Doctype)
**Location**: `helpdesk/helpdesk/doctype/hd_bot_response_template/`

Template system for bot responses:
- Multi-language support with variable substitution
- Keyboard layouts and message formatting
- Template categories and usage tracking
- Validation and rendering engine

### 4. HD Bot Command Mapping (Child Table)
**Location**: Part of HD Telegram Bot

Bridge table connecting bots to commands:
- Bot-specific command configuration
- Custom response overrides and access levels
- Sort ordering and activation status

### 5. Command Processing Engine

#### TelegramCommandProcessor
**Location**: `helpdesk/helpdesk/utils/telegram_command_processor.py`

Core command processing with:
- Message parsing and command detection
- Permission checking and validation
- Dynamic function loading and execution
- Response processing and error handling

#### CommandRouter
**Location**: `helpdesk/helpdesk/utils/command_router.py`

Advanced routing with middleware support:
- Route configuration and caching
- Middleware stack execution
- Fallback handling and statistics
- Custom route registration

#### BotResponseManager
**Location**: `helpdesk/helpdesk/utils/bot_response_manager.py`

Template rendering and response management:
- Template caching and fallback mechanisms
- Variable substitution and formatting
- Multi-language support and validation
- Response optimization

#### WelcomeMessageHandler
**Location**: `helpdesk/helpdesk/utils/welcome_message_handler.py`

First-time user interaction management:
- New vs returning user detection
- Personalized welcome messages
- User statistics and preferences
- Template-driven responses

#### CommandRegistry
**Location**: `helpdesk/helpdesk/utils/command_registry.py`

Dynamic command registration system:
- Function validation and caching
- Module loading and discovery
- Registry synchronization
- Performance monitoring

## Features Implemented

✅ **Plugin-Based Command System**
- Dynamic command registration and execution
- Master command registry with database-driven configuration
- Function validation and caching

✅ **Template-Driven Responses**
- Multi-language template support
- Variable substitution and formatting
- Template caching and fallback mechanisms

✅ **Scalable Bot Configuration**
- Per-bot customization and command mapping
- Global and bot-specific command support
- Advanced bot settings and features

✅ **Comprehensive Permission System**
- Hierarchical access levels (Public, Registered, Premium, Admin)
- Role-based command access
- User management and statistics

✅ **Advanced Routing and Middleware**
- Command routing with middleware support
- Rate limiting and permission checking
- Custom middleware and fallback handlers

✅ **Robust Error Handling**
- Graceful error recovery and fallback responses
- Comprehensive logging and debugging
- Error template system

✅ **Testing and Validation**
- Comprehensive test suite for all components
- Performance testing and optimization
- Configuration validation tools

## Command System

### Built-in Commands

The system includes several built-in commands:

- **`/start`** - Welcome message and bot initialization
- **`/help`** - Show available commands and usage
- **`/ticket`** - Create new support tickets  
- **`/status`** - Check ticket status
- **`/cancel`** - Cancel current operations

### Creating Custom Commands

1. **Define the command function**:

```python
def handle_my_command(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle custom command
    
    Args:
        params: Dictionary containing command parameters
        
    Returns:
        Dict containing response data
    """
    user_data = params.get("user_data", {})
    message_data = params.get("message_data", {})
    bot_doc = params.get("bot_doc")
    
    # Your command logic here
    
    return {
        "success": True,
        "response_message": "Command executed successfully!",
        "parse_mode": "Markdown"
    }
```

2. **Register the command in the database**:

```python
command_doc = frappe.get_doc({
    "doctype": "HD Telegram Command",
    "command_name": "/mycommand",
    "display_name": "My Command",
    "description": "Custom command description",
    "function_path": "helpdesk.api.telegram.commands.my_command.handle_my_command",
    "command_type": "Custom",
    "category": "General",
    "access_level": "Public",
    "is_active": 1,
    "is_global": 1
})
command_doc.insert()
```

## Response Templates

### Template System

Templates support variable substitution using `{variable_name}` syntax:

```markdown
Hello {user_name}! Welcome to {bot_name}.

Available commands: {commands_count}

{available_commands}
```

### Common Variables

- `{user_name}` - User's first name
- `{bot_name}` - Bot's display name
- `{company_name}` - Company name
- `{available_commands}` - Formatted list of commands
- `{commands_count}` - Number of available commands
- `{current_date}` - Current date
- `{current_time}` - Current time

## Testing

### Comprehensive Test Suite

```python
from helpdesk.helpdesk.utils.telegram_bot_tester import TelegramBotTester

# Run all tests
tester = TelegramBotTester("your_bot_name")
results = tester.run_comprehensive_tests()

# Run specific tests
command_tests = tester.test_command_processing()
template_tests = tester.test_response_templates()
performance_tests = tester.test_performance()
```

### Test Categories

1. **Command Processing Tests** - Command parsing and execution
2. **Response Template Tests** - Template rendering and validation
3. **Command Router Tests** - Routing and middleware
4. **Welcome Message Tests** - User onboarding flow
5. **Permission System Tests** - Access control validation
6. **Error Handling Tests** - Error recovery and fallbacks
7. **Performance Tests** - Response time and throughput
8. **Integration Tests** - End-to-end webhook processing

## Setup and Configuration

### 1. Bot Setup

1. **Create a new Telegram bot** with @BotFather
2. **Configure the bot in Helpdesk**:
   - Go to Helpdesk → Telegram → HD Telegram Bot
   - Create new bot configuration
   - Enter bot token and settings

3. **Set up webhook**:
   - Configure webhook URL: `https://yourdomain.com/telegram/webhook`
   - Set webhook secret for security

### 2. Default Setup

```bash
# Load default templates and commands
bench execute helpdesk.setup.default_templates.create_default_templates
bench execute helpdesk.helpdesk.doctype.hd_telegram_command.hd_telegram_command.create_default_commands
```

## Performance Optimization

### Caching Strategy

The system implements multiple levels of caching:

1. **Command Cache** - Loaded command configurations
2. **Template Cache** - Rendered templates and contexts
3. **Route Cache** - Routing configurations
4. **User Cache** - Frequently accessed user data

### Database Optimization

- Database cursor optimization for large datasets
- Proper indexing on frequently queried fields
- Batch operations for bulk updates
- Connection pooling for concurrent requests

## Migration from Legacy System

The new system is designed to replace hardcoded bot behavior with:

1. **Database-driven configuration** instead of hardcoded settings
2. **Plugin-based commands** instead of fixed command handlers
3. **Template-driven responses** instead of hardcoded messages
4. **Scalable architecture** supporting multiple bots
5. **Comprehensive testing** and validation tools

## Security Features

- **Webhook secret validation** for secure communication
- **Access level-based permissions** with hierarchical control
- **Rate limiting** to prevent abuse
- **Input validation** and sanitization
- **Audit logging** for security monitoring

## API Reference

### Main Webhook Endpoint

**POST** `/telegram/webhook`

Processes incoming Telegram updates with webhook secret validation.

### Testing APIs

```python
# Test bot configuration
@frappe.whitelist()
def validate_bot_configuration(bot_name: str) -> Dict[str, Any]

# Run comprehensive tests
@frappe.whitelist() 
def run_bot_tests(bot_name: str = None) -> Dict[str, Any]

# Run specific test type
@frappe.whitelist()
def run_specific_test(bot_name: str, test_type: str) -> Dict[str, Any]
```

### Command Processing APIs

```python
# Route telegram message
@frappe.whitelist()
def route_telegram_message(bot_name: str, message_data: Dict, user_data: Dict) -> Dict[str, Any]

# Get router statistics  
@frappe.whitelist()
def get_router_stats(bot_name: str = None) -> Dict[str, Any]
```

## Troubleshooting

### Common Issues

1. **Webhook not receiving updates**
   - Check webhook URL accessibility and SSL certificate
   - Verify webhook secret configuration
   - Confirm bot token validity

2. **Command not found errors**
   - Verify command is active in HD Telegram Command
   - Check command mapping in bot configuration
   - Validate function path and imports

3. **Template rendering failures**
   - Check template exists and is active
   - Verify variable names in template
   - Review template syntax and formatting

4. **Permission denied errors**
   - Review user access levels
   - Check command permission requirements
   - Verify role-based permissions

### Debugging Tools

Enable debug logging in `site_config.json`:

```json
{
    "developer_mode": 1,
    "log_level": "DEBUG"
}
```

Test individual components:

```python
# Test command processing
from helpdesk.helpdesk.utils.telegram_command_processor import TelegramCommandProcessor

processor = TelegramCommandProcessor("your_bot")
result = processor.process_message(
    {"text": "/help"},
    {"id": "test_user", "first_name": "Test"}
)

# Test template rendering
from helpdesk.helpdesk.utils.bot_response_manager import BotResponseManager

response_manager = BotResponseManager("your_bot")
result = response_manager.render_template("welcome_message", {
    "user_name": "Test User",
    "bot_name": "Test Bot"
})
```

## Technical Architecture Benefits

### Scalability
- **Multi-bot support** with per-bot customization
- **Horizontal scaling** through stateless design
- **Caching layers** for improved performance
- **Background job processing** for heavy operations

### Maintainability
- **Modular design** with clear separation of concerns
- **Database-driven configuration** eliminating hardcoded values
- **Comprehensive testing** ensuring reliability
- **Clear documentation** and code organization

### Extensibility
- **Plugin-based command system** for easy additions
- **Template-driven responses** for customization
- **Middleware support** for cross-cutting concerns
- **API-based architecture** for integration

### Reliability
- **Graceful error handling** with fallback mechanisms
- **Comprehensive logging** for debugging
- **Input validation** and sanitization
- **Security features** built-in

This system represents a significant architectural improvement over the previous hardcoded approach, providing a robust, scalable, and maintainable foundation for Telegram bot functionality in the Helpdesk application. 