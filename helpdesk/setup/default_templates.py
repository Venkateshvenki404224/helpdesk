import frappe
from frappe import _

def create_default_templates():
    """Create default response templates for Telegram bot"""
    
    templates = [
        # Welcome Messages
        {
            "template_name": "welcome_message",
            "template_type": "Welcome",
            "language": "en",
            "title": "Welcome Message",
            "content": """🎉 Welcome to {bot_name}!

I'm here to help you with your support needs. Here's what I can do for you:

🆘 *Available Commands:*
/help - Show all available commands
/ticket - Create a new support ticket
/status - Check your ticket status
/cancel - Cancel current operation

💡 *Quick Tips:*
• Use /help to see detailed command information
• Type /ticket to get started with creating a support request
• All your conversations are secure and confidential

Ready to get started? Type /help to see all available options! 🚀""",
            "variables": "bot_name",
            "description": "Default welcome message for new users"
        },
        
        # Help Messages
        {
            "template_name": "help_message",
            "template_type": "Help",
            "language": "en", 
            "title": "Help Message",
            "content": """🤖 *{bot_name} - Available Commands*

🆘 *Support Commands:*
/ticket - Create a new support ticket
/status - Check your ticket status

ℹ️ *Information Commands:*
/help - Show this help message
/start - Show welcome message

⚙️ *Utility Commands:*
/cancel - Cancel current operation

💬 *How to Use:*
• Simply type any command to get started
• Follow the prompts for detailed guidance
• Use /cancel anytime to stop current operation

Need immediate help? Type /ticket to create a support request! 📝""",
            "variables": "bot_name",
            "description": "Comprehensive help message with all commands"
        },
        
        # Error Messages
        {
            "template_name": "error_unknown_command",
            "template_type": "Error",
            "language": "en",
            "title": "Unknown Command Error",
            "content": """❌ *Unknown Command*

Sorry, I don't understand that command.

🆘 *Available Commands:*
/help - Show all available commands
/ticket - Create a new support ticket
/status - Check your ticket status
/start - Show welcome message

Type /help to see all available options! 🤖""",
            "variables": "",
            "description": "Error message for unknown commands"
        },
        
        {
            "template_name": "error_permission_denied",
            "template_type": "Error", 
            "language": "en",
            "title": "Permission Denied Error",
            "content": """🚫 *Access Denied*

You don't have permission to use this command.

If you believe this is an error, please contact support for assistance.

Use /help to see available commands for your access level.""",
            "variables": "",
            "description": "Error message for permission denied"
        },
        
        {
            "template_name": "error_general",
            "template_type": "Error",
            "language": "en", 
            "title": "General Error",
            "content": """⚠️ *Something went wrong*

I encountered an error while processing your request.

Please try again in a few moments. If the problem persists, please contact support.

Use /help to see available commands.""",
            "variables": "",
            "description": "General error message for system errors"
        },
        
        # Ticket Commands
        {
            "template_name": "ticket_creation_start",
            "template_type": "Command",
            "language": "en",
            "title": "Ticket Creation Start",
            "content": """📝 *Create Support Ticket*

Let's create a support ticket for you. Please provide the following information:

**Step 1: Subject**
Please enter a brief subject for your ticket:

💡 *Examples:*
• "Login issue with account"
• "Payment not processed"
• "Feature request: Dark mode"

Type your subject below:""",
            "variables": "",
            "description": "Message to start ticket creation process"
        },
        
        {
            "template_name": "ticket_creation_success",
            "template_type": "Command",
            "language": "en",
            "title": "Ticket Created Successfully",
            "content": """✅ *Ticket Created Successfully!*

**Ticket Details:**
📋 **ID:** {ticket_id}
📝 **Subject:** {subject}
📅 **Created:** {created_date}
🎯 **Priority:** {priority}
📊 **Status:** {status}

**What's Next?**
• Our support team will review your ticket shortly
• You'll receive updates on ticket progress
• Use /status to check your ticket status anytime

**Need to add more details?**
Reply to this message with additional information, and it will be added to your ticket.

Thank you for contacting support! 🙏""",
            "variables": "ticket_id,subject,created_date,priority,status",
            "description": "Success message after ticket creation"
        },
        
        # Status Commands
        {
            "template_name": "status_no_tickets",
            "template_type": "Command",
            "language": "en",
            "title": "No Tickets Found",
            "content": """📋 *Ticket Status*

You don't have any support tickets yet.

To create a new ticket, use the /ticket command.

Need help? Type /help to see all available commands! 🤖""",
            "variables": "",
            "description": "Message when user has no tickets"
        },
        
        {
            "template_name": "status_ticket_list",
            "template_type": "Command",
            "language": "en",
            "title": "Ticket Status List",
            "content": """📋 *Your Support Tickets*

{ticket_list}

**Legend:**
🟢 Open • 🟡 In Progress • 🔴 Waiting • ✅ Closed

Use /ticket to create a new support request! 📝""",
            "variables": "ticket_list",
            "description": "Message showing user's ticket list"
        },
        
        # Cancel Commands
        {
            "template_name": "cancel_success",
            "template_type": "Command",
            "language": "en",
            "title": "Operation Cancelled",
            "content": """❌ *Operation Cancelled*

Your current operation has been cancelled.

You can start fresh with any of these commands:
• /ticket - Create a new support ticket
• /status - Check your ticket status
• /help - Show all available commands

How can I help you today? 🤖""",
            "variables": "",
            "description": "Success message after cancelling operation"
        },
        
        {
            "template_name": "cancel_nothing",
            "template_type": "Command",
            "language": "en",
            "title": "Nothing to Cancel",
            "content": """ℹ️ *Nothing to Cancel*

You don't have any active operations to cancel.

Ready to start something new?
• /ticket - Create a new support ticket
• /status - Check your ticket status
• /help - Show all available commands

What would you like to do? 🤖""",
            "variables": "",
            "description": "Message when there's nothing to cancel"
        },
        
        # Additional Templates
        {
            "template_name": "typing_indicator",
            "template_type": "System",
            "language": "en",
            "title": "Typing Indicator",
            "content": "💭 Processing...",
            "variables": "",
            "description": "Typing indicator message"
        },
        
        {
            "template_name": "maintenance_mode",
            "template_type": "System",
            "language": "en",
            "title": "Maintenance Mode",
            "content": """🔧 *Maintenance Mode*

The bot is currently undergoing maintenance.

Please try again in a few minutes. Thank you for your patience! 🙏""",
            "variables": "",
            "description": "Message shown during maintenance"
        }
    ]
    
    # Create templates
    for template_data in templates:
        # Check if template already exists
        if not frappe.db.exists("HD Bot Response Template", template_data["template_name"]):
            template = frappe.get_doc({
                "doctype": "HD Bot Response Template",
                **template_data
            })
            template.insert(ignore_permissions=True)
            print(f"Created template: {template_data['template_name']}")
        else:
            print(f"Template already exists: {template_data['template_name']}")
    
    frappe.db.commit()
    print("Default templates creation completed!")

if __name__ == "__main__":
    create_default_templates() 