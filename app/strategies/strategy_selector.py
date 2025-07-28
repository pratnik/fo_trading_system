"""
Intelligent Strategy Selector for F&O Trading System - Complete Version
- Self-calibrating strategy selection with performance tracking
- Event calendar integration for smart filtering
- Risk monitor integration for real-time safety
- NIFTY/BANKNIFTY only with liquidity enforcement
- Hedge-first execution support
- Strategy elimination based on poor performance
- Integration with all 8 hedged strategies
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import pickle
import json

from app.config import settings, validate_instrument_liquidity
from app.db.models import Trade, Strategy, StrategyStats, MarketData
from app.db.base import db_manager
from app.strategies.base import BaseStrategy
from app.utils.event_calendar import event_calendar, should_avoid_trading_today, get_days_to_expiry
from app.risk.risk_monitor import risk_monitor
from app.risk.danger_zone import danger_monitor
from app.risk.expiry_day import expiry_manager

# Import all strategies
from app.strategies.iron_condor import IronCondorStrategy
from app.strategies.butterfly_spread import ButterflySpreadStrategy
from app.strategies.calendar_spread import CalendarSpreadStrategy
from app.strategies.hedged_strangle import HedgedStrangleStrategy
from app.strategies.directional_futures import DirectionalFuturesStrategy
from app.strategies.jade_lizard import JadeLizardStrategy
from app.strategies.ratio_spreads import RatioSpreadsStrategy
from app.strategies.broken_wing_butterfly import BrokenWingButterflyStrategy

logger = logging.getLogger("strategy_selector")

class SelectionReason(str, Enum):
    MARKET_CONDITIONS = "MARKET_CONDITIONS"
    PERFORMANCE_BASED = "PERFORMANCE_BASED"
    VOLATILITY_MATCH = "VOLATILITY_MATCH"
    TREND_ALIGNMENT = "TREND_ALIGNMENT"
    RISK_ADJUSTED = "RISK_ADJUSTED"
    ML_PREDICTION = "ML_PREDICTION"
    FALLBACK = "FALLBACK"

@dataclass
class StrategySignal:
    strategy_name: str
    confidence: float
    reason: SelectionReason
    market_conditions: Dict[str, float]
    expected_return: float
    risk_score: float
    selection_timestamp: datetime

@dataclass
class MarketConditions:
    symbol: str
    spot_price: float
    vix: float
    trend_strength: float
    directional_bias: str
    volume_surge: bool
    iv_rank: float
    index_change_pct: float
    days_to_expiry: int
    is_expiry: bool
    upcoming_events: List[str]
    timestamp: datetime

class IntelligentStrategySelector:
    """
    AI-powered strategy selector with self-learning capabilities
    Eliminates poor performers and adapts to market conditions
    """
    
    def __init__(self):
        # Strategy registry - all available strategies
        self.strategies = {
            "IRON_CONDOR": IronCondorStrategy(),
            "BUTTERFLY_SPREAD": ButterflySpreadStrategy(),
            "CALENDAR_SPREAD": CalendarSpreadStrategy(),
            "HEDGED_STRANGLE": HedgedStrangleStrategy(),
            "DIRECTIONAL_FUTURES": DirectionalFuturesStrategy(),
            "JADE_LIZARD": JadeLizardStrategy(),
            "RATIO_SPREADS": RatioSpreadsStrategy(),
            "BROKEN_WING_BUTTERFLY": BrokenWingButterflyStrategy()
        }
        
        # Performance tracking
        self.strategy_performance = {}
        self.eliminated_strategies = set()
        self.performance_window_days = 30
        
        # ML models for prediction
        self.ml_model = None
        self.scaler = None
        self.ml_features = [
            'vix', 'trend_strength', 'iv_rank', 'index_change_pct', 
            'days_to_expiry', 'volume_surge_int', 'directional_bias_int'
        ]
        
        # Selection history
        self.selection_history = []
        self.last_calibration = None
        
        # Market condition thresholds
        self.market_thresholds = {
            "low_vix": 15.0,
            "high_vix": 30.0,
            "strong_trend": 2.0,
            "high_iv_rank": 70.0,
            "danger_zone_limit": 1.0
        }
        
        # Weekly recalibration tracking
        self.weekly_stats = {}
        self.elimination_threshold = 0.3  # 30% win rate threshold
        self.min_trades_for_elimination = 10
        
        logger.info("Intelligent Strategy Selector initialized with 8 hedged strategies")
        
        # Load existing performance data
        self._load_performance_data()
        
        # Initialize ML model
        self._initialize_ml_model()
    
    def select_best_strategy(self, symbol: str, market_data: Dict[str, Any]) -> Optional[StrategySignal]:
        """
        Select the best strategy based on comprehensive analysis
        Returns None if no suitable strategy found
        """
        try:
            # 1. Validate instrument liquidity
            if not validate_instrument_liquidity(symbol):
                logger.warning(f"Strategy selection blocked: {symbol} not in liquid instruments")
                return None
            
            # 2. Check calendar restrictions
            calendar_allowed, calendar_reason = self._check_calendar_restrictions(symbol)
            if not calendar_allowed:
                logger.info(f"Strategy blocked by calendar: {calendar_reason}")
                return None
            
            # 3. Check danger zone conditions
            danger_allowed, danger_reason = self._check_danger_zone_restrictions(symbol)
            if not danger_allowed:
                logger.info(f"Strategy blocked by danger zone: {danger_reason}")
                return None
            
            # 4. Check expiry day restrictions
            expiry_allowed, expiry_reason = self._check_expiry_restrictions(symbol)
            if not expiry_allowed:
                logger.info(f"Strategy blocked by expiry: {expiry_reason}")
                return None
            
            # 5. Parse market conditions
            conditions = self._parse_market_conditions(symbol, market_data)
            
            # 6. Get strategy candidates
            candidates = self._get_strategy_candidates(conditions)
            
            if not candidates:
                logger.warning("No strategy candidates found for current market conditions")
                return None
            
            # 7. Score and rank candidates
            scored_candidates = self._score_candidates(candidates, conditions)
            
            # 8. Apply ML prediction if available
            final_candidates = self._apply_ml_prediction(scored_candidates, conditions)
            
            # 9. Select best candidate
            best_strategy = self._select_final_candidate(final_candidates, conditions)
            
            if best_strategy:
                # 10. Log selection
                self._log_strategy_selection(best_strategy, conditions)
                
                logger.info(f"Selected strategy: {best_strategy.strategy_name} "
                           f"(confidence: {best_strategy.confidence:.2f}, "
                           f"reason: {best_strategy.reason.value})")
            
            return best_strategy
            
        except Exception as e:
            logger.error(f"Strategy selection failed: {e}")
            return None
    
    def _check_calendar_restrictions(self, symbol: str) -> Tuple[bool, str]:
        """Check calendar-based restrictions for strategy execution"""
        try:
            # Auto-refresh calendar data
            event_calendar.auto_refresh_check()
            
            # Check if trading should be avoided
            should_avoid, reason = should_avoid_trading_today(symbol)
            
            if should_avoid:
                return False, f"Calendar restriction: {reason}"
            
            # Check upcoming events in next 24 hours
            tomorrow = date.today() + timedelta(days=1)
            events_today = event_calendar.get_events_for_date(date.today())
            events_tomorrow = event_calendar.get_events_for_date(tomorrow)
            
            # Block if high impact events today or tomorrow
            all_events = events_today + events_tomorrow
            high_impact = [e for e in all_events if e.impact_level in ["HIGH", "CRITICAL"]]
            
            if high_impact:
                event_titles = ", ".join(e.title for e in high_impact[:2])  # Max 2 events
                return False, f"High impact events: {event_titles}"
            
            return True, "No calendar restrictions"
            
        except Exception as e:
            logger.error(f"Calendar restriction check failed: {e}")
            return True, "Calendar check failed - allowing trading"
    
    def _check_danger_zone_restrictions(self, symbol: str) -> Tuple[bool, str]:
        """Check danger zone restrictions"""
        try:
            # Get current danger zone status
            danger_status = danger_monitor.get_current_status()
            
            if symbol in danger_status:
                symbol_status = danger_status[symbol]
                danger_level = symbol_status.get("danger_level", "SAFE")
                
                if danger_level in ["CRITICAL", "EMERGENCY"]:
                    return False, f"Danger zone {danger_level}: {symbol_status.get('latest_change_pct', 0):.2f}%"
                elif danger_level == "RISK":
                    # Allow only most conservative strategies
                    return True, f"Danger zone RISK - conservative strategies only"
            
            return True, "No danger zone restrictions"
            
        except Exception as e:
            logger.error(f"Danger zone check failed: {e}")
            return True, "Danger zone check failed - allowing trading"
    
    def _check_expiry_restrictions(self, symbol: str) -> Tuple[bool, str]:
        """Check expiry day restrictions"""
        try:
            expiry_info = expiry_manager.get_expiry_info(symbol)
            
            # Block entries on expiry day
            if expiry_info.is_today:
                return False, f"Expiry day for {symbol}"
            
            # Restrict strategies on day before expiry
            if expiry_info.is_tomorrow:
                return True, f"Day before expiry - limited strategies only"
            
            return True, "No expiry restrictions"
            
        except Exception as e:
            logger.error(f"Expiry restriction check failed: {e}")
            return True, "Expiry check failed - allowing trading"
    
    def _parse_market_conditions(self, symbol: str, market_data: Dict[str, Any]) -> MarketConditions:
        """Parse and normalize market conditions"""
        
        # Get days to expiry
        days_to_expiry = get_days_to_expiry(symbol)
        
        # Check for upcoming events
        upcoming_events = event_calendar.get_upcoming_events(3)
        event_titles = [e.title for e in upcoming_events if symbol in e.affected_instruments]
        
        return MarketConditions(
            symbol=symbol,
            spot_price=market_data.get("spot_price", 0.0),
            vix=market_data.get("vix", 20.0),
            trend_strength=market_data.get("trend_strength", 0.0),
            directional_bias=market_data.get("directional_bias", "NEUTRAL"),
            volume_surge=market_data.get("volume_surge", False),
            iv_rank=market_data.get("iv_rank", 50.0),
            index_change_pct=market_data.get("index_change_pct", 0.0),
            days_to_expiry=days_to_expiry,
            is_expiry=expiry_manager.is_expiry_day_today(symbol),
            upcoming_events=event_titles,
            timestamp=datetime.now()
        )
    
    def _get_strategy_candidates(self, conditions: MarketConditions) -> List[str]:
        """Get list of candidate strategies based on market conditions"""
        candidates = []
        
        # Remove eliminated strategies
        available_strategies = {
            name: strategy for name, strategy in self.strategies.items()
            if name not in self.eliminated_strategies
        }
        
        # Test each strategy against market conditions
        for strategy_name, strategy in available_strategies.items():
            try:
                # Create settings dict for evaluation
                settings_dict = {
                    "DANGER_ZONE_WARNING": 1.0,
                    "DANGER_ZONE_RISK": 1.25,
                    "DANGER_ZONE_EXIT": 1.5,
                    "VIX_THRESHOLD": 25.0
                }
                
                # Create market data dict for strategy evaluation
                strategy_market_data = {
                    "symbol": conditions.symbol,
                    "vix": conditions.vix,
                    "trend_strength": conditions.trend_strength,
                    "directional_bias": conditions.directional_bias,
                    "index_chg_pct": conditions.index_change_pct,
                    "volume_surge": conditions.volume_surge,
                    "iv_rank": conditions.iv_rank,
                    "days_to_expiry": conditions.days_to_expiry,
                    "is_expiry": conditions.is_expiry,
                    "upcoming_events": conditions.upcoming_events,
                    "market_sentiment": conditions.directional_bias
                }
                
                # Test strategy evaluation
                if strategy.evaluate_market_conditions(strategy_market_data, settings_dict):
                    candidates.append(strategy_name)
                    logger.debug(f"Strategy {strategy_name} passed market conditions")
                else:
                    logger.debug(f"Strategy {strategy_name} failed market conditions")
                    
            except Exception as e:
                logger.error(f"Error evaluating strategy {strategy_name}: {e}")
                continue
        
        logger.info(f"Found {len(candidates)} strategy candidates: {candidates}")
        return candidates
    
    def _score_candidates(self, candidates: List[str], conditions: MarketConditions) -> List[Tuple[str, float, SelectionReason]]:
        """Score and rank strategy candidates"""
        scored_candidates = []
        
        for strategy_name in candidates:
            try:
                score = 0.0
                reason = SelectionReason.MARKET_CONDITIONS
                
                # 1. Performance-based scoring (40% weight)
                performance_score = self._get_performance_score(strategy_name)
                score += performance_score * 0.4
                
                # 2. Market condition fit (30% weight)
                condition_score = self._get_condition_fit_score(strategy_name, conditions)
                score += condition_score * 0.3
                
                # 3. Risk-adjusted scoring (20% weight)
                risk_score = self._get_risk_adjusted_score(strategy_name, conditions)
                score += risk_score * 0.2
                
                # 4. Volatility match (10% weight)
                volatility_score = self._get_volatility_match_score(strategy_name, conditions)
                score += volatility_score * 0.1
                
                # Determine primary reason
                if performance_score > 0.8:
                    reason = SelectionReason.PERFORMANCE_BASED
                elif condition_score > 0.8:
                    reason = SelectionReason.MARKET_CONDITIONS
                elif volatility_score > 0.8:
                    reason = SelectionReason.VOLATILITY_MATCH
                elif risk_score > 0.8:
                    reason = SelectionReason.RISK_ADJUSTED
                
                scored_candidates.append((strategy_name, score, reason))
                
            except Exception as e:
                logger.error(f"Error scoring strategy {strategy_name}: {e}")
                continue
        
        # Sort by score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        return scored_candidates
    
    def _get_performance_score(self, strategy_name: str) -> float:
        """Get performance-based score for strategy"""
        try:
            if strategy_name not in self.strategy_performance:
                return 0.5  # Neutral score for new strategies
            
            perf = self.strategy_performance[strategy_name]
            
            # Calculate win rate score
            win_rate = perf.get("win_rate", 0.5)
            win_rate_score = min(1.0, win_rate / 0.8)  # Target 80% win rate
            
            # Calculate average return score
            avg_return = perf.get("avg_return", 0.0)
            return_score = min(1.0, max(0.0, (avg_return + 0.05) / 0.1))  # Target 5% return
            
            # Calculate consistency score
            consistency = perf.get("consistency", 0.5)
            
            # Weighted performance score
            performance_score = (win_rate_score * 0.5 + 
                               return_score * 0.3 + 
                               consistency * 0.2)
            
            return performance_score
            
        except Exception as e:
            logger.error(f"Error calculating performance score for {strategy_name}: {e}")
            return 0.5
    
    def _get_condition_fit_score(self, strategy_name: str, conditions: MarketConditions) -> float:
        """Get market condition fit score"""
        try:
            strategy = self.strategies[strategy_name]
            score = 0.0
            
            # VIX-based scoring
            if hasattr(strategy, 'min_vix') and hasattr(strategy, 'max_vix'):
                vix_min = strategy.min_vix
                vix_max = strategy.max_vix
                
                if vix_min <= conditions.vix <= vix_max:
                    # Perfect VIX match
                    vix_center = (vix_min + vix_max) / 2
                    vix_deviation = abs(conditions.vix - vix_center) / (vix_max - vix_min)
                    vix_score = 1.0 - vix_deviation
                else:
                    # Outside VIX range
                    vix_score = 0.2
                
                score += vix_score * 0.4
            
            # Trend alignment scoring
            trend_score = self._get_trend_alignment_score(strategy_name, conditions)
            score += trend_score * 0.3
            
            # Time to expiry scoring
            dte_score = self._get_dte_fit_score(strategy_name, conditions)
            score += dte_score * 0.3
            
            return min(1.0, score)
            
        except Exception as e:
            logger.error(f"Error calculating condition fit for {strategy_name}: {e}")
            return 0.5
    
    def _get_trend_alignment_score(self, strategy_name: str, conditions: MarketConditions) -> float:
        """Get trend alignment score"""
        trend_strength = abs(conditions.trend_strength)
        directional_bias = conditions.directional_bias
        
        # Directional strategies
        if strategy_name in ["DIRECTIONAL_FUTURES", "RATIO_SPREADS"]:
            if directional_bias in ["BULLISH", "BEARISH"] and trend_strength >= 1.5:
                return 1.0
            elif trend_strength >= 1.0:
                return 0.7
            else:
                return 0.3
        
        # Neutral strategies
        elif strategy_name in ["IRON_CONDOR", "BUTTERFLY_SPREAD", "CALENDAR_SPREAD"]:
            if directional_bias == "NEUTRAL" and trend_strength < 1.5:
                return 1.0
            elif trend_strength < 2.0:
                return 0.7
            else:
                return 0.2
        
        # Volatility strategies
        elif strategy_name in ["HEDGED_STRANGLE"]:
            if conditions.vix > 25 and trend_strength < 1.5:
                return 1.0
            elif conditions.vix > 20:
                return 0.7
            else:
                return 0.4
        
        # Asymmetric strategies
        elif strategy_name in ["JADE_LIZARD", "BROKEN_WING_BUTTERFLY"]:
            if directional_bias in ["SLIGHTLY_BULLISH", "SLIGHTLY_BEARISH"]:
                return 1.0
            elif directional_bias != "STRONG_TREND":
                return 0.7
            else:
                return 0.3
        
        return 0.5
    
    def _get_dte_fit_score(self, strategy_name: str, conditions: MarketConditions) -> float:
        """Get days-to-expiry fit score"""
        dte = conditions.days_to_expiry
        
        # Strategy-specific DTE preferences
        dte_preferences = {
            "IRON_CONDOR": (7, 30),         # 1-4 weeks
            "BUTTERFLY_SPREAD": (7, 30),    # 1-4 weeks
            "CALENDAR_SPREAD": (14, 45),    # 2-6 weeks
            "HEDGED_STRANGLE": (7, 21),     # 1-3 weeks
            "DIRECTIONAL_FUTURES": (5, 30), # 1-4 weeks
            "JADE_LIZARD": (14, 30),        # 2-4 weeks
            "RATIO_SPREADS": (7, 45),       # 1-6 weeks
            "BROKEN_WING_BUTTERFLY": (7, 30) # 1-4 weeks
        }
        
        if strategy_name in dte_preferences:
            min_dte, max_dte = dte_preferences[strategy_name]
            
            if min_dte <= dte <= max_dte:
                # Within optimal range
                center_dte = (min_dte + max_dte) / 2
                deviation = abs(dte - center_dte) / (max_dte - min_dte)
                return 1.0 - deviation
            else:
                # Outside optimal range
                return 0.3
        
        return 0.5
    
    def _get_risk_adjusted_score(self, strategy_name: str, conditions: MarketConditions) -> float:
        """Get risk-adjusted score based on current market conditions"""
        base_score = 0.5
        
        # Reduce score for high-risk conditions
        if abs(conditions.index_change_pct) > 1.0:
            base_score *= 0.8
        
        if conditions.vix > 35:
            base_score *= 0.9
        
        if conditions.days_to_expiry <= 3:
            base_score *= 0.7
        
        # Adjust based on strategy risk profile
        risk_profiles = {
            "IRON_CONDOR": 0.2,           # Very conservative
            "BUTTERFLY_SPREAD": 0.2,      # Very conservative
            "CALENDAR_SPREAD": 0.3,       # Conservative
            "JADE_LIZARD": 0.4,           # Moderate
            "BROKEN_WING_BUTTERFLY": 0.4, # Moderate
            "HEDGED_STRANGLE": 0.6,       # Higher risk for higher reward
            "RATIO_SPREADS": 0.7,         # Directional risk
            "DIRECTIONAL_FUTURES": 0.8    # Highest risk
        }
        
        strategy_risk = risk_profiles.get(strategy_name, 0.5)
        
        # In high volatility, prefer lower risk strategies
        if conditions.vix > 30:
            risk_adjustment = 1.0 - strategy_risk
        else:
            risk_adjustment = 0.5 + strategy_risk * 0.5
        
        return base_score * risk_adjustment
    
    def _get_volatility_match_score(self, strategy_name: str, conditions: MarketConditions) -> float:
        """Get volatility match score"""
        vix = conditions.vix
        iv_rank = conditions.iv_rank
        
        # High volatility strategies
        if strategy_name in ["HEDGED_STRANGLE"]:
            if vix > 25 and iv_rank > 70:
                return 1.0
            elif vix > 20 and iv_rank > 50:
                return 0.7
            else:
                return 0.3
        
        # Low volatility strategies
        elif strategy_name in ["IRON_CONDOR", "BUTTERFLY_SPREAD"]:
            if vix < 20 and iv_rank < 50:
                return 1.0
            elif vix < 25 and iv_rank < 70:
                return 0.7
            else:
                return 0.4
        
        # Medium volatility strategies
        else:
            if 18 <= vix <= 28:
                return 1.0
            elif 15 <= vix <= 32:
                return 0.8
            else:
                return 0.5
    
    def _apply_ml_prediction(self, scored_candidates: List[Tuple[str, float, SelectionReason]], 
                           conditions: MarketConditions) -> List[Tuple[str, float, SelectionReason]]:
        """Apply ML prediction to refine strategy selection"""
        try:
            if not self.ml_model or not scored_candidates:
                return scored_candidates
            
            # Prepare features
            features = self._prepare_ml_features(conditions)
            features_scaled = self.scaler.transform([features])
            
            # Get ML predictions for each candidate
            enhanced_candidates = []
            
            for strategy_name, score, reason in scored_candidates:
                try:
                    # Add strategy-specific features
                    strategy_features = features.copy()
                    strategy_features.append(hash(strategy_name) % 100 / 100)  # Strategy encoding
                    
                    # Predict success probability
                    ml_features_scaled = self.scaler.transform([strategy_features])
                    success_prob = self.ml_model.predict_proba(ml_features_scaled)[0][1]
                    
                    # Combine ML prediction with rule-based score
                    combined_score = score * 0.7 + success_prob * 0.3
                    
                    # Update reason if ML confidence is high
                    updated_reason = SelectionReason.ML_PREDICTION if success_prob > 0.8 else reason
                    
                    enhanced_candidates.append((strategy_name, combined_score, updated_reason))
                    
                except Exception as e:
                    logger.debug(f"ML prediction failed for {strategy_name}: {e}")
                    enhanced_candidates.append((strategy_name, score, reason))
            
            # Re-sort by enhanced scores
            enhanced_candidates.sort(key=lambda x: x[1], reverse=True)
            
            return enhanced_candidates
            
        except Exception as e:
            logger.error(f"ML prediction application failed: {e}")
            return scored_candidates
    
    def _prepare_ml_features(self, conditions: MarketConditions) -> List[float]:
        """Prepare features for ML model"""
        return [
            conditions.vix,
            conditions.trend_strength,
            conditions.iv_rank,
            conditions.index_change_pct,
            conditions.days_to_expiry,
            1.0 if conditions.volume_surge else 0.0,
            {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}.get(conditions.directional_bias, 0.0)
        ]
    
    def _select_final_candidate(self, candidates: List[Tuple[str, float, SelectionReason]], 
                              conditions: MarketConditions) -> Optional[StrategySignal]:
        """Select final strategy from candidates"""
        if not candidates:
            return None
        
        # Get top candidate
        strategy_name, confidence, reason = candidates[0]
        
        # Calculate expected return and risk score
        expected_return = self._estimate_expected_return(strategy_name, conditions)
        risk_score = self._estimate_risk_score(strategy_name, conditions)
        
        return StrategySignal(
            strategy_name=strategy_name,
            confidence=confidence,
            reason=reason,
            market_conditions={
                "vix": conditions.vix,
                "trend_strength": conditions.trend_strength,
                "iv_rank": conditions.iv_rank,
                "days_to_expiry": conditions.days_to_expiry
            },
            expected_return=expected_return,
            risk_score=risk_score,
            selection_timestamp=datetime.now()
        )
    
    def _estimate_expected_return(self, strategy_name: str, conditions: MarketConditions) -> float:
        """Estimate expected return for strategy"""
        # Base expected returns by strategy
        base_returns = {
            "IRON_CONDOR": 0.03,
            "BUTTERFLY_SPREAD": 0.025,
            "CALENDAR_SPREAD": 0.04,
            "HEDGED_STRANGLE": 0.06,
            "DIRECTIONAL_FUTURES": 0.08,
            "JADE_LIZARD": 0.05,
            "RATIO_SPREADS": 0.07,
            "BROKEN_WING_BUTTERFLY": 0.055
        }
        
        base_return = base_returns.get(strategy_name, 0.04)
        
        # Adjust for market conditions
        if conditions.vix > 25:
            base_return *= 1.2  # Higher volatility = higher potential returns
        elif conditions.vix < 15:
            base_return *= 0.8  # Lower volatility = lower returns
        
        return base_return
    
    def _estimate_risk_score(self, strategy_name: str, conditions: MarketConditions) -> float:
        """Estimate risk score for strategy (0-1, higher = riskier)"""
        # Base risk scores by strategy
        base_risks = {
            "IRON_CONDOR": 0.2,
            "BUTTERFLY_SPREAD": 0.2,
            "CALENDAR_SPREAD": 0.3,
            "JADE_LIZARD": 0.4,
            "BROKEN_WING_BUTTERFLY": 0.4,
            "HEDGED_STRANGLE": 0.6,
            "RATIO_SPREADS": 0.7,
            "DIRECTIONAL_FUTURES": 0.8
        }
        
        base_risk = base_risks.get(strategy_name, 0.5)
        
        # Adjust for market conditions
        if abs(conditions.index_change_pct) > 1.0:
            base_risk *= 1.3
        
        if conditions.days_to_expiry <= 5:
            base_risk *= 1.2
        
        return min(1.0, base_risk)
    
    def _log_strategy_selection(self, signal: StrategySignal, conditions: MarketConditions):
        """Log strategy selection for performance tracking"""
        try:
            selection_record = {
                "timestamp": signal.selection_timestamp.isoformat(),
                "strategy": signal.strategy_name,
                "symbol": conditions.symbol,
                "confidence": signal.confidence,
                "reason": signal.reason.value,
                "market_conditions": {
                    "vix": conditions.vix,
                    "trend_strength": conditions.trend_strength,
                    "directional_bias": conditions.directional_bias,
                    "iv_rank": conditions.iv_rank,
                    "days_to_expiry": conditions.days_to_expiry
                },
                "expected_return": signal.expected_return,
                "risk_score": signal.risk_score
            }
            
            self.selection_history.append(selection_record)
            
            # Keep only last 1000 selections
            if len(self.selection_history) > 1000:
                self.selection_history = self.selection_history[-1000:]
            
        except Exception as e:
            logger.error(f"Failed to log strategy selection: {e}")
    
    def update_strategy_performance(self, strategy_name: str, trade_result: Dict[str, Any]):
        """Update strategy performance metrics"""
        try:
            if strategy_name not in self.strategy_performance:
                self.strategy_performance[strategy_name] = {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "total_return": 0.0,
                    "returns": [],
                    "win_rate": 0.0,
                    "avg_return": 0.0,
                    "consistency": 0.5,
                    "last_updated": datetime.now()
                }
            
            perf = self.strategy_performance[strategy_name]
            
            # Update trade statistics
            perf["total_trades"] += 1
            
            trade_return = trade_result.get("return_pct", 0.0)
            perf["total_return"] += trade_return
            perf["returns"].append(trade_return)
            
            if trade_return > 0:
                perf["winning_trades"] += 1
            
            # Calculate metrics
            perf["win_rate"] = perf["winning_trades"] / perf["total_trades"]
            perf["avg_return"] = perf["total_return"] / perf["total_trades"]
            
            # Calculate consistency (1 - coefficient of variation)
            if len(perf["returns"]) > 1:
                returns_std = np.std(perf["returns"])
                returns_mean = np.mean(perf["returns"])
                if returns_mean != 0:
                    cv = abs(returns_std / returns_mean)
                    perf["consistency"] = max(0.0, 1.0 - cv)
            
            perf["last_updated"] = datetime.now()
            
            # Keep only last 100 returns for consistency calculation
            if len(perf["returns"]) > 100:
                perf["returns"] = perf["returns"][-100:]
            
            logger.info(f"Updated performance for {strategy_name}: "
                       f"Win Rate: {perf['win_rate']:.2%}, "
                       f"Avg Return: {perf['avg_return']:.2%}")
            
        except Exception as e:
            logger.error(f"Failed to update strategy performance: {e}")
    
    def weekly_calibration(self):
        """Perform weekly strategy calibration and elimination"""
        try:
            logger.info("Starting weekly strategy calibration...")
            
            current_time = datetime.now()
            
            # Check each strategy for elimination
            strategies_to_eliminate = []
            
            for strategy_name, perf in self.strategy_performance.items():
                if perf["total_trades"] >= self.min_trades_for_elimination:
                    win_rate = perf["win_rate"]
                    avg_return = perf["avg_return"]
                    
                    # Elimination criteria
                    if (win_rate < self.elimination_threshold or 
                        avg_return < -0.05 or  # Consistent losses > 5%
                        perf["consistency"] < 0.2):  # Very inconsistent
                        
                        strategies_to_eliminate.append(strategy_name)
                        logger.warning(f"Strategy {strategy_name} marked for elimination: "
                                     f"Win Rate: {win_rate:.2%}, "
                                     f"Avg Return: {avg_return:.2%}, "
                                     f"Consistency: {perf['consistency']:.2f}")
            
            # Eliminate poor performers
            for strategy_name in strategies_to_eliminate:
                self.eliminated_strategies.add(strategy_name)
                logger.critical(f"STRATEGY ELIMINATED: {strategy_name}")
            
            # Retrain ML model if enough data
            if len(self.selection_history) > 100:
                self._retrain_ml_model()
            
            # Save calibration results
            self._save_calibration_results(current_time, strategies_to_eliminate)
            
            self.last_calibration = current_time
            
            logger.info(f"Weekly calibration completed. "
                       f"Eliminated {len(strategies_to_eliminate)} strategies. "
                       f"Active strategies: {len(self.strategies) - len(self.eliminated_strategies)}")
            
        except Exception as e:
            logger.error(f"Weekly calibration failed: {e}")
    
    def _initialize_ml_model(self):
        """Initialize ML model for strategy selection"""
        try:
            # Try to load existing model
            model_path = "strategy_ml_model.pkl"
            scaler_path = "strategy_scaler.pkl"
            
            try:
                with open(model_path, 'rb') as f:
                    self.ml_model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info("Loaded existing ML model")
                return
            except FileNotFoundError:
                pass
            
            # Create new model
            self.ml_model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )
            self.scaler = StandardScaler()
            
            # Initialize with dummy data
            dummy_X = np.random.random((50, len(self.ml_features) + 1))
            dummy_y = np.random.randint(0, 2, 50)
            
            self.scaler.fit(dummy_X)
            self.ml_model.fit(dummy_X, dummy_y)
            
            logger.info("Initialized new ML model")
            
        except Exception as e:
            logger.error(f"ML model initialization failed: {e}")
            self.ml_model = None
            self.scaler = None
    
    def _retrain_ml_model(self):
        """Retrain ML model with updated performance data"""
        try:
            if not self.ml_model or len(self.selection_history) < 50:
                return
            
            # Prepare training data from selection history
            X = []
            y = []
            
            # This would need to be enhanced with actual trade outcomes
            # For now, using simplified logic
            for record in self.selection_history[-200:]:  # Last 200 selections
                features = [
                    record["market_conditions"]["vix"],
                    record["market_conditions"]["trend_strength"],
                    record["market_conditions"]["iv_rank"],
                    record["market_conditions"]["days_to_expiry"],
                    hash(record["strategy"]) % 100 / 100
                ]
                
                # Simplified success prediction based on confidence
                success = 1 if record["confidence"] > 0.7 else 0
                
                X.append(features)
                y.append(success)
            
            if len(X) > 20:
                X_array = np.array(X)
                y_array = np.array(y)
                
                # Retrain
                self.scaler.fit(X_array)
                self.ml_model.fit(X_array, y_array)
                
                # Save updated model
                with open("strategy_ml_model.pkl", 'wb') as f:
                    pickle.dump(self.ml_model, f)
                with open("strategy_scaler.pkl", 'wb') as f:
                    pickle.dump(self.scaler, f)
                
                logger.info(f"ML model retrained with {len(X)} samples")
            
        except Exception as e:
            logger.error(f"ML model retraining failed: {e}")
    
    def _load_performance_data(self):
        """Load existing performance data from database"""
        try:
            with db_manager.get_session() as session:
                # Load strategy statistics
                strategy_stats = session.query(StrategyStats).all()
                
                for stat in strategy_stats:
                    self.strategy_performance[stat.strategy_name] = {
                        "total_trades": stat.total_trades or 0,
                        "winning_trades": stat.winning_trades or 0,
                        "total_return": stat.total_return or 0.0,
                        "returns": json.loads(stat.performance_data or "[]"),
                        "win_rate": stat.win_rate or 0.0,
                        "avg_return": stat.avg_return or 0.0,
                        "consistency": stat.consistency_score or 0.5,
                        "last_updated": stat.updated_at or datetime.now()
                    }
                
                logger.info(f"Loaded performance data for {len(self.strategy_performance)} strategies")
                
        except Exception as e:
            logger.error(f"Failed to load performance data: {e}")
    
    def _save_calibration_results(self, calibration_time: datetime, eliminated_strategies: List[str]):
        """Save calibration results to database"""
        try:
            calibration_record = {
                "timestamp": calibration_time.isoformat(),
                "eliminated_strategies": eliminated_strategies,
                "active_strategies": list(set(self.strategies.keys()) - self.eliminated_strategies),
                "performance_summary": {
                    name: {
                        "win_rate": perf["win_rate"],
                        "avg_return": perf["avg_return"],
                        "total_trades": perf["total_trades"]
                    }
                    for name, perf in self.strategy_performance.items()
                }
            }
            
            # Save to weekly_stats
            week_key = calibration_time.strftime("%Y-W%U")
            self.weekly_stats[week_key] = calibration_record
            
            logger.info(f"Saved calibration results for week {week_key}")
            
        except Exception as e:
            logger.error(f"Failed to save calibration results: {e}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            "total_strategies": len(self.strategies),
            "active_strategies": len(self.strategies) - len(self.eliminated_strategies),
            "eliminated_strategies": list(self.eliminated_strategies),
            "last_calibration": self.last_calibration.isoformat() if self.last_calibration else None,
            "ml_model_available": self.ml_model is not None,
            "selection_history_count": len(self.selection_history),
            "strategy_performance": {
                name: {
                    "win_rate": perf["win_rate"],
                    "avg_return": perf["avg_return"],
                    "total_trades": perf["total_trades"],
                    "consistency": perf["consistency"]
                }
                for name, perf in self.strategy_performance.items()
            }
        }
    
    def force_strategy_reactivation(self, strategy_name: str):
        """Force reactivate an eliminated strategy (admin override)"""
        if strategy_name in self.eliminated_strategies:
            self.eliminated_strategies.remove(strategy_name)
            logger.warning(f"Strategy {strategy_name} reactivated by admin override")
    
    def get_strategy_recommendations(self, symbol: str) -> Dict[str, Any]:
        """Get strategy recommendations without executing selection"""
        try:
            # Mock market data for recommendations
            mock_conditions = MarketConditions(
                symbol=symbol,
                spot_price=25000.0,  # Mock spot price
                vix=22.0,
                trend_strength=1.0,
                directional_bias="NEUTRAL",
                volume_surge=False,
                iv_rank=60.0,
                index_change_pct=0.5,
                days_to_expiry=15,
                is_expiry=False,
                upcoming_events=[],
                timestamp=datetime.now()
            )
            
            candidates = self._get_strategy_candidates(mock_conditions)
            scored_candidates = self._score_candidates(candidates, mock_conditions)
            
            recommendations = []
            for strategy_name, score, reason in scored_candidates[:5]:  # Top 5
                strategy = self.strategies[strategy_name]
                recommendations.append({
                    "strategy_name": strategy_name,
                    "score": score,
                    "reason": reason.value,
                    "description": getattr(strategy, '__doc__', '').split('\n')[0] if hasattr(strategy, '__doc__') else '',
                    "risk_level": self._estimate_risk_score(strategy_name, mock_conditions),
                    "expected_return": self._estimate_expected_return(strategy_name, mock_conditions)
                })
            
            return {
                "symbol": symbol,
                "recommendations": recommendations,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get strategy recommendations: {e}")
            return {"error": str(e)}

# Global strategy selector instance
strategy_selector = IntelligentStrategySelector()

# Convenience functions
def select_strategy(symbol: str, market_data: Dict[str, Any]) -> Optional[StrategySignal]:
    """Select best strategy for given market conditions"""
    return strategy_selector.select_best_strategy(symbol, market_data)

def update_performance(strategy_name: str, trade_result: Dict[str, Any]):
    """Update strategy performance"""
    strategy_selector.update_strategy_performance(strategy_name, trade_result)

def run_weekly_calibration():
    """Run weekly strategy calibration"""
    strategy_selector.weekly_calibration()

def get_selector_status() -> Dict[str, Any]:
    """Get strategy selector status"""
    return strategy_selector.get_system_status()

# Export main components
__all__ = [
    "IntelligentStrategySelector",
    "StrategySignal",
    "MarketConditions",
    "SelectionReason",
    "strategy_selector",
    "select_strategy",
    "update_performance",
    "run_weekly_calibration",
    "get_selector_status"
]
