// Copyright (c) 2024, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('HD Telegram Bot', {
    refresh: function(frm) {
        // Add custom buttons to the form
        frm.add_custom_button(__('Test Connection'), function() {
            test_bot_connection(frm);
        }, __('Bot Actions'));

        frm.add_custom_button(__('Setup Webhook'), function() {
            setup_webhook(frm);
        }, __('Bot Actions'));

        frm.add_custom_button(__('Get Webhook Info'), function() {
            get_webhook_info(frm);
        }, __('Bot Actions'));

        frm.add_custom_button(__('Remove Webhook'), function() {
            remove_webhook(frm);
        }, __('Bot Actions'));

        // Add send test message button
        frm.add_custom_button(__('Send Test Message'), function() {
            send_test_message(frm);
        }, __('Bot Actions'));

        frm.add_custom_button(__('Get Recent Chats'), function() {
            get_recent_chats(frm);
        }, __('Bot Actions'));

        // Add ngrok configuration guide button
        frm.add_custom_button(__('Configuration Guide'), function() {
            show_ngrok_configuration_guide(frm);
        }, __('Testing'));

        frm.add_custom_button(__('Check Ngrok Status'), function() {
            check_ngrok_status(frm);
        }, __('Testing'));

        frm.add_custom_button(__('Refresh Webhook Secret'), function() {
            refresh_webhook_secret(frm);
        }, __('Testing'));

        // Update testing status on refresh
        if (frm.doc.name) {
            update_testing_status(frm);
        }

        // Set up auto-refresh for testing status if active
        if (frm.doc.test_mode_enabled) {
            setup_status_refresh(frm);
        }
    },

    // Handle testing button clicks
    start_testing: function(frm) {
        start_testing_session(frm);
    },

    stop_testing: function(frm) {
        stop_testing_session(frm);
    },

    // Auto-update testing status when test mode is toggled
    test_mode_enabled: function(frm) {
        if (frm.doc.test_mode_enabled && !frm.doc.ngrok_tunnel_url) {
            // If test mode is enabled but no tunnel exists, start session
            start_testing_session(frm);
        } else if (!frm.doc.test_mode_enabled && frm.doc.ngrok_tunnel_url) {
            // If test mode is disabled but tunnel exists, stop session
            stop_testing_session(frm);
        }
    }
});

// Bot connection test
function test_bot_connection(frm) {
    if (!frm.doc.bot_token) {
        frappe.msgprint(__('Please enter a bot token first'));
        return;
    }

    frappe.call({
        method: 'test_bot_connection',
        doc: frm.doc,
        callback: function(r) {
            if (r.message && r.message.success) {
                const bot_info = r.message.bot_info;
                // Handle large integer bot ID safely
                const bot_id = typeof bot_info.id === 'number' ? bot_info.id.toString() : bot_info.id;
                
                frappe.msgprint({
                    title: __('Connection Successful'),
                    message: `Bot Name: ${bot_info.first_name || 'N/A'}<br>
                             Username: @${bot_info.username || 'N/A'}<br>
                             Bot ID: ${bot_id}<br>
                             Can Join Groups: ${bot_info.can_join_groups || false}<br>
                             Can Read All Group Messages: ${bot_info.can_read_all_group_messages || false}`,
                    indicator: 'green'
                });
            } else {
                frappe.msgprint({
                    title: __('Connection Failed'),
                    message: r.message ? r.message.message : __('Unknown error'),
                    indicator: 'red'
                });
            }
        }
    });
}

// Webhook setup
function setup_webhook(frm) {
    frappe.call({
        method: 'setup_webhook',
        doc: frm.doc,
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.msgprint({
                    title: __('Webhook Setup Successful'),
                    message: __('Webhook has been configured successfully'),
                    indicator: 'green'
                });
                frm.reload_doc();
            } else {
                frappe.msgprint({
                    title: __('Webhook Setup Failed'),
                    message: r.message ? r.message.message : __('Unknown error'),
                    indicator: 'red'
                });
            }
        }
    });
}

// Get webhook info
function get_webhook_info(frm) {
    frappe.call({
        method: 'get_webhook_info',
        doc: frm.doc,
        callback: function(r) {
            if (r.message && r.message.success) {
                const info = r.message.webhook_info;
                const url = info.url || 'Not set';
                const pending_updates = info.pending_update_count || 0;
                const last_error = info.last_error_date ? 
                    new Date(info.last_error_date * 1000).toLocaleString() : 'None';

                frappe.msgprint({
                    title: __('Webhook Information'),
                    message: `URL: ${url}<br>
                             Pending Updates: ${pending_updates}<br>
                             Last Error: ${last_error}<br>
                             Has Custom Certificate: ${info.has_custom_certificate || false}`,
                    indicator: 'blue'
                });
            } else {
                frappe.msgprint({
                    title: __('Failed to Get Webhook Info'),
                    message: r.message ? r.message.message : __('Unknown error'),
                    indicator: 'red'
                });
            }
        }
    });
}

// Remove webhook
function remove_webhook(frm) {
    frappe.confirm(__('Are you sure you want to remove the webhook?'), function() {
        frappe.call({
            method: 'remove_webhook',
            doc: frm.doc,
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Webhook Removed'),
                        message: __('Webhook has been removed successfully'),
                        indicator: 'green'
                    });
                    frm.reload_doc();
                } else {
                    frappe.msgprint({
                        title: __('Failed to Remove Webhook'),
                        message: r.message ? r.message.message : __('Unknown error'),
                        indicator: 'red'
                    });
                }
            }
        });
    });
}

// Refresh webhook secret for testing
function refresh_webhook_secret(frm) {
    if (!frm.doc.test_mode_enabled) {
        frappe.msgprint({
            title: __('Testing Mode Required'),
            message: __('Testing mode must be enabled to refresh webhook secrets.'),
            indicator: 'yellow'
        });
        return;
    }

    frappe.confirm(
        __('This will generate a new webhook secret and update Telegram. Continue?'),
        function() {
            frappe.call({
                method: 'refresh_testing_webhook',
                doc: frm.doc,
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.msgprint({
                            title: __('🔄 Webhook Secret Refreshed'),
                            message: `✅ Webhook secret updated successfully!<br>🔗 URL: ${r.message.webhook_url}`,
                            indicator: 'green'
                        });
                        frm.reload_doc();
                    } else {
                        frappe.msgprint({
                            title: __('❌ Webhook Refresh Failed'),
                            message: r.message ? r.message.message : __('Unknown error occurred'),
                            indicator: 'red'
                        });
                    }
                }
            });
        }
    );
}

// Send test message
function send_test_message(frm) {
    frappe.prompt([
        {
            'fieldname': 'chat_id',
            'label': __('Chat ID'),
            'fieldtype': 'Data',
            'reqd': 1,
            'description': __('Telegram Chat ID (your user ID or group ID)')
        },
        {
            'fieldname': 'message',
            'label': __('Test Message'),
            'fieldtype': 'Text',
            'default': `🤖 Hello from ${frm.doc.bot_name}!\n\n✅ Bot is working correctly!\n📅 ${frappe.datetime.now_datetime()}\n\nYou can now send messages to test the webhook.`,
            'description': __('Custom message to send (leave default for standard test)')
        }
    ], function(values) {
        frappe.call({
            method: 'send_test_message',
            doc: frm.doc,
            args: {
                'chat_id': values.chat_id,
                'message': values.message
            },
            callback: function(r) {
                if (r.message && r.message.success) {
                    frappe.msgprint({
                        title: __('Test Message Sent'),
                        message: __('Test message sent successfully! Check your Telegram chat.'),
                        indicator: 'green'
                    });
                } else {
                    frappe.msgprint({
                        title: __('Failed to Send Test Message'),
                        message: r.message ? r.message.message : __('Unknown error'),
                        indicator: 'red'
                    });
                }
            }
        });
    }, __('Send Test Message'), __('Send'));
}

// Get recent chats to help find chat IDs
function get_recent_chats(frm) {
    frappe.call({
        method: 'get_recent_chats',
        doc: frm.doc,
        callback: function(r) {
            if (r.message && r.message.success) {
                const chats = r.message.chats || [];
                
                if (chats.length === 0) {
                    frappe.msgprint({
                        title: __('No Recent Chats Found'),
                        message: __('No recent messages found. Send a message to your bot first, then try again.'),
                        indicator: 'orange'
                    });
                    return;
                }
                
                // Format chat list for display
                let chat_list = '<div style="max-height: 400px; overflow-y: auto;">';
                chat_list += '<table class="table table-bordered"><thead><tr>';
                chat_list += '<th>Chat ID</th><th>Type</th><th>Name</th><th>Username</th><th>Action</th>';
                chat_list += '</tr></thead><tbody>';
                
                chats.forEach(chat => {
                    const name = chat.title || `${chat.first_name || ''} ${chat.last_name || ''}`.trim() || 'Unknown';
                    const username = chat.username ? `@${chat.username}` : '';
                    const chat_type = chat.type || 'unknown';
                    
                    chat_list += `<tr>
                        <td><code>${chat.chat_id}</code></td>
                        <td><span class="label label-default">${chat_type}</span></td>
                        <td>${name}</td>
                        <td>${username}</td>
                        <td><button class="btn btn-xs btn-primary" onclick="copy_chat_id('${chat.chat_id}')">Copy</button></td>
                    </tr>`;
                });
                
                chat_list += '</tbody></table></div>';
                
                frappe.msgprint({
                    title: __('Recent Chats'),
                    message: `
                        <div style="margin-bottom: 15px;">
                            <strong>Found ${chats.length} recent chat(s):</strong>
                        </div>
                        ${chat_list}
                        <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                            <strong>💡 How to use:</strong><br>
                            1. Copy the Chat ID you want to test with<br>
                            2. Use "Send Test Message" button with that Chat ID<br>
                            3. Or send a message to the bot and it will create a ticket
                        </div>
                        <script>
                            function copy_chat_id(chat_id) {
                                navigator.clipboard.writeText(chat_id).then(function() {
                                    frappe.show_alert({message: 'Chat ID copied: ' + chat_id, indicator: 'green'});
                                });
                            }
                        </script>
                    `,
                    indicator: 'blue'
                });
            } else {
                frappe.msgprint({
                    title: __('Failed to Get Recent Chats'),
                    message: r.message ? r.message.message : __('Unknown error'),
                    indicator: 'red'
                });
            }
        }
    });
}

// Development Testing Functions

function start_testing_session(frm) {
    if (!frm.doc.bot_token) {
        frappe.msgprint(__('Please enter a bot token first'));
        return;
    }

    // Show loading indicator
    frappe.show_alert({
        message: __('Starting testing session...'),
        indicator: 'blue'
    });

    frappe.call({
        method: 'start_testing_session',
        doc: frm.doc,
        callback: function(r) {
            if (r.message && r.message.success) {
                // Reload the form to show updated status
                frm.reload_doc();
                
                // Setup auto-refresh
                setup_status_refresh(frm);
                
                // Show comprehensive success message with testing guide
                frappe.msgprint({
                    title: __('🚀 Testing Session Started Successfully!'),
                    message: `
                        <div style="margin-bottom: 15px;">
                            <strong>✅ Ngrok Tunnel Created:</strong> <a href="${r.message.tunnel_url}" target="_blank">${r.message.tunnel_url}</a><br>
                            <strong>🔗 Webhook URL:</strong> ${r.message.webhook_url}<br>
                            <strong>🔒 Webhook Secret:</strong> ${r.message.webhook_secret ? 'Configured' : 'Not set'}<br>
                            <strong>🌐 Local Port:</strong> ${r.message.port}
                        </div>
                        
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <h5>🧪 Quick Testing Guide:</h5>
                            <ol style="margin: 10px 0; padding-left: 20px;">
                                <li><strong>Find your bot:</strong> Search <code>@${frm.doc.bot_name || 'your_bot_name'}</code> on Telegram</li>
                                <li><strong>Start chat:</strong> Send <code>/start</code> to your bot</li>
                                <li><strong>Test messaging:</strong> Send any message like "Hello, I need help!"</li>
                                <li><strong>Check logs:</strong> Watch the console for webhook calls</li>
                                <li><strong>Verify tickets:</strong> Check if tickets are created in HD Ticket list</li>
                            </ol>
                        </div>
                        
                        <div style="background: #e8f5e8; padding: 10px; border-radius: 5px; margin: 10px 0;">
                            <strong>💡 Pro Tip:</strong> Use the "Send Test Message" button to verify bot communication works!
                        </div>
                    `,
                    indicator: 'green'
                });
                
            } else {
                // Check if it's an authentication error
                if (r.message && (r.message.error === 'missing_api_key' || r.message.error === 'missing_authtoken')) {
                    show_ngrok_auth_error(r.message);
                } else {
                    frappe.msgprint({
                        title: __('❌ Testing Session Failed'),
                        message: `
                            <div style="margin-bottom: 15px;">
                                <strong>Error:</strong> ${r.message ? r.message.message : __('Unknown error')}
                            </div>
                            
                            <div style="background: #fff3cd; padding: 10px; border-radius: 5px; margin: 10px 0;">
                                <h5>🔧 Troubleshooting Steps:</h5>
                                <ol style="margin: 10px 0; padding-left: 20px;">
                                    <li>Check your bot token is valid</li>
                                    <li>Verify ngrok authentication is configured</li>
                                    <li>Ensure port ${frm.doc.ngrok_port || 8000} is available</li>
                                    <li>Check your internet connection</li>
                                    <li>Try the "Configuration Guide" for setup help</li>
                                </ol>
                            </div>
                        `,
                        indicator: 'red'
                    });
                }
            }
        },
        error: function(r) {
            frappe.msgprint({
                title: __('❌ Error Starting Testing Session'),
                message: __('A technical error occurred. Please check the console logs and try again.'),
                indicator: 'red'
            });
        }
    });
}

function stop_testing_session(frm) {
    frappe.confirm(__('Are you sure you want to stop the testing session?'), function() {
        // Show loading indicator
        frappe.show_alert({
            message: __('Stopping testing session...'),
            indicator: 'orange'
        });

        frappe.call({
            method: 'stop_testing_session',
            doc: frm.doc,
            callback: function(r) {
                if (r.message && r.message.success) {
                    // Reload the form to show updated status
                    frm.reload_doc();
                    
                    // Clear auto-refresh
                    clear_status_refresh(frm);
                    
                    frappe.show_alert({
                        message: __('Testing session stopped successfully'),
                        indicator: 'green'
                    });
                } else {
                    frappe.show_alert({
                        message: __('Failed to stop testing session: ') + (r.message ? r.message.message : __('Unknown error')),
                        indicator: 'red'
                    });
                }
            },
            error: function(r) {
                frappe.show_alert({
                    message: __('Error stopping testing session'),
                    indicator: 'red'
                });
            }
        });
    });
}

function update_testing_status(frm) {
    if (!frm.doc.name) return;

    frappe.call({
        method: 'get_testing_status',
        doc: frm.doc,
        callback: function(r) {
            if (r.message && r.message.success && r.message.status === 'active') {
                // Update status fields if they're different
                if (frm.doc.ngrok_tunnel_url !== r.message.tunnel_url) {
                    frm.set_value('ngrok_tunnel_url', r.message.tunnel_url);
                }
                if (frm.doc.testing_status !== 'Active - Testing Mode') {
                    frm.set_value('testing_status', 'Active - Testing Mode');
                }
                if (!frm.doc.test_mode_enabled) {
                    frm.set_value('test_mode_enabled', 1);
                }
            } else if (r.message && r.message.status === 'inactive') {
                // Clear testing fields if tunnel is inactive
                if (frm.doc.ngrok_tunnel_url) {
                    frm.set_value('ngrok_tunnel_url', '');
                }
                if (frm.doc.testing_status !== 'Inactive') {
                    frm.set_value('testing_status', 'Inactive');
                }
                if (frm.doc.test_mode_enabled) {
                    frm.set_value('test_mode_enabled', 0);
                }
            }
        },
        error: function(r) {
            // Silent error - testing status check shouldn't be intrusive
            console.log('Error checking testing status:', r);
        }
    });
}

// Auto-refresh functionality for testing status
let status_refresh_interval = null;

function setup_status_refresh(frm) {
    // Clear any existing interval
    clear_status_refresh(frm);
    
    // Set up new interval to check status every 30 seconds
    status_refresh_interval = setInterval(function() {
        if (frm.doc && frm.doc.test_mode_enabled) {
            update_testing_status(frm);
        } else {
            clear_status_refresh(frm);
        }
    }, 30000); // 30 seconds
}

function clear_status_refresh(frm) {
    if (status_refresh_interval) {
        clearInterval(status_refresh_interval);
        status_refresh_interval = null;
    }
}

// Clear interval when form is closed
frappe.ui.form.on('HD Telegram Bot', {
    onload: function(frm) {
        // Clear any existing intervals when form loads
        clear_status_refresh(frm);
    }
});

// Cleanup when page is unloaded
window.addEventListener('beforeunload', function() {
    if (status_refresh_interval) {
        clearInterval(status_refresh_interval);
    }
});

function show_ngrok_auth_error(error_data) {
    frappe.msgprint({
        title: __('Ngrok Authentication Required'),
        message: `
            <div style="margin-bottom: 15px;">
                <strong>Authentication Issue:</strong> ${error_data.message}
            </div>
            <div style="margin-bottom: 15px;">
                <strong>Quick Setup:</strong>
                <ol>
                    <li>Go to <a href="https://dashboard.ngrok.com/signup" target="_blank">ngrok.com</a> and create a free account</li>
                    <li>Get your authtoken from <a href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank">dashboard</a></li>
                    <li>Add to your site configuration or environment variables</li>
                </ol>
            </div>
            <div>
                <button class="btn btn-primary btn-sm" onclick="show_ngrok_configuration_guide()">
                    View Detailed Guide
                </button>
            </div>
        `,
        indicator: 'orange'
    });
}

function show_ngrok_configuration_guide(frm) {
    frappe.call({
        method: 'helpdesk.helpdesk.utils.ngrok_manager.get_configuration_guide',
        callback: function(r) {
            if (r.message && r.message.success) {
                const guide = r.message;
                let html = '<div class="ngrok-guide">';
                
                // Current Status
                html += '<div style="margin-bottom: 20px; padding: 10px; background: #f8f9fa; border-radius: 5px;">';
                html += '<h5>Current Configuration Status</h5>';
                const status = guide.current_status;
                html += `<ul style="margin: 10px 0;">`;
                html += `<li>Python API Available: ${status.python_api_available ? '✅' : '❌'}</li>`;
                html += `<li>API Key Configured: ${status.api_key_configured ? '✅' : '❌'}</li>`;
                html += `<li>Authtoken Configured: ${status.authtoken_configured ? '✅' : '❌'}</li>`;
                html += `<li>CLI Installed: ${status.cli_installed ? '✅' : '❌'}</li>`;
                html += `</ul></div>`;
                
                // Instructions
                html += '<div class="setup-instructions">';
                Object.values(guide.instructions).forEach(step => {
                    html += `<div style="margin-bottom: 15px; padding: 10px; border-left: 3px solid #007bff;">`;
                    html += `<h6>${step.title}</h6>`;
                    html += `<p>${step.description}</p>`;
                    
                    if (step.url) {
                        html += `<a href="${step.url}" target="_blank" class="btn btn-sm btn-outline-primary">Open Link</a>`;
                    }
                    
                    if (step.command) {
                        html += `<div style="background: #f1f1f1; padding: 8px; margin-top: 8px; border-radius: 3px; font-family: monospace;">${step.command}</div>`;
                    }
                    
                    if (step.options) {
                        step.options.forEach(option => {
                            html += `<div style="margin: 10px 0;">`;
                            html += `<strong>${option.method}:</strong><br>`;
                            if (option.config.site_config) {
                                html += `<em>site_config.json:</em> <code>${option.config['site_config.json']}</code><br>`;
                            }
                            if (option.config.environment) {
                                html += `<em>Environment:</em> <code>${option.config.environment}</code>`;
                            }
                            html += `</div>`;
                        });
                    }
                    
                    html += `</div>`;
                });
                html += '</div></div>';
                
                frappe.msgprint({
                    title: __('Ngrok Configuration Guide'),
                    message: html,
                    indicator: 'blue'
                });
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to load configuration guide'),
                    indicator: 'red'
                });
            }
        }
    });
}

function check_ngrok_status(frm) {
    frappe.call({
        method: 'helpdesk.helpdesk.utils.ngrok_manager.check_ngrok_status',
        callback: function(r) {
            if (r.message && r.message.success) {
                const status = r.message.status;
                let message = '<div class="ngrok-status">';
                message += '<h6>Ngrok Configuration Status</h6><ul>';
                message += `<li>Python API Available: ${status.python_api_available ? '✅ Yes' : '❌ No'}</li>`;
                message += `<li>API Key Configured: ${status.api_key_configured ? '✅ Yes' : '❌ No'}</li>`;
                message += `<li>Authtoken Configured: ${status.authtoken_configured ? '✅ Yes' : '❌ No'}</li>`;
                message += `<li>CLI Installed: ${status.cli_installed ? '✅ Yes' : '❌ No'}</li>`;
                message += `<li>Using Python API: ${status.use_python_api ? '✅ Yes' : '❌ No (CLI mode)'}</li>`;
                message += `<li>Authentication Ready: ${status.authentication_configured ? '✅ Yes' : '❌ No'}</li>`;
                message += '</ul></div>';
                
                frappe.msgprint({
                    title: __('Ngrok Status'),
                    message: message,
                    indicator: status.authentication_configured ? 'green' : 'orange'
                });
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    message: __('Failed to check ngrok status'),
                    indicator: 'red'
                });
            }
        }
    });
} 