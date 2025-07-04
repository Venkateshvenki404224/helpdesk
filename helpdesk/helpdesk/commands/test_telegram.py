#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Command-line test runner for Telegram Integration

This module provides command-line utilities to run and validate the Telegram
integration from the terminal using bench commands.
"""

import click
import frappe
from frappe.commands import pass_context


@click.group()
def telegram():
    """Telegram integration testing and management commands."""
    pass


@telegram.command()
@click.option('--category', default=None, help='Specific test category to run')
@click.option('--verbose', is_flag=True, help='Verbose output')
@pass_context
def test(context, category=None, verbose=False):
    """Run Telegram integration tests."""
    
    site = context.obj['sites'][0] if context.obj.get('sites') else None
    if not site:
        click.echo("❌ No site specified. Use --site <sitename>")
        return
    
    frappe.init(site=site)
    frappe.connect()
    
    try:
        if category:
            click.echo(f"🧪 Running {category} tests for Telegram integration...")
            from helpdesk.helpdesk.utils.test_telegram_integration import run_specific_test_category
            result = run_specific_test_category(category)
        else:
            click.echo("🧪 Running complete Telegram integration test suite...")
            from helpdesk.helpdesk.utils.test_telegram_integration import run_telegram_integration_tests
            result = run_telegram_integration_tests()
        
        if verbose:
            click.echo(f"📊 Test Results: {result}")
        
        if result.get('overall_status') == 'PASSED':
            click.echo("✅ All tests passed!")
            return 0
        else:
            click.echo("❌ Some tests failed!")
            return 1
            
    except Exception as e:
        click.echo(f"💥 Error running tests: {str(e)}")
        return 1
    finally:
        frappe.destroy()


@telegram.command()
@pass_context
def validate(context):
    """Validate Telegram integration readiness for production."""
    
    site = context.obj['sites'][0] if context.obj.get('sites') else None
    if not site:
        click.echo("❌ No site specified. Use --site <sitename>")
        return
    
    frappe.init(site=site)
    frappe.connect()
    
    try:
        click.echo("🔍 Validating Telegram integration readiness...")
        from helpdesk.helpdesk.utils.test_telegram_integration import validate_integration_readiness
        result = validate_integration_readiness()
        
        if result.get('ready_for_production'):
            click.echo("✅ Integration is ready for production!")
            return 0
        else:
            click.echo("⚠️ Integration is not ready for production!")
            checks = result.get('checks', {})
            for check_name, passed in checks.items():
                status = "✅" if passed else "❌"
                click.echo(f"  {status} {check_name.replace('_', ' ').title()}")
            return 1
            
    except Exception as e:
        click.echo(f"💥 Error validating integration: {str(e)}")
        return 1
    finally:
        frappe.destroy()


@telegram.command()
@click.argument('bot_name')
@click.option('--port', default=8000, help='Local development port')
@pass_context
def start_testing(context, bot_name, port):
    """Start ngrok testing session for development."""
    
    site = context.obj['sites'][0] if context.obj.get('sites') else None
    if not site:
        click.echo("❌ No site specified. Use --site <sitename>")
        return
    
    frappe.init(site=site)
    frappe.connect()
    
    try:
        click.echo(f"🚀 Starting testing session for bot: {bot_name}")
        from helpdesk.helpdesk.utils.ngrok_manager import start_testing_session
        result = start_testing_session(bot_name)
        
        if result.get('success'):
            click.echo("✅ Testing session started successfully!")
            click.echo(f"🔗 Tunnel URL: {result.get('tunnel_url')}")
            click.echo(f"🎯 Webhook URL: {result.get('webhook_url')}")
            return 0
        else:
            click.echo(f"❌ Failed to start testing session: {result.get('message')}")
            return 1
            
    except Exception as e:
        click.echo(f"💥 Error starting testing session: {str(e)}")
        return 1
    finally:
        frappe.destroy()


@telegram.command()
@click.argument('bot_name')
@pass_context
def stop_testing(context, bot_name):
    """Stop ngrok testing session."""
    
    site = context.obj['sites'][0] if context.obj.get('sites') else None
    if not site:
        click.echo("❌ No site specified. Use --site <sitename>")
        return
    
    frappe.init(site=site)
    frappe.connect()
    
    try:
        click.echo(f"🛑 Stopping testing session for bot: {bot_name}")
        from helpdesk.helpdesk.utils.ngrok_manager import stop_testing_session
        result = stop_testing_session(bot_name)
        
        if result.get('success'):
            click.echo("✅ Testing session stopped successfully!")
            return 0
        else:
            click.echo(f"❌ Failed to stop testing session: {result.get('message')}")
            return 1
            
    except Exception as e:
        click.echo(f"💥 Error stopping testing session: {str(e)}")
        return 1
    finally:
        frappe.destroy()


@telegram.command()
@pass_context
def status(context):
    """Show current Telegram integration status."""
    
    site = context.obj['sites'][0] if context.obj.get('sites') else None
    if not site:
        click.echo("❌ No site specified. Use --site <sitename>")
        return
    
    frappe.init(site=site)
    frappe.connect()
    
    try:
        click.echo("📊 Telegram Integration Status")
        click.echo("="*40)
        
        # Check for active bots
        bots = frappe.db.sql("""
            SELECT bot_name, is_active, test_mode_enabled, 
                   total_messages_received, total_tickets_created
            FROM `tabHD Telegram Bot`
        """, as_dict=True)
        
        if bots:
            for bot in bots:
                status_icon = "🟢" if bot.is_active else "🔴"
                test_icon = "🧪" if bot.test_mode_enabled else ""
                
                click.echo(f"{status_icon} Bot: {bot.bot_name} {test_icon}")
                click.echo(f"   Messages: {bot.total_messages_received}")
                click.echo(f"   Tickets: {bot.total_tickets_created}")
        else:
            click.echo("❌ No bots configured")
        
        return 0
        
    except Exception as e:
        click.echo(f"💥 Error getting status: {str(e)}")
        return 1
    finally:
        frappe.destroy()


# Add the command group to frappe commands
commands = [telegram] 