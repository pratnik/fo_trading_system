"""
Butterfly Spread Strategy – F&O (NIFTY/BANKNIFTY only) | 4-leg hedged structure
- Structure: Buy 1 lower strike, Sell 2 middle strikes, Buy 1 upper strike
- Designed for low volatility, range-bound markets with neutral bias
- Compatible with intelligent strategy selector and performance tracking system
- Always includes hedge protection with optimal strike selection
"""

from datetime import datetime
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config, validate_instrument_liquidity
import logging

logger = logging.getLogger("ButterflySpreadStrategy")

class ButterflySpreadStrategy(BaseStrategy):
    """
    Long Butterfly Spread Strategy - 4-leg hedged structure:
    1. Buy lower strike option (hedge)
    2. Sell 2 middle strike options (premium collection)
    3. Buy upper strike option (hedge)
    
    Can be constructed with calls or puts, offers limited risk/reward profile
    Best for: Low volatility, range-bound NIFTY/BANKNIFTY markets
    """

    name = "BUTTERFLY_SPREAD"
    required_leg_count = 4
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_vix = 12.0  # Low volatility preferred
        self.max_vix = 22.0  # Maximum VIX for entry
        self.target_win_rate = 80.0  # High win rate strategy
        self.max_loss_per_trade = 2000.0  # Conservative risk (net debit paid)
        
        # Butterfly specific parameters
        self.wing_width_nifty = 50      # Wing width for NIFTY
        self.wing_width_banknifty = 100 # Wing width for BANKNIFTY
        self.max_net_debit = 1500       # Maximum debit to pay
        self.min_days_to_expiry = 7     # Minimum DTE
        self.max_days_to_expiry = 30    # Maximum DTE

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Butterfly Spread:
        - NIFTY/BANKNIFTY only (high liquidity enforcement)
        - Low volatility environment (VIX < 22)
        - Range-bound market (no strong trend)
        - No major events or expiry day
        - Sufficient time but not too far out
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        index_chg = abs(market_data.get("index_chg_pct", 0))
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        trend_strength = abs(market_data.get("trend_strength", 0))
        days_to_expiry = market_data.get("days_to_expiry", 0)
        
        # Strict liquidity validation
        if not validate_instrument_liquidity(symbol):
            logger.warning(f"Butterfly Spread rejected: {symbol} not in liquid instruments")
            return False
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            index_chg < settings.get("DANGER_ZONE_WARNING", 1.0) and
            trend_strength < 1.5 and  # Not strongly trending
            not expiry and
            not events and
            self.min_days_to_expiry <= days_to_expiry <= self.max_days_to_expiry
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate Butterfly Spread orders with hedge-first execution:
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - expiry: Option expiry (e.g., "25JUL")
        - center_strike: Middle strike (where 2 options are sold)
        - option_type: "CE" or "PE" (calls or puts)
        - wing_width: Distance between strikes
        - estimated_net_debit: Expected cost of the spread
        """
        symbol = signal["symbol"]
        expiry = signal["expiry"]
        center_strike = signal["center_strike"]
        option_type = signal.get("option_type", "CE")  # Default to calls
        wing_width = signal.get("wing_width")
        lots = config.get("lot_count", 1)
        
        # Auto-calculate wing width if not provided
        if not wing_width:
            wing_width = self.wing_width_banknifty if symbol == "BANKNIFTY" else self.wing_width_nifty
        
        # Calculate strikes
        lower_strike = center_strike - wing_width
        upper_strike = center_strike + wing_width
        
        # Validate butterfly structure
        if not self._validate_butterfly_strikes(symbol, lower_strike, center_strike, upper_strike):
            raise ValueError(f"Invalid Butterfly Spread strike selection for {symbol}")
        
        # Get instrument configuration
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        # HEDGE-FIRST ORDER EXECUTION (for margin benefit)
        orders = [
            # 1. BUY Lower Strike (FIRST - hedge protection)
            {
                "symbol": f"{symbol}{expiry}{int(lower_strike)}{option_type}",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_lower",
                "is_hedge": True,
                "strike": lower_strike,
                "option_type": option_type,
                "expiry": expiry,
                "priority": 1,  # Execute FIRST
                "execution_order": "HEDGE_FIRST"
            },
            
            # 2. BUY Upper Strike (SECOND - hedge protection)
            {
                "symbol": f"{symbol}{expiry}{int(upper_strike)}{option_type}",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_upper",
                "is_hedge": True,
                "strike": upper_strike,
                "option_type": option_type,
                "expiry": expiry,
                "priority": 2,  # Execute SECOND
                "execution_order": "HEDGE_FIRST"
            },
            
            # 3. SELL Middle Strike (THIRD - after hedges in place)
            {
                "symbol": f"{symbol}{expiry}{int(center_strike)}{option_type}",
                "side": "SELL",
                "lots": 2 * lots,  # Sell 2x quantity
                "quantity": 2 * lots * lot_qty,
                "leg_type": "short_middle",
                "is_hedge": False,
                "strike": center_strike,
                "option_type": option_type,
                "expiry": expiry,
                "priority": 3,  # Execute AFTER hedges
                "execution_order": "MAIN_AFTER_HEDGE"
            }
        ]
        
        # Calculate expected net debit
        estimated_debit = signal.get("estimated_net_debit", 0)
        
        logger.info(f"Generated Butterfly Spread for {symbol}: "
                   f"{option_type} {lower_strike}/{center_strike}/{upper_strike}, "
                   f"Wing Width: {wing_width}, "
                   f"Estimated Debit: ₹{estimated_debit:,.0f}, "
                   f"HEDGE-FIRST execution for margin benefit")
        
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Butterfly Spread specific risk management:
        - Conservative SL/TP due to limited profit potential
        - Time decay advantage monitoring
        - Early profit taking when 50% of max profit achieved
        """
        sl = config.get("sl_per_lot", 1200) * lot_count  # Conservative SL (net debit)
        tp = config.get("tp_per_lot", 2000) * lot_count  # Conservative TP
        
        days_to_expiry = config.get("days_to_expiry", 15)
        time_decay_benefit = days_to_expiry < 14  # Time decay helps after 2 weeks
        
        if mtm <= -sl:
            return {
                "action": "HARD_STOP",
                "reason": "Butterfly Spread SL triggered (max debit loss)",
                "urgency": "HIGH"
            }
        elif mtm >= tp:
            return {
                "action": "TAKE_PROFIT",
                "reason": "Butterfly Spread TP achieved",
                "urgency": "MEDIUM"
            }
        elif days_to_expiry <= 5:
            return {
                "action": "EXPIRY_MANAGEMENT",
                "reason": f"Close to expiry: {days_to_expiry} days remaining",
                "urgency": "MEDIUM"
            }
        elif mtm >= tp * 0.5 and time_decay_benefit:
            return {
                "action": "PROFIT_OPPORTUNITY",
                "reason": f"50% max profit achieved with time decay benefit",
                "urgency": "LOW"
            }
        elif mtm <= -sl * 0.8:
            return {
                "action": "SOFT_WARN",
                "reason": "Approaching Butterfly Spread maximum loss",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def _validate_butterfly_strikes(self, symbol: str, lower_strike: float,
                                  center_strike: float, upper_strike: float) -> bool:
        """Validate Butterfly Spread strike selection"""
        
        # Basic order validation
        if not (lower_strike < center_strike < upper_strike):
            logger.error(f"Invalid strike order: {lower_strike} < {center_strike} < {upper_strike}")
            return False
        
        # Check equal wing distances
        lower_wing = center_strike - lower_strike
        upper_wing = upper_strike - center_strike
        
        if lower_wing != upper_wing:
            logger.error(f"Unequal wings: lower={lower_wing}, upper={upper_wing}")
            return False
        
        # Check wing width is appropriate for symbol
        expected_width = self.wing_width_banknifty if symbol == "BANKNIFTY" else self.wing_width_nifty
        
        if lower_wing < expected_width * 0.5 or lower_wing > expected_width * 2:
            logger.warning(f"Wing width {lower_wing} outside optimal range for {symbol}")
        
        return True

    def get_optimal_strikes(self, spot_price: float, symbol: str, 
                          days_to_expiry: int, option_type: str = "CE") -> Dict[str, float]:
        """
        Calculate optimal Butterfly Spread strikes
        """
        # Center strike at or near ATM
        if symbol == "NIFTY":
            center_strike = round(spot_price / 50) * 50  # Round to nearest 50
            wing_width = self.wing_width_nifty
        else:  # BANKNIFTY
            center_strike = round(spot_price / 100) * 100  # Round to nearest 100
            wing_width = self.wing_width_banknifty
        
        # Adjust center strike slightly based on option type and time
        if option_type == "CE" and days_to_expiry > 20:
            # Slightly OTM for call butterflies with more time
            center_strike += wing_width * 0.5
        elif option_type == "PE" and days_to_expiry > 20:
            # Slightly OTM for put butterflies with more time
            center_strike -= wing_width * 0.5
        
        # Ensure proper rounding
        if symbol == "NIFTY":
            center_strike = round(center_strike / 50) * 50
        else:
            center_strike = round(center_strike / 100) * 100
        
        lower_strike = center_strike - wing_width
        upper_strike = center_strike + wing_width
        
        return {
            "lower_strike": lower_strike,
            "center_strike": center_strike,
            "upper_strike": upper_strike,
            "wing_width": wing_width
        }

    def calculate_butterfly_payoff(self, strikes: Dict[str, float], 
                                 spot_at_expiry: float, net_debit: float) -> float:
        """
        Calculate Butterfly Spread payoff at expiry
        """
        lower = strikes["lower_strike"]
        center = strikes["center_strike"]
        upper = strikes["upper_strike"]
        
        if spot_at_expiry <= lower or spot_at_expiry >= upper:
            # Outside the wings - maximum loss (net debit paid)
            return -net_debit
        elif spot_at_expiry == center:
            # At center strike - maximum profit
            wing_width = center - lower
            return wing_width - net_debit
        elif lower < spot_at_expiry < center:
            # Between lower and center
            intrinsic_value = spot_at_expiry - lower
            return intrinsic_value - net_debit
        else:  # center < spot_at_expiry < upper
            # Between center and upper
            intrinsic_value = upper - spot_at_expiry
            return intrinsic_value - net_debit

    def get_breakeven_points(self, strikes: Dict[str, float], net_debit: float) -> Dict[str, float]:
        """
        Calculate Butterfly Spread breakeven points
        """
        lower = strikes["lower_strike"]
        center = strikes["center_strike"]
        upper = strikes["upper_strike"]
        
        return {
            "lower_breakeven": lower + net_debit,
            "upper_breakeven": upper - net_debit,
            "max_profit_point": center,
            "max_profit_amount": (center - lower) - net_debit,
            "max_loss_amount": net_debit,
            "profit_range": f"{lower + net_debit:.0f} to {upper - net_debit:.0f}"
        }

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum loss for Butterfly Spread
        Max loss = Net debit paid
        """
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum profit for Butterfly Spread
        Max profit = Wing width - Net debit paid
        """
        # Get wing width from orders
        strikes = []
        for order in orders:
            strikes.append(order.get("strike", 0))
        
        if len(strikes) >= 3:
            strikes.sort()
            wing_width = strikes[1] - strikes[0]  # Distance between strikes
            return wing_width - self.max_net_debit
        
        return self.max_net_debit  # Conservative estimate

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """Get Butterfly Spread specific performance metrics"""
        base_metrics = self.get_strategy_info()
        
        butterfly_metrics = {
            "wing_widths": {
                "NIFTY": self.wing_width_nifty,
                "BANKNIFTY": self.wing_width_banknifty
            },
            "max_net_debit": self.max_net_debit,
            "vix_range": {"min": self.min_vix, "max": self.max_vix},
            "dte_range": {"min": self.min_days_to_expiry, "max": self.max_days_to_expiry},
            "risk_profile": "LIMITED (net debit paid)",
            "profit_profile": "LIMITED (wing width minus debit)",
            "market_outlook": "NEUTRAL/RANGE-BOUND",
            "theta_strategy": True,
            "vega_strategy": "SHORT (benefits from IV decrease)",
            "gamma_risk": "LOW (balanced long/short)",
            "best_conditions": "Low VIX, range-bound market, ATM at expiry",
            "payoff_shape": "Tent-shaped with peak at center strike",
            "hedge_first_execution": True,
            "margin_efficiency": "HIGH (hedged structure)"
        }
        
        return {**base_metrics, **butterfly_metrics}

# Utility functions for Butterfly Spread analysis
def validate_butterfly_spread_structure(orders: List[Dict[str, Any]]) -> bool:
    """Validate that orders represent proper Butterfly Spread structure"""
    if len(orders) != 3:  # Can be 3 legs if middle is 2x quantity
        return False
    
    # Check quantities: should be 1-2-1 pattern
    quantities = []
    sides = []
    for order in orders:
        quantities.append(order.get("lots", 1))
        sides.append(order.get("side"))
    
    # Should have 2 BUY and 1 SELL (with 2x quantity)
    buy_count = sides.count("BUY")
    sell_count = sides.count("SELL")
    
    return buy_count == 2 and sell_count == 1

def calculate_butterfly_spread_greeks(strikes: Dict[str, float], spot_price: float,
                                    days_to_expiry: int, volatility: float) -> Dict[str, float]:
    """
    Calculate approximate Greeks for Butterfly Spread
    (Simplified calculation - would use Black-Scholes in production)
    """
    # Simplified Greeks calculation
    center = strikes["center_strike"]
    wing_width = strikes["upper_strike"] - strikes["center_strike"]
    
    # Delta approximately zero at center strike
    delta = 0.0 if abs(spot_price - center) < wing_width * 0.1 else 0.1
    
    # Gamma highest at center strike
    gamma = 1.0 / wing_width if abs(spot_price - center) < wing_width else 0.1
    
    # Theta positive (time decay helps)
    theta = 0.5 * days_to_expiry / 30.0
    
    # Vega negative (volatility decrease helps)
    vega = -0.3 * volatility / 20.0
    
    return {
        "delta": delta,
        "gamma": gamma, 
        "theta": theta,
        "vega": vega
    }

def check_butterfly_hedge_first_execution(orders: List[Dict[str, Any]]) -> bool:
    """Verify that long options (hedges) are executed before short options"""
    long_orders = [o for o in orders if o.get("side") == "BUY"]
    short_orders = [o for o in orders if o.get("side") == "SELL"]
    
    if not long_orders or not short_orders:
        return False
    
    # Check that all long orders have lower priority numbers (execute first)
    min_long_priority = min(o.get("priority", 999) for o in long_orders)
    min_short_priority = min(o.get("priority", 999) for o in short_orders)
    
    return min_long_priority < min_short_priority

# Export the strategy class and utilities
__all__ = [
    "ButterflySpreadStrategy",
    "validate_butterfly_spread_structure",
    "calculate_butterfly_spread_greeks",
    "check_butterfly_hedge_first_execution"
]
