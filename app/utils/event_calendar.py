"""
Event Calendar Management for F&O Trading System - Future-Proof Version
- Dynamically fetches Indian market holidays from NSE API
- Automatically works for current year + 3 years ahead
- F&O expiry date calculations and tracking
- Integration with strategy system for event-based filtering
- NIFTY/BANKNIFTY specific event handling
- Compatible with risk monitor and strategy selector
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import calendar
import requests
import json
from pathlib import Path

logger = logging.getLogger("event_calendar")

class EventType(str, Enum):
    MARKET_HOLIDAY = "MARKET_HOLIDAY"
    EXPIRY_DAY = "EXPIRY_DAY"
    ECONOMIC_EVENT = "ECONOMIC_EVENT"
    EARNINGS_ANNOUNCEMENT = "EARNINGS_ANNOUNCEMENT"
    RBI_POLICY = "RBI_POLICY"
    BUDGET = "BUDGET"
    ELECTION = "ELECTION"
    SPECIAL_SESSION = "SPECIAL_SESSION"

class EventImpact(str, Enum):
    LOW = "LOW"           # Minor impact, normal trading
    MEDIUM = "MEDIUM"     # Moderate impact, careful trading
    HIGH = "HIGH"         # High impact, avoid new positions
    CRITICAL = "CRITICAL" # Critical impact, exit all positions

@dataclass
class MarketEvent:
    date: date
    event_type: EventType
    title: str
    description: str
    impact_level: EventImpact
    affected_instruments: List[str]
    trading_action: str  # "NORMAL", "CAUTIOUS", "AVOID_ENTRY", "EXIT_ALL"
    source: str
    created_at: datetime

@dataclass
class ExpiryInfo:
    date: date
    instrument: str
    expiry_type: str  # "WEEKLY", "MONTHLY", "QUARTERLY"
    is_last_trading_day: bool
    settlement_date: date

class EventCalendar:
    """
    Future-proof event calendar for F&O trading
    Dynamically fetches holidays and manages events for any year
    """
    
    def __init__(self):
        # Market holidays - dynamically loaded
        self.market_holidays = self._load_market_holidays()
        self.last_holiday_refresh = datetime.now()
        
        # Economic events and their typical impact
        self.economic_events = self._load_economic_events()
        
        # F&O expiry rules
        self.expiry_rules = {
            "NIFTY": {
                "weekly_day": 3,  # Thursday (0=Monday)
                "monthly_rule": "last_thursday",
                "lot_size": 50
            },
            "BANKNIFTY": {
                "weekly_day": 3,  # Thursday
                "monthly_rule": "last_thursday", 
                "lot_size": 15
            },
            "FINNIFTY": {
                "weekly_day": 1,  # Tuesday
                "monthly_rule": "last_tuesday",
                "lot_size": 40
            },
            "MIDCPNIFTY": {
                "weekly_day": 0,  # Monday
                "monthly_rule": "last_monday",
                "lot_size": 75
            }
        }
        
        # Event cache
        self.events_cache: Dict[str, List[MarketEvent]] = {}
        self.cache_expiry = datetime.now()
        
        # External data sources
        self.data_sources = {
            "nse_holidays": "https://static.nseindia.com/api/holiday-master",
            "nse_trading_holidays": "https://www.nseindia.com/api/holiday-master",
            "economic_calendar": "https://api.investing.com/api/economicCalendar/"
        }
        
        logger.info("Event Calendar initialized successfully (future-proof version)")
    
    def _load_market_holidays(self) -> Dict[int, List[date]]:
        """
        Dynamically fetch Indian market holidays for current year + 3 years ahead
        Falls back to weekends-only if NSE feed is unavailable
        """
        years_ahead = 3  # Current year + 3 years ahead
        start_year = date.today().year
        holiday_map = {}
        
        for year in range(start_year, start_year + years_ahead + 1):
            try:
                logger.info(f"Fetching market holidays for {year}...")
                
                # Try multiple NSE endpoints
                holidays = self._fetch_nse_holidays(year)
                
                if holidays:
                    holiday_map[year] = holidays
                    logger.info(f"✅ Fetched {len(holidays)} NSE holidays for {year}")
                else:
                    # Fallback to hardcoded holidays for current year if available
                    fallback_holidays = self._get_fallback_holidays(year)
                    holiday_map[year] = fallback_holidays
                    logger.warning(f"⚠️ Using fallback holidays for {year}: {len(fallback_holidays)} holidays")
                    
            except Exception as e:
                logger.error(f"❌ Failed to fetch holidays for {year}: {e}")
                # Minimal fallback: empty list (only weekends will be considered holidays)
                holiday_map[year] = []
        
        return holiday_map
    
    def _fetch_nse_holidays(self, year: int) -> List[date]:
        """Fetch holidays from NSE API with multiple endpoint fallbacks"""
        endpoints = [
            f"https://static.nseindia.com/api/holiday-master?type=trading&year={year}",
            f"https://www.nseindia.com/api/holiday-master?type=trading&year={year}",
            f"https://nseindia.com/api/holiday-master?type=trading&year={year}"
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/'
        }
        
        for endpoint in endpoints:
            try:
                logger.debug(f"Trying endpoint: {endpoint}")
                response = requests.get(endpoint, headers=headers, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                holidays = []
                
                # Handle different response formats
                if isinstance(data, dict):
                    holiday_data = data.get('data', data.get('holidays', []))
                elif isinstance(data, list):
                    holiday_data = data
                else:
                    continue
                
                # Extract dates from various possible formats
                for item in holiday_data:
                    if isinstance(item, dict):
                        # Try different date field names
                        date_str = (item.get('tradingDate') or 
                                  item.get('date') or 
                                  item.get('holiday_date') or
                                  item.get('Date'))
                        
                        if date_str:
                            try:
                                # Handle different date formats
                                if 'T' in str(date_str):
                                    holiday_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
                                else:
                                    holiday_date = date.fromisoformat(str(date_str))
                                
                                if holiday_date.year == year:
                                    holidays.append(holiday_date)
                            except ValueError:
                                continue
                
                if holidays:
                    return sorted(holidays)
                    
            except Exception as e:
                logger.debug(f"Endpoint {endpoint} failed: {e}")
                continue
        
        return []
    
    def _get_fallback_holidays(self, year: int) -> List[date]:
        """
        Provide fallback holidays for years when API is unavailable
        Based on typical Indian market holiday patterns
        """
        # Common Indian holidays that typically result in market closure
        typical_holidays = []
        
        try:
            # Republic Day - January 26
            typical_holidays.append(date(year, 1, 26))
            
            # Independence Day - August 15
            typical_holidays.append(date(year, 8, 15))
            
            # Gandhi Jayanti - October 2
            typical_holidays.append(date(year, 10, 2))
            
            # Christmas - December 25
            typical_holidays.append(date(year, 12, 25))
            
            # Add some estimated festival dates (these vary each year)
            # This is a simplified approach - actual dates would need lunar calendar calculations
            
            # Estimated Diwali (varies each year, typically Oct/Nov)
            if year == 2025:
                typical_holidays.extend([
                    date(2025, 3, 14),  # Holi
                    date(2025, 4, 18),  # Good Friday
                    date(2025, 10, 20), # Dussehra
                    date(2025, 11, 1),  # Diwali
                ])
            elif year == 2026:
                typical_holidays.extend([
                    date(2026, 3, 4),   # Holi (estimated)
                    date(2026, 4, 3),   # Good Friday (estimated)
                    date(2026, 10, 9),  # Dussehra (estimated)
                    date(2026, 10, 21), # Diwali (estimated)
                ])
            elif year == 2027:
                typical_holidays.extend([
                    date(2027, 3, 22),  # Holi (estimated)
                    date(2027, 3, 26),  # Good Friday (estimated)
                    date(2027, 9, 28),  # Dussehra (estimated)
                    date(2027, 10, 11), # Diwali (estimated)
                ])
            elif year == 2028:
                typical_holidays.extend([
                    date(2028, 3, 11),  # Holi (estimated)
                    date(2028, 4, 14),  # Good Friday (estimated)
                    date(2028, 10, 16), # Dussehra (estimated)
                    date(2028, 10, 29), # Diwali (estimated)
                ])
            
            # Filter out weekends (they're already handled separately)
            weekday_holidays = [h for h in typical_holidays if h.weekday() < 5]
            
            return sorted(weekday_holidays)
            
        except Exception as e:
            logger.error(f"Error generating fallback holidays for {year}: {e}")
            return []
    
    def _load_economic_events(self) -> Dict[str, Dict]:
        """Load recurring economic events and their typical impact"""
        return {
            "RBI_POLICY": {
                "frequency": "bi_monthly",
                "typical_dates": [2, 4, 6, 8, 10, 12],  # Months
                "impact": EventImpact.HIGH,
                "description": "RBI Monetary Policy Committee Meeting",
                "affected_instruments": ["NIFTY", "BANKNIFTY"]
            },
            "UNION_BUDGET": {
                "frequency": "annual",
                "typical_month": 2,  # February
                "typical_day": 1,
                "impact": EventImpact.CRITICAL,
                "description": "Union Budget Presentation",
                "affected_instruments": ["NIFTY", "BANKNIFTY"]
            },
            "GDP_DATA": {
                "frequency": "quarterly",
                "typical_dates": [2, 5, 8, 11],  # Months
                "impact": EventImpact.MEDIUM,
                "description": "GDP Growth Data Release",
                "affected_instruments": ["NIFTY", "BANKNIFTY"]
            },
            "INFLATION_DATA": {
                "frequency": "monthly",
                "typical_dates": list(range(1, 13)),  # All months
                "impact": EventImpact.MEDIUM,
                "description": "CPI/WPI Inflation Data",
                "affected_instruments": ["NIFTY", "BANKNIFTY"]
            },
            "FII_DII_DATA": {
                "frequency": "daily",
                "typical_dates": [],
                "impact": EventImpact.LOW,
                "description": "FII/DII Investment Data",
                "affected_instruments": ["NIFTY", "BANKNIFTY"]
            },
            "QUARTERLY_RESULTS": {
                "frequency": "quarterly",
                "typical_dates": [1, 4, 7, 10],  # Result months
                "impact": EventImpact.MEDIUM,
                "description": "Corporate Quarterly Results",
                "affected_instruments": ["NIFTY", "BANKNIFTY"]
            }
        }
    
    def is_market_holiday(self, check_date: date) -> bool:
        """Check if given date is a market holiday"""
        # Check if it's a weekend
        if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
            return True
        
        year = check_date.year
        
        # If holiday data not available for the year, refresh it
        if year not in self.market_holidays:
            self._refresh_holidays_for_year(year)
        
        # Check against holiday list
        return check_date in self.market_holidays.get(year, [])
    
    def _refresh_holidays_for_year(self, year: int):
        """Refresh holiday data for a specific year"""
        try:
            holidays = self._fetch_nse_holidays(year)
            if not holidays:
                holidays = self._get_fallback_holidays(year)
            
            self.market_holidays[year] = holidays
            logger.info(f"Refreshed holidays for {year}: {len(holidays)} holidays")
            
        except Exception as e:
            logger.error(f"Failed to refresh holidays for {year}: {e}")
            self.market_holidays[year] = []
    
    def is_trading_day(self, check_date: date) -> bool:
        """Check if given date is a trading day"""
        return not self.is_market_holiday(check_date)
    
    def get_next_trading_day(self, from_date: date) -> date:
        """Get next trading day from given date"""
        next_date = from_date + timedelta(days=1)
        while not self.is_trading_day(next_date):
            next_date += timedelta(days=1)
        return next_date
    
    def get_previous_trading_day(self, from_date: date) -> date:
        """Get previous trading day from given date"""
        prev_date = from_date - timedelta(days=1)
        while not self.is_trading_day(prev_date):
            prev_date -= timedelta(days=1)
        return prev_date
    
    def get_expiry_date(self, instrument: str, expiry_type: str = "weekly", 
                       reference_date: Optional[date] = None) -> Optional[date]:
        """Get next expiry date for given instrument"""
        if instrument not in self.expiry_rules:
            logger.warning(f"Expiry rules not defined for {instrument}")
            return None
        
        ref_date = reference_date or date.today()
        rules = self.expiry_rules[instrument]
        
        if expiry_type.lower() == "weekly":
            return self._get_weekly_expiry(instrument, ref_date)
        elif expiry_type.lower() == "monthly":
            return self._get_monthly_expiry(instrument, ref_date)
        else:
            logger.error(f"Unknown expiry type: {expiry_type}")
            return None
    
    def _get_weekly_expiry(self, instrument: str, ref_date: date) -> date:
        """Calculate next weekly expiry for instrument"""
        rules = self.expiry_rules[instrument]
        target_weekday = rules["weekly_day"]
        
        # Calculate days until target weekday
        days_ahead = target_weekday - ref_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        expiry_date = ref_date + timedelta(days=days_ahead)
        
        # Adjust for holidays
        while self.is_market_holiday(expiry_date):
            expiry_date -= timedelta(days=1)
        
        return expiry_date
    
    def _get_monthly_expiry(self, instrument: str, ref_date: date) -> date:
        """Calculate next monthly expiry for instrument"""
        rules = self.expiry_rules[instrument]
        rule = rules["monthly_rule"]
        
        # Find last occurrence of target weekday in current month
        year = ref_date.year
        month = ref_date.month
        
        if "thursday" in rule:
            target_weekday = 3
        elif "tuesday" in rule:
            target_weekday = 1
        elif "monday" in rule:
            target_weekday = 0
        else:
            target_weekday = 3  # Default to Thursday
        
        # Get last day of month
        last_day = calendar.monthrange(year, month)[1]
        last_date = date(year, month, last_day)
        
        # Find last occurrence of target weekday
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
        while self.is_market_holiday(monthly_expiry):
            monthly_expiry -= timedelta(days=1)
        
        return monthly_expiry
    
    def get_all_expiries(self, instrument: str, months_ahead: int = 3) -> List[ExpiryInfo]:
        """Get all expiries for instrument for next few months"""
        expiries = []
        current_date = date.today()
        
        # Get weekly expiries
        for week in range(months_ahead * 4):  # Approximate weeks
            check_date = current_date + timedelta(weeks=week)
            weekly_expiry = self._get_weekly_expiry(instrument, check_date)
            
            # Avoid duplicates
            if not any(exp.date == weekly_expiry for exp in expiries):
                expiries.append(ExpiryInfo(
                    date=weekly_expiry,
                    instrument=instrument,
                    expiry_type="WEEKLY",
                    is_last_trading_day=True,
                    settlement_date=self.get_next_trading_day(weekly_expiry)
                ))
        
        # Get monthly expiries
        for month_offset in range(months_ahead):
            check_date = current_date.replace(day=1) + timedelta(days=32 * month_offset)
            monthly_expiry = self._get_monthly_expiry(instrument, check_date)
            
            # Avoid duplicates with weekly expiries
            if not any(exp.date == monthly_expiry for exp in expiries):
                expiries.append(ExpiryInfo(
                    date=monthly_expiry,
                    instrument=instrument,
                    expiry_type="MONTHLY",
                    is_last_trading_day=True,
                    settlement_date=self.get_next_trading_day(monthly_expiry)
                ))
        
        # Sort by date
        expiries.sort(key=lambda x: x.date)
        return expiries
    
    def get_events_for_date(self, check_date: date) -> List[MarketEvent]:
        """Get all events for a specific date"""
        events = []
        
        # Check for market holiday
        if self.is_market_holiday(check_date):
            if check_date.weekday() < 5:  # Weekday holiday
                events.append(MarketEvent(
                    date=check_date,
                    event_type=EventType.MARKET_HOLIDAY,
                    title="Market Holiday",
                    description="Market closed for trading",
                    impact_level=EventImpact.CRITICAL,
                    affected_instruments=["ALL"],
                    trading_action="EXIT_ALL",
                    source="HOLIDAY_CALENDAR",
                    created_at=datetime.now()
                ))
        
        # Check for expiry events
        for instrument in ["NIFTY", "BANKNIFTY"]:
            weekly_expiry = self._get_weekly_expiry(instrument, check_date - timedelta(days=7))
            monthly_expiry = self._get_monthly_expiry(instrument, check_date - timedelta(days=30))
            
            if weekly_expiry == check_date:
                events.append(MarketEvent(
                    date=check_date,
                    event_type=EventType.EXPIRY_DAY,
                    title=f"{instrument} Weekly Expiry",
                    description=f"Weekly options and futures expiry for {instrument}",
                    impact_level=EventImpact.HIGH,
                    affected_instruments=[instrument],
                    trading_action="AVOID_ENTRY",
                    source="EXPIRY_CALENDAR",
                    created_at=datetime.now()
                ))
            
            if monthly_expiry == check_date:
                events.append(MarketEvent(
                    date=check_date,
                    event_type=EventType.EXPIRY_DAY,
                    title=f"{instrument} Monthly Expiry",
                    description=f"Monthly options and futures expiry for {instrument}",
                    impact_level=EventImpact.CRITICAL,
                    affected_instruments=[instrument],
                    trading_action="EXIT_ALL",
                    source="EXPIRY_CALENDAR",
                    created_at=datetime.now()
                ))
        
        # Check for economic events
        events.extend(self._get_economic_events_for_date(check_date))
        
        return events
    
    def _get_economic_events_for_date(self, check_date: date) -> List[MarketEvent]:
        """Get economic events for specific date"""
        events = []
        
        # Check for known recurring events
        for event_key, event_config in self.economic_events.items():
            if self._is_event_scheduled(event_key, event_config, check_date):
                events.append(MarketEvent(
                    date=check_date,
                    event_type=EventType.ECONOMIC_EVENT,
                    title=event_key.replace("_", " ").title(),
                    description=event_config["description"],
                    impact_level=event_config["impact"],
                    affected_instruments=event_config["affected_instruments"],
                    trading_action=self._get_trading_action_for_impact(event_config["impact"]),
                    source="ECONOMIC_CALENDAR",
                    created_at=datetime.now()
                ))
        
        return events
    
    def _is_event_scheduled(self, event_key: str, event_config: Dict, check_date: date) -> bool:
        """Check if economic event is scheduled for given date"""
        # Enhanced logic that works for any year
        
        if event_key == "RBI_POLICY":
            # RBI policy typically on first Tuesday of certain months
            return (check_date.month in event_config.get("typical_dates", []) and 
                   1 <= check_date.day <= 7 and 
                   check_date.weekday() == 1)  # Tuesday
        
        elif event_key == "UNION_BUDGET":
            # Budget typically on Feb 1st
            return (check_date.month == 2 and check_date.day == 1)
        
        elif event_key == "GDP_DATA":
            # GDP data typically released in second week of certain months
            return (check_date.month in event_config.get("typical_dates", []) and 
                   8 <= check_date.day <= 14 and 
                   check_date.weekday() < 5)
        
        elif event_key == "QUARTERLY_RESULTS":
            # Quarterly results season
            return (check_date.month in event_config.get("typical_dates", []) and
                   check_date.weekday() < 5)
        
        return False
    
    def _get_trading_action_for_impact(self, impact: EventImpact) -> str:
        """Get recommended trading action based on event impact"""
        action_map = {
            EventImpact.LOW: "NORMAL",
            EventImpact.MEDIUM: "CAUTIOUS", 
            EventImpact.HIGH: "AVOID_ENTRY",
            EventImpact.CRITICAL: "EXIT_ALL"
        }
        return action_map.get(impact, "NORMAL")
    
    def get_events_for_period(self, start_date: date, end_date: date) -> List[MarketEvent]:
        """Get all events for a date range"""
        all_events = []
        current_date = start_date
        
        while current_date <= end_date:
            events = self.get_events_for_date(current_date)
            all_events.extend(events)
            current_date += timedelta(days=1)
        
        return sorted(all_events, key=lambda x: x.date)
    
    def get_upcoming_events(self, days_ahead: int = 7) -> List[MarketEvent]:
        """Get upcoming events for next N days"""
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)
        return self.get_events_for_period(start_date, end_date)
    
    def should_avoid_trading(self, check_date: date, instrument: str = "NIFTY") -> Tuple[bool, str]:
        """Check if trading should be avoided on given date"""
        events = self.get_events_for_date(check_date)
        
        # Filter events affecting the instrument
        relevant_events = [
            event for event in events 
            if instrument in event.affected_instruments or "ALL" in event.affected_instruments
        ]
        
        if not relevant_events:
            return False, "No significant events"
        
        # Check for critical events
        critical_events = [e for e in relevant_events if e.impact_level == EventImpact.CRITICAL]
        if critical_events:
            return True, f"Critical events: {', '.join(e.title for e in critical_events)}"
        
        # Check for high impact events
        high_impact_events = [e for e in relevant_events if e.impact_level == EventImpact.HIGH]
        if high_impact_events:
            return True, f"High impact events: {', '.join(e.title for e in high_impact_events)}"
        
        return False, "Low to medium impact events only"
    
    def get_trading_calendar(self, year: int) -> Dict[str, Any]:
        """Get complete trading calendar for a year"""
        # Ensure we have holiday data for the year
        if year not in self.market_holidays:
            self._refresh_holidays_for_year(year)
        
        trading_days = []
        holidays = []
        expiry_dates = {"NIFTY": [], "BANKNIFTY": []}
        
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        current_date = start_date
        
        while current_date <= end_date:
            if self.is_trading_day(current_date):
                trading_days.append(current_date)
            else:
                holidays.append(current_date)
            
            # Check for expiries
            for instrument in ["NIFTY", "BANKNIFTY"]:
                try:
                    weekly_expiry = self._get_weekly_expiry(instrument, current_date)
                    monthly_expiry = self._get_monthly_expiry(instrument, current_date)
                    
                    if weekly_expiry == current_date and weekly_expiry not in expiry_dates[instrument]:
                        expiry_dates[instrument].append(weekly_expiry)
                    
                    if monthly_expiry == current_date and monthly_expiry not in expiry_dates[instrument]:
                        expiry_dates[instrument].append(monthly_expiry)
                except Exception as e:
                    logger.debug(f"Expiry calculation error for {instrument} on {current_date}: {e}")
            
            current_date += timedelta(days=1)
        
        # Sort expiry dates
        for instrument in expiry_dates:
            expiry_dates[instrument].sort()
        
        return {
            "year": year,
            "total_trading_days": len(trading_days),
            "total_holidays": len(holidays),
            "trading_days": trading_days,
            "holidays": holidays,
            "expiry_dates": expiry_dates,
            "generated_at": datetime.now().isoformat()
        }
    
    def refresh_event_data(self):
        """Refresh event data from external sources"""
        try:
            logger.info("Refreshing event calendar data...")
            
            # Refresh holiday data for current year + 3 years
            current_year = date.today().year
            for year in range(current_year, current_year + 4):
                self._refresh_holidays_for_year(year)
            
            # Clear event cache to force reload
            self.events_cache.clear()
            self.cache_expiry = datetime.now()
            self.last_holiday_refresh = datetime.now()
            
            logger.info("✅ Event calendar data refreshed successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to refresh event data: {e}")
    
    def add_custom_event(self, event: MarketEvent):
        """Add custom event to calendar"""
        date_key = event.date.isoformat()
        if date_key not in self.events_cache:
            self.events_cache[date_key] = []
        
        self.events_cache[date_key].append(event)
        logger.info(f"Added custom event: {event.title} on {event.date}")
    
    def get_next_expiry_info(self, instrument: str) -> Dict[str, Any]:
        """Get comprehensive next expiry information"""
        today = date.today()
        
        try:
            weekly_expiry = self.get_expiry_date(instrument, "weekly")
            monthly_expiry = self.get_expiry_date(instrument, "monthly")
            
            # Determine which is next
            if weekly_expiry and monthly_expiry:
                if weekly_expiry <= monthly_expiry:
                    next_expiry = weekly_expiry
                    expiry_type = "WEEKLY"
                else:
                    next_expiry = monthly_expiry
                    expiry_type = "MONTHLY"
            elif weekly_expiry:
                next_expiry = weekly_expiry
                expiry_type = "WEEKLY"
            elif monthly_expiry:
                next_expiry = monthly_expiry
                expiry_type = "MONTHLY"
            else:
                return {"error": "No expiry dates found"}
            
            days_to_expiry = (next_expiry - today).days
            
            return {
                "instrument": instrument,
                "next_expiry_date": next_expiry.isoformat(),
                "expiry_type": expiry_type,
                "days_to_expiry": days_to_expiry,
                "is_today": days_to_expiry == 0,
                "is_tomorrow": days_to_expiry == 1,
                "weekly_expiry": weekly_expiry.isoformat() if weekly_expiry else None,
                "monthly_expiry": monthly_expiry.isoformat() if monthly_expiry else None,
                "settlement_date": self.get_next_trading_day(next_expiry).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting expiry info for {instrument}: {e}")
            return {"error": f"Failed to get expiry info: {str(e)}"}
    
    def auto_refresh_check(self):
        """Check if automatic refresh is needed (call this periodically)"""
        # Refresh if it's been more than 24 hours since last refresh
        if (datetime.now() - self.last_holiday_refresh).total_seconds() > 86400:
            logger.info("Auto-refresh triggered for event calendar")
            self.refresh_event_data()
        
        # Also refresh at the beginning of each year
        current_year = date.today().year
        if current_year not in self.market_holidays:
            logger.info(f"New year {current_year} detected, refreshing holiday data")
            self.refresh_event_data()

# Global event calendar instance
event_calendar = EventCalendar()

# Convenience functions
def is_trading_day(check_date: date = None) -> bool:
    """Check if today (or given date) is a trading day"""
    check_date = check_date or date.today()
    return event_calendar.is_trading_day(check_date)

def get_next_expiry(instrument: str) -> date:
    """Get next expiry date for instrument"""
    return event_calendar.get_expiry_date(instrument, "weekly")

def should_avoid_trading_today(instrument: str = "NIFTY") -> Tuple[bool, str]:
    """Check if trading should be avoided today"""
    return event_calendar.should_avoid_trading(date.today(), instrument)

def get_upcoming_events(days: int = 7) -> List[MarketEvent]:
    """Get upcoming events"""
    return event_calendar.get_upcoming_events(days)

def get_days_to_expiry(instrument: str) -> int:
    """Get days to next expiry"""
    expiry_info = event_calendar.get_next_expiry_info(instrument)
    return expiry_info.get("days_to_expiry", 0)

def refresh_calendar_data():
    """Manually refresh calendar data"""
    event_calendar.refresh_event_data()

def get_trading_calendar_for_year(year: int) -> Dict[str, Any]:
    """Get complete trading calendar for any year"""
    return event_calendar.get_trading_calendar(year)

# Export main components
__all__ = [
    "EventCalendar",
    "MarketEvent",
    "ExpiryInfo", 
    "EventType",
    "EventImpact",
    "event_calendar",
    "is_trading_day",
    "get_next_expiry",
    "should_avoid_trading_today",
    "get_upcoming_events",
    "get_days_to_expiry",
    "refresh_calendar_data",
    "get_trading_calendar_for_year"
]
