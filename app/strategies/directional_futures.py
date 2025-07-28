"""
Directional Futures Strategy – F&O (NIFTY/BANKNIFTY only) | 2-leg hedged structure
- Structure: Long/Short futures position + far OTM options hedge protection
- Designed for strong trending markets with clear directional bias
- Compatible with intelligent strategy selector and performance tracking system
- Always includes hedge protection (no naked futures exposure)
"""

from datetime import datetime
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config, validate_instrument_liquidity
import logging

logger = logging.getLogger("DirectionalFuturesStrategy")

class DirectionalFuturesStrategy(BaseStrategy):
    """
    Directional Futures Strategy - 2-leg hedged structure:
    1. Long/Short Futures position (main directional bet)
    2. Far OTM Options hedge (risk protection)
    
    For Long Futures: Buy futures + Buy far OTM Put (downside protection)
    For Short Futures: Sell futures + Buy far OTM Call (upside protection)
    
    Best for: Strong trending markets, clear directional bias, momentum plays
    """

    name = StrategyType.DIRECTIONAL_FUTURES
    required_leg_count = 2
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_vix = 15.0  # Minimum volatility for entry
        self.max_vix = 40.0  # Maximum volatility for entry
        self.target_win_rate = 65.0  # Expected win rate (lower due to directional risk)
        self.max_loss_per_trade = 5000.0  # Higher risk tolerance for trending moves
        
        # Directional Futures specific parameters
        self.min_trend_strength = 2.0        # Minimum trend strength for entry
        self.hedge_distance_nifty = 300      # Hedge distance for NIFTY
        self.hedge_distance_banknifty = 600  # Hedge distance for BANKNIFTY
        self.max_days_to_expiry = 30         # Maximum DTE for futures
        self.min_days_to_expiry = 5          # Minimum DTE for futures

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Directional Futures:
        - NIFTY/BANKNIFTY only (high liquidity enforcement)
        - Strong trending market (high trend strength)
        - Moderate to high volatility for momentum
        - Clear directional bias identified
        - No major events or expiry day
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        trend_strength = abs(market_data.get("trend_strength", 0))
        directional_bias = market_data.get("directional_bias", "NEUTRAL")
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        volume_surge = market_data.get("volume_surge", False)
        days_to_expiry = market_data.get("days_to_expiry", 0)
        
        # Strict liquidity validation
        if not validate_instrument_liquidity(symbol):
            logger.warning(f"Directional Futures rejected: {symbol} not in liquid instruments")
            return False
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            trend_strength >= self.min_trend_strength and
            directional_bias in ["BULLISH", "BEARISH"] and  # Clear direction required
            not expiry and
            not events and
            self.min_days_to_expiry <= days_to_expiry <= self.max_days_to_expiry and
            volume_surge  # Prefer high volume trending days
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate Directional Futures orders with hedge-first execution:
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - direction: "LONG" or "SHORT"
        - expiry: Futures expiry (e.g., "25JUL")
        - spot_price: Current underlying price
        - hedge_strike: Far OTM option strike for hedge
        - confidence: Signal confidence (0.0 to 1.0)
        """
        symbol = signal["symbol"]
        direction = signal["direction"]  # "LONG" or "SHORT"
        expiry = signal["expiry"]
        spot_price = signal["spot_price"]
        hedge_strike = signal["hedge_strike"]
        lots = config.get("lot_count", 1)
        
        # Validate direction and hedge
        if direction not in ["LONG", "SHORT"]:
            raise ValueError(f"Invalid direction for Directional Futures: {direction}")
        
        if not self._validate_futures_hedge(symbol, spot_price, hedge_strike, direction):
            raise ValueError(f"Invalid hedge configuration for {symbol} {direction} futures")
        
        # Get instrument configuration
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        # Futures symbol construction
        futures_symbol = f"{symbol}{expiry}FUT"
        
        # HEDGE-FIRST ORDER EXECUTION (for margin benefit)
        if direction == "LONG":
            # Long Futures + Put Hedge (downside protection)
            orders = [
                # 1. BUY Far OTM Put HEDGE (FIRST - for margin benefit)
                {
                    "symbol": f"{symbol}{expiry}{int(hedge_strike)}PE",
                    "side": "BUY",
                    "lots": lots,
                    "quantity": lots * lot_qty,
                    "leg_type": "hedge_put",
                    "is_hedge": True,
                    "strike": hedge_strike,
                    "option_type": "PE",
                    "expiry": expiry,
                    "priority": 1,  # Execute FIRST
                    "execution_order": "HEDGE_FIRST"
                },
                
                # 2. BUY Futures (SECOND - after hedge is in place)
                {
                    "symbol": futures_symbol,
                    "side": "BUY",
                    "lots": lots,
                    "quantity": lots * lot_qty,
                    "leg_type": "main_futures",
                    "is_hedge": False,
                    "instrument_type": "FUTURES",
                    "expiry": expiry,
                    "priority": 2,  # Execute AFTER hedge
                    "execution_order": "MAIN_AFTER_HEDGE"
                }
            ]
        else:  # SHORT
            # Short Futures + Call Hedge (upside protection)
            orders = [
                # 1. BUY Far OTM Call HEDGE (FIRST - for margin benefit)
                {
                    "symbol": f"{symbol}{expiry}{int(hedge_strike)}CE",
                    "side": "BUY",
                    "lots": lots,
                    "quantity": lots * lot_qty,
                    "leg_type": "hedge_call",
                    "is_hedge": True,
                    "strike": hedge_strike,
                    "option_type": "CE",
                    "expiry": expiry,
                    "priority": 1,  # Execute FIRST
                    "execution_order": "HEDGE_FIRST"
                },
                
                # 2. SELL Futures (SECOND - after hedge is in place)
                {
                    "symbol": futures_symbol,
                    "side": "SELL",
                    "lots": lots,
                    "quantity": lots * lot_qty,
                    "leg_type": "main_futures",
                    "is_hedge": False,
                    "instrument_type": "FUTURES",
                    "expiry": expiry,
                    "priority": 2,  # Execute AFTER hedge
                    "execution_order": "MAIN_AFTER_HEDGE"
                }
            ]
        
        logger.info(f"Generated Directional Futures {direction} for {symbol}: "
                   f"Futures: {futures_symbol}, "
                   f"Hedge: {hedge_strike}{'PE' if direction == 'LONG' else 'CE'}, "
                   f"HEDGE-FIRST execution for margin benefit")
        
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Directional Futures specific risk management:
        - Higher risk tolerance due to trending nature
        - Trend reversal detection for early exit
        - Momentum-based profit taking
        """
        base_sl = config.get("sl_per_lot", 3000) * lot_count  # Higher SL for futures
        base_tp = config.get("tp_per_lot", 6000) * lot_count  # Higher TP potential
        
        direction = config.get("direction", "LONG")
        trend_strength = config.get("current_trend_strength", 0)
        entry_trend_strength = config.get("entry_trend_strength", 0)
        days_to_expiry = config.get("days_to_expiry", 10)
        
        # Adjust SL/TP based on trend strength
        trend_multiplier = min(1.5, max(0.8, trend_strength / 2.0))
        adjusted_tp = base_tp * trend_multiplier
        
        # Trend reversal detection
        trend_weakening = trend_strength < entry_trend_strength * 0.6
        
        if mtm <= -base_sl:
            return {
                "action": "HARD_STOP",
                "reason": f"Directional Futures {direction} SL triggered",
                "urgency": "HIGH"
            }
        elif mtm >= adjusted_tp:
            return {
                "action": "TAKE_PROFIT",
                "reason": f"Directional Futures {direction} TP achieved (trend-adjusted)",
                "urgency": "MEDIUM"
            }
        elif trend_weakening:
            return {
                "action": "TREND_REVERSAL_WARNING",
                "reason": f"Trend weakening: {entry_trend_strength:.1f} → {trend_strength:.1f}",
                "urgency": "MEDIUM"
            }
        elif days_to_expiry <= 5:
            return {
                "action": "EXPIRY_RISK_WARNING",
                "reason": f"Futures expiry in {days_to_expiry} days",
                "urgency": "MEDIUM"
            }
        elif mtm >= adjusted_tp * 0.7:
            return {
                "action": "MOMENTUM_PROFIT_OPPORTUNITY",
                "reason": f"Strong momentum: 70% of target achieved",
                "urgency": "LOW"
            }
        elif mtm <= -base_sl * 0.8:
            return {
                "action": "SOFT_WARN",
                "reason": f"Approaching Directional Futures SL ({direction})",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def _validate_futures_hedge(self, symbol: str, spot_price: float,
                               hedge_strike: float, direction: str) -> bool:
        """Validate futures hedge configuration"""
        
        if direction == "LONG":
            # Long futures needs put hedge below spot
            if hedge_strike >= spot_price:
                logger.error(f"Put hedge {hedge_strike} not below spot {spot_price} for long futures")
                return False
            
            # Check hedge distance
            hedge_distance = spot_price - hedge_strike
            expected_distance = self.hedge_distance_banknifty if symbol == "BANKNIFTY" else self.hedge_distance_nifty
            
            if hedge_distance < expected_distance * 0.5:
                logger.warning(f"Put hedge distance {hedge_distance} too small for {symbol}")
        
        elif direction == "SHORT":
            # Short futures needs call hedge above spot
            if hedge_strike <= spot_price:
                logger.error(f"Call hedge {hedge_strike} not above spot {spot_price} for short futures")
                return False
            
            # Check hedge distance
            hedge_distance = hedge_strike - spot_price
            expected_distance = self.hedge_distance_banknifty if symbol == "BANKNIFTY" else self.hedge_distance_nifty
            
            if hedge_distance < expected_distance * 0.5:
                logger.warning(f"Call hedge distance {hedge_distance} too small for {symbol}")
        
        return True

    def get_optimal_hedge_strike(self, spot_price: float, symbol: str, 
                               direction: str, current_vix: float) -> float:
        """
        Calculate optimal hedge strike based on direction and volatility
        """
        base_distance = self.hedge_distance_banknifty if symbol == "BANKNIFTY" else self.hedge_distance_nifty
        
        # Adjust hedge distance based on VIX (higher VIX = further OTM hedge)
        vix_multiplier = min(1.5, max(0.8, current_vix / 25.0))
        adjusted_distance = base_distance * vix_multiplier
        
        if direction == "LONG":
            # Put hedge below spot
            if symbol == "NIFTY":
                hedge_strike = round((spot_price - adjusted_distance) / 50) * 50
            else:  # BANKNIFTY
                hedge_strike = round((spot_price - adjusted_distance) / 100) * 100
        else:  # SHORT
            # Call hedge above spot
            if symbol == "NIFTY":
                hedge_strike = round((spot_price + adjusted_distance) / 50) * 50
            else:  # BANKNIFTY
                hedge_strike = round((spot_price + adjusted_distance) / 100) * 100
        
        return hedge_strike

    def check_trend_conditions(self, current_data: Dict, entry_data: Dict) -> Dict[str, Any]:
        """
        Check if trend conditions are still favorable
        """
        entry_trend_strength = entry_data.get("trend_strength", 0)
        current_trend_strength = current_data.get("trend_strength", 0)
        entry_direction = entry_data.get("direction", "LONG")
        
        # Check for trend reversal
        if entry_direction == "LONG" and current_trend_strength < -1.0:
            return {
                "action": "TREND_REVERSAL_ALERT",
                "message": f"Bullish trend reversed: {entry_trend_strength:.1f} → {current_trend_strength:.1f}",
                "recommended_action": "Consider exit",
                "urgency": "HIGH"
            }
        elif entry_direction == "SHORT" and current_trend_strength > 1.0:
            return {
                "action": "TREND_REVERSAL_ALERT", 
                "message": f"Bearish trend reversed: {entry_trend_strength:.1f} → {current_trend_strength:.1f}",
                "recommended_action": "Consider exit",
                "urgency": "HIGH"
            }
        
        # Check for trend weakening
        trend_change_pct = abs(current_trend_strength - entry_trend_strength) / abs(entry_trend_strength) * 100 if entry_trend_strength != 0 else 0
        
        if trend_change_pct > 50:  # 50% trend strength change
            return {
                "action": "TREND_WEAKENING_WARNING",
                "message": f"Trend strength changed {trend_change_pct:.1f}%",
                "recommended_action": "Monitor closely",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def calculate_position_delta(self, orders: List[Dict[str, Any]], 
                               spot_price: float) -> float:
        """
        Calculate net position delta (sensitivity to underlying price)
        """
        # Futures delta is approximately ±1.0 per lot
        # Options delta depends on strike and time to expiry
        net_delta = 0.0
        
        for order in orders:
            if order.get("instrument_type") == "FUTURES":
                if order.get("side") == "BUY":
                    net_delta += order.get("lots", 1) * 1.0  # Long futures delta ≈ +1
                else:
                    net_delta -= order.get("lots", 1) * 1.0  # Short futures delta ≈ -1
            else:
                # Option delta (simplified calculation)
                strike = order.get("strike", spot_price)
                option_type = order.get("option_type", "CE")
                
                # Simplified delta calculation (would use Black-Scholes in production)
                if option_type == "CE":
                    option_delta = max(0.05, min(0.95, (spot_price - strike) / spot_price + 0.5))
                else:  # PE
                    option_delta = max(0.05, min(0.95, (strike - spot_price) / spot_price + 0.5))
                
                if order.get("side") == "BUY":
                    net_delta += order.get("lots", 1) * option_delta
                else:
                    net_delta -= order.get("lots", 1) * option_delta
        
        return net_delta

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum loss for Directional Futures position
        Max loss is limited by hedge protection
        """
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum profit for Directional Futures
        Theoretically unlimited, but we use reasonable targets
        """
        return self.max_loss_per_trade * 2.0  # 1:2 risk-reward target

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """Get Directional Futures specific performance metrics"""
        base_metrics = self.get_strategy_info()
        
        directional_futures_metrics = {
            "hedge_distances": {
                "NIFTY": self.hedge_distance_nifty,
                "BANKNIFTY": self.hedge_distance_banknifty
            },
            "min_trend_strength": self.min_trend_strength,
            "vix_range": {"min": self.min_vix, "max": self.max_vix},
            "dte_range": {"min": self.min_days_to_expiry, "max": self.max_days_to_expiry},
            "risk_profile": "HIGH (directional exposure with hedge protection)",
            "profit_profile": "HIGH potential in trending markets",
            "market_outlook": "DIRECTIONAL (bullish or bearish)",
            "delta_strategy": "HIGH (significant directional exposure)",
            "theta_impact": "MINIMAL (futures have no time decay)",
            "gamma_risk": "LOW (futures have no gamma)",
            "vega_sensitivity": "LOW (minimal options exposure)",
            "trend_dependent": True,
            "volume_dependent": True,
            "best_conditions": "Strong trending markets with clear directional bias",
            "hedge_first_execution": True,
            "margin_efficiency": "HIGH (futures with hedge)"
        }
        
        return {**base_metrics, **directional_futures_metrics}

# Utility functions for Directional Futures analysis
def validate_directional_futures_structure(orders: List[Dict[str, Any]]) -> bool:
    """Validate that orders represent proper Directional Futures structure"""
    if len(orders) != 2:
        return False
    
    # Should have one futures and one options hedge
    futures_orders = [o for o in orders if o.get("instrument_type") == "FUTURES"]
    option_orders = [o for o in orders if o.get("option_type") in ["CE", "PE"]]
    
    if len(futures_orders) != 1 or len(option_orders) != 1:
        return False
    
    # Hedge order should be a buy
    hedge_order = option_orders[0]
    return hedge_order.get("side") == "BUY" and hedge_order.get("is_hedge") == True

def calculate_futures_margin_requirement(symbol: str, lots: int, spot_price: float) -> float:
    """
    Calculate approximate futures margin requirement
    """
    # SPAN margin is approximately 10-15% of contract value
    lot_size = 50 if symbol == "NIFTY" else 15  # BANKNIFTY
    contract_value = spot_price * lot_size * lots
    span_margin_rate = 0.12  # 12% approximate
    
    return contract_value * span_margin_rate

def check_hedge_first_execution_futures(orders: List[Dict[str, Any]]) -> bool:
    """Verify that hedge option is executed before futures position"""
    futures_orders = [o for o in orders if o.get("instrument_type") == "FUTURES"]
    hedge_orders = [o for o in orders if o.get("is_hedge", False)]
    
    if not futures_orders or not hedge_orders:
        return False
    
    # Check priority - hedge should have lower priority number (execute first)
    hedge_priority = hedge_orders[0].get("priority", 999)
    futures_priority = futures_orders[0].get("priority", 999)
    
    return hedge_priority < futures_priority

# Export the strategy class and utilities
__all__ = [
    "DirectionalFuturesStrategy",
    "validate_directional_futures_structure",
    "calculate_futures_margin_requirement",
    "check_hedge_first_execution_futures"
]
