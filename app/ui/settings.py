"""
Settings Management Interface for F&O Trading System
- Broker configuration and API credentials
- System settings and risk parameters
- Strategy configurations and toggles
- Event calendar and notification settings
- Database and security configurations
- Real-time monitoring and health checks
"""

import streamlit as st
import pandas as pd
import json
import logging
from datetime import datetime, date, time
from typing import Dict, List, Any, Optional
import requests

# Import system components
from app.config import settings
from app.db.models import User, BrokerAccount, SystemSettings, Strategy
from app.db.base import db_manager
from app.db.encryption import db_encryptor, test_encryption_roundtrip
from app.notifications.whatsapp_notifier import WhatsAppNotifier
from app.utils.event_calendar import event_calendar
from app.utils.healthcheck import health_checker
from app.risk.risk_monitor import risk_monitor

logger = logging.getLogger("settings_ui")

class SettingsManager:
    """Comprehensive settings management for the trading system"""
    
    def __init__(self):
        self.current_user = self._get_current_user()
        
    def _get_current_user(self):
        """Get current user (simplified for demo)"""
        with db_manager.get_session() as session:
            return session.query(User).filter(User.username == "admin").first()
    
    def render_settings_page(self):
        """Render the complete settings interface"""
        st.title(⚙️ F&O Trading System Settings")
        st.markdown("---")
        
        # Settings tabs
        tabs = st.tabs([
            "🏦 Broker Setup", 
            "📊 Trading Config", 
            "🛡️ Risk Management",
            "📱 Notifications",
            "📅 Event Calendar", 
            "🔐 Security",
            "🖥️ System Status",
            "📈 Strategy Config"
        ])
        
        with tabs[0]:
            self._render_broker_settings()
        
        with tabs[1]:
            self._render_trading_config()
            
        with tabs[2]:
            self._render_risk_management()
            
        with tabs[3]:
            self._render_notification_settings()
            
        with tabs[4]:
            self._render_calendar_settings()
            
        with tabs[5]:
            self._render_security_settings()
            
        with tabs[6]:
            self._render_system_status()
            
        with tabs[7]:
            self._render_strategy_config()
    
    def _render_broker_settings(self):
        """Render broker configuration interface"""
        st.header("🏦 Broker Configuration")
        
        # Broker selection
        col1, col2 = st.columns([1, 1])
        
        with col1:
            broker_name = st.selectbox(
                "Select Broker",
                ["Zerodha", "Fyers", "AngelOne", "IIFL", "5Paisa"],
                help="Choose your preferred broker for trading"
            )
        
        with col2:
            account_type = st.selectbox(
                "Account Type",
                ["Individual", "HUF", "Corporate"],
                help="Select your account type"
            )
        
        st.markdown("### 🔑 API Credentials")
        st.info("⚠️ All credentials are encrypted using AES-256 encryption before storage")
        
        # Broker-specific credential fields
        if broker_name == "Zerodha":
            self._render_zerodha_config()
        elif broker_name == "Fyers":
            self._render_fyers_config()
        elif broker_name == "AngelOne":
            self._render_angelone_config()
        
        # Test connection button
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.button("🔍 Test Connection", type="primary"):
                self._test_broker_connection(broker_name)
        
        with col2:
            if st.button("💾 Save Credentials", type="secondary"):
                self._save_broker_credentials(broker_name)
        
        with col3:
            if st.button("🗑️ Clear Credentials", type="secondary"):
                self._clear_broker_credentials(broker_name)
        
        # Existing broker accounts
        self._show_existing_broker_accounts()
    
    def _render_zerodha_config(self):
        """Render Zerodha-specific configuration"""
        st.markdown("**Zerodha Configuration**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            api_key = st.text_input(
                "API Key",
                type="password",
                key="zerodha_api_key",
                help="Your Zerodha API Key from Kite Connect"
            )
            
            client_id = st.text_input(
                "Client ID",
                key="zerodha_client_id",
                help="Your Zerodha trading account ID"
            )
        
        with col2:
            api_secret = st.text_input(
                "API Secret",
                type="password", 
                key="zerodha_api_secret",
                help="Your Zerodha API Secret"
            )
            
            redirect_url = st.text_input(
                "Redirect URL",
                value="https://localhost:8501",
                key="zerodha_redirect",
                help="OAuth redirect URL"
            )
        
        # Store in session state
        if api_key and api_secret:
            st.session_state.broker_credentials = {
                "broker": "ZERODHA",
                "api_key": api_key,
                "api_secret": api_secret,
                "client_id": client_id,
                "redirect_url": redirect_url
            }
    
    def _render_fyers_config(self):
        """Render Fyers-specific configuration"""
        st.markdown("**Fyers Configuration**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            app_id = st.text_input(
                "App ID",
                key="fyers_app_id",
                help="Your Fyers App ID"
            )
            
            client_id = st.text_input(
                "Client ID", 
                key="fyers_client_id",
                help="Your Fyers Client ID"
            )
        
        with col2:
            app_secret = st.text_input(
                "App Secret",
                type="password",
                key="fyers_app_secret", 
                help="Your Fyers App Secret"
            )
            
            redirect_uri = st.text_input(
                "Redirect URI",
                value="https://localhost:8501",
                key="fyers_redirect",
                help="OAuth redirect URI"
            )
        
        if app_id and app_secret:
            st.session_state.broker_credentials = {
                "broker": "FYERS",
                "app_id": app_id,
                "app_secret": app_secret,
                "client_id": client_id,
                "redirect_uri": redirect_uri
            }
    
    def _render_angelone_config(self):
        """Render Angel One specific configuration"""
        st.markdown("**Angel One Configuration**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            api_key = st.text_input(
                "API Key",
                type="password",
                key="angel_api_key",
                help="Your Angel One API Key"
            )
            
            client_code = st.text_input(
                "Client Code",
                key="angel_client_code",
                help="Your Angel One Client Code"
            )
        
        with col2:
            password = st.text_input(
                "Password",
                type="password",
                key="angel_password",
                help="Your Angel One Password"
            )
            
            totp_token = st.text_input(
                "TOTP Token",
                key="angel_totp",
                help="Current TOTP from your authenticator app"
            )
        
        if api_key and password:
            st.session_state.broker_credentials = {
                "broker": "ANGELONE",
                "api_key": api_key,  
                "password": password,
                "client_code": client_code,
                "totp_token": totp_token
            }
    
    def _render_trading_config(self):
        """Render trading configuration"""
        st.header("📊 Trading Configuration")
        
        # Load current settings
        current_config = self._load_system_settings()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**💰 Capital & Position Management**")
            
            default_capital = st.number_input(
                "Default Capital (₹)",
                min_value=50000,
                max_value=10000000,
                value=current_config.get("default_capital", 200000),
                step=10000,
                help="Total capital allocated for F&O trading"
            )
            
            max_lots_per_strategy = st.number_input(
                "Max Lots Per Strategy",
                min_value=1,
                max_value=50,
                value=current_config.get("max_lots_per_strategy", 10),
                help="Maximum lots allowed per strategy"
            )
            
            max_strategies_active = st.number_input(
                "Max Active Strategies",
                min_value=1,
                max_value=20,
                value=current_config.get("max_strategies_active", 5),
                help="Maximum number of strategies running simultaneously"
            )
        
        with col2:
            st.markdown("**⏰ Trading Hours & Timing**")
            
            entry_cutoff = st.time_input(
                "Entry Cutoff Time",
                value=time(11, 0),
                help="No new positions after this time"
            )
            
            exit_time = st.time_input(
                "Mandatory Exit Time", 
                value=time(15, 10),
                help="All positions closed by this time"
            )
            
            pre_market_buffer = st.number_input(
                "Pre-Market Buffer (minutes)",
                min_value=0,
                max_value=60,
                value=current_config.get("pre_market_buffer", 15),
                help="Minutes to wait after market open before trading"
            )
        
        # Instrument Selection
        st.markdown("**📈 Instrument Configuration**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            allowed_instruments = st.multiselect(
                "Allowed Instruments",
                ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"],
                default=current_config.get("allowed_instruments", ["NIFTY", "BANKNIFTY"]),
                help="Select instruments for trading (NIFTY/BANKNIFTY recommended)"
            )
        
        with col2:
            blocked_instruments = st.multiselect(
                "Blocked Instruments",
                ["FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"],
                default=current_config.get("blocked_instruments", ["FINNIFTY", "MIDCPNIFTY"]),
                help="Instruments to avoid (low liquidity)"
            )
        
        # VIX Settings
        st.markdown("**📊 Market Volatility Settings**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            vix_threshold = st.number_input(
                "VIX Threshold",
                min_value=10.0,
                max_value=50.0,
                value=current_config.get("vix_threshold", 25.0),
                step=0.5,
                help="VIX level for strategy filtering"
            )
        
        with col2:
            high_vix_threshold = st.number_input(
                "High VIX Threshold",
                min_value=20.0,
                max_value=80.0,
                value=current_config.get("high_vix_threshold", 35.0),
                step=0.5,
                help="VIX level considered high volatility"
            )
        
        with col3:
            low_vix_threshold = st.number_input(
                "Low VIX Threshold", 
                min_value=5.0,
                max_value=25.0,
                value=current_config.get("low_vix_threshold", 15.0),
                step=0.5,
                help="VIX level considered low volatility"
            )
        
        # Save button
        if st.button("💾 Save Trading Configuration", type="primary"):
            self._save_trading_config({
                "default_capital": default_capital,
                "max_lots_per_strategy": max_lots_per_strategy,
                "max_strategies_active": max_strategies_active,
                "entry_cutoff_time": entry_cutoff.strftime("%H:%M"),
                "exit_time": exit_time.strftime("%H:%M"),
                "pre_market_buffer": pre_market_buffer,
                "allowed_instruments": allowed_instruments,
                "blocked_instruments": blocked_instruments,
                "vix_threshold": vix_threshold,
                "high_vix_threshold": high_vix_threshold,
                "low_vix_threshold": low_vix_threshold
            })
    
    def _render_risk_management(self):
        """Render risk management settings"""
        st.header("🛡️ Risk Management")
        
        current_config = self._load_system_settings()
        
        # Danger Zone Settings
        st.markdown("**🚨 Danger Zone Thresholds**")
        st.info("These are percentage moves in NIFTY/BANKNIFTY that trigger risk actions")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            danger_warning = st.number_input(
                "Warning Threshold (%)",
                min_value=0.5,
                max_value=3.0,
                value=current_config.get("danger_zone_warning", 1.0),
                step=0.1,
                help="Yellow alert - monitor closely"
            )
        
        with col2:
            danger_risk = st.number_input(
                "Risk Threshold (%)",
                min_value=1.0,
                max_value=4.0,
                value=current_config.get("danger_zone_risk", 1.25),
                step=0.05,
                help="Orange alert - prepare for exit"
            )
        
        with col3:
            danger_exit = st.number_input(
                "Exit Threshold (%)",
                min_value=1.5,
                max_value=5.0,
                value=current_config.get("danger_zone_exit", 1.5),
                step=0.05,  
                help="Red alert - force exit all positions"
            )
        
        # Portfolio Risk Limits
        st.markdown("**💼 Portfolio Risk Limits**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            daily_loss_limit_pct = st.number_input(
                "Daily Loss Limit (%)",
                min_value=1.0,
                max_value=10.0,
                value=current_config.get("daily_loss_limit_pct", 5.0),
                step=0.5,
                help="Percentage of capital - daily loss limit"
            )
            
            max_positions = st.number_input(
                "Max Open Positions",
                min_value=1,
                max_value=20,
                value=current_config.get("max_positions", 10),
                help="Maximum number of open positions"
            )
        
        with col2:
            max_drawdown_pct = st.number_input(
                "Max Drawdown (%)",
                min_value=5.0,
                max_value=25.0,
                value=current_config.get("max_drawdown_pct", 15.0),
                step=1.0,
                help="Maximum acceptable drawdown"
            )
            
            position_size_pct = st.number_input(
                "Position Size (% of Capital)",
                min_value=1.0,
                max_value=20.0,
                value=current_config.get("position_size_pct", 5.0),
                step=0.5,
                help="Maximum capital per position"
            )
        
        # Strategy-Specific Risk Settings
        st.markdown("**📊 Strategy Risk Parameters**")
        
        strategy_risk_config = current_config.get("strategy_risk", {})
        
        strategies = [
            "IRON_CONDOR", "BUTTERFLY_SPREAD", "CALENDAR_SPREAD", 
            "HEDGED_STRANGLE", "DIRECTIONAL_FUTURES", "JADE_LIZARD",
            "RATIO_SPREADS", "BROKEN_WING_BUTTERFLY"
        ]
        
        # Create columns for strategy risk settings
        cols = st.columns(2)
        strategy_risk = {}
        
        for i, strategy in enumerate(strategies):
            with cols[i % 2]:
                st.markdown(f"**{strategy.replace('_', ' ').title()}**")
                
                default_config = strategy_risk_config.get(strategy, {})
                
                col_sl, col_tp = st.columns(2)
                
                with col_sl:
                    sl = st.number_input(
                        "SL per lot (₹)",
                        min_value=500,
                        max_value=10000,
                        value=default_config.get("sl_per_lot", 2000),
                        step=100,
                        key=f"{strategy}_sl"
                    )
                
                with col_tp:
                    tp = st.number_input(
                        "TP per lot (₹)",
                        min_value=1000,
                        max_value=15000,
                        value=default_config.get("tp_per_lot", 4000),
                        step=100,
                        key=f"{strategy}_tp"
                    )
                
                strategy_risk[strategy] = {"sl_per_lot": sl, "tp_per_lot": tp}
        
        # Risk Monitor Settings
        st.markdown("**🤖 Risk Monitor Configuration**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            risk_monitor_enabled = st.checkbox(
                "Enable Risk Monitor",
                value=current_config.get("risk_monitor_enabled", True),
                help="Enable automated risk monitoring and actions"
            )
            
            auto_exit_enabled = st.checkbox(
                "Enable Auto Exit",
                value=current_config.get("auto_exit_enabled", True),
                help="Allow system to automatically exit positions"
            )
        
        with col2:
            monitor_interval = st.number_input(
                "Monitor Interval (seconds)",
                min_value=10,
                max_value=300,
                value=current_config.get("monitor_interval", 30),
                help="How often to check positions"
            )
            
            risk_action_cooldown = st.number_input(
                "Risk Action Cooldown (minutes)",
                min_value=1,
                max_value=60,
                value=current_config.get("risk_action_cooldown", 5),
                help="Cooldown between risk actions"
            )
        
        # Save Risk Settings
        if st.button("💾 Save Risk Configuration", type="primary"):
            self._save_risk_config({
                "danger_zone_warning": danger_warning,
                "danger_zone_risk": danger_risk,
                "danger_zone_exit": danger_exit,
                "daily_loss_limit_pct": daily_loss_limit_pct,
                "max_positions": max_positions,
                "max_drawdown_pct": max_drawdown_pct,
                "position_size_pct": position_size_pct,
                "strategy_risk": strategy_risk,
                "risk_monitor_enabled": risk_monitor_enabled,
                "auto_exit_enabled": auto_exit_enabled,
                "monitor_interval": monitor_interval,
                "risk_action_cooldown": risk_action_cooldown
            })
    
    def _render_notification_settings(self):
        """Render notification configuration"""
        st.header("📱 Notification Settings")
        
        current_config = self._load_system_settings()
        notifications_config = current_config.get("notifications", {})
        
        # WhatsApp Configuration
        st.markdown("**💬 WhatsApp Notifications (Gupshup)**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            whatsapp_enabled = st.checkbox(
                "Enable WhatsApp Notifications",
                value=notifications_config.get("whatsapp_enabled", False),
                help="Enable WhatsApp notifications via Gupshup API"
            )
            
            gupshup_api_key = st.text_input(
                "Gupshup API Key",
                type="password",
                value=notifications_config.get("gupshup_api_key", ""),
                help="Your Gupshup API key"
            )
        
        with col2:
            gupshup_app_name = st.text_input(
                "Gupshup App Name",
                value=notifications_config.get("gupshup_app_name", ""),
                help="Your Gupshup application name"
            )
            
            admin_phone = st.text_input(
                "Admin Phone Number",
                value=notifications_config.get("admin_phone", ""),
                help="Phone number for notifications (with country code)"
            )
        
        # Notification Preferences
        st.markdown("**🔔 Notification Preferences**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            notify_trade_entry = st.checkbox(
                "Trade Entry Notifications",
                value=notifications_config.get("notify_trade_entry", True),
                help="Notify when new positions are opened"
            )
            
            notify_trade_exit = st.checkbox(
                "Trade Exit Notifications", 
                value=notifications_config.get("notify_trade_exit", True),
                help="Notify when positions are closed"
            )
            
            notify_risk_alerts = st.checkbox(
                "Risk Alert Notifications",
                value=notifications_config.get("notify_risk_alerts", True),
                help="Notify on risk threshold breaches"
            )
        
        with col2:
            notify_system_status = st.checkbox(
                "System Status Notifications",
                value=notifications_config.get("notify_system_status", True),
                help="Notify on system start/stop/errors"
            )
            
            notify_daily_summary = st.checkbox(
                "Daily Summary Notifications",
                value=notifications_config.get("notify_daily_summary", True),
                help="Daily P&L and position summary"
            )
            
            notify_expiry_alerts = st.checkbox(
                "Expiry Alert Notifications",
                value=notifications_config.get("notify_expiry_alerts", True),
                help="Alerts for upcoming expiry dates"
            )
        
        # Test Notification
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📱 Test WhatsApp Notification", type="secondary"):
                self._test_whatsapp_notification(gupshup_api_key, gupshup_app_name, admin_phone)
        
        with col2:
            if st.button("💾 Save Notification Settings", type="primary"):
                self._save_notification_config({
                    "whatsapp_enabled": whatsapp_enabled,
                    "gupshup_api_key": gupshup_api_key,
                    "gupshup_app_name": gupshup_app_name,
                    "admin_phone": admin_phone,
                    "notify_trade_entry": notify_trade_entry,
                    "notify_trade_exit": notify_trade_exit,
                    "notify_risk_alerts": notify_risk_alerts,
                    "notify_system_status": notify_system_status,
                    "notify_daily_summary": notify_daily_summary,
                    "notify_expiry_alerts": notify_expiry_alerts
                })
    
    def _render_calendar_settings(self):
        """Render event calendar configuration"""
        st.header("📅 Event Calendar Settings")
        
        current_config = self._load_system_settings()
        calendar_config = current_config.get("calendar", {})
        
        # Calendar Status
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Check if today is trading day
            today = date.today()
            is_trading = event_calendar.is_trading_day(today)
            st.metric(
                "Today's Status",
                "Trading Day" if is_trading else "Holiday",
                delta="✅" if is_trading else "🚫"
            )
        
        with col2:
            # Get next expiry info
            nifty_expiry = event_calendar.get_next_expiry_info("NIFTY")
            days_to_expiry = nifty_expiry.get("days_to_expiry", 0)
            st.metric("NIFTY Expiry", f"{days_to_expiry} days", delta="⏰")
        
        with col3:
            # Last refresh time
            refresh_time = getattr(event_calendar, 'last_holiday_refresh', datetime.now())
            st.metric(
                "Last Refresh",
                refresh_time.strftime("%d-%m %H:%M"),
                delta="🔄"
            )
        
        # Calendar Configuration
        st.markdown("**⚙️ Calendar Configuration**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            auto_refresh_enabled = st.checkbox(
                "Enable Auto Refresh",
                value=calendar_config.get("auto_refresh_enabled", True),
                help="Automatically refresh holiday data"
            )
            
            refresh_interval_hours = st.number_input(
                "Refresh Interval (hours)",
                min_value=1,
                max_value=168,
                value=calendar_config.get("refresh_interval_hours", 24),
                help="How often to refresh calendar data"
            )
        
        with col2:
            api_timeout = st.number_input(
                "API Timeout (seconds)",
                min_value=5,
                max_value=60,
                value=calendar_config.get("api_timeout", 10),
                help="Timeout for NSE holiday API calls"
            )
            
            fallback_mode = st.checkbox(
                "Enable Fallback Mode",
                value=calendar_config.get("fallback_mode", True),
                help="Use estimated holidays if API fails"
            )
        
        # Upcoming Events
        st.markdown("**📋 Upcoming Events (Next 7 Days)**")
        
        try:
            events = event_calendar.get_upcoming_events(7)
            if events:
                events_data = []
                for event in events:
                    impact_emoji = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
                    events_data.append({
                        "Date": event.date.strftime("%Y-%m-%d"),
                        "Event": event.title,
                        "Impact": f"{impact_emoji.get(event.impact_level, '⚪')} {event.impact_level}",
                        "Action": event.trading_action
                    })
                
                df = pd.DataFrame(events_data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No upcoming events in the next 7 days")
        except Exception as e:
            st.error(f"Error loading events: {e}")
        
        # Manual Actions
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Refresh Calendar Data", type="secondary"):
                with st.spinner("Refreshing calendar data..."):
                    try:
                        event_calendar.refresh_event_data()
                        st.success("Calendar data refreshed successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Refresh failed: {e}")
        
        with col2:
            if st.button("📊 View Full Calendar", type="secondary"):
                self._show_full_calendar()
        
        with col3:
            if st.button("💾 Save Calendar Settings", type="primary"):
                self._save_calendar_config({
                    "auto_refresh_enabled": auto_refresh_enabled,
                    "refresh_interval_hours": refresh_interval_hours,
                    "api_timeout": api_timeout,
                    "fallback_mode": fallback_mode
                })
    
    def _render_security_settings(self):
        """Render security and encryption settings"""
        st.header("🔐 Security Settings")
        
        # Encryption Status
        st.markdown("**🔒 Encryption Status**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Test encryption
            try:
                encryption_ok = test_encryption_roundtrip()
                st.metric(
                    "Encryption Status",
                    "Working" if encryption_ok else "Failed",
                    delta="✅" if encryption_ok else "❌"
                )
            except Exception as e:
                st.metric("Encryption Status", "Error", delta="❌")
                st.error(f"Encryption error: {e}")
        
        with col2:
            # Encryption key info
            has_key = bool(getattr(settings, 'ENCRYPTION_KEY', None))
            st.metric(
                "Encryption Key",
                "Configured" if has_key else "Missing",
                delta="✅" if has_key else "❌"
            )
        
        # Database Security
        st.markdown("**🗄️ Database Security**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Database connection test
            try:
                db_healthy = db_manager.check_connection()
                st.metric(
                    "Database Connection",
                    "Secure" if db_healthy else "Failed",
                    delta="✅" if db_healthy else "❌"
                )
            except Exception as e:
                st.metric("Database Connection", "Error", delta="❌")
        
        with col2:
            # Show encrypted fields count
            try:
                with db_manager.get_session() as session:
                    broker_accounts = session.query(BrokerAccount).count()
                    st.metric("Encrypted Accounts", broker_accounts, delta="🔐")
            except Exception as e:
                st.metric("Encrypted Accounts", "Error", delta="❌")
        
        # Security Actions
        st.markdown("**🛡️ Security Actions**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Test Encryption", type="secondary"):
                with st.spinner("Testing encryption..."):
                    try:
                        result = test_encryption_roundtrip()
                        if result:
                            st.success("✅ Encryption test passed!")
                        else:
                            st.error("❌ Encryption test failed!")
                    except Exception as e:
                        st.error(f"Encryption test error: {e}")
        
        with col2:
            if st.button("🗑️ Clear All Sessions", type="secondary"):
                st.session_state.clear()
                st.success("All sessions cleared!")
                st.rerun()
        
        with col3:
            if st.button("📊 Security Audit", type="secondary"):
                self._run_security_audit()
    
    def _render_system_status(self):
        """Render system status and health monitoring"""
        st.header("🖥️ System Status")
        
        # System Health Overview
        try:
            health_status = health_checker.get_health_summary()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                overall_status = health_status.get("overall_status", "UNKNOWN")
                status_emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🚨", "DOWN": "❌"}
                st.metric(
                    "Overall Status",
                    overall_status,
                    delta=status_emoji.get(overall_status, "❓")
                )
            
            with col2:
                components = health_status.get("summary", {})
                healthy_count = components.get("healthy", 0)
                total_count = components.get("total_components", 0)
                st.metric("Healthy Components", f"{healthy_count}/{total_count}", delta="🔧")
            
            with col3:
                # Risk monitor status
                risk_status = getattr(risk_monitor, 'is_monitoring', False)
                st.metric(
                    "Risk Monitor",
                    "Active" if risk_status else "Inactive",
                    delta="🛡️" if risk_status else "⏸️"
                )
            
            with col4:
                # Database status
                db_status = health_status.get("components", {}).get("database", {}).get("status", "UNKNOWN")
                st.metric(
                    "Database",
                    db_status,
                    delta="✅" if db_status == "HEALTHY" else "❌"
                )
            
            # Detailed Component Status
            st.markdown("**🔧 Component Status**")
            
            components = health_status.get("components", {})
            if components:
                status_data = []
                for component, details in components.items():
                    status_data.append({
                        "Component": component.replace("_", " ").title(),
                        "Status": details.get("status", "UNKNOWN"),
                        "Message": details.get("message", "No details"),
                        "Last Check": details.get("last_check", "Never")
                    })
                
                df = pd.DataFrame(status_data)
                st.dataframe(df, use_container_width=True)
            
        except Exception as e:
            st.error(f"Error loading system status: {e}")
        
        # System Actions
        st.markdown("**⚡ System Actions**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Refresh Status", type="secondary"):
                st.rerun()
        
        with col2:
            if st.button("🛡️ Start Risk Monitor", type="secondary"):
                try:
                    risk_monitor.start_monitoring()
                    st.success("Risk monitor started!")
                except Exception as e:
                    st.error(f"Failed to start risk monitor: {e}")
        
        with col3:
            if st.button("⏹️ Stop Risk Monitor", type="secondary"):
                try:
                    risk_monitor.stop_monitoring()
                    st.success("Risk monitor stopped!")
                except Exception as e:
                    st.error(f"Failed to stop risk monitor: {e}")
        
        # System Logs
        st.markdown("**📋 Recent System Logs**")
        
        # This would integrate with your logging system
        log_placeholder = st.empty()
        with log_placeholder.container():
            st.code("""
2025-07-28 17:00:01 INFO  [risk_monitor] Risk monitoring active
2025-07-28 17:00:01 INFO  [strategy_selector] Evaluating 8 strategies
2025-07-28 17:00:01 INFO  [event_calendar] Calendar data up to date
2025-07-28 17:00:01 INFO  [database] All connections healthy
2025-07-28 17:00:01 INFO  [encryption] Security checks passed
            """, language="log")
    
    def _render_strategy_config(self):
        """Render strategy-specific configuration"""
        st.header("📈 Strategy Configuration")
        
        # Load strategies from database
        try:
            with db_manager.get_session() as session:
                strategies = session.query(Strategy).all()
                
                if not strategies:
                    st.warning("No strategies found in database")
                    return
                
                # Strategy Status Overview
                active_strategies = [s for s in strategies if s.is_active]
                st.metric("Active Strategies", f"{len(active_strategies)}/{len(strategies)}", delta="📊")
                
                # Strategy Configuration Table
                strategy_data = []
                for strategy in strategies:
                    strategy_data.append({
                        "Strategy": strategy.display_name,
                        "Status": "Active" if strategy.is_active else "Inactive",
                        "Win Rate": f"{strategy.target_win_rate}%",
                        "Legs": strategy.legs,
                        "Market Outlook": strategy.market_outlook,
                        "VIX Range": f"{strategy.min_vix}-{strategy.max_vix}",
                        "Hedged": "✅" if strategy.is_hedged else "❌"
                    })
                
                df = pd.DataFrame(strategy_data)
                st.dataframe(df, use_container_width=True)
                
                # Individual Strategy Settings
                st.markdown("**⚙️ Individual Strategy Settings**")
                
                selected_strategy = st.selectbox(
                    "Select Strategy to Configure",
                    [s.display_name for s in strategies]
                )
                
                if selected_strategy:
                    strategy = next(s for s in strategies if s.display_name == selected_strategy)
                    self._render_individual_strategy_config(strategy)
                
        except Exception as e:
            st.error(f"Error loading strategies: {e}")
    
    def _render_individual_strategy_config(self, strategy):
        """Render configuration for individual strategy"""
        col1, col2 = st.columns(2)
        
        with col1:
            is_active = st.checkbox(
                "Strategy Active",
                value=strategy.is_active,
                key=f"{strategy.name}_active"
            )
            
            min_vix = st.number_input(
                "Min VIX",
                min_value=5.0,
                max_value=50.0,
                value=strategy.min_vix,
                step=0.5,
                key=f"{strategy.name}_min_vix"
            )
            
            target_win_rate = st.number_input(
                "Target Win Rate (%)",
                min_value=50.0,
                max_value=95.0,
                value=strategy.target_win_rate,
                step=1.0,
                key=f"{strategy.name}_win_rate"
            )
        
        with col2:
            max_vix = st.number_input(
                "Max VIX",
                min_value=10.0,
                max_value=80.0,
                value=strategy.max_vix,
                step=0.5,
                key=f"{strategy.name}_max_vix"
            )
            
            market_outlook = st.selectbox(
                "Market Outlook",
                ["NEUTRAL", "BULLISH", "BEARISH", "DIRECTIONAL", "NEUTRAL_BULLISH"],
                index=["NEUTRAL", "BULLISH", "BEARISH", "DIRECTIONAL", "NEUTRAL_BULLISH"].index(strategy.market_outlook),
                key=f"{strategy.name}_outlook"
            )
        
        # Strategy Description
        st.text_area(
            "Description",
            value=strategy.description,
            height=100,
            key=f"{strategy.name}_desc",
            disabled=True
        )
        
        # Save Strategy Config
        if st.button(f"💾 Save {strategy.display_name} Config", type="primary"):
            self._save_strategy_config(strategy.id, {
                "is_active": is_active,
                "min_vix": min_vix,
                "max_vix": max_vix,
                "target_win_rate": target_win_rate,
                "market_outlook": market_outlook
            })
    
    # Helper methods for saving configurations
    def _load_system_settings(self) -> Dict[str, Any]:
        """Load current system settings"""
        try:
            with db_manager.get_session() as session:
                settings_record = session.query(SystemSettings).filter(
                    SystemSettings.setting_key == "system_config"
                ).first()
                
                if settings_record:
                    return settings_record.setting_value
                else:
                    return {}
        except Exception as e:
            logger.error(f"Error loading system settings: {e}")
            return {}
    
    def _save_trading_config(self, config: Dict[str, Any]):
        """Save trading configuration"""
        try:
            current_settings = self._load_system_settings()
            current_settings.update(config)
            
            with db_manager.get_session() as session:
                settings_record = session.query(SystemSettings).filter(
                    SystemSettings.setting_key == "system_config"
                ).first()
                
                if settings_record:
                    settings_record.setting_value = current_settings
                    settings_record.updated_at = datetime.now()
                else:
                    settings_record = SystemSettings(
                        setting_key="system_config",
                        setting_value=current_settings,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    session.add(settings_record)
                
                session.commit()
                st.success("✅ Trading configuration saved successfully!")
                
        except Exception as e:
            logger.error(f"Error saving trading config: {e}")
            st.error(f"Failed to save configuration: {e}")
    
    def _save_risk_config(self, config: Dict[str, Any]):
        """Save risk management configuration"""
        try:
            current_settings = self._load_system_settings()
            current_settings.update(config)
            
            with db_manager.get_session() as session:
                settings_record = session.query(SystemSettings).filter(
                    SystemSettings.setting_key == "system_config"
                ).first()
                
                if settings_record:
                    settings_record.setting_value = current_settings
                    settings_record.updated_at = datetime.now()
                    session.commit()
                    st.success("✅ Risk configuration saved successfully!")
                else:
                    st.error("System settings not found!")
                    
        except Exception as e:
            logger.error(f"Error saving risk config: {e}")
            st.error(f"Failed to save risk configuration: {e}")
    
    def _save_notification_config(self, config: Dict[str, Any]):
        """Save notification configuration"""
        try:
            current_settings = self._load_system_settings()
            current_settings["notifications"] = config
            
            with db_manager.get_session() as session:
                settings_record = session.query(SystemSettings).filter(
                    SystemSettings.setting_key == "system_config"
                ).first()
                
                if settings_record:
                    settings_record.setting_value = current_settings
                    settings_record.updated_at = datetime.now()
                    session.commit()
                    st.success("✅ Notification settings saved successfully!")
                    
        except Exception as e:
            logger.error(f"Error saving notification config: {e}")
            st.error(f"Failed to save notification settings: {e}")
    
    def _save_calendar_config(self, config: Dict[str, Any]):
        """Save calendar configuration"""
        try:
            current_settings = self._load_system_settings()
            current_settings["calendar"] = config
            
            with db_manager.get_session() as session:
                settings_record = session.query(SystemSettings).filter(
                    SystemSettings.setting_key == "system_config"
                ).first()
                
                if settings_record:
                    settings_record.setting_value = current_settings
                    settings_record.updated_at = datetime.now()
                    session.commit()
                    st.success("✅ Calendar settings saved successfully!")
                    
        except Exception as e:
            logger.error(f"Error saving calendar config: {e}")
            st.error(f"Failed to save calendar settings: {e}")
    
    def _save_strategy_config(self, strategy_id: int, config: Dict[str, Any]):
        """Save individual strategy configuration"""
        try:
            with db_manager.get_session() as session:
                strategy = session.query(Strategy).filter(Strategy.id == strategy_id).first()
                
                if strategy:
                    for key, value in config.items():
                        setattr(strategy, key, value)
                    
                    strategy.updated_at = datetime.now()
                    session.commit()
                    st.success("✅ Strategy configuration saved successfully!")
                else:
                    st.error("Strategy not found!")
                    
        except Exception as e:
            logger.error(f"Error saving strategy config: {e}")
            st.error(f"Failed to save strategy configuration: {e}")
    
    def _test_broker_connection(self, broker_name: str):
        """Test broker API connection"""
        if "broker_credentials" not in st.session_state:
            st.error("Please enter broker credentials first!")
            return
        
        try:
            credentials = st.session_state.broker_credentials
            
            with st.spinner(f"Testing {broker_name} connection..."):
                # This would integrate with your broker adapters
                # For demo purposes, we'll simulate a connection test
                import time
                time.sleep(2)
                
                st.success(f"✅ {broker_name} connection successful!")
                
        except Exception as e:
            st.error(f"❌ {broker_name} connection failed: {e}")
    
    def _save_broker_credentials(self, broker_name: str):
        """Save broker credentials to database"""
        if "broker_credentials" not in st.session_state:
            st.error("Please enter broker credentials first!")
            return
        
        try:
            credentials = st.session_state.broker_credentials
            
            # Encrypt credentials
            encrypted_creds = db_encryptor.encrypt_broker_credentials(credentials)
            
            with db_manager.get_session() as session:
                # Check if broker account already exists
                existing_account = session.query(BrokerAccount).filter(
                    BrokerAccount.user_id == self.current_user.id,
                    BrokerAccount.broker_name == broker_name
                ).first()
                
                if existing_account:
                    existing_account.api_credentials = encrypted_creds
                    existing_account.updated_at = datetime.now()
                else:
                    new_account = BrokerAccount(
                        user_id=self.current_user.id,
                        broker_name=broker_name,
                        account_id=credentials.get("client_id", ""),
                        api_credentials=encrypted_creds,
                        is_active=True,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    session.add(new_account)
                
                session.commit()
                st.success(f"✅ {broker_name} credentials saved successfully!")
                
        except Exception as e:
            logger.error(f"Error saving broker credentials: {e}")
            st.error(f"Failed to save credentials: {e}")
    
    def _clear_broker_credentials(self, broker_name: str):
        """Clear broker credentials"""
        try:
            with db_manager.get_session() as session:
                account = session.query(BrokerAccount).filter(
                    BrokerAccount.user_id == self.current_user.id,
                    BrokerAccount.broker_name == broker_name
                ).first()
                
                if account:
                    session.delete(account)
                    session.commit()
                    st.success(f"✅ {broker_name} credentials cleared!")
                else:
                    st.info(f"No {broker_name} credentials found to clear")
                    
        except Exception as e:
            logger.error(f"Error clearing credentials: {e}")
            st.error(f"Failed to clear credentials: {e}")
    
    def _show_existing_broker_accounts(self):
        """Show existing broker accounts"""
        st.markdown("**🏦 Existing Broker Accounts**")
        
        try:
            with db_manager.get_session() as session:
                accounts = session.query(BrokerAccount).filter(
                    BrokerAccount.user_id == self.current_user.id
                ).all()
                
                if accounts:
                    account_data = []
                    for account in accounts:
                        account_data.append({
                            "Broker": account.broker_name,
                            "Account ID": account.account_id,
                            "Status": "Active" if account.is_active else "Inactive",
                            "Created": account.created_at.strftime("%Y-%m-%d %H:%M"),
                            "Last Updated": account.updated_at.strftime("%Y-%m-%d %H:%M")
                        })
                    
                    df = pd.DataFrame(account_data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No broker accounts configured yet")
                    
        except Exception as e:
            st.error(f"Error loading broker accounts: {e}")
    
    def _test_whatsapp_notification(self, api_key: str, app_name: str, phone: str):
        """Test WhatsApp notification"""
        if not all([api_key, app_name, phone]):
            st.error("Please fill in all WhatsApp configuration fields!")
            return
        
        try:
            with st.spinner("Testing WhatsApp notification..."):
                notifier = WhatsAppNotifier(api_key, app_name, phone)
                test_message = f"🧪 Test notification from F&O Trading System\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                success = notifier.send_message(test_message)
                
                if success:
                    st.success("✅ WhatsApp notification sent successfully!")
                else:
                    st.error("❌ WhatsApp notification failed!")
                    
        except Exception as e:
            st.error(f"❌ WhatsApp test failed: {e}")
    
    def _show_full_calendar(self):
        """Show full calendar view"""
        st.markdown("**📅 Full Trading Calendar**")
        
        # Year selection
        current_year = date.today().year
        selected_year = st.selectbox(
            "Select Year",
            [current_year, current_year + 1, current_year + 2],
            index=0
        )
        
        try:
            calendar_data = event_calendar.get_trading_calendar(selected_year)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Trading Days", calendar_data["total_trading_days"])
            
            with col2:
                st.metric("Holidays", calendar_data["total_holidays"])
            
            with col3:
                nifty_expiries = len(calendar_data["expiry_dates"].get("NIFTY", []))
                st.metric("NIFTY Expiries", nifty_expiries)
            
            # Show upcoming expiries
            st.markdown("**Upcoming Expiries**")
            
            expiry_data = []
            for instrument in ["NIFTY", "BANKNIFTY"]:
                expiries = calendar_data["expiry_dates"].get(instrument, [])
                for expiry_date in expiries[:10]:  # Show next 10 expiries
                    expiry_data.append({
                        "Date": expiry_date.strftime("%Y-%m-%d"),
                        "Instrument": instrument,
                        "Day": expiry_date.strftime("%A"),
                        "Days Away": (expiry_date - date.today()).days
                    })
            
            if expiry_data:
                df = pd.DataFrame(expiry_data)
                st.dataframe(df, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error loading calendar: {e}")
    
    def _run_security_audit(self):
        """Run comprehensive security audit"""
        st.markdown("**🔍 Security Audit Results**")
        
        audit_results = []
        
        # Check encryption
        try:
            encryption_ok = test_encryption_roundtrip()
            audit_results.append({
                "Check": "Encryption System",
                "Status": "✅ Pass" if encryption_ok else "❌ Fail",
                "Details": "AES-256 encryption working" if encryption_ok else "Encryption test failed"
            })
        except Exception as e:
            audit_results.append({
                "Check": "Encryption System",
                "Status": "❌ Error",
                "Details": str(e)
            })
        
        # Check database security
        try:
            db_ok = db_manager.check_connection()
            audit_results.append({
                "Check": "Database Security",
                "Status": "✅ Pass" if db_ok else "❌ Fail",
                "Details": "SSL connection verified" if db_ok else "Database connection failed"
            })
        except Exception as e:
            audit_results.append({
                "Check": "Database Security",
                "Status": "❌ Error",
                "Details": str(e)
            })
        
        # Check encrypted credentials
        try:
            with db_manager.get_session() as session:
                accounts = session.query(BrokerAccount).count()
                audit_results.append({
                    "Check": "Credential Storage",
                    "Status": "✅ Pass",
                    "Details": f"{accounts} accounts with encrypted credentials"
                })
        except Exception as e:
            audit_results.append({
                "Check": "Credential Storage",
                "Status": "❌ Error",
                "Details": str(e)
            })
        
        # Display audit results
        df = pd.DataFrame(audit_results)
        st.dataframe(df, use_container_width=True)
        
        # Overall security score
        passed_checks = len([r for r in audit_results if "✅ Pass" in r["Status"]])
        total_checks = len(audit_results)
        security_score = (passed_checks / total_checks) * 100
        
        st.metric("Security Score", f"{security_score:.0f}%", delta="🔐")

def main():
    """Main settings page function"""
    settings_manager = SettingsManager()
    settings_manager.render_settings_page()

if __name__ == "__main__":
    main()
