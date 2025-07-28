"""
Ratio Spreads Strategy – F&O (NIFTY/BANKNIFTY only) | 3-4 leg hedged structure
- Structure: Buy 1 ITM/ATM option, Sell 2+ OTM options, Buy farther OTM hedge
- Designed for moderate directional moves with volatility advantage
- Compatible with intelligent strategy selector and performance tracking system
- Always includes hedge protection (no unlimited risk)
"""

from datetime import datetime
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config, validate_instrument_liquidity
import logging

logger = logging.getLogger("RatioSpreadsStrategy")

class RatioSpreadsStrategy(BaseStrategy):
    """
    Ratio Spreads Strategy - 3-4 leg hedged structure:
    1. Buy 1 ITM/ATM option (long position)
    2. Sell 2 OTM options (premium collection)
    3. Buy 1 far OTM option (hedge protection)
    
    Can be bullish (call ratio) or bearish (put ratio)
    Best for: Moderate directional moves with high implied volatility
    """

    name = "RATIO_SPREADS"
    required_leg_count = 3  # Minimum 3 legs (can be 4 with extra hedge)
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_vix = 18.0  # Moderate volatility required
        self.max_vix = 35.0  # Upper limit for entry
        self.target_win_rate = 70.0  # Expected win rate
        self.max_loss_per_trade = 3500.0  # Moderate risk tolerance
        
        # Ratio Spreads specific parameters
        self.ratio = 2  # 1x2 ratio (buy 1, sell 2)
        self.min_trend_strength = 1.5      # Minimum trend for directional bias
        self.strike_spacing_nifty = 50     # Strike spacing for NIFTY
        self.strike_spacing_banknifty = 100 # Strike spacing for BANKNIFTY
        self.hedge_distance_nifty = 150    # Hedge distance for NIFTY
        self.hedge_distance_banknifty = 300 # Hedge distance for BANKNIFTY
        self.min_credit_target = 1000      # Minimum net credit to collect

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Ratio Spreads:
        - NIFTY/BANKNIFTY only (high liquidity enforcement)
        - Moderate to high volatility (VIX 18-35)
        - Clear directional bias with moderate trend strength
        - No major events or expiry day
        - Sufficient implied volatility for premium collection
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        trend_strength = abs(market_data.get("trend_strength", 0))
        directional_bias = market_data.get("directional_bias", "NEUTRAL")
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        iv_rank = market_data.get("iv_rank", 50)
        days_to_expiry = market_data.get("days_to_expiry", 0)
        
        # Strict liquidity validation
        if not validate_instrument_liquidity(symbol):
            logger.warning(f"Ratio Spreads rejected: {symbol} not in liquid instruments")
            return False
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            trend_strength >= self.min_trend_strength and
            directional_bias in ["BULLISH", "BEARISH"] and  # Clear direction needed
            not expiry and
            not events and
            iv_rank > 50 and  # Above average IV for good premium
            7 <= days_to_expiry <= 45  # Reasonable time frame
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate Ratio Spreads orders with hedge-first execution:
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - direction: "CALL" or "PUT" (bullish or bearish)
        - expiry: Option expiry (e.g., "25JUL")
        - spot_price: Current underlying price
        - long_strike: ITM/ATM strike to buy
        - short_strike: OTM strike to sell (2x)
        - hedge_strike: Far OTM strike for hedge protection
        """
        symbol = signal["symbol"]
        direction = signal["direction"]  # "CALL" or "PUT"
        expiry = signal["expiry"]
        spot_price = signal["spot_price"]
        long_strike = signal["long_strike"]
        short_strike = signal["short_strike"]
        hedge_strike = signal["hedge_strike"]
        lots = config.get("lot_count", 1)
        
        # Validate strikes and direction
        if not self._validate_ratio_spread_strikes(symbol, spot_price, direction, 
                                                  long_strike, short_strike, hedge_strike):
            raise ValueError(f"Invalid Ratio Spread configuration for {symbol}")
        
        # Get instrument configuration
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        # Determine option type
        option_type = "CE" if direction == "CALL" else "PE"
        
        # HEDGE-FIRST ORDER EXECUTION (for margin benefit)
        orders = [
            # 1. BUY Long Strike (FIRST - establish position)
            {
                "symbol": f"{symbol}{expiry}{int(long_strike)}{option_type}",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_main",
                "is_hedge": False,  # Main position
                "strike": long_strike,
                "option_type": option_type,
                "expiry": expiry,
                "priority": 1,  # Execute FIRST
                "execution_order": "MAIN_FIRST"
            },
            
            # 2. BUY Far OTM Hedge (SECOND - hedge protection)
            {
                "symbol": f"{symbol}{expiry}{int(hedge_strike)}{option_type}",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "hedge_protection",
                "is_hedge": True,
                "strike": hedge_strike,
                "option_type": option_type,
                "expiry": expiry,
                "priority": 2,  # Execute SECOND
                "execution_order": "HEDGE_SECOND"
            },
            
            # 3. SELL Short Strikes (THIRD - after protection in place)
            {
                "symbol": f"{symbol}{expiry}{int(short_strike)}{option_type}",
                "side": "SELL",
                "lots": self.ratio * lots,  # Sell 2x quantity
                "quantity": self.ratio * lots * lot_qty,
                "leg_type": "short_ratio",
                "is_hedge": False,
                "strike": short_strike,
                "option_type": option_type,
                "expiry": expiry,
                "priority": 3,  # Execute AFTER hedge protection
                "execution_order": "SHORT_AFTER_HEDGE"
            }
        ]
        
        # Calculate expected net credit/debit
        estimated_net = self._calculate_estimated_net_premium(
            signal.get("estimated_premiums", {}), lots * lot_qty
        )
        
        logger.info(f"Generated {direction} Ratio Spread for {symbol}: "
                   f"Long: {long_strike}, Short: {short_strike} (2x), Hedge: {hedge_strike}, "
                   f"Estimated Net: ₹{estimated_net:,.0f}, "
                   f"HEDGE-FIRST execution for margin benefit")
        
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Ratio Spreads specific risk management:
        - Directional bias monitoring
        - Volatility crush protection
        - Asymmetric profit/loss management
        """
        sl = config.get("sl_per_lot", 2200) * lot_count  # Moderate SL
        tp = config.get("tp_per_lot", 4500) * lot_count  # Higher TP potential
        
        direction = config.get("direction", "CALL")
        underlying_move = config.get("underlying_change_pct", 0)
        entry_vix = config.get("entry_vix", 25)
        current_vix = config.get("current_vix", 25)
        days_to_expiry = config.get("days_to_expiry", 15)
        
        # Check for volatility crush
        vix_crush = current_vix < entry_vix * 0.75  # 25% VIX drop
        
        # Check directional performance
        favorable_move = (direction == "CALL" and underlying_move > 1.0) or \
                        (direction == "PUT" and underlying_move < -1.0)
        
        adverse_move = (direction == "CALL" and underlying_move < -2.0) or \
                      (direction == "PUT" and underlying_move > 2.0)
        
        if mtm <= -sl:
            return {
                "action": "HARD_STOP",
                "reason": f"{direction} Ratio Spread SL triggered",
                "urgency": "HIGH"
            }
        elif mtm >= tp:
            return {
                "action": "TAKE_PROFIT",
                "reason": f"{direction} Ratio Spread TP achieved",
                "urgency": "MEDIUM"
            }
        elif vix_crush:
            return {
                "action": "VOLATILITY_CRUSH_EXIT",
                "reason": f"VIX crushed from {entry_vix:.1f} to {current_vix:.1f}",
                "urgency": "HIGH"
            }
        elif adverse_move:
            return {
                "action": "ADVERSE_MOVE_WARNING",
                "reason": f"Adverse move: {underlying_move:+.1f}% against {direction} bias",
                "urgency": "HIGH"
            }
        elif favorable_move and mtm >= tp * 0.6:
            return {
                "action": "FAVORABLE_PROFIT_OPPORTUNITY",
                "reason": f"Favorable move: {underlying_move:+.1f}% with good profit",
                "urgency": "MEDIUM"
            }
        elif days_to_expiry <= 7:
            return {
                "action": "TIME_DECAY_ALERT",
                "reason": f"Time decay acceleration: {days_to_expiry} days left",
                "urgency": "MEDIUM"
            }
        elif mtm <= -sl * 0.8:
            return {
                "action": "SOFT_WARN",
                "reason": f"Approaching {direction} Ratio Spread SL",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def _validate_ratio_spread_strikes(self, symbol: str, spot_price: float, direction: str,
                                     long_strike: float, short_strike: float, 
                                     hedge_strike: float) -> bool:
        """Validate Ratio Spread strike configuration"""
        
        if direction == "CALL":
            # Call ratio spread: long strike < short strike < hedge strike
            # Long should be ITM/ATM, short OTM, hedge far OTM
            if not (long_strike <= spot_price < short_strike < hedge_strike):
                logger.error(f"Invalid call ratio strikes: long={long_strike}, short={short_strike}, hedge={hedge_strike}, spot={spot_price}")
                return False
        elif direction == "PUT":
            # Put ratio spread: hedge strike < short strike < long strike
            # Long should be ITM/ATM, short OTM, hedge far OTM
            if not (hedge_strike < short_strike < long_strike <= spot_price):
                logger.error(f"Invalid put ratio strikes: hedge={hedge_strike}, short={short_strike}, long={long_strike}, spot={spot_price}")
                return False
        else:
            logger.error(f"Invalid direction for ratio spread: {direction}")
            return False
        
        # Check strike spacing
        expected_spacing = self.strike_spacing_banknifty if symbol == "BANKNIFTY" else self.strike_spacing_nifty
        
        if direction == "CALL":
            short_spacing = short_strike - long_strike
            hedge_spacing = hedge_strike - short_strike
        else:  # PUT
            short_spacing = long_strike - short_strike
            hedge_spacing = short_strike - hedge_strike
        
        if short_spacing < expected_spacing * 0.5:
            logger.warning(f"Short strike spacing {short_spacing} too small for {symbol}")
        
        if hedge_spacing < expected_spacing:
            logger.warning(f"Hedge spacing {hedge_spacing} may be insufficient for {symbol}")
        
        return True

    def _calculate_estimated_net_premium(self, estimated_premiums: Dict, total_quantity: int) -> float:
        """Calculate estimated net premium for Ratio Spread"""
        long_premium = estimated_premiums.get("long_strike", 0)
        short_premium = estimated_premiums.get("short_strike", 0)
        hedge_premium = estimated_premiums.get("hedge_strike", 0)
        
        # Buy 1 long, sell 2 short, buy 1 hedge
        net_premium_per_share = long_premium + hedge_premium - (2 * short_premium)
        return net_premium_per_share * total_quantity

    def get_optimal_strikes(self, spot_price: float, symbol: str, direction: str,
                          current_vix: float) -> Dict[str, float]:
        """
        Calculate optimal Ratio Spread strikes based on direction and volatility
        """
        spacing = self.strike_spacing_banknifty if symbol == "BANKNIFTY" else self.strike_spacing_nifty
        hedge_distance = self.hedge_distance_banknifty if symbol == "BANKNIFTY" else self.hedge_distance_nifty
        
        # Adjust spacing based on VIX (higher VIX = wider spacing)
        vix_multiplier = min(1.5, max(0.8, current_vix / 25.0))
        adjusted_spacing = spacing * vix_multiplier
        
        if direction == "CALL":
            # Call ratio spread
            if symbol == "NIFTY":
                long_strike = round((spot_price - spacing * 0.5) / 50) * 50  # Slightly ITM
                short_strike = round((spot_price + adjusted_spacing) / 50) * 50  # OTM
                hedge_strike = short_strike + hedge_distance
            else:  # BANKNIFTY
                long_strike = round((spot_price - spacing * 0.5) / 100) * 100
                short_strike = round((spot_price + adjusted_spacing) / 100) * 100
                hedge_strike = short_strike + hedge_distance
        else:  # PUT
            # Put ratio spread
            if symbol == "NIFTY":
                long_strike = round((spot_price + spacing * 0.5) / 50) * 50  # Slightly ITM
                short_strike = round((spot_price - adjusted_spacing) / 50) * 50  # OTM
                hedge_strike = short_strike - hedge_distance
            else:  # BANKNIFTY
                long_strike = round((spot_price + spacing * 0.5) / 100) * 100
                short_strike = round((spot_price - adjusted_spacing) / 100) * 100
                hedge_strike = short_strike - hedge_distance
        
        return {
            "long_strike": long_strike,
            "short_strike": short_strike,
            "hedge_strike": hedge_strike,
            "spacing": adjusted_spacing,
            "vix_adjustment": vix_multiplier
        }

    def calculate_ratio_spread_breakevens(self, strikes: Dict[str, float], 
                                        net_premium: float, direction: str) -> Dict[str, float]:
        """
        Calculate Ratio Spread breakeven points
        """
        long_strike = strikes["long_strike"]
        short_strike = strikes["short_strike"]
        hedge_strike = strikes["hedge_strike"]
        
        if direction == "CALL":
            # Call ratio spread breakevens
            lower_breakeven = long_strike + net_premium
            upper_breakeven = short_strike + (short_strike - long_strike - net_premium)
            max_profit_point = short_strike
        else:  # PUT
            # Put ratio spread breakevens
            upper_breakeven = long_strike - net_premium
            lower_breakeven = short_strike - (long_strike - short_strike - net_premium)
            max_profit_point = short_strike
        
        return {
            "lower_breakeven": lower_breakeven,
            "upper_breakeven": upper_breakeven,
            "max_profit_point": max_profit_point,
            "max_profit_range": f"Near {max_profit_point}",
            "risk_zone": f"Beyond {upper_breakeven if direction == 'CALL' else lower_breakeven}"
        }

    def check_directional_performance(self, current_data: Dict, entry_data: Dict) -> Dict[str, Any]:
        """
        Check how well the directional bias is performing
        """
        entry_direction = entry_data.get("direction", "CALL")
        entry_price = entry_data.get("entry_spot_price", 0)
        current_price = current_data.get("spot_price", 0)
        
        if entry_price <= 0:
            return {"action": None}
        
        price_change_pct = (current_price - entry_price) / entry_price * 100
        
        # Check if direction is working
        if entry_direction == "CALL" and price_change_pct > 2.0:
            return {
                "action": "DIRECTION_FAVORABLE",
                "message": f"Call bias working: {price_change_pct:+.1f}% move",
                "confidence": "HIGH"
            }
        elif entry_direction == "PUT" and price_change_pct < -2.0:
            return {
                "action": "DIRECTION_FAVORABLE",
                "message": f"Put bias working: {price_change_pct:+.1f}% move",
                "confidence": "HIGH"
            }
        elif (entry_direction == "CALL" and price_change_pct < -3.0) or \
             (entry_direction == "PUT" and price_change_pct > 3.0):
            return {
                "action": "DIRECTION_ADVERSE",
                "message": f"{entry_direction} bias failing: {price_change_pct:+.1f}% move",
                "confidence": "HIGH",
                "suggested_action": "Consider early exit"
            }
        
        return {"action": None}

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum loss for Ratio Spread
        Max loss is limited by hedge protection
        """
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum profit for Ratio Spread
        Max profit occurs when short strikes expire worthless and long strike has value
        """
        return self.max_loss_per_trade * 2.0  # Typical 1:2 risk-reward for ratio spreads

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """Get Ratio Spreads specific performance metrics"""
        base_metrics = self.get_strategy_info()
        
        ratio_spreads_metrics = {
            "ratio": f"1x{self.ratio} (buy 1, sell {self.ratio})",
            "strike_spacings": {
                "NIFTY": self.strike_spacing_nifty,
                "BANKNIFTY": self.strike_spacing_banknifty
            },
            "hedge_distances": {
                "NIFTY": self.hedge_distance_nifty,
                "BANKNIFTY": self.hedge_distance_banknifty
            },
            "min_trend_strength": self.min_trend_strength,
            "min_credit_target": self.min_credit_target,
            "vix_range": {"min": self.min_vix, "max": self.max_vix},
            "risk_profile": "LIMITED by hedge protection",
            "profit_profile": "ASYMMETRIC (higher in favorable direction)",
            "market_outlook": "DIRECTIONAL with moderate move expectation",
            "delta_strategy": "MODERATE (net long delta)",
            "theta_impact": "POSITIVE (time decay helps short positions)",
            "gamma_risk": "MODERATE (managed by hedge)",
            "vega_sensitivity": "MODERATE (benefits from volatility)",
            "directional_bias_required": True,
            "best_conditions": "Moderate trend with high IV",
            "hedge_protection": True,
            "margin_efficiency": "GOOD (hedged structure)"
        }
        
        return {**base_metrics, **ratio_spreads_metrics}

# Utility functions for Ratio Spreads analysis
def validate_ratio_spread_structure(orders: List[Dict[str, Any]]) -> bool:
    """Validate that orders represent proper Ratio Spread structure"""
    if len(orders) != 3:
        return False
    
    # Should have specific quantity pattern: 1 long, 2 short, 1 hedge
    buy_orders = [o for o in orders if o.get("side") == "BUY"]
    sell_orders = [o for o in orders if o.get("side") == "SELL"]
    
    if len(buy_orders) != 2 or len(sell_orders) != 1:
        return False
    
    # Check that sell order has 2x quantity
    sell_order = sell_orders[0]
    buy_quantities = [o.get("lots", 1) for o in buy_orders]
    sell_quantity = sell_order.get("lots", 1)
    
    return sell_quantity == 2 * min(buy_quantities)

def calculate_ratio_spread_payoff(strikes: Dict[str, float], spot_at_expiry: float,
                                net_premium: float, direction: str) -> float:
    """
    Calculate Ratio Spread payoff at expiry
    """
    long_strike = strikes["long_strike"]
    short_strike = strikes["short_strike"]
    hedge_strike = strikes["hedge_strike"]
    
    if direction == "CALL":
        # Call ratio spread payoff
        long_payoff = max(0, spot_at_expiry - long_strike)
        short_payoff = -2 * max(0, spot_at_expiry - short_strike)
        hedge_payoff = max(0, spot_at_expiry - hedge_strike)
    else:  # PUT
        # Put ratio spread payoff
        long_payoff = max(0, long_strike - spot_at_expiry)
        short_payoff = -2 * max(0, short_strike - spot_at_expiry)
        hedge_payoff = max(0, hedge_strike - spot_at_expiry)
    
    total_payoff = long_payoff + short_payoff + hedge_payoff - net_premium
    return total_payoff

def check_ratio_spread_hedge_execution(orders: List[Dict[str, Any]]) -> bool:
    """Verify proper execution order for ratio spread"""
    # Check that long and hedge orders execute before short orders
    long_orders = [o for o in orders if o.get("side") == "BUY"]
    short_orders = [o for o in orders if o.get("side") == "SELL"]
    
    if not long_orders or not short_orders:
        return False
    
    # All buy orders should have lower priority than sell orders
    max_buy_priority = max(o.get("priority", 0) for o in long_orders)
    min_sell_priority = min(o.get("priority", 999) for o in short_orders)
    
    return max_buy_priority < min_sell_priority

# Export the strategy class and utilities
__all__ = [
    "RatioSpreadsStrategy",
    "validate_ratio_spread_structure",
    "calculate_ratio_spread_payoff",
    "check_ratio_spread_hedge_execution"
]
