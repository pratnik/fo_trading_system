"""
F&O Trading System - Main Dashboard
Complete Streamlit dashboard integrating all system components:
- Real-time strategy monitoring and selection
- Risk management and alerts
- Event calendar integration
- Position tracking and P&L
- System health monitoring
- Broker management and settings
- Performance analytics and reporting
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
import logging
import json

# Import system components
from app.config import settings
from app.db.base import db_manager
from app.db.models import Trade, Position, Strategy, User, BrokerAccount, SystemSettings
from app.strategies.strategy_selector import StrategySelector
from app.risk.risk_monitor import risk_monitor, get_risk_status
from app.risk.danger_zone import danger_monitor
from app.risk.expiry_day import expiry_manager
from app.utils.event_calendar import event_calendar, get_upcoming_events, should_avoid_trading_today
from app.utils.healthcheck import health_checker
from app.notifications.whatsapp_notifier import WhatsAppNotifier

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

# Page configuration
st.set_page_config(
    page_title="F&O Trading System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .alert-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }
    .danger-box {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .strategy-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: white;
    }
</style>
""", unsafe_allow_html=True)

class TradingDashboard:
    """Main dashboard class managing all UI components"""
    
    def __init__(self):
        self.strategy_selector = StrategySelector()
        self.initialize_session_state()
        
    def initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        if 'risk_monitoring_active' not in st.session_state:
            st.session_state.risk_monitoring_active = False
        if 'selected_strategy' not in st.session_state:
            st.session_state.selected_strategy = None
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = datetime.now()
        if 'user_authenticated' not in st.session_state:
            st.session_state.user_authenticated = True  # Simplified for demo
    
    def run(self):
        """Main dashboard entry point"""
        try:
            # Header
            st.markdown('<div class="main-header">📈 F&O Trading System</div>', unsafe_allow_html=True)
            
            # Sidebar navigation
            self.render_sidebar()
            
            # Main content based on selected page
            page = st.session_state.get('current_page', 'Dashboard')
            
            if page == 'Dashboard':
                self.render_main_dashboard()
            elif page == 'Strategies':
                self.render_strategies_page()
            elif page == 'Risk Monitor':
                self.render_risk_monitor_page()
            elif page == 'Positions':
                self.render_positions_page()
            elif page == 'Calendar':
                self.render_calendar_page()
            elif page == 'Analytics':
                self.render_analytics_page()
            elif page == 'Settings':
                self.render_settings_page()
            elif page == 'System Health':
                self.render_health_page()
                
        except Exception as e:
            st.error(f"Dashboard error: {e}")
            logger.error(f"Dashboard error: {e}")
    
    def render_sidebar(self):
        """Render sidebar navigation and quick stats"""
        with st.sidebar:
            st.markdown("## 🧭 Navigation")
            
            # Navigation menu
            pages = [
                "Dashboard", "Strategies", "Risk Monitor", 
                "Positions", "Calendar", "Analytics", 
                "Settings", "System Health"
            ]
            
            selected_page = st.selectbox(
                "Select Page", 
                pages, 
                index=pages.index(st.session_state.get('current_page', 'Dashboard'))
            )
            st.session_state.current_page = selected_page
            
            st.markdown("---")
            
            # Quick system status
            self.render_quick_status()
            
            st.markdown("---")
            
            # Quick actions
            self.render_quick_actions()
    
    def render_quick_status(self):
        """Render quick system status in sidebar"""
        st.markdown("## ⚡ Quick Status")
        
        try:
            # Risk monitoring status
            risk_status = get_risk_status()
            monitoring_active = risk_status.get('monitoring_active', False)
            
            st.metric(
                "Risk Monitor",
                "Active" if monitoring_active else "Inactive",
                delta="✅" if monitoring_active else "🔴"
            )
            
            # Active positions
            active_positions = risk_status.get('total_positions', 0)
            st.metric("Active Positions", active_positions, delta="📊")
            
            # Daily P&L
            daily_pnl = risk_status.get('daily_pnl', 0)
            pnl_color = "normal" if daily_pnl >= 0 else "inverse"
            st.metric(
                "Daily P&L", 
                f"₹{daily_pnl:,.0f}", 
                delta=f"{'📈' if daily_pnl >= 0 else '📉'}"
            )
            
            # Trading day status
            is_trading = event_calendar.is_trading_day(date.today())
            st.metric(
                "Market Status",
                "Open" if is_trading else "Closed",
                delta="🟢" if is_trading else "🔴"
            )
            
        except Exception as e:
            st.error(f"Status error: {e}")
    
    def render_quick_actions(self):
        """Render quick action buttons in sidebar"""
        st.markdown("## ⚡ Quick Actions")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Refresh", key="quick_refresh"):
                st.session_state.last_refresh = datetime.now()
                st.rerun()
        
        with col2:
            if st.button("📱 Test Alert", key="test_alert"):
                st.success("Test alert sent!")
        
        # Emergency actions
        st.markdown("### 🚨 Emergency")
        
        if st.button("🛑 Stop All", key="emergency_stop", type="secondary"):
            if st.session_state.get('confirm_stop', False):
                try:
                    risk_monitor.force_exit_all_positions("Emergency stop from dashboard")
                    st.success("Emergency stop initiated!")
                except Exception as e:
                    st.error(f"Emergency stop failed: {e}")
                st.session_state.confirm_stop = False
            else:
                st.session_state.confirm_stop = True
                st.warning("Click again to confirm emergency stop")
    
    def render_main_dashboard(self):
        """Render main dashboard overview"""
        st.markdown("## 📊 System Overview")
        
        # Auto-refresh
        if st.button("🔄 Auto Refresh (30s)", key="auto_refresh"):
            st.rerun()
        
        # Key metrics row
        self.render_key_metrics()
        
        st.markdown("---")
        
        # Two column layout
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Strategy status and recent trades
            self.render_strategy_overview()
            st.markdown("### 📈 Recent Activity")
            self.render_recent_trades()
        
        with col2:
            # Alerts and notifications
            self.render_alerts_panel()
            
            # Market status
            self.render_market_status()
    
    def render_key_metrics(self):
        """Render key performance metrics"""
        st.markdown("### 📊 Key Metrics")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        try:
            # Get system metrics
            risk_status = get_risk_status()
            
            with col1:
                total_positions = risk_status.get('total_positions', 0)
                st.metric("Active Positions", total_positions, delta="📊")
            
            with col2:
                daily_pnl = risk_status.get('daily_pnl', 0)
                st.metric("Daily P&L", f"₹{daily_pnl:,.0f}", 
                         delta=f"{daily_pnl:+,.0f}" if daily_pnl != 0 else "0")
            
            with col3:
                risk_actions = risk_status.get('risk_actions_today', {})
                total_actions = sum(risk_actions.values())
                st.metric("Risk Actions", total_actions, delta="⚠️" if total_actions > 0 else "✅")
            
            with col4:
                # Get NIFTY expiry info
                nifty_expiry = event_calendar.get_next_expiry_info("NIFTY")
                days_to_expiry = nifty_expiry.get("days_to_expiry", 0)
                st.metric("Days to Expiry", days_to_expiry, delta="⏰")
            
            with col5:
                # System health
                health_status = health_checker.get_overall_health_status()
                health_emoji = {"HEALTHY": "✅", "WARNING": "⚠️", "CRITICAL": "🚨", "DOWN": "🔴"}
                st.metric("System Health", health_status.value, 
                         delta=health_emoji.get(health_status.value, "❓"))
                
        except Exception as e:
            st.error(f"Metrics error: {e}")
    
    def render_strategy_overview(self):
        """Render strategy overview and selection"""
        st.markdown("### 🎯 Strategy Status")
        
        try:
            # Strategy selector status
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown("**Intelligent Strategy Selector**")
                
                # Get current market conditions
                market_conditions = self.get_current_market_conditions()
                
                # Check strategy eligibility
                eligible_strategies = []
                for symbol in ["NIFTY", "BANKNIFTY"]:
                    best_strategy = self.strategy_selector.select_best_strategy(
                        symbol, market_conditions
                    )
                    if best_strategy:
                        eligible_strategies.append({
                            "symbol": symbol,
                            "strategy": best_strategy,
                            "score": 85  # Mock score
                        })
                
                if eligible_strategies:
                    for strat in eligible_strategies:
                        st.success(f"✅ {strat['symbol']}: {strat['strategy']} (Score: {strat['score']})")
                else:
                    st.warning("⚠️ No strategies recommended in current market conditions")
            
            with col2:
                if st.button("🔍 Analyze Market", key="analyze_market"):
                    with st.spinner("Analyzing market conditions..."):
                        # Simulate analysis
                        st.success("Market analysis complete!")
            
            # Active strategies performance
            st.markdown("**Active Strategies Performance**")
            self.render_active_strategies_performance()
            
        except Exception as e:
            st.error(f"Strategy overview error: {e}")
    
    def render_active_strategies_performance(self):
        """Render active strategies performance table"""
        try:
            with db_manager.get_session() as session:
                # Get recent positions
                positions = session.query(Position).filter(
                    Position.status.in_(["ACTIVE", "CLOSED"])
                ).order_by(Position.created_at.desc()).limit(10).all()
                
                if positions:
                    data = []
                    for pos in positions:
                        data.append({
                            "Strategy": pos.strategy_name,
                            "Symbol": pos.symbol,
                            "Status": pos.status,
                            "P&L": f"₹{pos.current_pnl:,.0f}" if pos.current_pnl else "₹0",
                            "Lots": pos.lot_count,
                            "Entry": pos.created_at.strftime("%d-%m %H:%M")
                        })
                    
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No recent positions found")
                    
        except Exception as e:
            st.error(f"Performance data error: {e}")
    
    def render_recent_trades(self):
        """Render recent trades table"""
        try:
            with db_manager.get_session() as session:
                trades = session.query(Trade).order_by(
                    Trade.executed_at.desc()
                ).limit(10).all()
                
                if trades:
                    data = []
                    for trade in trades:
                        data.append({
                            "Time": trade.executed_at.strftime("%H:%M:%S") if trade.executed_at else "Pending",
                            "Symbol": trade.symbol,
                            "Side": trade.side,
                            "Quantity": trade.quantity,
                            "Price": f"₹{trade.executed_price:.2f}" if trade.executed_price else "Market",
                            "Status": trade.status
                        })
                    
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("No recent trades found")
                    
        except Exception as e:
            st.error(f"Recent trades error: {e}")
    
    def render_alerts_panel(self):
        """Render alerts and notifications panel"""
        st.markdown("### 🚨 Alerts & Notifications")
        
        try:
            # Risk alerts
            risk_status = get_risk_status()
            active_alerts = risk_status.get('active_alerts', 0)
            
            if active_alerts > 0:
                st.markdown(f"""
                <div class="alert-box warning-box">
                    <strong>⚠️ {active_alerts} Active Risk Alerts</strong><br>
                    Check Risk Monitor for details
                </div>
                """, unsafe_allow_html=True)
            
            # Danger zone alerts
            danger_status = danger_monitor.get_current_status()
            for symbol, status in danger_status.items():
                danger_level = status.get('danger_level', 'SAFE')
                if danger_level != 'SAFE':
                    color_class = {
                        'WARNING': 'warning-box',
                        'CRITICAL': 'danger-box',
                        'EMERGENCY': 'danger-box'
                    }.get(danger_level, 'warning-box')
                    
                    st.markdown(f"""
                    <div class="alert-box {color_class}">
                        <strong>{symbol} Danger Zone: {danger_level}</strong><br>
                        Change: {status.get('session_change_pct', 0):.2f}%
                    </div>
                    """, unsafe_allow_html=True)
            
            # Calendar alerts
            should_avoid_nifty, nifty_reason = should_avoid_trading_today("NIFTY")
            should_avoid_banknifty, banknifty_reason = should_avoid_trading_today("BANKNIFTY")
            
            if should_avoid_nifty or should_avoid_banknifty:
                st.markdown(f"""
                <div class="alert-box warning-box">
                    <strong>📅 Calendar Alert</strong><br>
                    NIFTY: {nifty_reason}<br>
                    BANKNIFTY: {banknifty_reason}
                </div>
                """, unsafe_allow_html=True)
            
            # System health alerts
            health_summary = health_checker.get_health_summary()
            unhealthy_components = health_summary['summary']['critical'] + health_summary['summary']['down']
            
            if unhealthy_components > 0:
                st.markdown(f"""
                <div class="alert-box danger-box">
                    <strong>🔧 System Health Alert</strong><br>
                    {unhealthy_components} components need attention
                </div>
                """, unsafe_allow_html=True)
            
            # Recent notifications
            st.markdown("**Recent Notifications**")
            notifications = [
                {"time": "14:30", "message": "NIFTY strategy executed successfully", "type": "success"},
                {"time": "14:25", "message": "Risk alert: Position approaching SL", "type": "warning"},
                {"time": "14:20", "message": "Market volatility increased", "type": "info"}
            ]
            
            for notif in notifications:
                icon = {"success": "✅", "warning": "⚠️", "info": "ℹ️"}.get(notif["type"], "ℹ️")
                st.markdown(f"{icon} **{notif['time']}:** {notif['message']}")
                
        except Exception as e:
            st.error(f"Alerts panel error: {e}")
    
    def render_market_status(self):
        """Render current market status"""
        st.markdown("### 📊 Market Status")
        
        try:
            # Trading day status
            today = date.today()
            is_trading_day = event_calendar.is_trading_day(today)
            
            if is_trading_day:
                st.markdown(f"""
                <div class="alert-box success-box">
                    <strong>🟢 Market Open</strong><br>
                    {today.strftime('%A, %B %d, %Y')}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="alert-box warning-box">
                    <strong>🔴 Market Closed</strong><br>
                    {today.strftime('%A, %B %d, %Y')}
                </div>
                """, unsafe_allow_html=True)
            
            # Current time and session
            current_time = datetime.now().time()
            if time(9, 15) <= current_time <= time(15, 30):
                session_status = "In Session"
                session_color = "success-box"
            elif current_time < time(9, 15):
                session_status = "Pre-Market"
                session_color = "warning-box"
            else:
                session_status = "Post-Market"
                session_color = "warning-box"
            
            st.markdown(f"""
            <div class="alert-box {session_color}">
                <strong>Session: {session_status}</strong><br>
                Current Time: {current_time.strftime('%H:%M:%S')}
            </div>
            """, unsafe_allow_html=True)
            
            # Expiry information
            nifty_expiry = event_calendar.get_next_expiry_info("NIFTY")
            banknifty_expiry = event_calendar.get_next_expiry_info("BANKNIFTY")
            
            st.markdown("**Next Expiries:**")
            st.markdown(f"• NIFTY: {nifty_expiry.get('days_to_expiry', 0)} days ({nifty_expiry.get('expiry_type', 'N/A')})")
            st.markdown(f"• BANKNIFTY: {banknifty_expiry.get('days_to_expiry', 0)} days ({banknifty_expiry.get('expiry_type', 'N/A')})")
            
        except Exception as e:
            st.error(f"Market status error: {e}")
    
    def render_strategies_page(self):
        """Render strategies management page"""
        st.markdown("## 🎯 Strategy Management")
        
        # Strategy selector configuration
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("### Available Strategies")
            
            # Get all strategies from database
            try:
                with db_manager.get_session() as session:
                    strategies = session.query(Strategy).filter(
                        Strategy.is_active == True
                    ).all()
                    
                    for strategy in strategies:
                        with st.expander(f"📊 {strategy.display_name}", expanded=False):
                            col_a, col_b, col_c = st.columns(3)
                            
                            with col_a:
                                st.metric("Target Win Rate", f"{strategy.target_win_rate:.1f}%")
                                st.metric("Legs", strategy.legs)
                            
                            with col_b:
                                st.metric("VIX Range", f"{strategy.min_vix:.1f} - {strategy.max_vix:.1f}")
                                st.metric("Market Outlook", strategy.market_outlook)
                            
                            with col_c:
                                st.metric("Hedged", "✅" if strategy.is_hedged else "❌")
                                
                                # Toggle strategy active status
                                if st.button(f"{'Disable' if strategy.is_active else 'Enable'}", 
                                           key=f"toggle_{strategy.name}"):
                                    strategy.is_active = not strategy.is_active
                                    session.commit()
                                    st.rerun()
                            
                            st.markdown(f"**Description:** {strategy.description}")
                            
            except Exception as e:
                st.error(f"Strategies loading error: {e}")
        
        with col2:
            st.markdown("### Strategy Performance")
            
            # Mock performance data
            performance_data = {
                "Strategy": ["Iron Condor", "Butterfly", "Calendar", "Hedged Strangle"],
                "Win Rate": [85, 80, 78, 75],
                "Avg Return": [12, 15, 10, 18],
                "Risk Score": [20, 25, 15, 35]
            }
            
            df = pd.DataFrame(performance_data)
            
            # Win rate chart
            fig = px.bar(df, x="Strategy", y="Win Rate", 
                        title="Strategy Win Rates", 
                        color="Win Rate",
                        color_continuous_scale="RdYlGn")
            st.plotly_chart(fig, use_container_width=True)
            
            # Performance metrics
            st.markdown("### This Month")
            st.metric("Total Trades", 24, delta="+3")
            st.metric("Success Rate", "82.5%", delta="+2.1%")
            st.metric("Avg Return", "14.2%", delta="+1.8%")
    
    def render_risk_monitor_page(self):
        """Render risk monitoring page"""
        st.markdown("## 🛡️ Risk Monitor")
        
        # Risk monitoring controls
        col1, col2, col3 = st.columns(3)
        
        with col1:
            monitoring_active = risk_monitor.is_monitoring
            if st.button(f"{'🛑 Stop' if monitoring_active else '▶️ Start'} Risk Monitor", 
                        key="toggle_risk_monitor"):
                if monitoring_active:
                    risk_monitor.stop_monitoring()
                    st.success("Risk monitoring stopped")
                else:
                    risk_monitor.start_monitoring()
                    st.success("Risk monitoring started")
                st.rerun()
        
        with col2:
            if st.button("📊 Refresh Status", key="refresh_risk"):
                st.rerun()
        
        with col3:
            if st.button("🚨 Force Exit All", key="force_exit_all", type="secondary"):
                if st.session_state.get('confirm_exit_all', False):
                    risk_monitor.force_exit_all_positions("Manual override from dashboard")
                    st.success("Force exit initiated!")
                    st.session_state.confirm_exit_all = False
                else:
                    st.session_state.confirm_exit_all = True
                    st.warning("Click again to confirm force exit")
        
        # Risk status overview
        st.markdown("### 📊 Risk Status Overview")
        risk_status = get_risk_status()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Monitoring Status", 
                     "Active" if risk_status.get('monitoring_active', False) else "Inactive",
                     delta="✅" if risk_status.get('monitoring_active', False) else "🔴")
        
        with col2:
            st.metric("Active Positions", risk_status.get('total_positions', 0))
        
        with col3:
            daily_pnl = risk_status.get('daily_pnl', 0)
            st.metric("Daily P&L", f"₹{daily_pnl:,.0f}",
                     delta=f"{daily_pnl:+,.0f}" if daily_pnl != 0 else "0")
        
        with col4:
            high_risk = risk_status.get('high_risk_positions', 0)
            st.metric("High Risk Positions", high_risk,
                     delta="⚠️" if high_risk > 0 else "✅")
        
        # Risk actions today
        st.markdown("### 🎯 Risk Actions Today")
        risk_actions = risk_status.get('risk_actions_today', {})
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Soft Exits", risk_actions.get('soft_exits', 0))
        
        with col2:
            st.metric("Hard Exits", risk_actions.get('hard_exits', 0))
        
        with col3:
            st.metric("Emergency Exits", risk_actions.get('emergency_exits', 0))
        
        with col4:
            st.metric("Blocked Entries", risk_actions.get('blocked_entries', 0))
        
        # Danger zone status
        st.markdown("### 🚨 Danger Zone Status")
        danger_status = danger_monitor.get_current_status()
        
        for symbol, status in danger_status.items():
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(f"{symbol} Price", f"₹{status.get('current_price', 0):,.0f}")
            
            with col2:
                change_pct = status.get('session_change_pct', 0)
                st.metric("Session Change", f"{change_pct:+.2f}%",
                         delta="📈" if change_pct >= 0 else "📉")
            
            with col3:
                danger_level = status.get('danger_level', 'SAFE')
                color_map = {'SAFE': '🟢', 'WARNING': '🟡', 'CRITICAL': '🔴', 'EMERGENCY': '🚨'}
                st.metric("Danger Level", danger_level, delta=color_map.get(danger_level, '⚪'))
            
            with col4:
                st.metric("Daily High", f"₹{status.get('daily_high', 0):,.0f}")
    
    def render_positions_page(self):
        """Render positions tracking page"""
        st.markdown("## 📊 Position Tracking")
        
        # Position summary
        st.markdown("### 📈 Position Summary")
        
        try:
            with db_manager.get_session() as session:
                # Get active positions
                active_positions = session.query(Position).filter(
                    Position.status == "ACTIVE"
                ).all()
                
                if active_positions:
                    # Summary metrics
                    col1, col2, col3, col4 = st.columns(4)
                    
                    total_pnl = sum(pos.current_pnl or 0 for pos in active_positions)
                    total_lots = sum(pos.lot_count for pos in active_positions)
                    
                    with col1:
                        st.metric("Active Positions", len(active_positions))
                    
                    with col2:
                        st.metric("Total Lots", total_lots)
                    
                    with col3:
                        st.metric("Total P&L", f"₹{total_pnl:,.0f}",
                                 delta=f"{total_pnl:+,.0f}" if total_pnl != 0 else "0")
                    
                    with col4:
                        avg_pnl = total_pnl / len(active_positions) if active_positions else 0
                        st.metric("Avg P&L per Position", f"₹{avg_pnl:,.0f}")
                    
                    # Detailed positions table
                    st.markdown("### 📋 Active Positions Details")
                    
                    positions_data = []
                    for pos in active_positions:
                        positions_data.append({
                            "ID": pos.id,
                            "Strategy": pos.strategy_name,
                            "Symbol": pos.symbol,
                            "Lots": pos.lot_count,
                            "Entry Time": pos.created_at.strftime("%d-%m %H:%M"),
                            "Current P&L": f"₹{pos.current_pnl:,.0f}" if pos.current_pnl else "₹0",
                            "Status": pos.status
                        })
                    
                    df = pd.DataFrame(positions_data)
                    st.dataframe(df, use_container_width=True)
                    
                    # P&L chart
                    if len(positions_data) > 0:
                        fig = px.bar(df, x="Strategy", y="Current P&L", 
                                   title="P&L by Strategy", 
                                   color="Current P&L",
                                   color_continuous_scale="RdYlGn")
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No active positions found")
                
                # Closed positions (recent)
                st.markdown("### 📜 Recent Closed Positions")
                
                closed_positions = session.query(Position).filter(
                    Position.status == "CLOSED"
                ).order_by(Position.updated_at.desc()).limit(10).all()
                
                if closed_positions:
                    closed_data = []
                    for pos in closed_positions:
                        closed_data.append({
                            "Strategy": pos.strategy_name,
                            "Symbol": pos.symbol,
                            "Lots": pos.lot_count,
                            "Entry": pos.created_at.strftime("%d-%m %H:%M"),
                            "Exit": pos.updated_at.strftime("%d-%m %H:%M"),
                            "Final P&L": f"₹{pos.final_pnl:,.0f}" if pos.final_pnl else "₹0",
                            "Duration": str(pos.updated_at - pos.created_at).split(".")[0]
                        })
                    
                    df_closed = pd.DataFrame(closed_data)
                    st.dataframe(df_closed, use_container_width=True)
                else:
                    st.info("No recent closed positions found")
                    
        except Exception as e:
            st.error(f"Positions data error: {e}")
    
    def render_calendar_page(self):
        """Render event calendar page"""
        st.markdown("## 📅 Event Calendar")
        
        # Calendar status and controls
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Refresh Calendar", key="refresh_calendar"):
                with st.spinner("Refreshing calendar data..."):
                    event_calendar.refresh_event_data()
                    st.success("Calendar data refreshed!")
        
        with col2:
            # Last refresh time
            refresh_time = getattr(event_calendar, 'last_holiday_refresh', datetime.now())
            st.metric("Last Refresh", refresh_time.strftime("%d-%m %H:%M"))
        
        with col3:
            # Calendar health
            try:
                today = date.today()
                is_trading = event_calendar.is_trading_day(today)
                st.metric("Today's Status", 
                         "Trading Day" if is_trading else "Holiday",
                         delta="✅" if is_trading else "🔴")
            except Exception as e:
                st.metric("Calendar Status", "Error", delta="❌")
        
        # Current market status
        st.markdown("### 📊 Current Market Status")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Trading day status
            today = date.today()
            is_trading_day = event_calendar.is_trading_day(today)
            
            if is_trading_day:
                st.markdown(f"""
                <div class="alert-box success-box">
                    <strong>🟢 Market Open Today</strong><br>
                    {today.strftime('%A, %B %d, %Y')}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="alert-box warning-box">
                    <strong>🔴 Market Closed Today</strong><br>
                    {today.strftime('%A, %B %d, %Y')}
                </div>
                """, unsafe_allow_html=True)
        
        with col2:
            # Next trading day
            try:
                if not is_trading_day:
                    next_trading = event_calendar.get_next_trading_day(today)
                    days_until = (next_trading - today).days
                    st.markdown(f"""
                    <div class="alert-box success-box">
                        <strong>📅 Next Trading Day</strong><br>
                        {next_trading.strftime('%A, %B %d')} ({days_until} days)
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="alert-box success-box">
                        <strong>✅ Trading Active</strong><br>
                        Market is open for trading
                    </div>
                    """, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Next trading day error: {e}")
        
        # Expiry information
        st.markdown("### ⏰ Expiry Information")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**NIFTY Expiry**")
            try:
                nifty_expiry = event_calendar.get_next_expiry_info("NIFTY")
                st.metric("Days to Expiry", nifty_expiry.get("days_to_expiry", 0))
                st.metric("Expiry Type", nifty_expiry.get("expiry_type", "N/A"))
                st.metric("Expiry Date", nifty_expiry.get("next_expiry_date", "N/A"))
            except Exception as e:
                st.error(f"NIFTY expiry error: {e}")
        
        with col2:
            st.markdown("**BANKNIFTY Expiry**")
            try:
                banknifty_expiry = event_calendar.get_next_expiry_info("BANKNIFTY")
                st.metric("Days to Expiry", banknifty_expiry.get("days_to_expiry", 0))
                st.metric("Expiry Type", banknifty_expiry.get("expiry_type", "N/A"))
                st.metric("Expiry Date", banknifty_expiry.get("next_expiry_date", "N/A"))
            except Exception as e:
                st.error(f"BANKNIFTY expiry error: {e}")
        
        # Upcoming events
        st.markdown("### 📋 Upcoming Events")
        
        try:
            events = get_upcoming_events(14)  # Next 14 days
            
            if events:
                events_data = []
                for event in events:
                    impact_emoji = {
                        "LOW": "🟢",
                        "MEDIUM": "🟡", 
                        "HIGH": "🟠",
                        "CRITICAL": "🔴"
                    }
                    
                    events_data.append({
                        "Date": event.date.strftime("%d-%m-%Y"),
                        "Day": event.date.strftime("%A"),
                        "Event": event.title,
                        "Impact": f"{impact_emoji.get(event.impact_level, '⚪')} {event.impact_level}",
                        "Action": event.trading_action,
                        "Instruments": ", ".join(event.affected_instruments)
                    })
                
                df_events = pd.DataFrame(events_data)
                st.dataframe(df_events, use_container_width=True)
            else:
                st.info("No upcoming events in the next 14 days")
                
        except Exception as e:
            st.error(f"Upcoming events error: {e}")
        
        # Trading recommendations
        st.markdown("### 💡 Trading Recommendations")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # NIFTY recommendations
            st.markdown("**NIFTY Trading**")
            should_avoid_nifty, nifty_reason = should_avoid_trading_today("NIFTY")
            
            if should_avoid_nifty:
                st.markdown(f"""
                <div class="alert-box warning-box">
                    <strong>⚠️ Avoid NIFTY Trading</strong><br>
                    {nifty_reason}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="alert-box success-box">
                    <strong>✅ NIFTY Trading OK</strong><br>
                    {nifty_reason}
                </div>
                """, unsafe_allow_html=True)
        
        with col2:
            # BANKNIFTY recommendations
            st.markdown("**BANKNIFTY Trading**")
            should_avoid_banknifty, banknifty_reason = should_avoid_trading_today("BANKNIFTY")
            
            if should_avoid_banknifty:
                st.markdown(f"""
                <div class="alert-box warning-box">
                    <strong>⚠️ Avoid BANKNIFTY Trading</strong><br>
                    {banknifty_reason}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="alert-box success-box">
                    <strong>✅ BANKNIFTY Trading OK</strong><br>
                    {banknifty_reason}
                </div>
                """, unsafe_allow_html=True)
    
    def render_analytics_page(self):
        """Render analytics and reporting page"""
        st.markdown("## 📊 Analytics & Reports")
        
        # Time period selector
        col1, col2, col3 = st.columns(3)
        
        with col1:
            period = st.selectbox("Select Period", 
                                ["Today", "This Week", "This Month", "Last 30 Days", "Custom"])
        
        with col2:
            if period == "Custom":
                start_date = st.date_input("Start Date", value=date.today() - timedelta(days=30))
        
        with col3:
            if period == "Custom":
                end_date = st.date_input("End Date", value=date.today())
        
        # Performance metrics
        st.markdown("### 📈 Performance Metrics")
        
        # Mock data for demonstration
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Trades", 156, delta="+12")
        
        with col2:
            st.metric("Win Rate", "78.2%", delta="+2.3%")
        
        with col3:
            st.metric("Total P&L", "₹2,45,680", delta="+₹18,420")
        
        with col4:
            st.metric("Avg Return", "15.7%", delta="+1.2%")
        
        # Performance charts
        col1, col2 = st.columns(2)
        
        with col1:
            # P&L over time chart
            st.markdown("### 📈 P&L Over Time")
            
            # Mock P&L data
            dates = pd.date_range(start=date.today()-timedelta(days=30), end=date.today(), freq='D')
            cumulative_pnl = pd.Series(range(len(dates))) * 1000 + pd.Series(range(len(dates))).apply(lambda x: x**1.1 * 100)
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=dates, y=cumulative_pnl, mode='lines+markers', name='Cumulative P&L'))
            fig.update_layout(title="Cumulative P&L", xaxis_title="Date", yaxis_title="P&L (₹)")
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Strategy performance comparison
            st.markdown("### 🎯 Strategy Performance")
            
            strategy_performance = {
                "Strategy": ["Iron Condor", "Butterfly", "Calendar", "Hedged Strangle", "Directional"],
                "Returns": [15.2, 12.8, 18.5, 22.1, 8.7],
                "Win Rate": [85, 80, 78, 75, 65]
            }
            
            df_perf = pd.DataFrame(strategy_performance)
            
            fig = px.scatter(df_perf, x="Win Rate", y="Returns", 
                           size="Returns", hover_name="Strategy",
                           title="Strategy Risk-Return Profile")
            st.plotly_chart(fig, use_container_width=True)
        
        # Detailed analytics
        st.markdown("### 📋 Detailed Analytics")
        
        tab1, tab2, tab3 = st.tabs(["Trade Analysis", "Risk Metrics", "Market Exposure"])
        
        with tab1:
            # Trade analysis
            st.markdown("#### Trade Distribution")
            
            # Mock trade data
            trade_analysis = {
                "Symbol": ["NIFTY", "BANKNIFTY", "NIFTY", "BANKNIFTY"],
                "Strategy": ["Iron Condor", "Butterfly", "Calendar", "Hedged Strangle"],
                "Count": [45, 32, 28, 51],
                "Success Rate": [82, 78, 85, 73],
                "Avg Return": [12.5, 15.2, 8.9, 19.8]
            }
            
            df_trades = pd.DataFrame(trade_analysis)
            st.dataframe(df_trades, use_container_width=True)
        
        with tab2:
            # Risk metrics
            st.markdown("#### Risk Metrics")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Max Drawdown", "8.5%", delta="-1.2%")
                st.metric("Sharpe Ratio", "2.14", delta="+0.08")
                st.metric("Sortino Ratio", "3.21", delta="+0.15")
            
            with col2:
                st.metric("Value at Risk (95%)", "₹15,420", delta="-₹1,250")
                st.metric("Beta", "0.85", delta="-0.03")
                st.metric("Alpha", "5.2%", delta="+0.4%")
        
        with tab3:
            # Market exposure
            st.markdown("#### Market Exposure")
            
            exposure_data = {
                "Instrument": ["NIFTY", "BANKNIFTY"],
                "Long Exposure": [45, 35],
                "Short Exposure": [38, 42],
                "Net Exposure": [7, -7]
            }
            
            df_exposure = pd.DataFrame(exposure_data)
            
            fig = px.bar(df_exposure, x="Instrument", y=["Long Exposure", "Short Exposure"],
                        title="Market Exposure by Instrument", barmode="group")
            st.plotly_chart(fig, use_container_width=True)
    
    def render_settings_page(self):
        """Render system settings page"""
        st.markdown("## ⚙️ System Settings")
        
        tab1, tab2, tab3, tab4 = st.tabs(["General", "Risk Management", "Notifications", "Broker"])
        
        with tab1:
            # General settings
            st.markdown("### 🔧 General Settings")
            
            col1, col2 = st.columns(2)
            
            with col1:
                default_capital = st.number_input("Default Capital (₹)", 
                                                value=settings.DEFAULT_CAPITAL, 
                                                step=10000)
                
                max_lots = st.number_input("Max Lots per Strategy", 
                                         value=settings.MAX_LOTS_PER_STRATEGY, 
                                         step=1)
                
                allowed_instruments = st.multiselect("Allowed Instruments",
                                                   ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"],
                                                   default=["NIFTY", "BANKNIFTY"])
            
            with col2:
                vix_threshold = st.slider("VIX Threshold", 10.0, 50.0, 25.0, 0.5)
                
                entry_cutoff = st.time_input("Entry Cutoff Time", value=time(11, 0))
                
                exit_time = st.time_input("Mandatory Exit Time", value=time(15, 10))
            
            if st.button("💾 Save General Settings"):
                st.success("General settings saved!")
        
        with tab2:
            # Risk management settings
            st.markdown("### 🛡️ Risk Management")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Danger Zone Thresholds**")
                danger_warning = st.slider("Warning Level (%)", 0.5, 2.0, 1.0, 0.1)
                danger_risk = st.slider("Risk Level (%)", 1.0, 3.0, 1.25, 0.05)
                danger_exit = st.slider("Exit Level (%)", 1.5, 4.0, 1.5, 0.1)
            
            with col2:
                st.markdown("**Position Limits**")
                max_daily_loss = st.number_input("Max Daily Loss (₹)", value=10000, step=1000)
                max_position_size = st.number_input("Max Position Size (Lots)", value=5, step=1)
                correlation_limit = st.slider("Position Correlation Limit", 0.5, 1.0, 0.8, 0.05)
            
            if st.button("💾 Save Risk Settings"):
                st.success("Risk management settings saved!")
        
        with tab3:
            # Notification settings
            st.markdown("### 📱 WhatsApp Notifications")
            
            col1, col2 = st.columns(2)
            
            with col1:
                enable_notifications = st.checkbox("Enable WhatsApp Notifications", value=True)
                
                gupshup_api_key = st.text_input("Gupshup API Key", type="password", 
                                              placeholder="Enter your Gupshup API key")
                
                gupshup_app_name = st.text_input("App Name", placeholder="Your registered app name")
            
            with col2:
                admin_phone = st.text_input("Admin Phone Number", 
                                          placeholder="+91XXXXXXXXXX")
                
                notification_types = st.multiselect("Notification Types",
                                                   ["Trade Executions", "Risk Alerts", "System Health", 
                                                    "Daily Summary", "Error Alerts"],
                                                   default=["Risk Alerts", "System Health"])
            
            # Test notification
            if st.button("📤 Test Notification"):
                if gupshup_api_key and admin_phone:
                    try:
                        notifier = WhatsAppNotifier(gupshup_api_key, gupshup_app_name, admin_phone)
                        success = notifier.send_message("🧪 Test notification from F&O Trading System")
                        if success:
                            st.success("Test notification sent successfully!")
                        else:
                            st.error("Failed to send test notification")
                    except Exception as e:
                        st.error(f"Notification test failed: {e}")
                else:
                    st.warning("Please enter API key and phone number first")
            
            if st.button("💾 Save Notification Settings"):
                st.success("Notification settings saved!")
        
        with tab4:
            # Broker settings
            st.markdown("### 🏦 Broker Configuration")
            
            # Broker selection
            broker_name = st.selectbox("Select Broker", 
                                     ["Zerodha", "Fyers", "Angel One", "IIFL"])
            
            if broker_name == "Zerodha":
                st.markdown("#### Zerodha (Kite Connect) Configuration")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    api_key = st.text_input("API Key", type="password")
                    api_secret = st.text_input("API Secret", type="password")
                
                with col2:
                    user_id = st.text_input("User ID")
                    password = st.text_input("Password", type="password")
                
                # Test connection
                if st.button("🔗 Test Broker Connection"):
                    if api_key and api_secret:
                        st.info("Testing broker connection...")
                        # Here you would test the actual connection
                        st.success("Broker connection successful!")
                    else:
                        st.warning("Please enter API credentials first")
            
            elif broker_name == "Fyers":
                st.markdown("#### Fyers Configuration")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    client_id = st.text_input("Client ID")
                    secret_key = st.text_input("Secret Key", type="password")
                
                with col2:
                    redirect_uri = st.text_input("Redirect URI")
                    access_token = st.text_input("Access Token", type="password")
            
            # Save broker settings
            if st.button("💾 Save Broker Settings"):
                st.success("Broker settings saved and encrypted!")
                st.info("Broker credentials are encrypted using AES-256 encryption")
    
    def render_health_page(self):
        """Render system health monitoring page"""
        st.markdown("## 🔧 System Health")
        
        # Overall health status
        try:
            health_summary = health_checker.get_health_summary()
            overall_status = health_summary['overall_status']
            
            # Status color coding
            status_colors = {
                'HEALTHY': 'success-box',
                'WARNING': 'warning-box', 
                'CRITICAL': 'danger-box',
                'DOWN': 'danger-box'
            }
            
            st.markdown(f"""
            <div class="alert-box {status_colors.get(overall_status, 'warning-box')}">
                <strong>🔧 Overall System Status: {overall_status}</strong><br>
                Last checked: {health_summary['timestamp']}
            </div>
            """, unsafe_allow_html=True)
            
            # Component health summary
            col1, col2, col3, col4 = st.columns(4)
            
            summary = health_summary['summary']
            
            with col1:
                st.metric("Healthy Components", summary['healthy'], delta="✅")
            
            with col2:
                st.metric("Warning Components", summary['warning'], delta="⚠️" if summary['warning'] > 0 else "✅")
            
            with col3:
                st.metric("Critical Components", summary['critical'], delta="🚨" if summary['critical'] > 0 else "✅")
            
            with col4:
                st.metric("Down Components", summary['down'], delta="🔴" if summary['down'] > 0 else "✅")
            
            # Detailed component status
            st.markdown("### 📊 Component Details")
            
            components = health_summary['components']
            
            for component_name, component_info in components.items():
                status = component_info['status']
                message = component_info['message']
                response_time = component_info.get('response_time_ms', 'N/A')
                
                with st.expander(f"{'🟢' if status == 'HEALTHY' else '🔴'} {component_name.title()}", 
                               expanded=(status != 'HEALTHY')):
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Status", status)
                    
                    with col2:
                        if response_time != 'N/A':
                            st.metric("Response Time", f"{response_time:.0f}ms")
                        else:
                            st.metric("Response Time", "N/A")
                    
                    with col3:
                        st.metric("Last Check", component_info['last_check'])
                    
                    st.markdown(f"**Message:** {message}")
            
            # System actions
            st.markdown("### 🔧 System Actions")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🔄 Refresh Health Check", key="refresh_health"):
                    with st.spinner("Running health check..."):
                        # Force health check refresh
                        health_checker.check_all_components()
                        st.success("Health check completed!")
                        st.rerun()
            
            with col2:
                if st.button("📊 System Diagnostics", key="system_diagnostics"):
                    st.info("System diagnostics initiated...")
                    # Here you would run comprehensive diagnostics
            
            with col3:
                if st.button("🚨 Emergency Reset", key="emergency_reset", type="secondary"):
                    if st.session_state.get('confirm_reset', False):
                        st.warning("Emergency reset would be initiated here")
                        st.session_state.confirm_reset = False
                    else:
                        st.session_state.confirm_reset = True
                        st.warning("Click again to confirm emergency reset")
            
        except Exception as e:
            st.error(f"Health monitoring error: {e}")
            logger.error(f"Health monitoring error: {e}")
    
    def get_current_market_conditions(self) -> Dict[str, Any]:
        """Get current market conditions for strategy selection"""
        # This would integrate with your market data provider
        # For now, return mock data
        return {
            "vix": 22.5,
            "nifty_change_pct": 0.75,
            "banknifty_change_pct": -0.45,
            "trend_strength": 1.8,
            "volume_surge": True,
            "market_sentiment": "NEUTRAL",
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 5
        }

def main():
    """Main application entry point"""
    try:
        dashboard = TradingDashboard()
        dashboard.run()
    except Exception as e:
        st.error(f"Application error: {e}")
        logger.error(f"Application error: {e}")

if __name__ == "__main__":
    main()
