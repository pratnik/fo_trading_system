"""
Hedged Strangle Strategy – F&O (NIFTY/BANKNIFTY only) | 4-leg hedged structure
- Structure: Sell OTM Call & OTM Put, buy further OTM Call & Put as hedge
- Designed for high volatility, range-expanding markets with neutral bias
- Compatible with intelligent strategy selector and performance tracking system
- Always includes hedge protection (no naked risk)
"""

from datetime import datetime
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config, validate_instrument_liquidity
import logging

logger = logging.getLogger("HedgedStrangleStrategy")

class HedgedStrangleStrategy(BaseStrategy):
    """
    Hedged Short Strangle Strategy - 4-leg structure:
    1. Sell OTM Call (premium collection)
    2. Sell OTM Put (premium collection)
    3. Buy far OTM Call (hedge protection)
    4. Buy far OTM Put (hedge protection)
    
    Best for: High volatility, neutral bias, expecting range expansion
    """

    name = StrategyType.HEDGED_STRANGLE
    required_leg_count = 4
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_vix = 20.0  # High volatility required
        self.max_vix = 45.0  # Upper limit for entry
        self.target_win_rate = 75.0  # Expected win rate
        self.max_loss_per_trade = 4000.0  # Higher risk tolerance for volatility
        
        # Hedged Strangle specific parameters
        self.hedge_distance_nifty = 200     # Hedge distance for NIFTY
        self.hedge_distance_banknifty = 400 # Hedge distance for BANKNIFTY
        self.min_premium_target = 2000      # Minimum premium to collect
        self.otm_distance_nifty = 100       # OTM distance for NIFTY short strikes
        self.otm_distance_banknifty = 200   # OTM distance for BANKNIFTY short strikes

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Hedged Strangle:
        - NIFTY/BANKNIFTY only (high liquidity enforcement)
        - High volatility environment (VIX > 20)
        - Neutral market bias (no strong directional trend)
        - No major events or expiry day
        - Sufficient implied volatility for premium collection
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        index_chg = abs(market_data.get("index_chg_pct", 0))
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        trend_strength = abs(market_data.get("trend_strength", 0))
        iv_rank = market_data.get("iv_rank", 50)  # Implied volatility rank
        
        # Strict liquidity validation
        if not validate_instrument_liquidity(symbol):
            logger.warning(f"Hedged Strangle rejected: {symbol} not in liquid instruments")
            return False
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            index_chg < settings.get("DANGER_ZONE_RISK", 1.25) and
            trend_strength < 2.0 and  # Not strongly trending
            not expiry and
            not events and
            iv_rank > 60  # High IV rank for good premium
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate Hedged Strangle orders with hedge-first execution:
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - expiry: Option expiry (e.g., "25JUL")
        - spot_price: Current underlying price
        - ce_otm_strike: Call strike to sell (OTM)
        - pe_otm_strike: Put strike to sell (OTM)
        - ce_hedge_strike: Far OTM call hedge
        - pe_hedge_strike: Far OTM put hedge
        """
        symbol = signal["symbol"]
        expiry = signal["expiry"]
        spot_price = signal["spot_price"]
        ce_otm = signal["ce_otm_strike"]
        pe_otm = signal["pe_otm_strike"]
        ce_hedge = signal["ce_hedge_strike"]
        pe_hedge = signal["pe_hedge_strike"]
        lots = config.get("lot_count", 1)
        
        # Validate strikes
        if not self._validate_strangle_strikes(symbol, spot_price, ce_otm, pe_otm, ce_hedge, pe_hedge):
            raise ValueError(f"Invalid Hedged Strangle strike selection for {symbol}")
        
        # Get instrument configuration
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        # HEDGE-FIRST ORDER EXECUTION (for margin benefit)
        orders = [
            # 1. BUY Far OTM Call HEDGE (FIRST - for margin benefit)
            {
                "symbol": f"{symbol}{expiry}{int(ce_hedge)}CE",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "hedge_call",
                "is_hedge": True,
                "strike": ce_hedge,
                "option_type": "CE",
                "expiry": expiry,
                "priority": 1,  # Execute FIRST
                "execution_order": "HEDGE_FIRST"
            },
            
            # 2. BUY Far OTM Put HEDGE (SECOND - for margin benefit)
            {
                "symbol": f"{symbol}{expiry}{int(pe_hedge)}PE",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "hedge_put",
                "is_hedge": True,
                "strike": pe_hedge,
                "option_type": "PE",
                "expiry": expiry,
                "priority": 2,  # Execute SECOND
                "execution_order": "HEDGE_FIRST"
            },
            
            # 3. SELL OTM Call (THIRD - after hedges are in place)
            {
                "symbol": f"{symbol}{expiry}{int(ce_otm)}CE",
                "side": "SELL",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_call",
                "is_hedge": False,
                "strike": ce_otm,
                "option_type": "CE",
                "expiry": expiry,
                "priority": 3,  # Execute AFTER hedges
                "execution_order": "MAIN_AFTER_HEDGE"
            },
            
            # 4. SELL OTM Put (FOURTH - after hedges are in place)
            {
                "symbol": f"{symbol}{expiry}{int(pe_otm)}PE",
                "side": "SELL",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_put",
                "is_hedge": False,
                "strike": pe_otm,
                "option_type": "PE",
                "expiry": expiry,
                "priority": 4,  # Execute AFTER hedges
                "execution_order": "MAIN_AFTER_HEDGE"
            }
        ]
        
        # Calculate expected net credit
        estimated_credit = self._calculate_estimated_credit(
            signal.get("estimated_premiums", {}), lots * lot_qty
        )
        
        logger.info(f"Generated Hedged Strangle for {symbol}: "
                   f"Short: {ce_otm}CE/{pe_otm}PE, "
                   f"Hedge: {ce_hedge}CE/{pe_hedge}PE, "
                   f"Estimated Credit: ₹{estimated_credit:,.0f}, "
                   f"HEDGE-FIRST execution for margin benefit")
        
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Hedged Strangle specific risk management:
        - Higher risk tolerance due to volatility strategy nature
        - Early exit on volatility crush
        - Gamma risk monitoring near expiry
        """
        sl = config.get("sl_per_lot", 2500) * lot_count  # Higher SL for vol strategies
        tp = config.get("tp_per_lot", 5000) * lot_count  # Higher TP potential
        
        # Check for volatility changes
        current_vix = config.get("current_vix", 20)
        entry_vix = config.get("entry_vix", 20)
        vix_crush = current_vix < entry_vix * 0.7  # 30% VIX drop
        days_to_expiry = config.get("days_to_expiry", 10)
        
        if mtm <= -sl:
            return {
                "action": "HARD_STOP",
                "reason": "Hedged Strangle SL triggered",
                "urgency": "HIGH"
            }
        elif mtm >= tp:
            return {
                "action": "TAKE_PROFIT",
                "reason": "Hedged Strangle TP achieved",
                "urgency": "MEDIUM"
            }
        elif vix_crush:
            return {
                "action": "VOLATILITY_CRUSH_EXIT",
                "reason": f"VIX crushed from {entry_vix:.1f} to {current_vix:.1f}",
                "urgency": "HIGH"
            }
        elif days_to_expiry <= 3:
            return {
                "action": "GAMMA_RISK_WARNING",
                "reason": f"High gamma risk: {days_to_expiry} days to expiry",
                "urgency": "MEDIUM"
            }
        elif mtm >= tp * 0.6:
            return {
                "action": "PROFIT_OPPORTUNITY",
                "reason": "60% of target profit achieved",
                "urgency": "LOW"
            }
        elif mtm <= -0.8 * sl:
            return {
                "action": "SOFT_WARN",
                "reason": "Approaching Hedged Strangle SL",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def _validate_strangle_strikes(self, symbol: str, spot_price: float,
                                 ce_otm: float, pe_otm: float, 
                                 ce_hedge: float, pe_hedge: float) -> bool:
        """Validate Hedged Strangle strike selection"""
        
        # Call strikes should be above spot
        if ce_otm <= spot_price or ce_hedge <= ce_otm:
            logger.error(f"Invalid call strikes: spot={spot_price}, ce_otm={ce_otm}, ce_hedge={ce_hedge}")
            return False
        
        # Put strikes should be below spot
        if pe_otm >= spot_price or pe_hedge >= pe_otm:
            logger.error(f"Invalid put strikes: spot={spot_price}, pe_otm={pe_otm}, pe_hedge={pe_hedge}")
            return False
        
        # Check hedge distances
        call_hedge_distance = ce_hedge - ce_otm
        put_hedge_distance = pe_otm - pe_hedge
        expected_distance = self.hedge_distance_banknifty if symbol == "BANKNIFTY" else self.hedge_distance_nifty
        
        if call_hedge_distance < expected_distance * 0.5:
            logger.warning(f"Call hedge distance {call_hedge_distance} too small for {symbol}")
        
        if put_hedge_distance < expected_distance * 0.5:
            logger.warning(f"Put hedge distance {put_hedge_distance} too small for {symbol}")
        
        return True

    def _calculate_estimated_credit(self, estimated_premiums: Dict, total_quantity: int) -> float:
        """Calculate estimated net credit for Hedged Strangle"""
        ce_sale_premium = estimated_premiums.get("ce_otm", 0)
        pe_sale_premium = estimated_premiums.get("pe_otm", 0)
        ce_hedge_premium = estimated_premiums.get("ce_hedge", 0)
        pe_hedge_premium = estimated_premiums.get("pe_hedge", 0)
        
        net_credit_per_share = (ce_sale_premium + pe_sale_premium) - (ce_hedge_premium + pe_hedge_premium)
        return net_credit_per_share * total_quantity

    def get_optimal_strikes(self, spot_price: float, symbol: str, 
                          current_vix: float) -> Dict[str, float]:
        """
        Calculate optimal Hedged Strangle strikes based on volatility
        """
        if symbol == "NIFTY":
            otm_distance = self.otm_distance_nifty
            hedge_distance = self.hedge_distance_nifty
            # Round to 50-point intervals
            ce_otm = round((spot_price + otm_distance) / 50) * 50
            pe_otm = round((spot_price - otm_distance) / 50) * 50
        elif symbol == "BANKNIFTY":
            otm_distance = self.otm_distance_banknifty
            hedge_distance = self.hedge_distance_banknifty
            # Round to 100-point intervals
            ce_otm = round((spot_price + otm_distance) / 100) * 100
            pe_otm = round((spot_price - otm_distance) / 100) * 100
        else:
            raise ValueError(f"Unsupported symbol for Hedged Strangle: {symbol}")
        
        # Adjust OTM distance based on VIX (higher VIX = further OTM)
        vix_multiplier = min(1.5, current_vix / 25.0)  # Scale with VIX
        adjusted_otm = otm_distance * vix_multiplier
        
        if symbol == "NIFTY":
            ce_otm = round((spot_price + adjusted_otm) / 50) * 50
            pe_otm = round((spot_price - adjusted_otm) / 50) * 50
        else:
            ce_otm = round((spot_price + adjusted_otm) / 100) * 100
            pe_otm = round((spot_price - adjusted_otm) / 100) * 100
        
        # Calculate hedge strikes
        ce_hedge = ce_otm + hedge_distance
        pe_hedge = pe_otm - hedge_distance
        
        return {
            "ce_otm_strike": ce_otm,
            "pe_otm_strike": pe_otm,
            "ce_hedge_strike": ce_hedge,
            "pe_hedge_strike": pe_hedge,
            "hedge_distance": hedge_distance,
            "vix_adjustment": vix_multiplier
        }

    def check_volatility_conditions(self, current_data: Dict, entry_data: Dict) -> Dict[str, Any]:
        """
        Check if volatility conditions are still favorable for the strangle
        """
        entry_vix = entry_data.get("entry_vix", 20)
        current_vix = current_data.get("vix", 20)
        iv_rank_current = current_data.get("iv_rank", 50)
        
        vix_change_pct = (current_vix - entry_vix) / entry_vix * 100
        
        if current_vix < entry_vix * 0.7:  # 30% VIX drop
            return {
                "action": "VOLATILITY_CRUSH_ALERT",
                "message": f"VIX crushed: {entry_vix:.1f} → {current_vix:.1f} ({vix_change_pct:+.1f}%)",
                "recommended_action": "Consider early exit",
                "urgency": "HIGH"
            }
        elif current_vix > entry_vix * 1.3:  # 30% VIX spike
            return {
                "action": "VOLATILITY_SPIKE_OPPORTUNITY",
                "message": f"VIX spiked: {entry_vix:.1f} → {current_vix:.1f} ({vix_change_pct:+.1f}%)",
                "recommended_action": "Monitor for profit taking opportunity",
                "urgency": "MEDIUM"
            }
        elif iv_rank_current < 30:  # Low IV rank
            return {
                "action": "LOW_IV_WARNING",
                "message": f"IV rank dropped to {iv_rank_current}",
                "recommended_action": "Consider closing position",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum loss for Hedged Strangle
        Max loss is limited by hedge protection
        """
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum profit for Hedged Strangle
        Max profit = Net credit received (if price stays between short strikes)
        """
        return self.min_premium_target * 1.5  # Estimate based on premium target

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """Get Hedged Strangle specific performance metrics"""
        base_metrics = self.get_strategy_info()
        
        hedged_strangle_metrics = {
            "hedge_distances": {
                "NIFTY": self.hedge_distance_nifty,
                "BANKNIFTY": self.hedge_distance_banknifty
            },
            "otm_distances": {
                "NIFTY": self.otm_distance_nifty,
                "BANKNIFTY": self.otm_distance_banknifty
            },
            "min_premium_target": self.min_premium_target,
            "vix_range": {"min": self.min_vix, "max": self.max_vix},
            "risk_profile": "LIMITED by hedge protection",
            "profit_profile": "HIGH potential with volatility expansion",
            "market_outlook": "NEUTRAL with volatility expectation",
            "theta_strategy": False,  # Short term, not theta dependent
            "vega_strategy": "LONG (benefits from volatility increase)",
            "gamma_risk": "MODERATE (hedged but still present)",
            "volatility_dependent": True,
            "best_conditions": "High VIX, neutral bias, expecting range expansion",
            "hedge_first_execution": True  # Key feature for margin benefit
        }
        
        return {**base_metrics, **hedged_strangle_metrics}

# Utility functions for Hedged Strangle analysis
def validate_hedged_strangle_structure(orders: List[Dict[str, Any]]) -> bool:
    """Validate that orders represent proper Hedged Strangle structure"""
    if len(orders) != 4:
        return False
    
    # Should have 2 calls and 2 puts
    calls = [o for o in orders if o.get("option_type") == "CE"]
    puts = [o for o in orders if o.get("option_type") == "PE"]
    
    if len(calls) != 2 or len(puts) != 2:
        return False
    
    # Should have one short and one long for each type
    call_sides = [o.get("side") for o in calls]
    put_sides = [o.get("side") for o in puts]
    
    return ("BUY" in call_sides and "SELL" in call_sides and 
            "BUY" in put_sides and "SELL" in put_sides)

def calculate_strangle_breakevens(ce_strike: float, pe_strike: float, 
                                net_credit: float) -> Dict[str, float]:
    """Calculate Hedged Strangle breakeven points"""
    return {
        "upper_breakeven": ce_strike + net_credit,
        "lower_breakeven": pe_strike - net_credit,
        "profit_zone_upper": ce_strike,
        "profit_zone_lower": pe_strike,
        "max_profit_range": f"Between {pe_strike} and {ce_strike}"
    }

def check_hedge_first_execution(orders: List[Dict[str, Any]]) -> bool:
    """Verify that hedge orders have priority for execution first"""
    hedge_orders = [o for o in orders if o.get("is_hedge", False)]
    main_orders = [o for o in orders if not o.get("is_hedge", False)]
    
    if not hedge_orders or not main_orders:
        return False
    
    # Check that all hedge orders have lower priority numbers (execute first)
    min_hedge_priority = min(o.get("priority", 999) for o in hedge_orders)
    min_main_priority = min(o.get("priority", 999) for o in main_orders)
    
    return min_hedge_priority < min_main_priority

# Export the strategy class and utilities
__all__ = [
    "HedgedStrangleStrategy",
    "validate_hedged_strangle_structure",
    "calculate_strangle_breakevens",
    "check_hedge_first_execution"
]
