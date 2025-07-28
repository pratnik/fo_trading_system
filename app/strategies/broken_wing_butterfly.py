"""
Broken Wing Butterfly Strategy – F&O (NIFTY/BANKNIFTY only) | 4-leg asymmetric hedged structure
- Structure: Unequal wing distances creating directional bias with limited risk
- Can be structured for net credit (eliminating one-sided risk) or directional advantage
- Compatible with intelligent strategy selector and performance tracking system
- Designed for moderate volatility with slight directional bias
"""

from datetime import datetime
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config
import logging

logger = logging.getLogger("BrokenWingButterflyStrategy")

class BrokenWingButterflyStrategy(BaseStrategy):
    """
    Broken Wing Butterfly Strategy - 4-leg asymmetric structure:
    - Buy 1 lower strike option
    - Sell 2 middle strike options (not equidistant)
    - Buy 1 higher strike option
    
    Key Feature: Unequal wing distances create directional bias
    Can be structured for net credit or better profit potential in preferred direction
    """

    name = "BROKEN_WING_BUTTERFLY"
    required_leg_count = 4
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_v volatility required
        self.max_vix = 32.0  # Upper limit for entry
        self.target_win_rate = 75.0  # Expected win rate
        self.max_loss_per_trade = 3500.0  # Moderate risk tolerance
        
        # Broken Wing Butterfly specific parameters
        self.min_wing_ratio = 1.2  # Minimum ratio between wings (asymmetry)
        self.max_wing_ratio = 3.0  # Maximum wing ratio for reasonable risk
        self.preferred_net_credit = True  # Prefer net credit structures
        self.skew_multiplier = 1.5  # How much to skew towards profitable side

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Broken Wing Butterfly:
        - NIFTY/BANKNIFTY only (high liquidity)
        - Moderate volatility (VIX 18-32)
        - Slight directional bias identified
        - No major events or expiry day
        - Sufficient premium skew for asymmetric structure
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        index_chg = market_data.get("index_chg_pct", 0)
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        directional_bias = market_data.get("directional_bias", "NEUTRAL")
        iv_skew = market_data.get("iv_skew", 0)  # Implied volatility skew
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            abs(index_chg) < settings.get("DANGER_ZONE_WARNING", 1.0) and
            not expiry and
            not events and
            directional_bias in ["SLIGHTLY_BULLISH", "SLIGHTLY_BEARISH"] and
            abs(iv_skew) > 2.0  # Sufficient skew for asymmetric advantage
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate Broken Wing Butterfly orders with asymmetric structure:
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - spot_price: Current underlying price
        - expiry: Option expiry (e.g., "25JUL")
        - direction: "CALL" or "PUT" (option type)
        - bias: "BULLISH" or "BEARISH" (directional skew)
        - lower_strike: Lower strike price
        - middle_strike: Middle strike price (where 2 options are sold)
        - upper_strike: Upper strike price
        - wing_distances: Dict with short_wing and long_wing distances
        """
        symbol = signal["symbol"]
        expiry = signal["expiry"]
        direction = signal["direction"]  # "CALL" or "PUT"
        bias = signal["bias"]  # "BULLISH" or "BEARISH"
        lower_strike = signal["lower_strike"]
        middle_strike = signal["middle_strike"]
        upper_strike = signal["upper_strike"]
        lots = config.get("lot_count", 1)
        
        # Get instrument configuration
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        # Validate broken wing structure
        if not self._validate_broken_wing_structure(
            lower_strike, middle_strike, upper_strike, bias
        ):
            raise ValueError(f"Invalid broken wing structure for {symbol}")
        
        # Determine option type
        option_type = "CE" if direction == "CALL" else "PE"
        
        # Calculate wing distances for logging
        short_wing = middle_strike - lower_strike
        long_wing = upper_strike - middle_strike
        wing_ratio = long_wing / short_wing if short_wing > 0 else 1.0
        
        orders = [
            # 1. BUY Lower Strike (hedge)
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
                "wing_position": "lower_wing"
            },
            
            # 2. SELL Middle Strike (2 contracts - main risk)
            {
                "symbol": f"{symbol}{expiry}{int(middle_strike)}{option_type}",
                "side": "SELL",
                "lots": 2 * lots,  # Double quantity for butterfly body
                "quantity": 2 * lots * lot_qty,
                "leg_type": "short_middle",
                "is_hedge": False,
                "strike": middle_strike,
                "option_type": option_type,
                "expiry": expiry,
                "wing_position": "body"
            },
            
            # 3. BUY Upper Strike (hedge)
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
                "wing_position": "upper_wing"
            },
            
            # 4. Additional hedge if needed for risk management
            # (This could be a farther OTM option for extra protection)
            {
                "symbol": f"{symbol}{expiry}{int(self._calculate_safety_strike(upper_strike, bias, symbol))}{option_type}",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "safety_hedge",
                "is_hedge": True,
                "strike": self._calculate_safety_strike(upper_strike, bias, symbol),
                "option_type": option_type,
                "expiry": expiry,
                "wing_position": "safety_wing"
            }
        ]
        
        logger.info(f"Generated Broken Wing Butterfly for {symbol}: "
                   f"{direction} {bias} bias, "
                   f"Strikes: {lower_strike}/{middle_strike}/{upper_strike}, "
                   f"Wing Ratio: {wing_ratio:.2f}, "
                   f"Short Wing: {short_wing}, Long Wing: {long_wing}")
        
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Broken Wing Butterfly specific risk management:
        - Asymmetric profit profile requires different SL/TP on each side
        - Monitor for early assignment on short middle strikes
        - Adjust based on directional bias performance
        """
        base_sl = config.get("sl_per_lot", 2000) * lot_count
        base_tp = config.get("tp_per_lot", 4500) * lot_count
        
        # Adjust SL/TP based on directional bias
        bias = config.get("directional_bias", "NEUTRAL")
        underlying_move = config.get("underlying_change_pct", 0)
        
        # More aggressive TP in favorable direction
        if bias == "BULLISH" and underlying_move > 0:
            tp = base_tp * 1.2  # 20% higher TP for favorable moves
        elif bias == "BEARISH" and underlying_move < 0:
            tp = base_tp * 1.2
        else:
            tp = base_tp
        
        # More conservative SL against bias
        if (bias == "BULLISH" and underlying_move < -1.0) or \
           (bias == "BEARISH" and underlying_move > 1.0):
            sl = base_sl * 0.8  # Tighter SL for adverse moves
        else:
            sl = base_sl
        
        days_to_expiry = config.get("days_to_expiry", 10)
        
        if mtm <= -sl:
            return {
                "action": "HARD_STOP",
                "reason": f"Broken Wing Butterfly SL triggered (bias: {bias})",
                "urgency": "HIGH"
            }
        elif mtm >= tp:
            return {
                "action": "TAKE_PROFIT",
                "reason": f"Broken Wing Butterfly TP achieved (bias: {bias})",
                "urgency": "MEDIUM"
            }
        elif days_to_expiry <= 3 and abs(underlying_move) > 1.5:
            return {
                "action": "EXPIRY_RISK_EXIT",
                "reason": f"High gamma risk: {days_to_expiry} DTE, {underlying_move:.1f}% move",
                "urgency": "HIGH"
            }
        elif mtm <= -0.75 * sl:
            return {
                "action": "SOFT_WARN",
                "reason": f"Approaching Broken Wing SL (bias working against: {bias})",
                "urgency": "MEDIUM"
            }
        elif mtm >= 0.6 * tp and days_to_expiry <= 7:
            return {
                "action": "EARLY_PROFIT_OPPORTUNITY",
                "reason": f"Good profit with week to expiry (bias: {bias})",
                "urgency": "LOW"
            }
        
        return {"action": None}

    def _validate_broken_wing_structure(self, lower_strike: float, middle_strike: float,
                                       upper_strike: float, bias: str) -> bool:
        """
        Validate that strikes create proper broken wing butterfly structure
        """
        # Basic order validation
        if not (lower_strike < middle_strike < upper_strike):
            logger.error(f"Invalid strike order: {lower_strike} < {middle_strike} < {upper_strike}")
            return False
        
        # Calculate wing distances
        short_wing = middle_strike - lower_strike
        long_wing = upper_strike - middle_strike
        
        if short_wing <= 0 or long_wing <= 0:
            logger.error("Wing distances must be positive")
            return False
        
        # Check wing ratio for proper asymmetry
        wing_ratio = long_wing / short_wing
        
        if wing_ratio < self.min_wing_ratio or wing_ratio > self.max_wing_ratio:
            logger.error(f"Wing ratio {wing_ratio:.2f} outside valid range "
                        f"[{self.min_wing_ratio}, {self.max_wing_ratio}]")
            return False
        
        # Validate bias matches structure
        if bias == "BULLISH" and wing_ratio < 1.0:
            logger.warning("Bullish bias should have longer upper wing")
        elif bias == "BEARISH" and wing_ratio > 1.0:
            logger.warning("Bearish bias should have longer lower wing")
        
        return True

    def _calculate_safety_strike(self, upper_strike: float, bias: str, symbol: str) -> float:
        """
        Calculate additional safety hedge strike
        """
        if symbol == "NIFTY":
            safety_buffer = 100  # 100 points further OTM
        else:  # BANKNIFTY
            safety_buffer = 200  # 200 points further OTM
        
        return upper_strike + safety_buffer

    def calculate_asymmetric_breakevens(self, strikes: Dict[str, float],
                                      premiums: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate breakeven points for asymmetric butterfly structure
        """
        lower = strikes.get("lower", 0)
        middle = strikes.get("middle", 0)
        upper = strikes.get("upper", 0)
        
        # Net premium calculation (simplified)
        net_premium = (
            premiums.get("middle", 0) * 2 -  # Sold 2x middle
            premiums.get("lower", 0) -       # Bought lower
            premiums.get("upper", 0)         # Bought upper
        )
        
        return {
            "lower_breakeven": lower + net_premium,
            "upper_breakeven": upper - net_premium,
            "max_profit_point": middle,
            "net_credit_debit": net_premium,
            "profit_range_lower": lower + net_premium,
            "profit_range_upper": upper - net_premium
        }

    def check_directional_bias_performance(self, current_data: Dict, 
                                         entry_data: Dict) -> Dict[str, Any]:
        """
        Check how well the directional bias is performing
        """
        entry_bias = entry_data.get("directional_bias", "NEUTRAL")
        entry_price = entry_data.get("entry_spot_price", 0)
        current_price = current_data.get("spot_price", 0)
        
        if entry_price <= 0:
            return {"action": None}
        
        price_change_pct = (current_price - entry_price) / entry_price * 100
        
        # Check if bias is working
        bias_working = False
        if entry_bias == "BULLISH" and price_change_pct > 0.5:
            bias_working = True
        elif entry_bias == "BEARISH" and price_change_pct < -0.5:
            bias_working = True
        
        # Check if bias is strongly against us
        bias_against = False
        if entry_bias == "BULLISH" and price_change_pct < -1.5:
            bias_against = True
        elif entry_bias == "BEARISH" and price_change_pct > 1.5:
            bias_against = True
        
        if bias_working:
            return {
                "action": "BIAS_FAVORABLE",
                "message": f"{entry_bias} bias working: {price_change_pct:+.1f}% move",
                "confidence": "HIGH"
            }
        elif bias_against:
            return {
                "action": "BIAS_ADVERSE", 
                "message": f"{entry_bias} bias failing: {price_change_pct:+.1f}% move",
                "confidence": "HIGH",
                "suggested_action": "Consider early exit"
            }
        
        return {"action": None}

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum loss for Broken Wing Butterfly
        Max loss is limited due to hedged structure
        """
        # For broken wing butterfly, max loss occurs at the far wing
        # It's the cost of the structure plus the wing imbalance
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum profit for Broken Wing Butterfly
        Max profit occurs near the middle strike but skewed towards favorable direction
        """
        return self.max_loss_per_trade * 2.5  # Typical 1:2.5 risk-reward

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """Get Broken Wing Butterfly specific performance metrics"""
        base_metrics = self.get_strategy_info()
        
        broken_wing_metrics = {
            "wing_ratio_range": {
                "min": self.min_wing_ratio,
                "max": self.max_wing_ratio
            },
            "preferred_structure": "Net credit with directional bias",
            "asymmetric_profile": True,
            "directional_sensitivity": "MODERATE",
            "skew_multiplier": self.skew_multiplier,
            "optimal_conditions": "Moderate IV with slight directional bias",
            "gamma_risk": "MANAGED by hedge structure",
            "theta_advantage": "MODERATE (time decay helps)",
            "vega_sensitivity": "LOW to MODERATE"
        }
        
        return {**base_metrics, **broken_wing_metrics}

# Utility functions for Broken Wing Butterfly analysis
def calculate_wing_asymmetry_ratio(short_wing: float, long_wing: float) -> float:
    """
    Calculate the asymmetry ratio between wings
    Values > 1.0 indicate longer upper wing (bullish skew)
    Values < 1.0 indicate longer lower wing (bearish skew)
    """
    if short_wing <= 0:
        return 1.0
    return long_wing / short_wing

def validate_broken_wing_credit_structure(strikes: Dict[str, float],
                                        premiums: Dict[str, float]) -> bool:
    """
    Validate that the broken wing structure results in net credit
    (preferred for eliminating risk on one side)
    """
    net_credit = (
        premiums.get("middle", 0) * 2 -  # Sold 2x middle
        premiums.get("lower", 0) -       # Bought lower  
        premiums.get("upper", 0) -       # Bought upper
        premiums.get("safety", 0)        # Bought safety hedge
    )
    
    return net_credit > 0

def calculate_directional_advantage(wing_ratio: float, bias: str) -> float:
    """
    Calculate the directional advantage score based on wing structure and bias
    Higher scores indicate better directional alignment
    """
    if bias == "BULLISH":
        # For bullish bias, prefer longer upper wing (ratio > 1)
        return min(1.0, wing_ratio / 2.0)
    elif bias == "BEARISH":
        # For bearish bias, prefer longer lower wing (ratio < 1)
        return min(1.0, (2.0 - wing_ratio) / 2.0)
    else:
        # Neutral bias prefers balanced wings (ratio close to 1)
        return 1.0 - abs(wing_ratio - 1.0)

# Export the strategy class and utilities
__all__ = [
    "BrokenWingButterflyStrategy",
    "calculate_wing_asymmetry_ratio",
    "validate_broken_wing_credit_structure", 
    "calculate_directional_advantage"
]
