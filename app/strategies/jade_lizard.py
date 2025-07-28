"""
Jade Lizard Strategy – F&O (NIFTY/BANKNIFTY only) | 3-leg hedged structure
- Structure: Short put + short call spread (short call + long call)
- Neutral to slightly bullish strategy with no upside risk
- Designed for high implied volatility environment and premium collection
- Compatible with intelligent strategy selector and performance tracking
"""

from datetime import datetime
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config
import logging

logger = logging.getLogger("JadeLizardStrategy")

class JadeLizardStrategy(BaseStrategy):
    """
    Jade Lizard Options Strategy - 3-leg structure:
    1. Sell OTM Put (premium collection)
    2. Sell OTM Call (short wing of call spread)
    3. Buy farther OTM Call (long wing of call spread - HEDGE)
    
    Key Feature: Total premium collected > call spread width = No upside risk
    Best for: High IV environments with neutral to slightly bullish bias
    """

    name = "JADE_LIZARD"
    required_leg_count = 3
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_vix = 22.0  # Higher VIX required for good premium
        self.max_vix = 40.0  # Upper limit for entry
        self.target_win_rate = 78.0  # Expected win rate
        self.max_loss_per_trade = 4000.0  # Higher risk tolerance
        
        # Jade Lizard specific parameters
        self.min_credit_to_spread_ratio = 1.1  # Credit must exceed spread width
        self.preferred_put_delta = 0.20_delta = 0.25  # Delta for short call
        self.call_spread_width_nifty = 100  # NIFTY call spread width
        self.call_spread_width_banknifty = 200  # BANKNIFTY call spread width

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Jade Lizard:
        - NIFTY/BANKNIFTY only (high liquidity)
        - High implied volatility (VIX > 22)
        - No major events or expiry day
        - Neutral to slightly bullish market sentiment
        - Sufficient premium available to exceed call spread width
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        index_chg = market_data.get("index_chg_pct", 0)
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        market_sentiment = market_data.get("market_sentiment", "NEUTRAL")
        iv_rank = market_data.get("iv_rank", 50)  # Implied volatility rank
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            abs(index_chg) < settings.get("DANGER_ZONE_WARNING", 1.0) and
            not expiry and
            not events and
            market_sentiment in ["NEUTRAL", "SLIGHTLY_BULLISH"] and
            iv_rank > 60  # High IV rank for good premium collection
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate Jade Lizard orders with proper validation:
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - spot_price: Current underlying price
        - expiry: Option expiry (e.g., "25JUL")
        - put_strike: OTM put strike to sell
        - call_strike_short: OTM call strike to sell
        - call_strike_long: Farther OTM call strike to buy (hedge)
        - estimated_premiums: Dict with premium estimates for validation
        """
        symbol = signal["symbol"]
        expiry = signal["expiry"]
        spot_price = signal["spot_price"]
        put_strike = signal["put_strike"]
        call_strike_short = signal["call_strike_short"]
        call_strike_long = signal["call_strike_long"]
        lots = config.get("lot_count", 1)
        
        # Get instrument configuration
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        # Validate strike selection
        if not self._validate_jade_lizard_strikes(
            symbol, spot_price, put_strike, call_strike_short, call_strike_long, signal
        ):
            raise ValueError(f"Invalid strike selection for {symbol} Jade Lizard")
        
        # Calculate call spread width
        call_spread_width = call_strike_long - call_strike_short
        
        orders = [
            # 1. SELL OTM Put (premium collection)
            {
                "symbol": f"{symbol}{expiry}{int(put_strike)}PE",
                "side": "SELL",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_put",
                "is_hedge": False,
                "strike": put_strike,
                "option_type": "PE",
                "expiry": expiry,
                "estimated_premium": signal.get("estimated_premiums", {}).get("put", 0),
                "target_delta": -self.preferred_put_delta  # Negative for short put
            },
            
            # 2. SELL OTM Call (short wing of call spread)
            {
                "symbol": f"{symbol}{expiry}{int(call_strike_short)}CE",
                "side": "SELL", 
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_call",
                "is_hedge": False,
                "strike": call_strike_short,
                "option_type": "CE",
                "expiry": expiry,
                "estimated_premium": signal.get("estimated_premiums", {}).get("call_short", 0),
                "target_delta": -self.preferred_call_delta  # Negative for short call
            },
            
            # 3. BUY Farther OTM Call (long wing - HEDGE)
            {
                "symbol": f"{symbol}{expiry}{int(call_strike_long)}CE",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_call_hedge",
                "is_hedge": True,
                "strike": call_strike_long,
                "option_type": "CE",
                "expiry": expiry,
                "estimated_premium": signal.get("estimated_premiums", {}).get("call_long", 0),
                "spread_width": call_spread_width,
                "max_call_spread_loss": call_spread_width * lot_qty * lots
            }
        ]
        
        # Log strategy details
        estimated_net_credit = self._calculate_estimated_net_credit(
            signal.get("estimated_premiums", {}), lots * lot_qty
        )
        
        logger.info(f"Generated Jade Lizard for {symbol}: "
                   f"Put: {put_strike}PE, Call Spread: {call_strike_short}/{call_strike_long}CE, "
                   f"Estimated Credit: ₹{estimated_net_credit:,.0f}, "
                   f"Call Spread Width: {call_spread_width}")
        
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Jade Lizard specific risk management:
        - More aggressive TP due to premium collection nature
        - Watch for early assignment risk on short options
        - Monitor for significant market moves that could threaten position
        """
        sl = config.get("sl_per_lot", 2500) * lot_count  # Higher SL for Jade Lizard
        tp = config.get("tp_per_lot", 4500) * lot_count  # Higher TP potential
        
        # Check for early assignment risk indicators
        days_to_expiry = config.get("days_to_expiry", 10)
        underlying_move = abs(config.get("underlying_change_pct", 0))
        
        if mtm <= -sl:
            return {
                "action": "HARD_STOP",
                "reason": "Jade Lizard SL triggered",
                "urgency": "HIGH"
            }
        elif mtm >= tp:
            return {
                "action": "TAKE_PROFIT",
                "reason": "Jade Lizard TP achieved",
                "urgency": "MEDIUM"
            }
        elif days_to_expiry <= 3 and underlying_move > 2.0:
            return {
                "action": "ASSIGNMENT_RISK_EXIT",
                "reason": f"High assignment risk: {days_to_expiry} DTE, {underlying_move:.1f}% move",
                "urgency": "HIGH"
            }
        elif mtm <= -0.8 * sl:
            return {
                "action": "SOFT_WARN",
                "reason": "Approaching Jade Lizard SL",
                "urgency": "MEDIUM"
            }
        elif mtm >= 0.7 * tp:
            return {
                "action": "PROFIT_TAKING_OPPORTUNITY",
                "reason": "Good profit achieved, consider early exit",
                "urgency": "LOW"
            }
        
        return {"action": None}

    def _validate_jade_lizard_strikes(self, symbol: str, spot_price: float,
                                    put_strike: float, call_strike_short: float,
                                    call_strike_long: float, signal: Dict) -> bool:
        """
        Validate that strikes are appropriate for Jade Lizard strategy
        """
        # Put should be OTM (below spot for puts)
        if put_strike >= spot_price:
            logger.error(f"Put strike {put_strike} not OTM for spot {spot_price}")
            return False
        
        # Short call should be OTM (above spot for calls)
        if call_strike_short <= spot_price:
            logger.error(f"Short call strike {call_strike_short} not OTM for spot {spot_price}")
            return False
        
        # Long call should be farther OTM than short call
        if call_strike_long <= call_strike_short:
            logger.error(f"Long call {call_strike_long} not farther OTM than short call {call_strike_short}")
            return False
        
        # Check call spread width is reasonable
        call_spread_width = call_strike_long - call_strike_short
        max_width = self.call_spread_width_banknifty if symbol == "BANKNIFTY" else self.call_spread_width_nifty
        
        if call_spread_width > max_width:
            logger.warning(f"Call spread width {call_spread_width} exceeds recommended {max_width}")
        
        # Validate credit vs spread width ratio (key Jade Lizard requirement)
        estimated_premiums = signal.get("estimated_premiums", {})
        if estimated_premiums:
            estimated_credit = (
                estimated_premiums.get("put", 0) +
                estimated_premiums.get("call_short", 0) -
                estimated_premiums.get("call_long", 0)
            )
            
            credit_to_width_ratio = estimated_credit / call_spread_width if call_spread_width > 0 else 0
            
            if credit_to_width_ratio < self.min_credit_to_spread_ratio:
                logger.warning(f"Credit to spread ratio {credit_to_width_ratio:.2f} below minimum {self.min_credit_to_spread_ratio}")
                return False
        
        return True

    def _calculate_estimated_net_credit(self, estimated_premiums: Dict, total_quantity: int) -> float:
        """Calculate estimated net credit for the Jade Lizard position"""
        put_premium = estimated_premiums.get("put", 0)
        call_short_premium = estimated_premiums.get("call_short", 0)
        call_long_premium = estimated_premiums.get("call_long", 0)
        
        net_credit_per_share = put_premium + call_short_premium - call_long_premium
        return net_credit_per_share * total_quantity

    def check_assignment_risk(self, current_data: Dict, entry_data: Dict) -> Dict[str, Any]:
        """
        Check for early assignment risk on short options
        """
        days_to_expiry = current_data.get("days_to_expiry", 10)
        spot_price = current_data.get("spot_price", 0)
        put_strike = entry_data.get("put_strike", 0)
        call_strike_short = entry_data.get("call_strike_short", 0)
        
        assignment_risks = []
        
        # Check short put assignment risk
        if spot_price <= put_strike * 1.02 and days_to_expiry <= 5:  # Within 2% and close to expiry
            assignment_risks.append(f"Short put assignment risk: Spot {spot_price} near put strike {put_strike}")
        
        # Check short call assignment risk
        if spot_price >= call_strike_short * 0.98 and days_to_expiry <= 5:  # Within 2% and close to expiry
            assignment_risks.append(f"Short call assignment risk: Spot {spot_price} near call strike {call_strike_short}")
        
        if assignment_risks:
            return {
                "action": "ASSIGNMENT_RISK_ALERT",
                "risks": assignment_risks,
                "urgency": "HIGH",
                "recommended_action": "Consider closing position or rolling strikes"
            }
        
        return {"action": None}

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum loss for Jade Lizard
        Max loss occurs if underlying moves significantly below put strike
        """
        # Find the put strike and call spread width
        put_strike = 0
        call_spread_width = 0
        
        for order in orders:
            if order.get("leg_type") == "short_put":
                put_strike = order.get("strike", 0)
            elif order.get("leg_type") == "long_call_hedge":
                call_spread_width = order.get("spread_width", 0)
        
        # Max loss is theoretically unlimited on downside, but practically limited
        # Use a reasonable estimate based on put strike distance from spot
        if put_strike > 0:
            max_downside_move = put_strike  # If underlying goes to zero
            estimated_max_loss = max_downside_move * orders[0].get("quantity", 50)  # Simplified
            return min(estimated_max_loss, self.max_loss_per_trade * 2)  # Cap at 2x normal max loss
        
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum profit for Jade Lizard
        Max profit is the net credit received if price stays between put strike and short call strike
        """
        # Max profit is the net credit collected
        estimated_credit = 0
        for order in orders:
            premium = order.get("estimated_premium", 0)
            quantity = order.get("quantity", 50)
            if order.get("side") == "SELL":
                estimated_credit += premium * quantity
            else:
                estimated_credit -= premium * quantity
        
        return max(estimated_credit, self.max_loss_per_trade * 1.5)  # Reasonable estimate

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """Get Jade Lizard specific performance metrics"""
        base_metrics = self.get_strategy_info()
        
        jade_lizard_metrics = {
            "min_credit_to_spread_ratio": self.min_credit_to_spread_ratio,
            "preferred_put_delta": self.preferred_put_delta,
            "preferred_call_delta": self.preferred_call_delta,
            "call_spread_widths": {
                "NIFTY": self.call_spread_width_nifty,
                "BANKNIFTY": self.call_spread_width_banknifty
            },
            "upside_risk": "NONE (if properly structured)",
            "downside_risk": "LIMITED by position sizing",
            "assignment_risk": "MODERATE on short options",
            "best_market_conditions": "High IV, neutral to slightly bullish",
            "premium_collection_strategy": True
        }
        
        return {**base_metrics, **jade_lizard_metrics}

# Utility functions for Jade Lizard analysis
def validate_jade_lizard_credit_ratio(net_credit: float, call_spread_width: float) -> bool:
    """
    Validate that net credit exceeds call spread width (key Jade Lizard requirement)
    """
    if call_spread_width <= 0:
        return False
    
    ratio = net_credit / call_spread_width
    return ratio >= 1.0  # Credit should exceed spread width

def calculate_jade_lizard_breakevens(put_strike: float, call_strike_short: float,
                                   net_credit: float) -> Dict[str, float]:
    """
    Calculate breakeven points for Jade Lizard strategy
    """
    return {
        "lower_breakeven": put_strike - net_credit,  # Below this, losses start
        "upper_breakeven": float('inf'),  # No upside risk if properly structured
        "profit_zone_lower": put_strike - net_credit,
        "profit_zone_upper": call_strike_short,  # Maximum profit between these points
        "max_profit_zone": f"{put_strike - net_credit:.0f} to {call_strike_short:.0f}"
    }

# Export the strategy class and utilities
__all__ = [
    "JadeLizardStrategy",
    "validate_jade_lizard_credit_ratio",
    "calculate_jade_lizard_breakevens"
]
