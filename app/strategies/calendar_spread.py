"""
Calendar Spread Strategy - F&O (NIFTY/BANKNIFTY) | 4-leg time decay strategy
- Sell weekly options, buy monthly options at same strike
- Profits from time decay differential (theta harvesting)
- Compatible with self-calibrating, performance-tracking system
- Liquidity and risk parameters enforced
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config
import logging

logger = logging.getLogger("CalendarSpreadStrategy")

class CalendarSpreadStrategy(BaseStrategy):
    """
    Calendar Spread Strategy (Time Spread)
    - Sell near-term options (weekly expiry)
    - Buy far-term options (monthly expiry) 
    - Same strikes, profits from time decay differential
    - Works best in low-moderate volatility environments
    """

    name = "CALENDAR_SPREAD"
    required_leg_count = 4  # 2 calls + 2 puts for balanced risk
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_vix = 12.0  # Minimum VIX for entry
        self.max_vix = 28.0  # Maximum VIX for entry
        self.target_win_rate = 80per_trade = 3000.0  # Conservative risk
        
        # Calendar spread specific parameters
        self.min_time_spread = 7   # Minimum days between expiries
        self.max_time_spread = 45  # Maximum days between expiries
        self.preferred_dte_near = 7   # Days to expiry for near leg
        self.preferred_dte_far = 30   # Days to expiry for far leg

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Calendar Spread:
        - NIFTY/BANKNIFTY only
        - Low to moderate volatility (VIX in range)
        - No major events or expiry day
        - Sufficient time spread available
        - Market in sideways to slightly trending mode
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        index_chg = abs(market_data.get("index_chg_pct", 0))
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        trend_strength = market_data.get("trend_strength", 0)
        
        # Available expiry dates check
        near_expiry_dte = market_data.get("near_expiry_dte", 0)
        far_expiry_dte = market_data.get("far_expiry_dte", 0)
        time_spread = far_expiry_dte - near_expiry_dte
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            index_chg < settings.get("DANGER_ZONE_WARNING", 1.0) and
            not expiry and
            not events and
            abs(trend_strength) < 2.0 and  # Not strongly trending
            self.min_time_spread <= time_spread <= self.max_time_spread and
            near_expiry_dte >= 5  # Don't enter too close to near expiry
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate calendar spread orders:
        - Sell weekly CE + PE (same strikes, near expiry)
        - Buy monthly CE + PE (same strikes, far expiry)
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - atm_strike: At-the-money strike price
        - near_expiry: Near term expiry date
        - far_expiry: Far term expiry date
        - strike_adjustment: Strike adjustment from ATM (default 0)
        """
        symbol = signal["symbol"]
        atm_strike = signal["atm_strike"]
        near_expiry = signal["near_expiry"]  # e.g., "25JUL"
        far_expiry = signal["far_expiry"]    # e.g., "29AUG"
        strike_adj = signal.get("strike_adjustment", 0)  # +/- from ATM
        lots = config.get("lot_count", 1)
        
        # Get lot size for the instrument
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        # Calculate the actual strike to use
        target_strike = atm_strike + strike_adj
        
        # Ensure strike is rounded to valid strikes
        if symbol == "NIFTY":
            target_strike = round(target_strike / 50) * 50  # Round to nearest 50
        elif symbol == "BANKNIFTY":
            target_strike = round(target_strike / 100) * 100  # Round to nearest 100
        
        orders = [
            # SELL near-term Call (weekly)
            {
                "symbol": f"{symbol}{near_expiry}{int(target_strike)}CE",
                "side": "SELL",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_near",
                "is_hedge": False,
                "expiry": near_expiry,
                "strike": target_strike,
                "option_type": "CE",
                "time_to_expiry": signal.get("near_dte", 7)
            },
            # BUY far-term Call (monthly) - HEDGE
            {
                "symbol": f"{symbol}{far_expiry}{int(target_strike)}CE",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_far",
                "is_hedge": True,
                "expiry": far_expiry,
                "strike": target_strike,
                "option_type": "CE", 
                "time_to_expiry": signal.get("far_dte", 30)
            },
            # SELL near-term Put (weekly)
            {
                "symbol": f"{symbol}{near_expiry}{int(target_strike)}PE",
                "side": "SELL",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_near",
                "is_hedge": False,
                "expiry": near_expiry,
                "strike": target_strike,
                "option_type": "PE",
                "time_to_expiry": signal.get("near_dte", 7)
            },
            # BUY far-term Put (monthly) - HEDGE
            {
                "symbol": f"{symbol}{far_expiry}{int(target_strike)}PE",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_far",
                "is_hedge": True,
                "expiry": far_expiry,
                "strike": target_strike,
                "option_type": "PE",
                "time_to_expiry": signal.get("far_dte", 30)
            }
        ]
        
        logger.info(f"Generated Calendar Spread for {symbol} at strike {target_strike}: "
                   f"Short {near_expiry}, Long {far_expiry}")
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Calendar Spread specific risk management:
        - More conservative SL/TP due to time decay nature
        - Early exit if volatility spikes significantly
        - Profit taking when theta advantage is captured
        """
        sl = config.get("sl_per_lot", 1500) * lot_count  # Conservative SL
        tp = config.get("tp_per_lot", 3000) * lot_count  # Conservative TP
        
        # Check current conditions for early exit
        current_vix = config.get("current_vix", 20)
        entry_vix = config.get("entry_vix", 20)
        vix_spike = current_vix > entry_vix * 1.4  # 40% VIX increase
        
        if mtm <= -sl:
            return {
                "action": "HARD_STOP",
                "reason": "Calendar Spread SL triggered",
                "urgency": "HIGH"
            }
        elif mtm >= tp:
            return {
                "action": "TAKE_PROFIT", 
                "reason": "Calendar Spread TP achieved",
                "urgency": "MEDIUM"
            }
        elif vix_spike:
            return {
                "action": "VOLATILITY_EXIT",
                "reason": f"VIX spiked from {entry_vix:.1f} to {current_vix:.1f}",
                "urgency": "HIGH"
            }
        elif mtm <= -0.85 * sl:
            return {
                "action": "SOFT_WARN",
                "reason": "Approaching Calendar Spread SL",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def check_near_expiry_management(self, current_data: Dict, entry_data: Dict) -> Dict[str, Any]:
        """
        Special handling for near expiry management in Calendar Spreads
        """
        near_expiry_dte = current_data.get("near_expiry_dte", 10)
        
        # Close or roll the near leg when it gets too close to expiry
        if near_expiry_dte <= 2:
            return {
                "action": "NEAR_EXPIRY_EXIT",
                "reason": f"Near leg expires in {near_expiry_dte} days",
                "urgency": "HIGH",
                "suggested_action": "Close entire position or roll near leg"
            }
        elif near_expiry_dte <= 5:
            return {
                "action": "NEAR_EXPIRY_WARN",
                "reason": f"Near leg expires in {near_expiry_dte} days", 
                "urgency": "MEDIUM",
                "suggested_action": "Monitor closely or consider early exit"
            }
        
        return {"action": None}

    def calculate_theta_advantage(self, near_leg_theta: float, far_leg_theta: float) -> float:
        """
        Calculate the theta advantage of the calendar spread
        Positive theta advantage means time decay is working in our favor
        """
        # Near leg theta (short position) contributes positively
        # Far leg theta (long position) contributes negatively
        net_theta = -near_leg_theta - far_leg_theta  # Short near, long far
        return net_theta

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calendar spread max loss calculation
        Maximum loss occurs when both legs expire worthless or at max distance
        """
        # For calendar spreads, max loss is typically the net debit paid
        # Plus some buffer for execution costs
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calendar spread max profit calculation
        Maximum profit occurs when near leg expires worthless and far leg retains value
        """
        # Theoretical max profit is when price stays at strike and near leg expires worthless
        # While far leg retains significant time value
        return self.max_loss_per_trade * 2.5  # Typical 1:2.5 risk-reward for calendars

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """
        Get calendar spread specific performance metrics
        """
        base_metrics = self.get_strategy_info()
        
        calendar_metrics = {
            "min_time_spread_days": self.min_time_spread,
            "max_time_spread_days": self.max_time_spread,
            "preferred_near_dte": self.preferred_dte_near,
            "preferred_far_dte": self.preferred_dte_far,
            "vix_range": {"min": self.min_vix, "max": self.max_vix},
            "theta_strategy": True,
            "volatility_sensitive": True,
            "best_market_conditions": "Low volatility, sideways movement"
        }
        
        return {**base_metrics, **calendar_metrics}

# Utility functions for calendar spread analysis
def calculate_time_decay_advantage(near_days: int, far_days: int, 
                                 current_iv: float) -> float:
    """
    Calculate the theoretical time decay advantage
    Higher values indicate better calendar spread conditions
    """
    if near_days <= 0 or far_days <= near_days:
        return 0.0
    
    # Time decay accelerates as expiry approaches (non-linear)
    near_decay_rate = 1.0 / (near_days ** 0.5)
    far_decay_rate = 1.0 / (far_days ** 0.5)
    
    # Account for implied volatility impact
    iv_factor = min(2.0, max(0.5, current_iv / 20.0))  # Normalize around 20% IV
    
    time_advantage = (near_decay_rate - far_decay_rate) * iv_factor
    return max(0.0, time_advantage)

def validate_calendar_structure(orders: List[Dict[str, Any]]) -> bool:
    """
    Validate that orders represent a proper calendar spread structure
    """
    if len(orders) != 4:
        return False
    
    # Check that we have both calls and puts
    calls = [o for o in orders if o.get("option_type") == "CE"]
    puts = [o for o in orders if o.get("option_type") == "PE"]
    
    if len(calls) != 2 or len(puts) != 2:
        return False
    
    # Check that we have one short and one long for each option type
    call_sides = [o.get("side") for o in calls]
    put_sides = [o.get("side") for o in puts]
    
    return ("BUY" in call_sides and "SELL" in call_sides and 
            "BUY" in put_sides and "SELL" in put_sides)

# Export the strategy class and utilities
__all__ = [
    "CalendarSpreadStrategy",
    "calculate_time_decay_advantage", 
    "validate_calendar_structure"
]
