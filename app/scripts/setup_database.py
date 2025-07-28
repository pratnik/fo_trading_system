"""
Database Setup Script for F&O Trading System - Updated Version
- Creates all database tables from models
- Sets up initial configurations and settings
- Creates admin user and default data
- Initializes encryption and security settings
- Integrates with future-proof event calendar system
- Validates database connectivity and structure
"""

import sys
import os
import logging
from datetime import datetime, date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Add the parent directories to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import settings
from app.db.base import Base, engine, db_manager
from app.db.models import (
    User, BrokerAccount, Strategy, Trade, Position, 
    MarketData, AuditLog, SystemSettings, StrategyStats
)
from app.db.encryption import (
    generate_encryption_key, test_encryption_roundtrip, 
    db_encryptor, DatabaseEncryption
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("database_setup")

class DatabaseSetup:
    """
    Comprehensive database setup and initialization with event calendar integration
    """
    
    def __init__(self):
        self.engine = engine
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.setup_successful = False
        
    def run_complete_setup(self):
        """Run the complete database setup process"""
        try:
            logger.info("🚀 Starting F&O Trading System Database Setup...")
            
            # Step 1: Test database connectivity
            self._test_database_connection()
            
            # Step 2: Create all tables
            self._create_database_tables()
            
            # Step 3: Test encryption system
            self._setup_encryption()
            
            # Step 4: Create initial system settings
            self._create_system_settings()
            
            # Step 5: Create admin user
            self._create_admin_user()
            
            # Step 6: Initialize strategies
            self._initialize_strategies()
            
            # Step 7: Create initial market data structure
            self._setup_market_data()
            
            # Step 8: Initialize event calendar system
            self._setup_event_calendar()
            
            # Step 9: Create sample broker account (optional)
            self._create_sample_broker_account()
            
            # Step 10: Setup initial audit logs
            self._create_initial_audit_logs()
            
            # Step 11: Validate setup
            self._validate_setup()
            
            self.setup_successful = True
            logger.info("✅ Database setup completed successfully!")
            
            # Display summary
            self._display_setup_summary()
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
            raise
    
    def _test_database_connection(self):
        """Test database connectivity"""
        try:
            logger.info("Testing database connection...")
            
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.fetchone()[0]
                logger.info(f"✅ Connected to PostgreSQL: {version}")
                
            # Test session creation
            with self.SessionLocal() as session:
                session.execute(text("SELECT 1"))
                logger.info("✅ Session creation successful")
                
            # Test database write permissions
            with self.SessionLocal() as session:
                session.execute(text("CREATE TEMP TABLE test_permissions (id INTEGER)"))
                session.execute(text("DROP TABLE test_permissions"))
                logger.info("✅ Database write permissions confirmed")
                
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    def _create_database_tables(self):
        """Create all database tables"""
        try:
            logger.info("Creating database tables...")
            
            # Ask user about dropping existing tables
            if input("Drop existing tables? (y/N): ").lower() == 'y':
                logger.warning("Dropping existing tables...")
                Base.metadata.drop_all(bind=self.engine)
                logger.info("✅ Existing tables dropped")
            
            # Create all tables
            Base.metadata.create_all(bind=self.engine)
            
            # Verify tables were created
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """))
                tables = [row[0] for row in result.fetchall()]
            
            expected_tables = [
                'users', 'broker_accounts', 'strategies', 'trades', 
                'positions', 'market_data', 'audit_logs', 
                'system_settings', 'strategy_stats'
            ]
            
            created_tables = [table for table in expected_tables if table in tables]
            logger.info(f"✅ Created {len(created_tables)} tables: {created_tables}")
            
            if len(created_tables) != len(expected_tables):
                missing = set(expected_tables) - set(created_tables)
                logger.warning(f"⚠️ Missing tables: {missing}")
            
        except Exception as e:
            logger.error(f"❌ Table creation failed: {e}")
            raise
    
    def _setup_encryption(self):
        """Setup and test encryption system"""
        try:
            logger.info("Setting up encryption system...")
            
            # Test encryption roundtrip
            if not test_encryption_roundtrip():
                raise Exception("Encryption roundtrip test failed")
            
            logger.info("✅ Encryption system validated")
            
            # Generate new encryption key if needed
            if not hasattr(settings, 'ENCRYPTION_KEY') or not settings.ENCRYPTION_KEY:
                new_key = generate_encryption_key()
                logger.warning(f"⚠️ Generated new encryption key: {new_key}")
                logger.warning("Please update your .env file with this key!")
                logger.warning("ENCRYPTION_KEY=" + new_key)
            
            # Test database encryption capabilities
            test_data = {"test_key": "test_value", "api_secret": "secret_123"}
            encrypted = db_encryptor.encrypt_json(test_data)
            decrypted = db_encryptor.decrypt_json(encrypted)
            
            if test_data == decrypted:
                logger.info("✅ Database encryption test passed")
            else:
                raise Exception("Database encryption test failed")
            
        except Exception as e:
            logger.error(f"❌ Encryption setup failed: {e}")
            raise
    
    def _create_system_settings(self):
        """Create initial system settings"""
        try:
            logger.info("Creating system settings...")
            
            with self.SessionLocal() as session:
                # Check if settings already exist
                existing_settings = session.query(SystemSettings).first()
                if existing_settings:
                    logger.info("System settings already exist, updating...")
                    # Update existing settings with new values
                    existing_settings.setting_value.update({
                        "calendar_auto_refresh": True,
                        "calendar_refresh_interval_hours": 24,
                        "nse_holiday_api_timeout": 10,
                        "calendar_fallback_mode": True
                    })
                    existing_settings.updated_at = datetime.now()
                    session.commit()
                    return
                
                # Create default system settings
                system_settings = SystemSettings(
                    setting_key="system_config",
                    setting_value={
                        # Core trading settings
                        "default_capital": 200000.0,
                        "max_lots_per_strategy": 10,
                        "danger_zone_warning": 1.0,
                        "danger_zone_risk": 1.25,
                        "danger_zone_exit": 1.5,
                        "vix_threshold": 25.0,
                        "entry_cutoff_time": "11:00",
                        "exit_time": "15:10",
                        
                        # Instrument restrictions
                        "allowed_instruments": ["NIFTY", "BANKNIFTY"],
                        "blocked_instruments": ["FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"],
                        
                        # Event calendar settings (NEW)
                        "calendar_auto_refresh": True,
                        "calendar_refresh_interval_hours": 24,
                        "nse_holiday_api_timeout": 10,
                        "calendar_fallback_mode": True,
                        
                        # Risk management
                        "max_daily_loss_pct": 5.0,
                        "position_size_limit": 10,
                        "strategy_allocation_pct": 20.0,
                        
                        # Notification settings
                        "whatsapp_notifications": True,
                        "email_notifications": False,
                        "sms_notifications": False,
                        
                        # System features
                        "auto_strategy_selection": True,
                        "performance_tracking": True,
                        "risk_monitoring": True,
                        "danger_zone_monitoring": True,
                        
                        # Version info
                        "system_version": "2.0.0",
                        "database_version": "1.0.0",
                        "setup_date": datetime.now().isoformat()
                    },
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(system_settings)
                session.commit()
                
                logger.info("✅ System settings created with event calendar integration")
                
        except Exception as e:
            logger.error(f"❌ System settings creation failed: {e}")
            raise
    
    def _create_admin_user(self):
        """Create admin user account"""
        try:
            logger.info("Creating admin user...")
            
            with self.SessionLocal() as session:
                # Check if admin user exists
                existing_admin = session.query(User).filter(
                    User.username == "admin"
                ).first()
                
                if existing_admin:
                    logger.info("Admin user already exists, updating...")
                    existing_admin.updated_at = datetime.now()
                    existing_admin.is_active = True
                    session.commit()
                    return
                
                # Get admin details
                print("\n" + "="*50)
                print("ADMIN USER SETUP")
                print("="*50)
                
                admin_username = input("Enter admin username (default: admin): ").strip() or "admin"
                admin_email = input("Enter admin email: ").strip()
                admin_phone = input("Enter admin phone: ").strip()
                admin_name = input("Enter admin full name (default: System Administrator): ").strip() or "System Administrator"
                
                if not admin_email:
                    admin_email = "admin@fotrading.com"
                    logger.info("Using default admin email: admin@fotrading.com")
                
                # Create admin user
                admin_user = User(
                    username=admin_username,
                    email=admin_email,
                    phone_number=admin_phone,
                    full_name=admin_name,
                    user_type="ADMIN",
                    is_active=True,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(admin_user)
                session.commit()
                
                logger.info(f"✅ Admin user '{admin_username}' created successfully")
                
        except Exception as e:
            logger.error(f"❌ Admin user creation failed: {e}")
            raise
    
    def _initialize_strategies(self):
        """Initialize all available strategies with updated configurations"""
        try:
            logger.info("Initializing strategies...")
            
            strategies_config = [
                {
                    "name": "IRON_CONDOR",
                    "display_name": "Iron Condor",
                    "description": "4-leg neutral strategy for low volatility markets",
                    "min_vix": 12.0,
                    "max_vix": 25.0,
                    "target_win_rate": 85.0,
                    "legs": 4,
                    "is_hedged": True,
                    "market_outlook": "NEUTRAL",
                    "is_active": True,
                    "default_sl_per_lot": 1500,
                    "default_tp_per_lot": 3000,
                    "max_lots": 5
                },
                {
                    "name": "BUTTERFLY_SPREAD",
                    "display_name": "Butterfly Spread",
                    "description": "4-leg limited risk/reward strategy for range-bound markets",
                    "min_vix": 12.0,
                    "max_vix": 22.0,
                    "target_win_rate": 80.0,
                    "legs": 4,
                    "is_hedged": True,
                    "market_outlook": "NEUTRAL",
                    "is_active": True,
                    "default_sl_per_lot": 1200,
                    "default_tp_per_lot": 2500,
                    "max_lots": 5
                },
                {
                    "name": "CALENDAR_SPREAD",
                    "display_name": "Calendar Spread",
                    "description": "Time decay strategy with different expiries",
                    "min_vix": 12.0,
                    "max_vix": 28.0,
                    "target_win_rate": 80.0,
                    "legs": 4,
                    "is_hedged": True,
                    "market_outlook": "NEUTRAL",
                    "is_active": True,
                    "default_sl_per_lot": 1500,
                    "default_tp_per_lot": 3000,
                    "max_lots": 4
                },
                {
                    "name": "HEDGED_STRANGLE",
                    "display_name": "Hedged Strangle",
                    "description": "High volatility strategy with hedge protection",
                    "min_vix": 20.0,
                    "max_vix": 45.0,
                    "target_win_rate": 75.0,
                    "legs": 4,
                    "is_hedged": True,
                    "market_outlook": "NEUTRAL",
                    "is_active": True,
                    "default_sl_per_lot": 2500,
                    "default_tp_per_lot": 5000,
                    "max_lots": 3
                },
                {
                    "name": "DIRECTIONAL_FUTURES",
                    "display_name": "Directional Futures",
                    "description": "Trend-following strategy with hedge protection",
                    "min_vix": 15.0,
                    "max_vix": 40.0,
                    "target_win_rate": 65.0,
                    "legs": 2,
                    "is_hedged": True,
                    "market_outlook": "DIRECTIONAL",
                    "is_active": True,
                    "default_sl_per_lot": 3000,
                    "default_tp_per_lot": 6000,
                    "max_lots": 2
                },
                {
                    "name": "JADE_LIZARD",
                    "display_name": "Jade Lizard",
                    "description": "No upside risk strategy for high IV environments",
                    "min_vix": 22.0,
                    "max_vix": 40.0,
                    "target_win_rate": 78.0,
                    "legs": 3,
                    "is_hedged": True,
                    "market_outlook": "NEUTRAL_BULLISH",
                    "is_active": True,
                    "default_sl_per_lot": 2500,
                    "default_tp_per_lot": 4500,
                    "max_lots": 4
                },
                {
                    "name": "RATIO_SPREADS",
                    "display_name": "Ratio Spreads",
                    "description": "Directional strategy with hedge protection",
                    "min_vix": 18.0,
                    "max_vix": 35.0,
                    "target_win_rate": 70.0,
                    "legs": 3,
                    "is_hedged": True,
                    "market_outlook": "DIRECTIONAL",
                    "is_active": True,
                    "default_sl_per_lot": 2200,
                    "default_tp_per_lot": 4500,
                    "max_lots": 3
                },
                {
                    "name": "BROKEN_WING_BUTTERFLY",
                    "display_name": "Broken Wing Butterfly",
                    "description": "Asymmetric butterfly with directional bias",
                    "min_vix": 18.0,
                    "max_vix": 32.0,
                    "target_win_rate": 75.0,
                    "legs": 4,
                    "is_hedged": True,
                    "market_outlook": "DIRECTIONAL",
                    "is_active": True,
                    "default_sl_per_lot": 2000,
                    "default_tp_per_lot": 4500,
                    "max_lots": 3
                }
            ]
            
            with self.SessionLocal() as session:
                for strategy_config in strategies_config:
                    # Check if strategy already exists
                    existing_strategy = session.query(Strategy).filter(
                        Strategy.name == strategy_config["name"]
                    ).first()
                    
                    if existing_strategy:
                        logger.info(f"Strategy {strategy_config['name']} already exists, updating...")
                        # Update existing strategy
                        for key, value in strategy_config.items():
                            setattr(existing_strategy, key, value)
                        existing_strategy.updated_at = datetime.now()
                    else:
                        # Create new strategy
                        strategy = Strategy(
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                            **strategy_config
                        )
                        session.add(strategy)
                
                session.commit()
                logger.info(f"✅ Initialized {len(strategies_config)} strategies")
                
        except Exception as e:
            logger.error(f"❌ Strategy initialization failed: {e}")
            raise
    
    def _setup_market_data(self):
        """Setup initial market data structure"""
        try:
            logger.info("Setting up market data structure...")
            
            with self.SessionLocal() as session:
                # Create initial market data entries for NIFTY and BANKNIFTY
                symbols = ["NIFTY", "BANKNIFTY"]
                
                for symbol in symbols:
                    existing_data = session.query(MarketData).filter(
                        MarketData.symbol == symbol,
                        MarketData.data_date == date.today()
                    ).first()
                    
                    if not existing_data:
                        market_data = MarketData(
                            symbol=symbol,
                            data_date=date.today(),
                            open_price=0.0,
                            high_price=0.0,
                            low_price=0.0,
                            close_price=0.0,
                            volume=0,
                            vix=20.0,  # Default VIX
                            data_source="INITIAL_SETUP",
                            created_at=datetime.now()
                        )
                        session.add(market_data)
                
                session.commit()
                logger.info("✅ Market data structure created")
                
        except Exception as e:
            logger.error(f"❌ Market data setup failed: {e}")
            raise
    
    def _setup_event_calendar(self):
        """Initialize event calendar system with future-proof capabilities"""
        try:
            logger.info("Initializing event calendar system...")
            
            # Import and initialize event calendar
            from app.utils.event_calendar import event_calendar
            
            # Refresh calendar data during setup
            logger.info("Refreshing event calendar data...")
            event_calendar.refresh_event_data()
            
            # Test calendar functionality
            today = date.today()
            is_trading = event_calendar.is_trading_day(today)
            
            logger.info(f"✅ Today ({today}) is a {'trading' if is_trading else 'non-trading'} day")
            
            # Get next expiry information for validation
            for instrument in ["NIFTY", "BANKNIFTY"]:
                try:
                    expiry_info = event_calendar.get_next_expiry_info(instrument)
                    if "error" not in expiry_info:
                        days_to_expiry = expiry_info.get("days_to_expiry", 0)
                        expiry_type = expiry_info.get("expiry_type", "UNKNOWN")
                        logger.info(f"✅ {instrument} next {expiry_type} expiry in {days_to_expiry} days")
                    else:
                        logger.warning(f"⚠️ Could not get expiry info for {instrument}: {expiry_info['error']}")
                except Exception as e:
                    logger.warning(f"⚠️ Expiry calculation failed for {instrument}: {e}")
            
            # Test upcoming events
            try:
                upcoming_events = event_calendar.get_upcoming_events(7)
                logger.info(f"✅ Found {len(upcoming_events)} upcoming events in next 7 days")
                
                # Log high impact events
                high_impact_events = [e for e in upcoming_events if e.impact_level in ["HIGH", "CRITICAL"]]
                for event in high_impact_events[:3]:  # Show max 3 events
                    logger.info(f"  📅 {event.date}: {event.title} ({event.impact_level})")
                    
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch upcoming events: {e}")
            
            # Test holiday data for current year
            try:
                current_year = date.today().year
                year_holidays = event_calendar.market_holidays.get(current_year, [])
                logger.info(f"✅ Loaded {len(year_holidays)} market holidays for {current_year}")
                
                # Test trading calendar generation
                calendar_info = event_calendar.get_trading_calendar(current_year)
                total_trading_days = calendar_info.get("total_trading_days", 0)
                logger.info(f"✅ {current_year} has {total_trading_days} trading days")
                
            except Exception as e:
                logger.warning(f"⚠️ Holiday data validation failed: {e}")
            
            # Create audit log for calendar initialization
            self.create_audit_log(
                "CALENDAR_INITIALIZED", 
                f"Event calendar system initialized with future-proof capabilities. "
                f"Today is {'trading' if is_trading else 'non-trading'} day."
            )
            
            logger.info("✅ Event calendar system initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Event calendar initialization failed: {e}")
            # Don't raise as it's not critical for database setup
            logger.warning("⚠️ Continuing setup without event calendar (can be initialized later)")
    
    def _create_sample_broker_account(self):
        """Create sample broker account (optional)"""
        try:
            print("\n" + "="*50)
            print("BROKER ACCOUNT SETUP (OPTIONAL)")
            print("="*50)
            
            create_sample = input("Create sample broker account? (y/N): ").lower() == 'y'
            if not create_sample:
                logger.info("Skipping sample broker account creation")
                return
            
            logger.info("Creating sample broker account...")
            
            with self.SessionLocal() as session:
                # Get admin user
                admin_user = session.query(User).filter(User.username == "admin").first()
                if not admin_user:
                    logger.warning("Admin user not found, skipping broker account")
                    return
                
                # Get broker details
                broker_name = input("Enter broker name (default: SAMPLE_BROKER): ").strip() or "SAMPLE_BROKER"
                account_id = input("Enter account ID (default: SAMPLE_ACCOUNT): ").strip() or "SAMPLE_ACCOUNT"
                
                # Create sample broker account
                sample_credentials = {
                    "api_key": "SAMPLE_API_KEY_REPLACE_WITH_REAL",
                    "api_secret": "SAMPLE_API_SECRET_REPLACE_WITH_REAL",
                    "access_token": "",
                    "client_id": account_id,
                    "broker_type": broker_name.lower(),
                    "created_during_setup": True
                }
                
                # Encrypt credentials
                encrypted_creds = db_encryptor.encrypt_broker_credentials(sample_credentials)
                
                broker_account = BrokerAccount(
                    user_id=admin_user.id,
                    broker_name=broker_name,
                    account_id=account_id,
                    api_credentials=encrypted_creds,
                    is_active=False,  # Keep inactive for sample
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                session.add(broker_account)
                session.commit()
                
                logger.info(f"✅ Sample broker account '{broker_name}' created (INACTIVE)")
                logger.warning("⚠️ Remember to update API credentials before activating!")
                
        except Exception as e:
            logger.error(f"❌ Sample broker account creation failed: {e}")
            # Don't raise here as this is optional
    
    def _create_initial_audit_logs(self):
        """Create initial audit log entries"""
        try:
            logger.info("Creating initial audit logs...")
            
            self.create_audit_log(
                "DATABASE_SETUP_STARTED", 
                "Database setup process initiated"
            )
            
            self.create_audit_log(
                "TABLES_CREATED", 
                "All database tables created successfully"
            )
            
            self.create_audit_log(
                "STRATEGIES_INITIALIZED", 
                "All 8 hedged strategies initialized with default configurations"
            )
            
            self.create_audit_log(
                "SYSTEM_SETTINGS_CREATED", 
                "System settings created with event calendar integration"
            )
            
            logger.info("✅ Initial audit logs created")
            
        except Exception as e:
            logger.error(f"❌ Initial audit logs creation failed: {e}")
            # Don't raise as this is not critical
    
    def _validate_setup(self):
        """Validate the database setup"""
        try:
            logger.info("Validating database setup...")
            
            with self.SessionLocal() as session:
                # Check users table
                user_count = session.query(User).count()
                logger.info(f"Users: {user_count}")
                
                # Check strategies table
                strategy_count = session.query(Strategy).count()
                active_strategies = session.query(Strategy).filter(Strategy.is_active == True).count()
                logger.info(f"Strategies: {strategy_count} total, {active_strategies} active")
                
                # Check system settings
                settings_count = session.query(SystemSettings).count()
                logger.info(f"System settings: {settings_count}")
                
                # Check broker accounts
                broker_count = session.query(BrokerAccount).count()
                logger.info(f"Broker accounts: {broker_count}")
                
                # Check audit logs
                audit_count = session.query(AuditLog).count()
                logger.info(f"Audit logs: {audit_count}")
                
                # Validate minimum requirements
                if user_count == 0:
                    raise Exception("No users created")
                if strategy_count < 8:
                    raise Exception("Not all strategies initialized")
                if settings_count == 0:
                    raise Exception("No system settings created")
                
                # Test event calendar integration
                try:
                    from app.utils.event_calendar import event_calendar
                    current_year = date.today().year
                    holidays_count = len(event_calendar.market_holidays.get(current_year, []))
                    logger.info(f"Event calendar: {holidays_count} holidays loaded for {current_year}")
                except Exception as e:
                    logger.warning(f"Event calendar validation warning: {e}")
                
                logger.info("✅ Database validation passed")
                
        except Exception as e:
            logger.error(f"❌ Database validation failed: {e}")
            raise
    
    def _display_setup_summary(self):
        """Display comprehensive setup summary"""
        try:
            print("\n" + "="*60)
            print("✅ F&O TRADING SYSTEM - SETUP COMPLETED SUCCESSFULLY!")
            print("="*60)
            
            with self.SessionLocal() as session:
                # Get counts
                user_count = session.query(User).count()
                strategy_count = session.query(Strategy).count()
                active_strategies = session.query(Strategy).filter(Strategy.is_active == True).count()
                broker_count = session.query(BrokerAccount).count()
                
            print(f"📊 DATABASE STATISTICS:")
            print(f"   • Users Created: {user_count}")
            print(f"   • Strategies Available: {strategy_count} ({active_strategies} active)")
            print(f"   • Broker Accounts: {broker_count}")
            
            # Event calendar status
            try:
                from app.utils.event_calendar import event_calendar
                current_year = date.today().year
                holidays_count = len(event_calendar.market_holidays.get(current_year, []))
                is_trading_today = event_calendar.is_trading_day(date.today())
                
                print(f"📅 EVENT CALENDAR:")
                print(f"   • Holidays Loaded for {current_year}: {holidays_count}")
                print(f"   • Today's Status: {'Trading Day' if is_trading_today else 'Non-Trading Day'}")
                
                # Next expiries
                for instrument in ["NIFTY", "BANKNIFTY"]:
                    try:
                        expiry_info = event_calendar.get_next_expiry_info(instrument)
                        if "error" not in expiry_info:
                            days = expiry_info.get("days_to_expiry", 0)
                            exp_type = expiry_info.get("expiry_type", "")
                            print(f"   • {instrument} Next Expiry: {days} days ({exp_type})")
                    except:
                        pass
                        
            except Exception as e:
                print(f"📅 EVENT CALENDAR: Warning - {e}")
            
            print(f"\n🎯 NEXT STEPS:")
            print(f"   1. Update .env file with any new encryption keys")
            print(f"   2. Configure broker API credentials in the UI")
            print(f"   3. Start the application:")
            print(f"      streamlit run app/ui/dashboard.py")
            print(f"   4. Setup WhatsApp notifications in settings")
            print(f"   5. Test event calendar auto-refresh functionality")
            
            print(f"\n🔧 SYSTEM FEATURES ENABLED:")
            print(f"   ✅ 8 Hedged Strategies (NIFTY/BANKNIFTY only)")
            print(f"   ✅ Future-Proof Event Calendar")
            print(f"   ✅ Real-time Risk Monitoring")
            print(f"   ✅ Encrypted Database Storage")
            print(f"   ✅ Intelligent Strategy Selection")
            print(f"   ✅ Performance Tracking & Analytics")
            print(f"   ✅ WhatsApp Notification Support")
            print(f"   ✅ Danger Zone Monitoring")
            
            print("="*60)
            print()
            
        except Exception as e:
            logger.error(f"Summary display failed: {e}")
    
    def create_audit_log(self, action: str, details: str):
        """Create audit log entry"""
        try:
            with self.SessionLocal() as session:
                audit_log = AuditLog(
                    user_id=None,  # System action
                    action=action,
                    details=details,
                    ip_address="127.0.0.1",
                    user_agent="DatabaseSetup",
                    created_at=datetime.now()
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")

def main():
    """Main setup function"""
    try:
        print("=" * 60)
        print("F&O Trading System - Database Setup (Updated Version)")
        print("Features: Event Calendar, Future-Proof Holidays, Enhanced Strategies")
        print("=" * 60)
        print()
        
        # Display system requirements
        print("🔧 SYSTEM REQUIREMENTS CHECK:")
        print("   • PostgreSQL database running")
        print("   • Python dependencies installed")
        print("   • .env file configured")
        print("   • Internet connection (for holiday data)")
        print()
        
        # Confirm setup
        confirm = input("This will setup the complete database. Continue? (y/N): ").lower()
        if confirm != 'y':
            print("Setup cancelled.")
            return
        
        # Run setup
        setup = DatabaseSetup()
        setup.run_complete_setup()
        
        if setup.setup_successful:
            # Final success message
            print("🎉 SUCCESS! Your F&O Trading System is ready to use!")
        else:
            print("❌ Setup failed. Check logs for details.")
            
    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user.")
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        logger.exception("Full error details:")
        sys.exit(1)

if __name__ == "__main__":
    main()
