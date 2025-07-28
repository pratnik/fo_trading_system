"""
Comprehensive Risk Monitor for F&O Trading System - UPDATED VERSION
- Real-time MTM monitoring and alerts
- Danger zone detection and auto-exit logic
- Position size validation and margin checks
- Integration with WhatsApp notifications
- Strategy-specific risk management
- Enhanced event calendar integration
- Auto-refresh calendar checks
- Compatible with NIFTY/BANKNIFTY hedged strategies only
"""

import logging
from datetime import datetime, time, timedelta, date
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.db.models import Trade, Position, AuditLog
from app.db.base import db_manager
from app.notifications.whatsapp_notifier import WhatsAppNotifier
from app.risk.danger_zone import danger_monitor, DangerLevel
from app.risk.expiry_day import expiry_manager
from app.utils.healthcheck import health_checker
from app.utils.event_calendar import event_calendar, should_avoid_trading_today

logger = logging.getLogger("risk_monitor")

class RiskLevel(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"

class ActionType(str, Enum):
    MONITOR = "MONITOR"
    ALERT = "ALERT"
    SOFT_EXIT = "SOFT_EXIT"
    HARD_EXIT = "HARD_EXIT"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    BLOCK_ENTRY = "BLOCK_ENTRY"
    CALENDAR_RESTRICTION = "CALENDAR_RESTRICTION"

@dataclass
class RiskAlert:
    timestamp: datetime
    risk_level: RiskLevel
    action_type: ActionType
    symbol: str
    strategy_name: str
    message: str
    mtm: float
    position_size: int
    urgency: str
    auto_action_taken: bool = False
    notification_sent: bool = False

@dataclass
class PositionRisk:
    position_id: str
    symbol: str
    strategy_name: str
    current_mtm: float
    max_loss_limit: float
    profit_target: float
    position_size: int
    days_to_expiry: int
    risk_score: float
    last_updated: datetime

class RiskMonitor:
    """
    Comprehensive Risk Management System - Updated with Event Calendar Integration
    Monitors all positions in real-time and takes automated risk actions
    """
    
    def __init__(self):
        # Risk monitoring settings
        self.is_monitoring = False
        self.monitor_thread = None
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Risk limits from settings
        self.global_daily_loss_limit = settings.DEFAULT_CAPITAL * 0.05  # 5% of capital
        self.global_position_limit = settings.MAX_LOTS_PER_STRATEGY
        self.danger_zone_limits = {
            "warning": settings.DANGER_ZONE_WARNING,      # 1.0%
            "risk": settings.DANGER_ZONE_RISK,           # 1.25%
            "exit": settings.DANGER_ZONE_EXIT            # 1.5%
        }
        
        # Time-based controls
        self.entry_cutoff_time = time(11, 0)  # 11:00 AM
        self.mandatory_exit_time = time(15, 10)  # 3:10 PM
        self.market_open_time = time(9, 15)   # 9:15 AM
        self.market_close_time = time(15, 30)  # 3:30 PM
        
        # Risk tracking
        self.active_alerts: Dict[str, RiskAlert] = {}
        self.position_risks: Dict[str, PositionRisk] = {}
        self.daily_pnl = 0.0
        self.total_positions = 0
        
        # Calendar integration
        self.last_calendar_check = datetime.now()
        self.calendar_blocked_symbols = set()
        
        # External integrations
        self.whatsapp_notifier = None
        self._init_whatsapp_notifier()
        
        # Risk action counters
        self.risk_actions_today = {
            "soft_exits": 0,
            "hard_exits": 0,
            "emergency_exits": 0,
            "blocked_entries": 0,
            "calendar_blocks": 0
        }
        
        logger.info("Risk Monitor initialized successfully (Updated Version with Calendar Integration)")
    
    def _init_whatsapp_notifier(self):
        """Initialize WhatsApp notifier if configured"""
        try:
            api_key = getattr(settings, 'GUPSHUP_API_KEY', None)
            app_name = getattr(settings, 'GUPSHUP_APP_NAME', None)
            phone_number = getattr(settings, 'ADMIN_PHONE_NUMBER', None)
            
            if all([api_key, app_name, phone_number]):
                self.whatsapp_notifier = WhatsAppNotifier(api_key, app_name, phone_number)
                logger.info("WhatsApp notifier initialized")
            else:
                logger.warning("WhatsApp notifier not configured - missing credentials")
        except Exception as e:
            logger.error(f"Failed to initialize WhatsApp notifier: {e}")
    
    def start_monitoring(self):
        """Start the risk monitoring system"""
        if self.is_monitoring:
            logger.warning("Risk monitoring already active")
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Risk monitoring started")
        self._send_notification("🟢 Risk Monitor STARTED", "Real-time risk monitoring with calendar integration is now active")
    
    def stop_monitoring(self):
        """Stop the risk monitoring system"""
        self.is_monitoring = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        logger.info("Risk monitoring stopped")
        self._send_notification("🔴 Risk Monitor STOPPED", "Risk monitoring has been disabled")
    
    def _monitoring_loop(self):
        """Main monitoring loop - runs continuously during market hours"""
        while self.is_monitoring:
            try:
                current_time = datetime.now().time()
                
                # Only monitor during market hours
                if self.market_open_time <= current_time <= self.market_close_time:
                    # Run all risk checks
                    self._run_comprehensive_risk_check()
                    
                    # Sleep for 30 seconds between checks
                    threading.Event().wait(30)
                else:
                    # Outside market hours - sleep for 5 minutes
                    threading.Event().wait(300)
                    
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                threading.Event().wait(60)  # Wait 1 minute on error
    
    def _run_comprehensive_risk_check(self):
        """Run all risk monitoring checks - UPDATED with calendar integration"""
        try:
            # 1. Check time-based controls
            self._check_time_controls()
            
            # 2. Check calendar events (NEW - Enhanced)
            self._check_calendar_events()
            
            # 3. Check danger zone conditions
            self._check_danger_zone()
            
            # 4. Check individual position risks
            self._check_position_risks()
            
            # 5. Check global portfolio risk
            self._check_global_portfolio_risk()
            
            # 6. Check expiry day conditions
            self._check_expiry_conditions()
            
            # 7. Check system health
            self._check_system_health()
            
            # 8. Process any pending risk actions
            self._process_pending_actions()
            
        except Exception as e:
            logger.error(f"Comprehensive risk check failed: {e}")
    
    def _check_time_controls(self):
        """Check time-based trading controls"""
        current_time = datetime.now().time()
        
        # Check for mandatory exit time
        if current_time >= self.mandatory_exit_time:
            self._trigger_mandatory_exit("Mandatory exit time reached (3:10 PM)")
        
        # Check for entry cutoff
        elif current_time >= self.entry_cutoff_time:
            self._block_new_entries("Entry cutoff time reached (11:00 AM)")
    
    def _check_calendar_events(self):
        """Check calendar events and apply trading restrictions - NEW ENHANCED METHOD"""
        try:
            # Auto-refresh calendar data if needed
            event_calendar.auto_refresh_check()
            
            # Check if trading should be avoided for each symbol
            for symbol in ["NIFTY", "BANKNIFTY"]:
                should_avoid, reason = should_avoid_trading_today(symbol)
                
                if should_avoid:
                    # Add to blocked symbols
                    self.calendar_blocked_symbols.add(symbol)
                    
                    # Create calendar restriction alert
                    self._create_calendar_alert(symbol, reason)
                    
                    # If critical events, consider exiting positions
                    if any(word in reason.lower() for word in ["critical", "emergency", "holiday"]):
                        self._trigger_calendar_based_exit(symbol, reason)
                        
                else:
                    # Remove from blocked symbols if previously blocked
                    self.calendar_blocked_symbols.discard(symbol)
            
            # Check upcoming high-impact events (next 24 hours)
            self._check_upcoming_calendar_events()
            
            # Update last check time
            self.last_calendar_check = datetime.now()
            
        except Exception as e:
            logger.error(f"Calendar events check failed: {e}")
    
    def _check_upcoming_calendar_events(self):
        """Check for upcoming high-impact events"""
        try:
            # Get events for today and tomorrow
            today = date.today()
            tomorrow = today + timedelta(days=1)
            
            events_today = event_calendar.get_events_for_date(today)
            events_tomorrow = event_calendar.get_events_for_date(tomorrow)
            
            # Combine and filter for high impact events
            all_events = events_today + events_tomorrow
            high_impact_events = [
                e for e in all_events 
                if e.impact_level in ["HIGH", "CRITICAL"] and 
                   any(symbol in e.affected_instruments for symbol in ["NIFTY", "BANKNIFTY", "ALL"])
            ]
            
            for event in high_impact_events:
                # Create alert for upcoming high impact event
                alert_message = f"Upcoming {event.impact_level} event: {event.title} on {event.date}"
                
                if event.impact_level == "CRITICAL":
                    # Critical events - consider pre-emptive action
                    self._create_system_alert(
                        f"🚨 CRITICAL EVENT ALERT: {alert_message}",
                        "HIGH"
                    )
                    
                    # If event is tomorrow, warn about early exit
                    if event.date == tomorrow:
                        self._send_notification(
                            "⚠️ CRITICAL EVENT TOMORROW",
                            f"{event.title}\nRecommendation: Consider early position exit"
                        )
                
                elif event.impact_level == "HIGH":
                    self._create_system_alert(
                        f"⚠️ HIGH IMPACT EVENT: {alert_message}",
                        "MEDIUM"
                    )
                
        except Exception as e:
            logger.error(f"Upcoming calendar events check failed: {e}")
    
    def _create_calendar_alert(self, symbol: str, reason: str):
        """Create calendar-based trading restriction alert"""
        try:
            # Create mock position for alert (since this is symbol-level)
            class CalendarPosition:
                def __init__(self, symbol):
                    self.id = f"calendar_{symbol}"
                    self.symbol = symbol
                    self.strategy_name = "CALENDAR_RESTRICTION"
                    self.lot_count = 0
            
            calendar_position = CalendarPosition(symbol)
            
            alert = self._create_risk_alert(
                calendar_position, 
                RiskLevel.WARNING, 
                ActionType.CALENDAR_RESTRICTION,
                f"Calendar restriction for {symbol}: {reason}"
            )
            
            # Increment counter
            self.risk_actions_today["calendar_blocks"] += 1
            
            logger.warning(f"Calendar restriction applied to {symbol}: {reason}")
            
        except Exception as e:
            logger.error(f"Failed to create calendar alert for {symbol}: {e}")
    
    def _trigger_calendar_based_exit(self, symbol: str, reason: str):
        """Trigger exit for positions based on calendar events"""
        try:
            with db_manager.get_session() as session:
                # Get active positions for the symbol
                symbol_positions = session.query(Position).filter(
                    Position.status == "ACTIVE",
                    Position.symbol == symbol
                ).all()
                
                if symbol_positions:
                    logger.critical(f"Triggering calendar-based exit for {len(symbol_positions)} {symbol} positions")
                    
                    for position in symbol_positions:
                        self._trigger_position_exit(
                            position, 
                            ActionType.HARD_EXIT, 
                            f"Calendar event exit: {reason}"
                        )
                    
                    # Send urgent notification
                    self._send_urgent_notification(
                        f"🚨 CALENDAR EXIT - {symbol}",
                        f"Reason: {reason}\n"
                        f"Positions exited: {len(symbol_positions)}"
                    )
                
        except Exception as e:
            logger.error(f"Calendar-based exit failed for {symbol}: {e}")
    
    def _check_danger_zone(self):
        """Check danger zone conditions for NIFTY/BANKNIFTY"""
        try:
            # Get current market data (you'd integrate with your data provider)
            market_data = self._get_current_market_data()
            
            for symbol in ["NIFTY", "BANKNIFTY"]:
                if symbol in market_data:
                    current_price = market_data[symbol]["price"]
                    change_pct = market_data[symbol]["change_pct"]
                    
                    # Update danger zone monitor
                    alert = danger_monitor.update_price(symbol, current_price)
                    
                    if alert:
                        self._handle_danger_zone_alert(alert)
                        
        except Exception as e:
            logger.error(f"Danger zone check failed: {e}")
    
    def _check_position_risks(self):
        """Check individual position risk levels"""
        try:
            with db_manager.get_session() as session:
                # Get all active positions
                active_positions = session.query(Position).filter(
                    Position.status == "ACTIVE",
                    Position.symbol.in_(["NIFTY", "BANKNIFTY"])  # Only liquid instruments
                ).all()
                
                for position in active_positions:
                    self._evaluate_position_risk(position)
                    
        except Exception as e:
            logger.error(f"Position risk check failed: {e}")
    
    def _evaluate_position_risk(self, position):
        """Evaluate risk for individual position"""
        try:
            # Check if symbol is calendar-blocked
            if position.symbol in self.calendar_blocked_symbols:
                logger.warning(f"Position {position.id} in calendar-blocked symbol {position.symbol}")
                # Don't exit existing positions immediately, but flag for monitoring
            
            # Calculate current MTM
            current_mtm = self._calculate_position_mtm(position)
            
            # Get strategy-specific risk limits
            strategy_config = self._get_strategy_risk_config(position.strategy_name)
            
            # Calculate risk metrics
            max_loss = strategy_config.get("sl_per_lot", 2000) * position.lot_count
            profit_target = strategy_config.get("tp_per_lot", 4000) * position.lot_count
            
            # Create/update position risk
            position_risk = PositionRisk(
                position_id=str(position.id),
                symbol=position.symbol,
                strategy_name=position.strategy_name,
                current_mtm=current_mtm,
                max_loss_limit=max_loss,
                profit_target=profit_target,
                position_size=position.lot_count,
                days_to_expiry=self._get_days_to_expiry(position),
                risk_score=self._calculate_risk_score(current_mtm, max_loss, position),
                last_updated=datetime.now()
            )
            
            self.position_risks[str(position.id)] = position_risk
            
            # Check for risk triggers
            self._check_position_triggers(position, position_risk)
            
        except Exception as e:
            logger.error(f"Position risk evaluation failed for {position.id}: {e}")
    
    def _check_position_triggers(self, position, position_risk: PositionRisk):
        """Check if position triggers any risk actions"""
        mtm = position_risk.current_mtm
        max_loss = position_risk.max_loss_limit
        profit_target = position_risk.profit_target
        
        # Hard stop loss trigger
        if mtm <= -max_loss:
            self._trigger_position_exit(
                position, ActionType.HARD_EXIT, 
                f"Stop loss triggered: MTM ₹{mtm:,.0f} <= SL ₹{-max_loss:,.0f}"
            )
        
        # Profit target trigger
        elif mtm >= profit_target:
            self._trigger_position_exit(
                position, ActionType.SOFT_EXIT,
                f"Profit target reached: MTM ₹{mtm:,.0f} >= TP ₹{profit_target:,.0f}"
            )
        
        # Warning threshold (80% of max loss)
        elif mtm <= -max_loss * 0.8:
            self._create_risk_alert(
                position, RiskLevel.WARNING, ActionType.ALERT,
                f"Approaching stop loss: MTM ₹{mtm:,.0f} (80% of SL)"
            )
        
        # High profit opportunity (70% of target)
        elif mtm >= profit_target * 0.7:
            self._create_risk_alert(
                position, RiskLevel.SAFE, ActionType.ALERT,
                f"Good profit opportunity: MTM ₹{mtm:,.0f} (70% of TP)"
            )
    
    def _check_global_portfolio_risk(self):
        """Check overall portfolio risk levels"""
        try:
            # Calculate total daily P&L
            total_daily_pnl = self._calculate_total_daily_pnl()
            
            # Check global daily loss limit
            if total_daily_pnl <= -self.global_daily_loss_limit:
                self._trigger_global_exit(
                    f"Daily loss limit breached: ₹{total_daily_pnl:,.0f} <= ₹{-self.global_daily_loss_limit:,.0f}"
                )
            
            # Check total position count
            active_position_count = len(self.position_risks)
            if active_position_count >= self.global_position_limit:
                self._block_new_entries(
                    f"Position limit reached: {active_position_count} >= {self.global_position_limit}"
                )
            
            # Update daily P&L tracking
            self.daily_pnl = total_daily_pnl
            self.total_positions = active_position_count
            
        except Exception as e:
            logger.error(f"Global portfolio risk check failed: {e}")
    
    def _check_expiry_conditions(self):
        """Check expiry-related risk conditions"""
        try:
            for symbol in ["NIFTY", "BANKNIFTY"]:
                expiry_info = expiry_manager.get_expiry_info(symbol)
                
                # Block entries on expiry day
                if expiry_info.is_today:
                    self._block_new_entries(f"Expiry day for {symbol}")
                
                # Early exit warning for positions expiring tomorrow
                elif expiry_info.is_tomorrow:
                    self._warn_expiry_positions(symbol)
                    
        except Exception as e:
            logger.error(f"Expiry conditions check failed: {e}")
    
    def _check_system_health(self):
        """Check overall system health"""
        try:
            health_status = health_checker.get_health_summary()
            
            # Check for critical system issues
            if health_status["overall_status"] == "DOWN":
                self._trigger_emergency_action(
                    "System health critical - Multiple components down"
                )
            elif health_status["overall_status"] == "CRITICAL":
                self._create_system_alert(
                    "System health degraded - Some components critical"
                )
                
        except Exception as e:
            logger.error(f"System health check failed: {e}")
    
    def _trigger_position_exit(self, position, action_type: ActionType, reason: str):
        """Trigger exit for specific position"""
        try:
            # Create risk alert
            alert = self._create_risk_alert(
                position, RiskLevel.CRITICAL, action_type, reason
            )
            
            # Execute the exit (integrate with your broker)
            success = self._execute_position_exit(position)
            
            if success:
                alert.auto_action_taken = True
                
                if action_type == ActionType.HARD_EXIT:
                    self.risk_actions_today["hard_exits"] += 1
                else:
                    self.risk_actions_today["soft_exits"] += 1
                
                # Send notification
                self._send_urgent_notification(
                    f"🚨 POSITION EXITED",
                    f"{position.strategy_name} {position.symbol}\n"
                    f"Reason: {reason}\n"
                    f"Position ID: {position.id}"
                )
                
                logger.critical(f"Position {position.id} auto-exited: {reason}")
            else:
                logger.error(f"Failed to auto-exit position {position.id}")
                
        except Exception as e:
            logger.error(f"Position exit trigger failed: {e}")
    
    def _trigger_mandatory_exit(self, reason: str):
        """Trigger mandatory exit for all positions"""
        try:
            with db_manager.get_session() as session:
                active_positions = session.query(Position).filter(
                    Position.status == "ACTIVE"
                ).all()
                
                for position in active_positions:
                    self._trigger_position_exit(position, ActionType.HARD_EXIT, reason)
                
                # Send global notification
                self._send_urgent_notification(
                    f"🚨 MANDATORY EXIT - ALL POSITIONS",
                    f"Reason: {reason}\n"
                    f"Positions affected: {len(active_positions)}"
                )
                
        except Exception as e:
            logger.error(f"Mandatory exit failed: {e}")
    
    def _handle_danger_zone_alert(self, danger_alert):
        """Handle danger zone alerts from danger monitor"""
        if danger_alert.danger_level == DangerLevel.CRITICAL:
            # Force exit all positions
            self._trigger_mandatory_exit(
                f"Danger zone critical: {danger_alert.message}"
            )
        elif danger_alert.danger_level == DangerLevel.EMERGENCY:
            # Emergency exit
            self._trigger_emergency_action(
                f"Danger zone emergency: {danger_alert.message}"
            )
    
    def _create_risk_alert(self, position, risk_level: RiskLevel, 
                          action_type: ActionType, message: str) -> RiskAlert:
        """Create and store risk alert"""
        alert = RiskAlert(
            timestamp=datetime.now(),
            risk_level=risk_level,
            action_type=action_type,
            symbol=position.symbol,
            strategy_name=position.strategy_name,
            message=message,
            mtm=self.position_risks.get(str(position.id), PositionRisk("", "", "", 0, 0, 0, 0, 0, 0, datetime.now())).current_mtm,
            position_size=position.lot_count,
            urgency="HIGH" if risk_level in [RiskLevel.CRITICAL, RiskLevel.EMERGENCY] else "MEDIUM"
        )
        
        # Store alert
        self.active_alerts[f"{position.id}_{datetime.now().timestamp()}"] = alert
        
        # Send notification if urgent
        if alert.urgency == "HIGH":
            self._send_risk_notification(alert)
        
        return alert
    
    def _send_risk_notification(self, alert: RiskAlert):
        """Send risk notification via WhatsApp"""
        if not self.whatsapp_notifier:
            return
        
        emoji_map = {
            RiskLevel.WARNING: "⚠️",
            RiskLevel.CRITICAL: "🚨",
            RiskLevel.EMERGENCY: "🔴"
        }
        
        emoji = emoji_map.get(alert.risk_level, "ℹ️")
        
        message = (
            f"{emoji} RISK ALERT\n"
            f"Strategy: {alert.strategy_name}\n"
            f"Symbol: {alert.symbol}\n"
            f"MTM: ₹{alert.mtm:,.0f}\n"
            f"Size: {alert.position_size} lots\n"
            f"Alert: {alert.message}"
        )
        
        success = self._send_notification("Risk Alert", message)
        alert.notification_sent = success
    
    def _send_notification(self, title: str, message: str) -> bool:
        """Send WhatsApp notification"""
        if not self.whatsapp_notifier:
            return False
        
        try:
            full_message = f"{title}\n{message}\nTime: {datetime.now().strftime('%H:%M:%S')}"
            return self.whatsapp_notifier.send_message(full_message)
        except Exception as e:
            logger.error(f"Notification send failed: {e}")
            return False
    
    def _send_urgent_notification(self, title: str, message: str) -> bool:
        """Send urgent notification with retry"""
        success = self._send_notification(title, message)
        
        # Retry once if failed
        if not success:
            threading.Event().wait(5)  # Wait 5 seconds
            success = self._send_notification(f"RETRY: {title}", message)
        
        return success
    
    # Helper methods (implement based on your system)
    def _get_current_market_data(self) -> Dict[str, Dict]:
        """Get current market data - integrate with your data provider"""
        # This would integrate with your market data provider
        # For now, return mock data structure
        return {
            "NIFTY": {"price": 22000, "change_pct": 0.5},
            "BANKNIFTY": {"price": 48000, "change_pct": -0.3}
        }
    
    def _calculate_position_mtm(self, position) -> float:
        """Calculate current mark-to-market for position"""
        # Integrate with your broker API or market data provider
        # This is a simplified implementation
        return 0.0  # Replace with actual MTM calculation
    
    def _get_strategy_risk_config(self, strategy_name: str) -> Dict[str, Any]:
        """Get risk configuration for strategy"""
        # Default risk parameters by strategy
        default_configs = {
            "IRON_CONDOR": {"sl_per_lot": 1500, "tp_per_lot": 3000},
            "BUTTERFLY_SPREAD": {"sl_per_lot": 1200, "tp_per_lot": 2500},
            "CALENDAR_SPREAD": {"sl_per_lot": 1500, "tp_per_lot": 3000},
            "HEDGED_STRANGLE": {"sl_per_lot": 2500, "tp_per_lot": 5000},
            "DIRECTIONAL_FUTURES": {"sl_per_lot": 3000, "tp_per_lot": 6000},
            "JADE_LIZARD": {"sl_per_lot": 2500, "tp_per_lot": 4500},
            "RATIO_SPREADS": {"sl_per_lot": 2200, "tp_per_lot": 4500},
            "BROKEN_WING_BUTTERFLY": {"sl_per_lot": 2000, "tp_per_lot": 4500}
        }
        
        return default_configs.get(strategy_name, {"sl_per_lot": 2000, "tp_per_lot": 4000})
    
    def _get_days_to_expiry(self, position) -> int:
        """Calculate days to expiry for position"""
        # Extract expiry from position and calculate days
        # This is a simplified implementation
        return 15  # Replace with actual calculation
    
    def _calculate_risk_score(self, current_mtm: float, max_loss: float, position) -> float:
        """Calculate composite risk score (0-100)"""
        # Simple risk score based on MTM vs max loss
        if max_loss == 0:
            return 0.0
        
        loss_ratio = abs(current_mtm) / abs(max_loss)
        risk_score = min(100.0, loss_ratio * 100)
        
        return risk_score
    
    def _calculate_total_daily_pnl(self) -> float:
        """Calculate total daily P&L across all positions"""
        total_pnl = 0.0
        for position_risk in self.position_risks.values():
            total_pnl += position_risk.current_mtm
        return total_pnl
    
    def _execute_position_exit(self, position) -> bool:
        """Execute position exit via broker - integrate with your broker"""
        # This would integrate with your broker adapter
        # Return True if successful, False otherwise
        return True  # Mock implementation
    
    def _block_new_entries(self, reason: str):
        """Block new position entries"""
        logger.warning(f"Blocking new entries: {reason}")
        self._send_notification("🚫 ENTRIES BLOCKED", reason)
        self.risk_actions_today["blocked_entries"] += 1
    
    def _warn_expiry_positions(self, symbol: str):
        """Warn about positions expiring soon"""
        message = f"Positions in {symbol} expire tomorrow - consider early exit"
        self._send_notification("⏰ EXPIRY WARNING", message)
    
    def _trigger_emergency_action(self, reason: str):
        """Trigger emergency actions - highest priority"""
        logger.critical(f"Emergency action triggered: {reason}")
        self._send_urgent_notification("🚨 EMERGENCY", reason)
        self.risk_actions_today["emergency_exits"] += 1
        
        # Additional emergency actions
        self.stop_monitoring()  # Stop all trading
    
    def _create_system_alert(self, message: str, urgency: str = "MEDIUM"):
        """Create system-level alert"""
        logger.warning(f"System alert: {message}")
        
        if urgency == "HIGH":
            self._send_urgent_notification("⚠️ SYSTEM ALERT", message)
        else:
            self._send_notification("⚠️ SYSTEM ALERT", message)
    
    def _process_pending_actions(self):
        """Process any pending risk actions"""
        # Clean up old alerts
        current_time = datetime.now()
        expired_alerts = [
            alert_id for alert_id, alert in self.active_alerts.items()
            if (current_time - alert.timestamp).seconds > 3600  # 1 hour
        ]
        
        for alert_id in expired_alerts:
            del self.active_alerts[alert_id]
    
    # Public interface methods - UPDATED with calendar features
    def get_risk_summary(self) -> Dict[str, Any]:
        """Get comprehensive risk summary - UPDATED"""
        return {
            "monitoring_active": self.is_monitoring,
            "total_positions": len(self.position_risks),
            "daily_pnl": self.daily_pnl,
            "active_alerts": len(self.active_alerts),
            "risk_actions_today": self.risk_actions_today.copy(),
            "high_risk_positions": len([
                r for r in self.position_risks.values() 
                if r.risk_score > 80
            ]),
            "calendar_blocked_symbols": list(self.calendar_blocked_symbols),
            "last_calendar_check": self.last_calendar_check.isoformat(),
            "last_updated": datetime.now().isoformat()
        }
    
    def force_exit_all_positions(self, reason: str = "Manual override"):
        """Manually force exit all positions"""
        self._trigger_mandatory_exit(f"Manual override: {reason}")
    
    def add_manual_alert(self, symbol: str, message: str, risk_level: RiskLevel = RiskLevel.WARNING):
        """Add manual risk alert"""
        # Create mock position object for alert
        class MockPosition:
            def __init__(self):
                self.id = "manual"
                self.symbol = symbol
                self.strategy_name = "MANUAL"
                self.lot_count = 0
        
        mock_position = MockPosition()
        self._create_risk_alert(mock_position, risk_level, ActionType.ALERT, message)
    
    def check_calendar_restrictions(self, symbol: str) -> Tuple[bool, str]:
        """Check if symbol is restricted due to calendar events - NEW METHOD"""
        try:
            # Force calendar check
            event_calendar.auto_refresh_check()
            
            # Check current restrictions
            should_avoid, reason = should_avoid_trading_today(symbol)
            
            return should_avoid, reason
            
        except Exception as e:
            logger.error(f"Calendar restriction check failed for {symbol}: {e}")
            return False, "Calendar check failed"
    
    def get_upcoming_calendar_events(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """Get upcoming calendar events that may affect trading - NEW METHOD"""
        try:
            events = event_calendar.get_upcoming_events(days_ahead)
            
            # Filter for NIFTY/BANKNIFTY relevant events
            relevant_events = []
            for event in events:
                if any(symbol in event.affected_instruments for symbol in ["NIFTY", "BANKNIFTY", "ALL"]):
                    relevant_events.append({
                        "date": event.date.isoformat(),
                        "title": event.title,
                        "impact_level": event.impact_level,
                        "trading_action": event.trading_action,
                        "affected_instruments": event.affected_instruments
                    })
            
            return relevant_events
            
        except Exception as e:
            logger.error(f"Failed to get upcoming calendar events: {e}")
            return []
    
    def refresh_calendar_data_manually(self):
        """Manually refresh calendar data - NEW METHOD"""
        try:
            logger.info("Manual calendar refresh initiated")
            event_calendar.refresh_event_data()
            
            # Re-check calendar restrictions after refresh
            self._check_calendar_events()
            
            self._send_notification(
                "📅 Calendar Refreshed",
                "Event calendar data has been manually refreshed"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Manual calendar refresh failed: {e}")
            return False

# Global risk monitor instance
risk_monitor = RiskMonitor()

# Convenience functions - UPDATED
def start_risk_monitoring():
    """Start the global risk monitor"""
    risk_monitor.start_monitoring()

def stop_risk_monitoring():
    """Stop the global risk monitor"""
    risk_monitor.stop_monitoring()

def get_risk_status() -> Dict[str, Any]:
    """Get current risk status"""
    return risk_monitor.get_risk_summary()

def force_exit_all():
    """Force exit all positions"""
    risk_monitor.force_exit_all_positions("Emergency manual exit")

def check_symbol_calendar_restrictions(symbol: str) -> Tuple[bool, str]:
    """Check calendar restrictions for symbol - NEW"""
    return risk_monitor.check_calendar_restrictions(symbol)

def get_upcoming_events(days: int = 7) -> List[Dict[str, Any]]:
    """Get upcoming calendar events - NEW"""
    return risk_monitor.get_upcoming_calendar_events(days)

def refresh_calendar_data():
    """Refresh calendar data - NEW"""
    return risk_monitor.refresh_calendar_data_manually()

# Export main components
__all__ = [
    "RiskMonitor",
    "RiskAlert", 
    "PositionRisk",
    "RiskLevel",
    "ActionType",
    "risk_monitor",
    "start_risk_monitoring",
    "stop_risk_monitoring", 
    "get_risk_status",
    "force_exit_all",
    "check_symbol_calendar_restrictions",
    "get_upcoming_events",
    "refresh_calendar_data"
]
