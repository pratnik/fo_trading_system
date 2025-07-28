"""
Danger Zone Monitor - Enhanced Real-time Index Movement Detection
- Advanced NIFTY/BANKNIFTY movement tracking with dynamic thresholds
- Integration with event calendar for enhanced risk assessment  
- Multi-timeframe analysis for better signal accuracy
- WhatsApp notifications and auto-exit triggers
- Support for intraday volatility patterns and market session analysis
- Compatible with risk monitor and strategy selector
"""

import logging
from datetime import datetime, timedelta, time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from collections import deque
import threading
import asyncio
from app.config import settings
from app.utils.event_calendar import event_calendar

logger = logging.getLogger("danger_zone")

class DangerLevel(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"      # 1.0% move
    RISK = "RISK"           # 1.25% move  
    CRITICAL = "CRITICAL"   # 1.5% move
    EMERGENCY = "EMERGENCY" # 2.0% move
    EXTREME = "EXTREME"     # 2.5% move (new level)

class SessionPhase(str, Enum):
    PRE_MARKET = "PRE_MARKET"       # 9:00-9:15 AM
    OPENING = "OPENING"             # 9:15-9:45 AM  
    MORNING = "MORNING"             # 9:45-11:30 AM
    MID_DAY = "MID_DAY"            # 11:30-1:30 PM
    AFTERNOON = "AFTERNOON"         # 1:30-3:00 PM
    CLOSING = "CLOSING"             # 3:00-3:30 PM
    POST_MARKET = "POST_MARKET"     # After 3:30 PM

@dataclass
class PricePoint:
    timestamp: datetime
    price: float
    volume: int
    change_pct: float
    session_phase: SessionPhase

@dataclass  
class DangerZoneAlert:
    timestamp: datetime
    symbol: str
    current_price: float
    price_change: float
    price_change_pct: float
    danger_level: DangerLevel
    session_phase: SessionPhase
    message: str
    action_required: str
    urgency: str
    volatility_context: Dict[str, float] = field(default_factory=dict)
    market_context: Dict[str, Any] = field(default_factory=dict)
    technical_indicators: Dict[str, float] = field(default_factory=dict)

@dataclass
class VolatilityProfile:
    symbol: str
    current_volatility: float
    session_avg_volatility: float
    daily_high_volatility: float
    volatility_percentile: float
    is_abnormal: bool
    last_updated: datetime

class DangerZoneMonitor:
    """
    Enhanced Real-time Danger Zone Monitoring System
    - Dynamic threshold adjustment based on market conditions
    - Multi-timeframe volatility analysis
    - Session-based risk assessment
    - Integration with event calendar and market context
    """
    
    def __init__(self):
        # Enhanced threshold system with session-based adjustments
        self.base_thresholds = {
            "warning": settings.DANGER_ZONE_WARNING,      # 1.0%
            "risk": settings.DANGER_ZONE_RISK,           # 1.25%  
            "critical": settings.DANGER_ZONE_EXIT,       # 1.5%
            "emergency": 2.0,                            # 2.0%
            "extreme": 2.5                               # 2.5%
        }
        
        # Session-based threshold multipliers
        self.session_multipliers = {
            SessionPhase.PRE_MARKET: 0.7,    # Lower thresholds pre-market
            SessionPhase.OPENING: 1.2,       # Higher thresholds during opening
            SessionPhase.MORNING: 1.0,       # Normal thresholds
            SessionPhase.MID_DAY: 0.9,       # Slightly lower during mid-day
            SessionPhase.AFTERNOON: 1.0,     # Normal thresholds
            SessionPhase.CLOSING: 1.3,       # Higher thresholds during closing
            SessionPhase.POST_MARKET: 0.8    # Lower thresholds post-market
        }
        
        # Enhanced data tracking
        self.price_history: Dict[str, deque] = {
            "NIFTY": deque(maxlen=1000),
            "BANKNIFTY": deque(maxlen=1000)
        }
        
        self.volatility_profiles: Dict[str, VolatilityProfile] = {}
        self.session_data: Dict[str, Dict] = {}
        self.alert_history: List[DangerZoneAlert] = []
        
        # Alert management
        self.last_alerts: Dict[str, DangerZoneAlert] = {}
        self.alert_cooldown = timedelta(minutes=3)  # Reduced cooldown for faster response
        self.escalation_cooldown = timedelta(minutes=1)  # Quick escalation
        
        # Daily tracking with enhanced metrics
        self.daily_metrics: Dict[str, Dict] = {
            "NIFTY": self._init_daily_metrics(),
            "BANKNIFTY": self._init_daily_metrics()
        }
        
        # Session start prices
        self.session_start_prices: Dict[str, float] = {}
        
        # Market context integration
        self.market_context = {
            "vix_level": 20.0,
            "market_trend": "NEUTRAL",
            "volume_surge": False,
            "news_impact": "NONE",
            "fii_activity": "NEUTRAL"
        }
        
        # Threading for real-time processing
        self.monitoring_active = False
        self.lock = threading.Lock()
        
        logger.info("Enhanced Danger Zone Monitor initialized")
    
    def _init_daily_metrics(self) -> Dict:
        """Initialize daily metrics structure"""
        return {
            "session_start_price": 0.0,
            "daily_high": 0.0,
            "daily_low": float('inf'),
            "max_positive_move": 0.0,
            "max_negative_move": 0.0,
            "volatility_events": 0,
            "danger_zone_breaches": 0,
            "last_major_move_time": None,
            "intraday_range": 0.0,
            "average_volatility": 0.0,
            "volume_weighted_price": 0.0,
            "total_volume": 0
        }
    
    def update_price(self, symbol: str, current_price: float, 
                    volume: int = 0, session_start_price: Optional[float] = None,
                    market_context: Optional[Dict] = None) -> Optional[DangerZoneAlert]:
        """
        Enhanced price update with comprehensive analysis
        """
        if symbol not in ["NIFTY", "BANKNIFTY"]:
            return None
        
        with self.lock:
            try:
                # Initialize session start price
                if session_start_price:
                    self.session_start_prices[symbol] = session_start_price
                elif symbol not in self.session_start_prices:
                    self.session_start_prices[symbol] = current_price
                
                # Update market context
                if market_context:
                    self.market_context.update(market_context)
                
                # Calculate price metrics
                start_price = self.session_start_prices[symbol]
                price_change = current_price - start_price
                price_change_pct = (price_change / start_price) * 100 if start_price > 0 else 0
                
                # Determine current session phase
                session_phase = self._get_current_session_phase()
                
                # Create price point
                price_point = PricePoint(
                    timestamp=datetime.now(),
                    price=current_price,
                    volume=volume,
                    change_pct=price_change_pct,
                    session_phase=session_phase
                )
                
                # Add to price history
                self.price_history[symbol].append(price_point)
                
                # Update daily metrics
                self._update_daily_metrics(symbol, price_point)
                
                # Update volatility profile
                self._update_volatility_profile(symbol)
                
                # Enhanced danger level calculation
                danger_level, adjusted_thresholds = self._calculate_enhanced_danger_level(
                    symbol, abs(price_change_pct), session_phase
                )
                
                # Check for alert conditions
                alert = self._evaluate_alert_conditions(
                    symbol, current_price, price_change, price_change_pct, 
                    danger_level, session_phase, adjusted_thresholds
                )
                
                if alert:
                    self.last_alerts[symbol] = alert
                    self.alert_history.append(alert)
                    
                    # Keep alert history manageable
                    if len(self.alert_history) > 500:
                        self.alert_history = self.alert_history[-400:]
                    
                    logger.warning(f"🚨 ENHANCED DANGER ZONE ALERT: {alert.message}")
                
                return alert
                
            except Exception as e:
                logger.error(f"Error in enhanced price update for {symbol}: {e}")
                return None
    
    def _get_current_session_phase(self) -> SessionPhase:
        """Determine current market session phase"""
        current_time = datetime.now().time()
        
        if time(9, 0) <= current_time < time(9, 15):
            return SessionPhase.PRE_MARKET
        elif time(9, 15) <= current_time < time(9, 45):
            return SessionPhase.OPENING
        elif time(9, 45) <= current_time < time(11, 30):
            return SessionPhase.MORNING
        elif time(11, 30) <= current_time < time(13, 30):
            return SessionPhase.MID_DAY
        elif time(13, 30) <= current_time < time(15, 0):
            return SessionPhase.AFTERNOON
        elif time(15, 0) <= current_time < time(15, 30):
            return SessionPhase.CLOSING
        else:
            return SessionPhase.POST_MARKET
    
    def _update_daily_metrics(self, symbol: str, price_point: PricePoint):
        """Update comprehensive daily metrics"""
        metrics = self.daily_metrics[symbol]
        price = price_point.price
        change_pct = price_point.change_pct
        
        # Update price extremes
        metrics["daily_high"] = max(metrics["daily_high"], price)
        metrics["daily_low"] = min(metrics["daily_low"], price)
        
        # Update move extremes
        metrics["max_positive_move"] = max(metrics["max_positive_move"], change_pct)
        metrics["max_negative_move"] = min(metrics["max_negative_move"], change_pct)
        
        # Update intraday range
        if metrics["daily_low"] != float('inf'):
            metrics["intraday_range"] = ((metrics["daily_high"] - metrics["daily_low"]) / 
                                       metrics["daily_low"]) * 100
        
        # Track volatility events (moves > 0.5%)
        if abs(change_pct) > 0.5:
            metrics["volatility_events"] += 1
        
        # Track danger zone breaches
        if abs(change_pct) >= self.base_thresholds["warning"]:
            metrics["danger_zone_breaches"] += 1
            metrics["last_major_move_time"] = datetime.now()
        
        # Update volume metrics
        if price_point.volume > 0:
            total_vol = metrics["total_volume"]
            metrics["volume_weighted_price"] = (
                (metrics["volume_weighted_price"] * total_vol + price * price_point.volume) /
                (total_vol + price_point.volume)
            )
            metrics["total_volume"] += price_point.volume
    
    def _update_volatility_profile(self, symbol: str):
        """Update volatility profile with rolling calculations"""
        if len(self.price_history[symbol]) < 10:
            return
        
        # Get recent price points (last 30 minutes)
        recent_points = [p for p in self.price_history[symbol] 
                        if (datetime.now() - p.timestamp).seconds <= 1800]
        
        if len(recent_points) < 5:
            return
        
        # Calculate various volatility measures
        changes = [p.change_pct for p in recent_points]
        
        current_volatility = np.std(changes) if len(changes) > 1 else 0
        session_avg_volatility = np.mean([abs(c) for c in changes])
        
        # Calculate volatility percentile (compared to recent history)
        all_changes = [p.change_pct for p in self.price_history[symbol]]
        volatility_percentile = (sum(1 for c in all_changes if abs(c) < abs(changes[-1])) / 
                               len(all_changes) * 100) if all_changes else 50
        
        # Determine if current volatility is abnormal
        is_abnormal = (current_volatility > session_avg_volatility * 2.0 or 
                      volatility_percentile > 90)
        
        self.volatility_profiles[symbol] = VolatilityProfile(
            symbol=symbol,
            current_volatility=current_volatility,
            session_avg_volatility=session_avg_volatility,
            daily_high_volatility=max(current_volatility, 
                                    self.volatility_profiles.get(symbol, 
                                    VolatilityProfile("", 0, 0, 0, 0, False, datetime.now())).daily_high_volatility),
            volatility_percentile=volatility_percentile,
            is_abnormal=is_abnormal,
            last_updated=datetime.now()
        )
    
    def _calculate_enhanced_danger_level(self, symbol: str, abs_change_pct: float, 
                                       session_phase: SessionPhase) -> Tuple[DangerLevel, Dict]:
        """Calculate danger level with enhanced logic"""
        
        # Get base thresholds
        base_thresholds = self.base_thresholds.copy()
        
        # Apply session multiplier
        session_multiplier = self.session_multipliers.get(session_phase, 1.0)
        
        # Apply volatility adjustment
        volatility_multiplier = self._get_volatility_multiplier(symbol)
        
        # Apply event calendar adjustment
        calendar_multiplier = self._get_calendar_multiplier(symbol)
        
        # Apply market context adjustment
        context_multiplier = self._get_market_context_multiplier()
        
        # Calculate final multiplier
        final_multiplier = session_multiplier * volatility_multiplier * calendar_multiplier * context_multiplier
        
        # Adjust thresholds
        adjusted_thresholds = {
            level: threshold * final_multiplier 
            for level, threshold in base_thresholds.items()
        }
        
        # Determine danger level
        if abs_change_pct >= adjusted_thresholds["extreme"]:
            danger_level = DangerLevel.EXTREME
        elif abs_change_pct >= adjusted_thresholds["emergency"]:
            danger_level = DangerLevel.EMERGENCY
        elif abs_change_pct >= adjusted_thresholds["critical"]:
            danger_level = DangerLevel.CRITICAL
        elif abs_change_pct >= adjusted_thresholds["risk"]:
            danger_level = DangerLevel.RISK
        elif abs_change_pct >= adjusted_thresholds["warning"]:
            danger_level = DangerLevel.WARNING
        else:
            danger_level = DangerLevel.SAFE
        
        return danger_level, adjusted_thresholds
    
    def _get_volatility_multiplier(self, symbol: str) -> float:
        """Get volatility-based threshold multiplier"""
        if symbol not in self.volatility_profiles:
            return 1.0
        
        vol_profile = self.volatility_profiles[symbol]
        
        # If volatility is abnormally high, lower thresholds (more sensitive)
        if vol_profile.is_abnormal:
            return 0.8
        
        # If volatility is very low, raise thresholds (less sensitive)
        if vol_profile.current_volatility < 0.1:
            return 1.3
        
        return 1.0
    
    def _get_calendar_multiplier(self, symbol: str) -> float:
        """Get calendar event-based threshold multiplier"""
        try:
            # Check for events today
            today_events = event_calendar.get_events_for_date(datetime.now().date())
            
            # Check for high impact events
            high_impact_events = [e for e in today_events 
                                if e.impact_level in ["HIGH", "CRITICAL"] and 
                                symbol in e.affected_instruments]
            
            if high_impact_events:
                return 0.7  # Lower thresholds on event days (more sensitive)
            
            # Check for expiry day
            expiry_events = [e for e in today_events if e.event_type == "EXPIRY_DAY"]
            if expiry_events:
                return 0.8  # Slightly lower thresholds on expiry
            
            return 1.0
            
        except Exception as e:
            logger.debug(f"Calendar multiplier calculation failed: {e}")
            return 1.0
    
    def _get_market_context_multiplier(self) -> float:
        """Get market context-based threshold multiplier"""
        multiplier = 1.0
        
        # VIX-based adjustment
        vix = self.market_context.get("vix_level", 20)
        if vix > 30:
            multiplier *= 0.8  # More sensitive in high VIX environment
        elif vix < 15:
            multiplier *= 1.2  # Less sensitive in low VIX environment
        
        # Volume surge adjustment
        if self.market_context.get("volume_surge", False):
            multiplier *= 0.9  # Slightly more sensitive during volume surges
        
        # News impact adjustment
        news_impact = self.market_context.get("news_impact", "NONE")
        if news_impact == "HIGH":
            multiplier *= 0.7
        elif news_impact == "MEDIUM":
            multiplier *= 0.85
        
        return multiplier
    
    def _evaluate_alert_conditions(self, symbol: str, current_price: float, 
                                 price_change: float, price_change_pct: float,
                                 danger_level: DangerLevel, session_phase: SessionPhase,
                                 adjusted_thresholds: Dict) -> Optional[DangerZoneAlert]:
        """Evaluate whether to trigger an alert with enhanced conditions"""
        
        if danger_level == DangerLevel.SAFE:
            return None
        
        # Check for alert escalation
        should_alert, alert_reason = self._should_trigger_alert(symbol, danger_level)
        
        if not should_alert:
            return None
        
        # Create enhanced alert
        alert = self._create_enhanced_alert(
            symbol, current_price, price_change, price_change_pct, 
            danger_level, session_phase, adjusted_thresholds, alert_reason
        )
        
        return alert
    
    def _should_trigger_alert(self, symbol: str, danger_level: DangerLevel) -> Tuple[bool, str]:
        """Enhanced alert triggering logic"""
        
        # Always trigger for extreme levels
        if danger_level in [DangerLevel.EXTREME, DangerLevel.EMERGENCY]:
            return True, "EXTREME_LEVEL"
        
        # Always trigger critical on first occurrence
        if danger_level == DangerLevel.CRITICAL:
            last_alert = self.last_alerts.get(symbol)
            if not last_alert or last_alert.danger_level != DangerLevel.CRITICAL:
                return True, "CRITICAL_FIRST"
        
        # Check escalation conditions
        last_alert = self.last_alerts.get(symbol)
        if last_alert:
            time_since_last = datetime.now() - last_alert.timestamp
            
            # Escalation logic
            if (danger_level.value > last_alert.danger_level.value and 
                time_since_last >= self.escalation_cooldown):
                return True, "ESCALATION"
            
            # Repeat alert logic for sustained danger
            if (danger_level == last_alert.danger_level and 
                time_since_last >= self.alert_cooldown and
                danger_level in [DangerLevel.CRITICAL, DangerLevel.EMERGENCY]):
                return True, "SUSTAINED_DANGER"
            
            # Skip if within cooldown
            if time_since_last < self.alert_cooldown:
                return False, "COOLDOWN"
        
        # Default trigger for first alerts
        return True, "FIRST_ALERT"
    
    def _create_enhanced_alert(self, symbol: str, current_price: float, 
                             price_change: float, price_change_pct: float,
                             danger_level: DangerLevel, session_phase: SessionPhase,
                             adjusted_thresholds: Dict, alert_reason: str) -> DangerZoneAlert:
        """Create enhanced alert with comprehensive context"""
        
        # Generate contextual message
        direction = "📈" if price_change > 0 else "📉"
        session_emoji = self._get_session_emoji(session_phase)
        
        base_message = f"{direction} {symbol} moved {abs(price_change_pct):.2f}% {session_emoji}"
        
        # Add context based on alert reason
        if alert_reason == "ESCALATION":
            message = f"🚨 ESCALATION: {base_message}"
        elif alert_reason == "SUSTAINED_DANGER":
            message = f"⚠️ SUSTAINED: {base_message}"
        elif alert_reason == "EXTREME_LEVEL":
            message = f"🔴 EXTREME MOVE: {base_message}"
        else:
            message = base_message
        
        # Add session context
        message += f" [{session_phase.value}]"
        
        # Determine action and urgency
        action_map = {
            DangerLevel.WARNING: "MONITOR_CLOSELY",
            DangerLevel.RISK: "PREPARE_EXIT",
            DangerLevel.CRITICAL: "AUTO_EXIT",
            DangerLevel.EMERGENCY: "EMERGENCY_EXIT",
            DangerLevel.EXTREME: "IMMEDIATE_EXIT"
        }
        
        urgency_map = {
            DangerLevel.WARNING: "MEDIUM",
            DangerLevel.RISK: "HIGH",
            DangerLevel.CRITICAL: "CRITICAL",
            DangerLevel.EMERGENCY: "CRITICAL",
            DangerLevel.EXTREME: "CRITICAL"
        }
        
        # Get volatility context
        vol_context = {}
        if symbol in self.volatility_profiles:
            vol_profile = self.volatility_profiles[symbol]
            vol_context = {
                "current_volatility": vol_profile.current_volatility,
                "volatility_percentile": vol_profile.volatility_percentile,
                "is_abnormal_volatility": vol_profile.is_abnormal
            }
        
        # Get market context
        market_context = self.market_context.copy()
        market_context.update({
            "session_phase": session_phase.value,
            "adjusted_thresholds": adjusted_thresholds,
            "alert_reason": alert_reason
        })
        
        # Calculate technical indicators
        technical_indicators = self._calculate_technical_indicators(symbol)
        
        return DangerZoneAlert(
            timestamp=datetime.now(),
            symbol=symbol,
            current_price=current_price,
            price_change=price_change,
            price_change_pct=price_change_pct,
            danger_level=danger_level,
            session_phase=session_phase,
            message=message,
            action_required=action_map.get(danger_level, "MONITOR"),
            urgency=urgency_map.get(danger_level, "MEDIUM"),
            volatility_context=vol_context,
            market_context=market_context,
            technical_indicators=technical_indicators
        )
    
    def _get_session_emoji(self, session_phase: SessionPhase) -> str:
        """Get emoji for session phase"""
        emoji_map = {
            SessionPhase.PRE_MARKET: "🌅",
            SessionPhase.OPENING: "🔔",
            SessionPhase.MORNING: "🌄", 
            SessionPhase.MID_DAY: "☀️",
            SessionPhase.AFTERNOON: "🌇",
            SessionPhase.CLOSING: "🔕",
            SessionPhase.POST_MARKET: "🌃"
        }
        return emoji_map.get(session_phase, "📊")
    
    def _calculate_technical_indicators(self, symbol: str) -> Dict[str, float]:
        """Calculate basic technical indicators"""
        if len(self.price_history[symbol]) < 20:
            return {}
        
        # Get recent prices
        recent_prices = [p.price for p in list(self.price_history[symbol])[-20:]]
        
        # Simple moving averages
        sma_5 = np.mean(recent_prices[-5:]) if len(recent_prices) >= 5 else 0
        sma_10 = np.mean(recent_prices[-10:]) if len(recent_prices) >= 10 else 0
        sma_20 = np.mean(recent_prices) if len(recent_prices) >= 20 else 0
        
        # Price position relative to moving averages
        current_price = recent_prices[-1]
        price_vs_sma5 = ((current_price - sma_5) / sma_5 * 100) if sma_5 > 0 else 0
        price_vs_sma20 = ((current_price - sma_20) / sma_20 * 100) if sma_20 > 0 else 0
        
        # Momentum (rate of change)
        momentum_5 = ((current_price - recent_prices[-6]) / recent_prices[-6] * 100) if len(recent_prices) >= 6 else 0
        
        return {
            "sma_5": sma_5,
            "sma_10": sma_10,
            "sma_20": sma_20,
            "price_vs_sma5_pct": price_vs_sma5,
            "price_vs_sma20_pct": price_vs_sma20,
            "momentum_5min": momentum_5,
            "current_price": current_price
        }
    
    # Additional utility methods
    
    def check_multiple_symbols(self, price_data: Dict[str, Dict]) -> List[DangerZoneAlert]:
        """Check danger zones for multiple symbols simultaneously"""
        alerts = []
        for symbol, data in price_data.items():
            if symbol in ["NIFTY", "BANKNIFTY"]:
                alert = self.update_price(
                    symbol=symbol,
                    current_price=data.get("price", 0),
                    volume=data.get("volume", 0),
                    market_context=data.get("context", {})
                )
                if alert:
                    alerts.append(alert)
        return alerts
    
    def get_enhanced_status(self) -> Dict[str, Any]:
        """Get comprehensive danger zone status"""
        status = {}
        
        for symbol in ["NIFTY", "BANKNIFTY"]:
            if symbol in self.session_start_prices and self.price_history[symbol]:
                latest = list(self.price_history[symbol])[-1]
                
                # Get current danger level
                danger_level, adjusted_thresholds = self._calculate_enhanced_danger_level(
                    symbol, abs(latest.change_pct), latest.session_phase
                )
                
                # Get volatility profile
                vol_profile = self.volatility_profiles.get(symbol)
                
                status[symbol] = {
                    "current_price": latest.price,
                    "session_change_pct": latest.change_pct,
                    "danger_level": danger_level.value,
                    "session_phase": latest.session_phase.value,
                    "daily_metrics": self.daily_metrics[symbol].copy(),
                    "volatility_profile": {
                        "current": vol_profile.current_volatility if vol_profile else 0,
                        "percentile": vol_profile.volatility_percentile if vol_profile else 50,
                        "is_abnormal": vol_profile.is_abnormal if vol_profile else False
                    } if vol_profile else {},
                    "adjusted_thresholds": adjusted_thresholds,
                    "last_update": latest.timestamp.isoformat(),
                    "data_points": len(self.price_history[symbol])
                }
        
        return {
            "symbols": status,
            "market_context": self.market_context,
            "total_alerts_today": len(self.alert_history),
            "monitoring_active": self.monitoring_active,
            "last_refresh": datetime.now().isoformat()
        }
    
    def get_alert_summary(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get summary of alerts in the specified time period"""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        
        recent_alerts = [
            alert for alert in self.alert_history 
            if alert.timestamp >= cutoff_time
        ]
        
        # Group by symbol and danger level
        summary = {"NIFTY": {}, "BANKNIFTY": {}}
        
        for alert in recent_alerts:
            symbol = alert.symbol
            level = alert.danger_level.value
            
            if level not in summary[symbol]:
                summary[symbol][level] = 0
            summary[symbol][level] += 1
        
        return {
            "time_period_hours": hours_back,
            "total_alerts": len(recent_alerts),
            "alerts_by_symbol": summary,
            "highest_alert_level": max([a.danger_level.value for a in recent_alerts]) if recent_alerts else "SAFE",
            "most_recent_alert": recent_alerts[-1].timestamp.isoformat() if recent_alerts else None
        }
    
    def reset_daily_tracking(self):
        """Reset daily tracking data (call at market open)"""
        with self.lock:
            for symbol in ["NIFTY", "BANKNIFTY"]:
                self.daily_metrics[symbol] = self._init_daily_metrics()
                self.price_history[symbol].clear()
                self.volatility_profiles.pop(symbol, None)
            
            self.session_start_prices.clear()
            self.last_alerts.clear()
            self.alert_history.clear()
            
            logger.info("Enhanced danger zone daily tracking reset")
    
    def is_safe_to_enter(self, symbol: str) -> Tuple[bool, str, Dict]:
        """Enhanced safety check for new position entries"""
        if symbol not in self.price_history or not self.price_history[symbol]:
            return True, "No recent data available", {}
        
        latest = list(self.price_history[symbol])[-1]
        danger_level, thresholds = self._calculate_enhanced_danger_level(
            symbol, abs(latest.change_pct), latest.session_phase
        )
        
        # Check recent volatility
        vol_profile = self.volatility_profiles.get(symbol)
        is_volatile = vol_profile and vol_profile.is_abnormal
        
        # Check recent alerts
        recent_critical_alerts = [
            a for a in self.alert_history[-10:] 
            if a.symbol == symbol and a.danger_level in [DangerLevel.CRITICAL, DangerLevel.EMERGENCY, DangerLevel.EXTREME]
        ]
        
        # Safety determination
        if danger_level in [DangerLevel.CRITICAL, DangerLevel.EMERGENCY, DangerLevel.EXTREME]:
            return False, f"Current danger level: {danger_level.value}", {"danger_level": danger_level.value}
        
        if is_volatile:
            return False, "Abnormal volatility detected", {"volatility_abnormal": True}
        
        if recent_critical_alerts:
            return False, f"Recent critical alerts: {len(recent_critical_alerts)}", {"recent_critical_alerts": len(recent_critical_alerts)}
        
        # Check session phase
        if latest.session_phase in [SessionPhase.OPENING, SessionPhase.CLOSING]:
            return False, f"Volatile session phase: {latest.session_phase.value}", {"session_phase": latest.session_phase.value}
        
        return True, "Safe for entry", {
            "danger_level": danger_level.value,
            "session_phase": latest.session_phase.value,
            "volatility_normal": not is_volatile
        }
    
    def should_exit_positions(self, symbol: str) -> Tuple[bool, str, Dict]:
        """Enhanced position exit recommendation"""
        if symbol not in self.price_history or not self.price_history[symbol]:
            return False, "No data available", {}
        
        latest = list(self.price_history[symbol])[-1]
        danger_level, thresholds = self._calculate_enhanced_danger_level(
            symbol, abs(latest.change_pct), latest.session_phase
        )
        
        # Immediate exit conditions
        if danger_level in [DangerLevel.EMERGENCY, DangerLevel.EXTREME]:
            return True, f"Emergency exit required: {danger_level.value}", {
                "exit_reason": "EMERGENCY_LEVEL",
                "danger_level": danger_level.value
            }
        
        # Critical level with additional factors
        if danger_level == DangerLevel.CRITICAL:
            vol_profile = self.volatility_profiles.get(symbol)
            if vol_profile and vol_profile.is_abnormal:
                return True, "Critical level with abnormal volatility", {
                    "exit_reason": "CRITICAL_WITH_VOLATILITY",
                    "danger_level": danger_level.value
                }
        
        return False, f"Current level manageable: {danger_level.value}", {
            "danger_level": danger_level.value
        }
    
    def update_market_context(self, context_update: Dict[str, Any]):
        """Update market context information"""
        self.market_context.update(context_update)
        logger.debug(f"Market context updated: {context_update}")

# Global enhanced danger zone monitor instance
danger_monitor = DangerZoneMonitor()

# Export main components
__all__ = [
    "DangerZoneMonitor", 
    "DangerZoneAlert", 
    "DangerLevel",
    "SessionPhase",
    "VolatilityProfile",
    "PricePoint", 
    "danger_monitor"
]
