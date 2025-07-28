"""
Expiry Day Management - Enhanced Version with Future-Proof Calendar Integration
- Integrates with dynamic event calendar system
- Automatic holiday detection for any year
- Enhanced expiry calculations with NSE API integration
- Strategy adjustments and auto-exit logic
- Compatible with future-proof event calendar
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import calendar

logger = logging.getLogger("expiry_day")

class ExpiryType(str, Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"

class ExpiryAction(str, Enum):
    BLOCK_ENTRY = "BLOCK_ENTRY"
    EARLY_EXIT = "EARLY_EXIT"
    STRATEGY_ADJUST = "STRATEGY_ADJUST"
    NORMAL_TRADING = "NORMAL_TRADING"
    FORCE_EXIT = "FORCE_EXIT"

@dataclass
class ExpiryInfo:
    date: date
    expiry_type: ExpiryType
    symbol: str
    days_to_expiry: int
    is_today: bool
    is_tomorrow: bool
    recommended_action: ExpiryAction
    message: str
    settlement_date: Optional[date] = None
    last_trading_day: Optional[date] = None

class ExpiryDayManager:
    """
    Enhanced Expiry Day Manager with Future-Proof Calendar Integration
    Manages F&O expiry day logic for NIFTY and BANKNIFTY with dynamic calendar
    """
    
    def __init__(self):
        # Import event calendar for integration
        try:
            from app.utils.event_calendar import event_calendar
            self.event_calendar = event_calendar
            logger.info("Integrated with future-proof event calendar")
        except ImportError:
            logger.warning("Event calendar not available - using basic expiry logic")
            self.event_calendar = None
        
        # Expiry day rules (enhanced with more instruments)
        self.weekly_expiry_day = 3  # Thursday (0=Monday, 3=Thursday)
        self.monthly_expiry_rules = {
            "NIFTY": "last_thursday",
            "BANKNIFTY": "last_thursday",
            "FINNIFTY": "last_tuesday",
            "MIDCPNIFTY": "last_monday"
        }
        
        # Strategy restrictions on expiry day (enhanced)
        self.expiry_day_restrictions = {
            "IRON_CONDOR": "BLOCK_ENTRY",
            "BUTTERFLY_SPREAD": "BLOCK_ENTRY", 
            "CALENDAR_SPREAD": "EARLY_EXIT",
            "HEDGED_STRANGLE": "STRATEGY_ADJUST",
            "JADE_LIZARD": "STRATEGY_ADJUST",
            "RATIO_SPREADS": "EARLY_EXIT",
            "BROKEN_WING_BUTTERFLY": "BLOCK_ENTRY",
            "DIRECTIONAL_FUTURES": "NORMAL_TRADING"  # Only strategy allowed on expiry
        }
        
        # Enhanced risk parameters for expiry periods
        self.expiry_risk_multipliers = {
            0: 0.3,   # Expiry day - very conservative
            1: 0.5,   # 1 day to expiry - conservative
            2: 0.7,   # 2 days to expiry - moderate
            3: 0.8,   # 3 days to expiry - slightly conservative
            4: 0.9,   # 4 days to expiry - normal with slight adjustment
            5: 1.0    # 5+ days to expiry - normal
        }
        
        # Time-based exit rules for expiry day
        self.expiry_day_exit_times = {
            "morning_exit": "10:30",    # 10:30 AM - first exit window
            "afternoon_exit": "14:30",  # 2:30 PM - final exit window
            "force_exit": "15:00"       # 3:00 PM - force exit all positions
        }
        
    def get_next_expiry_date(self, symbol: str, expiry_type: ExpiryType = ExpiryType.WEEKLY,
                           reference_date: Optional[date] = None) -> Optional[date]:
        """Get next expiry date using enhanced calendar integration"""
        
        # Use event calendar if available
        if self.event_calendar:
            try:
                expiry_date = self.event_calendar.get_expiry_date(
                    symbol, 
                    expiry_type.value.lower(), 
                    reference_date
                )
                return expiry_date
            except Exception as e:
                logger.warning(f"Event calendar expiry lookup failed: {e}")
        
        # Fallback to local calculation
        return self._calculate_expiry_local(symbol, expiry_type, reference_date)
    
    def _calculate_expiry_local(self, symbol: str, expiry_type: ExpiryType, 
                              reference_date: Optional[date] = None) -> Optional[date]:
        """Local expiry calculation as fallback"""
        ref_date = reference_date or date.today()
        
        if expiry_type == ExpiryType.WEEKLY:
            return self._get_next_weekly_expiry_local(ref_date)
        elif expiry_type == ExpiryType.MONTHLY:
            return self._get_next_monthly_expiry_local(symbol, ref_date)
        else:
            logger.error(f"Unsupported expiry type: {expiry_type}")
            return None
    
    def _get_next_weekly_expiry_local(self, ref_date: date) -> date:
        """Calculate next weekly expiry (Thursday) with holiday adjustment"""
        days_ahead = self.weekly_expiry_day - ref_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        expiry_date = ref_date + timedelta(days=days_ahead)
        
        # Adjust for holidays using event calendar if available
        if self.event_calendar:
            while self.event_calendar.is_market_holiday(expiry_date):
                expiry_date -= timedelta(days=1)
        else:
            # Basic weekend check
            while expiry_date.weekday() >= 5:
                expiry_date -= timedelta(days=1)
                
        return expiry_date
    
    def _get_next_monthly_expiry_local(self, symbol: str, ref_date: date) -> date:
        """Calculate next monthly expiry with holiday adjustment"""
        if symbol not in self.monthly_expiry_rules:
            logger.warning(f"No monthly expiry rules for {symbol}, using default")
            symbol = "NIFTY"
        
        rule = self.monthly_expiry_rules[symbol]
        
        # Determine target weekday
        if "thursday" in rule:
            target_weekday = 3
        elif "tuesday" in rule:
            target_weekday = 1
        elif "monday" in rule:
            target_weekday = 0
        else:
            target_weekday = 3  # Default to Thursday
        
        # Find last occurrence in current month
        year = ref_date.year
        month = ref_date.month
        
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)
        
        days_back = (last_date.weekday() - target_weekday) % 7
        monthly_expiry = last_date - timedelta(days=days_back)
        
        # If monthly expiry has passed, get next month
        if monthly_expiry <= ref_date:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
                
            last_day = calendar.monthrange(year, month)[1]
            last_date = date(year, month, last_day)
            days_back = (last_date.weekday() - target_weekday) % 7
            monthly_expiry = last_date - timedelta(days=days_back)
        
        # Adjust for holidays
        if self.event_calendar:
            while self.event_calendar.is_market_holiday(monthly_expiry):
                monthly_expiry -= timedelta(days=1)
        else:
            while monthly_expiry.weekday() >= 5:
                monthly_expiry -= timedelta(days=1)
                
        return monthly_expiry
    
    def is_expiry_day(self, check_date: Optional[date] = None, 
                     symbol: str = "NIFTY") -> Tuple[bool, Optional[ExpiryInfo]]:
        """Enhanced expiry day check with comprehensive info"""
        check_date = check_date or date.today()
        
        try:
            # Get all expiry information using enhanced calendar
            expiry_info = self.get_expiry_info(symbol, check_date)
            
            if expiry_info.is_today:
                return True, expiry_info
            else:
                return False, expiry_info
                
        except Exception as e:
            logger.error(f"Expiry day check failed: {e}")
            return False, None
    
    def get_expiry_info(self, symbol: str, reference_date: Optional[date] = None) -> ExpiryInfo:
        """Get comprehensive expiry information with enhanced calendar integration"""
        ref_date = reference_date or date.today()
        
        try:
            # Get expiry information from event calendar if available
            if self.event_calendar:
                expiry_data = self.event_calendar.get_next_expiry_info(symbol)
                
                if "error" not in expiry_data:
                    next_expiry = date.fromisoformat(expiry_data["next_expiry_date"])
                    expiry_type = ExpiryType(expiry_data["expiry_type"])
                    days_to_expiry = expiry_data["days_to_expiry"]
                    is_today = expiry_data["is_today"]
                    is_tomorrow = expiry_data["is_tomorrow"]
                    settlement_date = date.fromisoformat(expiry_data["settlement_date"])
                else:
                    # Fallback to local calculation
                    next_expiry = self._calculate_expiry_local(symbol, ExpiryType.WEEKLY, ref_date)
                    expiry_type = ExpiryType.WEEKLY
                    days_to_expiry = (next_expiry - ref_date).days if next_expiry else 0
                    is_today = days_to_expiry == 0
                    is_tomorrow = days_to_expiry == 1
                    settlement_date = self._get_settlement_date(next_expiry) if next_expiry else None
            else:
                # Use local calculation
                next_expiry = self._calculate_expiry_local(symbol, ExpiryType.WEEKLY, ref_date)
                expiry_type = ExpiryType.WEEKLY
                days_to_expiry = (next_expiry - ref_date).days if next_expiry else 0
                is_today = days_to_expiry == 0
                is_tomorrow = days_to_expiry == 1
                settlement_date = self._get_settlement_date(next_expiry) if next_expiry else None
            
            # Determine recommended action
            recommended_action, message = self._get_recommended_action(
                days_to_expiry, is_today, is_tomorrow, expiry_type, symbol
            )
            
            return ExpiryInfo(
                date=next_expiry,
                expiry_type=expiry_type,
                symbol=symbol,
                days_to_expiry=days_to_expiry,
                is_today=is_today,
                is_tomorrow=is_tomorrow,
                recommended_action=recommended_action,
                message=message,
                settlement_date=settlement_date,
                last_trading_day=next_expiry
            )
            
        except Exception as e:
            logger.error(f"Failed to get expiry info for {symbol}: {e}")
            # Return safe default
            return ExpiryInfo(
                date=ref_date + timedelta(days=7),
                expiry_type=ExpiryType.WEEKLY,
                symbol=symbol,
                days_to_expiry=7,
                is_today=False,
                is_tomorrow=False,
                recommended_action=ExpiryAction.NORMAL_TRADING,
                message="Error getting expiry info - using safe defaults",
                settlement_date=ref_date + timedelta(days=8)
            )
    
    def _get_recommended_action(self, days_to_expiry: int, is_today: bool, 
                               is_tomorrow: bool, expiry_type: ExpiryType, 
                               symbol: str) -> Tuple[ExpiryAction, str]:
        """Get recommended action based on expiry proximity"""
        
        if is_today:
            if expiry_type == ExpiryType.MONTHLY:
                return ExpiryAction.FORCE_EXIT, f"Today is {symbol} monthly expiry - Force exit all positions"
            else:
                return ExpiryAction.BLOCK_ENTRY, f"Today is {symbol} weekly expiry - Block new entries"
        
        elif is_tomorrow:
            return ExpiryAction.EARLY_EXIT, f"Tomorrow is {symbol} expiry - Consider early exit"
        
        elif days_to_expiry <= 3:
            return ExpiryAction.STRATEGY_ADJUST, f"{days_to_expiry} days to {symbol} expiry - Adjust strategy parameters"
        
        elif days_to_expiry <= 7:
            return ExpiryAction.NORMAL_TRADING, f"{days_to_expiry} days to {symbol} expiry - Normal trading with monitoring"
        
        else:
            return ExpiryAction.NORMAL_TRADING, f"{days_to_expiry} days to {symbol} expiry - Normal trading"
    
    def _get_settlement_date(self, expiry_date: date) -> date:
        """Calculate settlement date (next trading day after expiry)"""
        if self.event_calendar:
            return self.event_calendar.get_next_trading_day(expiry_date)
        else:
            # Basic calculation - next weekday
            settlement = expiry_date + timedelta(days=1)
            while settlement.weekday() >= 5:
                settlement += timedelta(days=1)
            return settlement
    
    def should_block_strategy(self, strategy_name: str, symbol: str) -> Tuple[bool, str]:
        """Enhanced strategy blocking with calendar integration"""
        try:
            expiry_info = self.get_expiry_info(symbol)
            
            if strategy_name not in self.expiry_day_restrictions:
                return False, "Strategy not in expiry restrictions"
                
            restriction = self.expiry_day_restrictions[strategy_name]
            
            # Block entry restrictions
            if expiry_info.is_today and restriction == "BLOCK_ENTRY":
                return True, f"Blocked: {strategy_name} not allowed on expiry day"
            
            elif expiry_info.is_tomorrow and restriction in ["BLOCK_ENTRY", "EARLY_EXIT"]:
                return True, f"Blocked: {strategy_name} restricted before expiry"
            
            elif expiry_info.days_to_expiry <= 3 and restriction == "STRATEGY_ADJUST":
                return False, f"Allowed with adjustment: {strategy_name} near expiry"
            
            # Force exit restrictions
            elif expiry_info.recommended_action == ExpiryAction.FORCE_EXIT:
                return True, f"Force exit required: {expiry_info.message}"
            
            return False, "No expiry restrictions"
            
        except Exception as e:
            logger.error(f"Strategy blocking check failed: {e}")
            return False, "Error in expiry check - allowing trading"
    
    def get_expiry_adjusted_config(self, strategy_name: str, base_config: Dict[str, Any],
                                  symbol: str) -> Dict[str, Any]:
        """Enhanced configuration adjustment for expiry periods"""
        try:
            expiry_info = self.get_expiry_info(symbol)
            adjusted_config = base_config.copy()
            
            # Get risk multiplier based on days to expiry
            days = expiry_info.days_to_expiry
            risk_multiplier = self.expiry_risk_multipliers.get(
                min(days, 5), 1.0  # Use 5+ days multiplier for anything > 5
            )
            
            # Adjust risk parameters
            if days <= 5:
                # Tighter risk management near expiry
                adjusted_config["sl_per_lot"] = int(base_config.get("sl_per_lot", 2000) * risk_multiplier)
                adjusted_config["tp_per_lot"] = int(base_config.get("tp_per_lot", 4000) * (risk_multiplier + 0.2))
                
                # Reduce position size near expiry
                adjusted_config["lot_count"] = min(
                    base_config.get("lot_count", 1), 
                    2 if days >= 3 else 1
                )
                
                # Add expiry-specific parameters
                adjusted_config["expiry_adjusted"] = True
                adjusted_config["original_sl"] = base_config.get("sl_per_lot", 2000)
                adjusted_config["original_tp"] = base_config.get("tp_per_lot", 4000)
                adjusted_config["risk_multiplier"] = risk_multiplier
                adjusted_config["days_to_expiry"] = days
                
                logger.info(f"Adjusted config for {strategy_name} with {days} DTE: "
                           f"SL={adjusted_config['sl_per_lot']}, "
                           f"TP={adjusted_config['tp_per_lot']}, "
                           f"Lots={adjusted_config['lot_count']}")
            
            return adjusted_config
            
        except Exception as e:
            logger.error(f"Config adjustment failed: {e}")
            return base_config
    
    def get_all_expiry_info(self) -> Dict[str, ExpiryInfo]:
        """Get expiry information for all supported symbols"""
        symbols = ["NIFTY", "BANKNIFTY"]
        expiry_info = {}
        
        for symbol in symbols:
            try:
                info = self.get_expiry_info(symbol)
                expiry_info[symbol] = info
            except Exception as e:
                logger.error(f"Failed to get expiry info for {symbol}: {e}")
                
        return expiry_info
    
    def is_trading_allowed(self, strategy_name: str, symbol: str) -> Tuple[bool, str]:
        """Comprehensive check if trading is allowed"""
        try:
            # Check expiry restrictions
            blocked, reason = self.should_block_strategy(strategy_name, symbol)
            if blocked:
                return False, reason
            
            # Check if it's a market holiday using event calendar
            today = date.today()
            if self.event_calendar and self.event_calendar.is_market_holiday(today):
                return False, "Market holiday - No trading allowed"
            
            # Check for high-impact events if event calendar is available
            if self.event_calendar:
                try:
                    should_avoid, avoid_reason = self.event_calendar.should_avoid_trading(today, symbol)
                    if should_avoid and "Critical" in avoid_reason:
                        return False, f"Critical market events - {avoid_reason}"
                except Exception as e:
                    logger.debug(f"Event check failed: {e}")
            
            return True, "Trading allowed"
            
        except Exception as e:
            logger.error(f"Trading allowance check failed: {e}")
            return True, "Error in check - allowing trading"
    
    def get_expiry_calendar(self, months_ahead: int = 3) -> List[Dict[str, Any]]:
        """Get expiry calendar for next few months using enhanced calendar"""
        try:
            if self.event_calendar:
                # Use enhanced event calendar
                calendar_entries = []
                today = date.today()
                
                for symbol in ["NIFTY", "BANKNIFTY"]:
                    expiries = self.event_calendar.get_all_expiries(symbol, months_ahead)
                    
                    for expiry in expiries:
                        calendar_entries.append({
                            "date": expiry.date,
                            "symbol": symbol,
                            "type": expiry.expiry_type,
                            "days_from_today": (expiry.date - today).days,
                            "settlement_date": expiry.settlement_date,
                            "is_last_trading_day": expiry.is_last_trading_day
                        })
                
                # Sort by date
                calendar_entries = sorted(calendar_entries, key=lambda x: x["date"])
                return calendar_entries
            else:
                # Fallback to basic calculation
                return self._get_basic_expiry_calendar(months_ahead)
                
        except Exception as e:
            logger.error(f"Expiry calendar generation failed: {e}")
            return []
    
    def _get_basic_expiry_calendar(self, months_ahead: int) -> List[Dict[str, Any]]:
        """Basic expiry calendar as fallback"""
        calendar_entries = []
        today = date.today()
        
        for i in range(months_ahead * 4):  # Approximate weeks
            check_date = today + timedelta(weeks=i)
            
            for symbol in ["NIFTY", "BANKNIFTY"]:
                # Weekly expiry
                weekly_expiry = self._get_next_weekly_expiry_local(check_date)
                if weekly_expiry not in [entry["date"] for entry in calendar_entries]:
                    calendar_entries.append({
                        "date": weekly_expiry,
                        "symbol": symbol,
                        "type": "WEEKLY",
                        "days_from_today": (weekly_expiry - today).days,
                        "settlement_date": self._get_settlement_date(weekly_expiry),
                        "is_last_trading_day": True
                    })
                
                # Monthly expiry
                monthly_expiry = self._get_next_monthly_expiry_local(symbol, check_date)
                if monthly_expiry not in [entry["date"] for entry in calendar_entries]:
                    calendar_entries.append({
                        "date": monthly_expiry,
                        "symbol": symbol,
                        "type": "MONTHLY", 
                        "days_from_today": (monthly_expiry - today).days,
                        "settlement_date": self._get_settlement_date(monthly_expiry),
                        "is_last_trading_day": True
                    })
        
        return sorted(calendar_entries, key=lambda x: x["date"])
    
    def check_time_based_exit_rules(self, current_time: datetime, 
                                   expiry_info: ExpiryInfo) -> Optional[Dict[str, Any]]:
        """Check time-based exit rules for expiry day"""
        if not expiry_info.is_today:
            return None
        
        current_time_str = current_time.strftime("%H:%M")
        
        # Force exit time (3:00 PM on expiry day)
        if current_time_str >= self.expiry_day_exit_times["force_exit"]:
            return {
                "action": "FORCE_EXIT",
                "reason": "Force exit time reached on expiry day",
                "urgency": "CRITICAL",
                "time_triggered": current_time_str
            }
        
        # Afternoon exit time (2:30 PM on expiry day)
        elif current_time_str >= self.expiry_day_exit_times["afternoon_exit"]:
            return {
                "action": "AFTERNOON_EXIT_WARNING",
                "reason": "Afternoon exit window on expiry day",
                "urgency": "HIGH",
                "time_triggered": current_time_str
            }
        
        # Morning exit time (10:30 AM on expiry day)
        elif current_time_str >= self.expiry_day_exit_times["morning_exit"]:
            return {
                "action": "MORNING_EXIT_OPPORTUNITY",
                "reason": "Morning exit window on expiry day",
                "urgency": "MEDIUM",
                "time_triggered": current_time_str
            }
        
        return None
    
    def get_gamma_risk_assessment(self, expiry_info: ExpiryInfo, 
                                 current_price: float, strike_prices: List[float]) -> Dict[str, Any]:
        """Assess gamma risk near expiry"""
        if expiry_info.days_to_expiry > 3:
            return {"risk_level": "LOW", "message": "No significant gamma risk"}
        
        # Find closest strikes to current price
        closest_strikes = sorted(strike_prices, key=lambda x: abs(x - current_price))[:3]
        
        risk_level = "LOW"
        risk_score = 0
        
        if expiry_info.is_today:
            # High gamma risk on expiry day
            risk_level = "CRITICAL"
            risk_score = 100
            message = "Critical gamma risk on expiry day - positions can move rapidly"
        elif expiry_info.is_tomorrow:
            risk_level = "HIGH"
            risk_score = 80
            message = "High gamma risk - expiry tomorrow"
        elif expiry_info.days_to_expiry <= 3:
            risk_level = "MEDIUM"
            risk_score = 60
            message = f"Moderate gamma risk - {expiry_info.days_to_expiry} days to expiry"
        
        # Adjust based on moneyness
        for strike in closest_strikes[:1]:  # Check closest strike
            distance_pct = abs(current_price - strike) / current_price * 100
            if distance_pct < 2:  # Within 2% of strike
                risk_score += 20
                if risk_level == "MEDIUM":
                    risk_level = "HIGH"
                elif risk_level == "LOW":
                    risk_level = "MEDIUM"
        
        return {
            "risk_level": risk_level,
            "risk_score": min(risk_score, 100),
            "message": message,
            "closest_strikes": closest_strikes[:3],
            "days_to_expiry": expiry_info.days_to_expiry,
            "assessment_time": datetime.now().isoformat()
        }

# Global expiry manager instance with enhanced capabilities
expiry_manager = ExpiryDayManager()

# Enhanced convenience functions
def is_expiry_day_today(symbol: str = "NIFTY") -> bool:
    """Quick check if today is expiry day"""
    is_expiry, _ = expiry_manager.is_expiry_day(symbol=symbol)
    return is_expiry

def get_days_to_expiry(symbol: str = "NIFTY") -> int:
    """Get days to next expiry"""
    info = expiry_manager.get_expiry_info(symbol)
    return info.days_to_expiry

def should_exit_before_expiry(symbol: str = "NIFTY") -> bool:
    """Check if positions should be exited before expiry"""
    info = expiry_manager.get_expiry_info(symbol)
    return info.recommended_action in [ExpiryAction.EARLY_EXIT, ExpiryAction.FORCE_EXIT]

def get_expiry_adjusted_risk_params(strategy: str, symbol: str, base_config: Dict) -> Dict:
    """Get expiry-adjusted risk parameters"""
    return expiry_manager.get_expiry_adjusted_config(strategy, base_config, symbol)

def is_high_gamma_risk_period(symbol: str = "NIFTY", current_price: float = 0) -> bool:
    """Check if we're in high gamma risk period"""
    expiry_info = expiry_manager.get_expiry_info(symbol)
    return expiry_info.days_to_expiry <= 2

def get_comprehensive_expiry_status() -> Dict[str, Any]:
    """Get comprehensive expiry status for all symbols"""
    all_info = expiry_manager.get_all_expiry_info()
    
    status = {
        "timestamp": datetime.now().isoformat(),
        "symbols": {},
        "overall_risk": "LOW",
        "trading_recommendations": []
    }
    
    max_risk_level = 0
    
    for symbol, info in all_info.items():
        risk_level = 0
        if info.is_today:
            risk_level = 4
        elif info.is_tomorrow:
            risk_level = 3
        elif info.days_to_expiry <= 3:
            risk_level = 2
        elif info.days_to_expiry <= 7:
            risk_level = 1
        
        max_risk_level = max(max_risk_level, risk_level)
        
        status["symbols"][symbol] = {
            "next_expiry": info.date.isoformat(),
            "days_to_expiry": info.days_to_expiry,
            "expiry_type": info.expiry_type.value,
            "recommended_action": info.recommended_action.value,
            "message": info.message,
            "risk_level": risk_level
        }
        
        if info.recommended_action != ExpiryAction.NORMAL_TRADING:
            status["trading_recommendations"].append({
                "symbol": symbol,
                "action": info.recommended_action.value,
                "reason": info.message
            })
    
    # Set overall risk
    risk_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL", "EMERGENCY"]
    status["overall_risk"] = risk_levels[min(max_risk_level, len(risk_levels) - 1)]
    
    return status

# Export main components
__all__ = [
    "ExpiryDayManager", 
    "ExpiryInfo", 
    "ExpiryType", 
    "ExpiryAction",
    "expiry_manager",
    "is_expiry_day_today",
    "get_days_to_expiry", 
    "should_exit_before_expiry",
    "get_expiry_adjusted_risk_params",
    "is_high_gamma_risk_period",
    "get_comprehensive_expiry_status"
]
