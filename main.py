#!/usr/bin/env python3
"""
Discord/Telegram Message Scraper with AI Processing and Forex Trading Analysis
Main application entry point
"""

import asyncio
import signal
import sys
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import traceback

# Fix import path when running from src directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.insert(0, parent_dir)

# Now imports should work
from utils.config import config
from utils.logger import create_logger
from scrapers.telegram_scraper import TelegramScraper
# Updated import for Forex AI processor
from ai_processor.forex_gemini_processor import ForexGeminiProcessor
from notifications.fcm_notifier import FCMNotifier, PushbulletNotifier

# Import FCM V1 notifier
try:
    from notifications.fcm_v1_notifier import FCMv1Notifier
    FCM_V1_AVAILABLE = True
except ImportError:
    FCM_V1_AVAILABLE = False
    print("⚠️ FCM V1 notifier not available. Using legacy FCM.")

class ForexMessageScraperApp:
    def __init__(self):
        # Initialize logger
        system_config = config.get_system_config()
        self.logger = create_logger(
            log_level=system_config.get('log_level', 'INFO'),
            log_file=system_config.get('log_file'),
            console_output=True
        )
        
        # Initialize components
        self.telegram_scraper = None
        self.ai_processor = None
        self.notifier = None
        
        # Runtime state
        self.is_running = False
        self.processed_messages = 0
        self.trading_signals_processed = 0
        self.start_time = None
        
        # Message queue for processing
        self.message_queue = asyncio.Queue()
        
        self.logger.info("🚀 Forex Message Scraper App initializing...")
    
    async def initialize(self) -> bool:
        """Initialize all components for forex trading"""
        try:
            # Validate configuration
            config_errors = config.validate_config()
            if config_errors:
                self.logger.error("❌ Configuration errors:")
                for error in config_errors:
                    self.logger.error(f"   - {error}")
                return False
            
            # Initialize FOREX AI processor (UPDATED)
            self.logger.info("🤖 Initializing Forex AI processor...")
            self.ai_processor = ForexGeminiProcessor()  # Changed from GeminiProcessor
            
            if not await self.ai_processor.test_connection():
                self.logger.error("❌ Failed to connect to Forex Gemini AI")
                return False
            
            # Initialize notification system
            self.logger.info("📱 Initializing trading notification system...")
            notification_method = config.get('notifications.method', 'fcm')
            
            # Choose notification method based on config
            if notification_method in ['fcm_v1', 'fcm-v1'] and FCM_V1_AVAILABLE:
                self.logger.info("📱 Using FCM V1 API (recommended for trading)")
                self.notifier = FCMv1Notifier()
                config_errors = self.notifier.validate_config()
                if config_errors:
                    self.logger.warning(f"⚠️ FCM V1 config issues: {config_errors}")
                    # Try legacy FCM as fallback
                    self.logger.info("📱 Falling back to legacy FCM...")
                    self.notifier = FCMNotifier()
                    legacy_errors = self.notifier.validate_config()
                    if legacy_errors:
                        self.logger.warning(f"⚠️ Legacy FCM config issues: {legacy_errors}")
                        # Try Pushbullet as final fallback
                        self.logger.info("📱 Falling back to Pushbullet...")
                        self.notifier = PushbulletNotifier()
            
            elif notification_method == 'fcm':
                self.logger.info("📱 Using legacy FCM API")
                self.notifier = FCMNotifier()
                config_errors = self.notifier.validate_config()
                if config_errors:
                    self.logger.warning(f"⚠️ FCM config issues: {config_errors}")
                    # Try Pushbullet as fallback
                    self.logger.info("📱 Falling back to Pushbullet...")
                    self.notifier = PushbulletNotifier()
            
            elif notification_method == 'pushbullet':
                self.logger.info("📱 Using Pushbullet notifications (optimized for trading)")
                self.notifier = PushbulletNotifier()
            
            else:
                self.logger.error(f"❌ Unknown notification method: {notification_method}")
                # Default to Pushbullet
                self.logger.info("📱 Defaulting to Pushbullet...")
                self.notifier = PushbulletNotifier()
            
            # Initialize Telegram scraper
            self.logger.info("📱 Initializing Telegram scraper with forex analysis...")
            self.telegram_scraper = TelegramScraper()
            self.telegram_scraper.set_message_callback(self.handle_new_message)
            
            if not await self.telegram_scraper.initialize():
                self.logger.error("❌ Failed to initialize Telegram scraper")
                return False
            
            # Test notification system
            self.logger.info("🧪 Testing trading notification system...")
            if hasattr(self.notifier, 'send_test_notification'):
                await self.notifier.send_test_notification()
            
            self.logger.info("✅ All forex trading components initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Initialization failed: {e}")
            self.logger.debug(traceback.format_exc())
            return False
    
    async def handle_new_message(self, message_data: Dict[str, Any]):
        """Handle new message from scrapers with trading context"""
        try:
            # Add to processing queue
            await self.message_queue.put(message_data)
            
            # Log with trading context
            if message_data.get('is_trading_message', False):
                signal_info = message_data.get('trading_signal', {})
                instrument = signal_info.get('instrument', 'Unknown')
                confidence = int(signal_info.get('confidence', 0) * 100)
                self.logger.debug(f"📊 Trading signal queued: {instrument} ({confidence}% confidence) - ID: {message_data['id']}")
            else:
                self.logger.debug(f"📥 Message queued for processing: {message_data['id']}")
            
        except Exception as e:
            self.logger.error(f"❌ Error handling new message: {e}")
    
    async def process_message_queue(self):
        """Process messages from the queue with forex prioritization"""
        self.logger.info("🔄 Starting forex message processing queue...")
        
        while self.is_running:
            try:
                # Get message from queue (with timeout)
                message_data = await asyncio.wait_for(
                    self.message_queue.get(), 
                    timeout=5.0
                )
                
                # Process the message
                await self.process_single_message(message_data)
                
                # Mark task as done
                self.message_queue.task_done()
                
            except asyncio.TimeoutError:
                # No messages in queue, continue
                continue
            except Exception as e:
                self.logger.error(f"❌ Error processing message queue: {e}")
                await asyncio.sleep(1)
    
    async def process_single_message(self, message_data: Dict[str, Any]):
        """Process a single message through Forex AI and send trading notification"""
        try:
            message_id = message_data.get('id', 'unknown')
            is_trading = message_data.get('is_trading_message', False)
            
            if is_trading:
                self.logger.info(f"📊 Processing TRADING message {message_id}...")
            else:
                self.logger.info(f"🔄 Processing message {message_id}...")
            
            # Determine processing type
            if message_data.get('has_media') and message_data.get('media_type') in ['photo', 'image']:
                # Process chart image with forex analysis
                formatted_message = await self.ai_processor.process_image_message(message_data)
            else:
                # Process text message with forex signal extraction
                formatted_message = await self.ai_processor.process_text_message(message_data)
            
            # Send notification (enhanced for trading)
            notification_sent = await self.notifier.send_notification(formatted_message, message_data)
            
            if notification_sent:
                self.processed_messages += 1
                if is_trading:
                    self.trading_signals_processed += 1
                    signal_info = message_data.get('trading_signal', {})
                    instrument = signal_info.get('instrument', 'Unknown')
                    confidence = int(signal_info.get('confidence', 0) * 100)
                    self.logger.info(f"✅ TRADING SIGNAL {message_id} processed: {instrument} ({confidence}% confidence)")
                else:
                    self.logger.info(f"✅ Message {message_id} processed and notification sent")
            else:
                self.logger.error(f"❌ Failed to send notification for message {message_id}")
                
                # Try to send urgent alert about failure
                if hasattr(self.notifier, 'send_urgent_alert'):
                    await self.notifier.send_urgent_alert(
                        "Trading Notification Failed",
                        f"Failed to send trading alert for message from {message_data.get('chat_title', 'Unknown')}"
                    )
            
        except Exception as e:
            self.logger.error(f"❌ Error processing message: {e}")
            self.logger.debug(traceback.format_exc())
    
    async def start_monitoring(self):
        """Start monitoring all configured platforms for forex signals"""
        if not await self.initialize():
            self.logger.error("❌ Failed to initialize, cannot start forex monitoring")
            return False
        
        self.is_running = True
        self.start_time = datetime.now()
        
        # Log startup summary with forex context
        config_summary = {
            'telegram_chats': len(config.get('telegram.target_chats', [])),
            'notification_method': config.get('notifications.method', 'unknown'),
            'ai_model': config.get('gemini.model', 'unknown'),
            'debug_mode': config.is_debug_enabled(),
            'notifier_type': type(self.notifier).__name__ if self.notifier else 'None',
            'forex_mode': True,
            'monitored_pairs': len(config.get('forex_filters.monitored_pairs', []))
        }
        self.logger.log_startup(config_summary)
        
        try:
            # Start all monitoring tasks
            tasks = [
                asyncio.create_task(self.telegram_scraper.start_monitoring(), name="telegram_forex_monitor"),
                asyncio.create_task(self.process_message_queue(), name="forex_message_processor"),
                asyncio.create_task(self.forex_status_reporter(), name="forex_status_reporter")
            ]
            
            self.logger.info("🎯 Forex message scraper is now monitoring for trading signals...")
            self.logger.info("📊 Ready to analyze charts and extract trading signals")
            self.logger.info("🛑 Press Ctrl+C to stop monitoring")
            
            # Wait for all tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            self.logger.info("🛑 Keyboard interrupt received, shutting down forex monitoring...")
            self.is_running = False
        except Exception as e:
            self.logger.error(f"❌ Forex monitoring error: {e}")
            self.logger.debug(traceback.format_exc())
            self.is_running = False
        finally:
            await self.cleanup()
    
    async def forex_status_reporter(self):
        """Periodically report forex trading status"""
        while self.is_running:
            try:
                await asyncio.sleep(300)  # Report every 5 minutes
                
                if self.start_time:
                    uptime = datetime.now() - self.start_time
                    self.logger.info(f"📊 Forex Status: {self.processed_messages} total messages, "
                                   f"{self.trading_signals_processed} trading signals processed, "
                                   f"uptime: {uptime}")
                
            except Exception as e:
                self.logger.error(f"❌ Forex status reporter error: {e}")
    
    async def cleanup(self):
        """Cleanup resources with forex context"""
        if not self.is_running:
            return  # Already cleaned up
            
        self.is_running = False
        self.logger.info("🧹 Cleaning up forex scraper resources...")
        
        try:
            # Stop Telegram scraper first
            if self.telegram_scraper:
                self.logger.info("📱 Stopping Telegram forex monitoring...")
                await self.telegram_scraper.stop_monitoring()
            
            # Process remaining messages in queue (with timeout)
            if not self.message_queue.empty():
                queue_size = self.message_queue.qsize()
                self.logger.info(f"📤 Processing {queue_size} remaining trading messages...")
                
                # Process with timeout to avoid hanging
                timeout_seconds = min(queue_size * 2, 30)  # Max 30 seconds
                try:
                    await asyncio.wait_for(self._process_remaining_messages(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    self.logger.warning("⏰ Timeout processing remaining messages, proceeding with shutdown")
            
            # Send shutdown notification with trading stats
            if self.notifier and hasattr(self.notifier, 'send_urgent_alert'):
                try:
                    stats_message = (f"Forex scraper has stopped.\n"
                                   f"📊 Session Stats:\n"
                                   f"• Total messages: {self.processed_messages}\n"
                                   f"• Trading signals: {self.trading_signals_processed}\n"
                                   f"• Success rate: {(self.trading_signals_processed/max(self.processed_messages,1)*100):.1f}%")
                    
                    await asyncio.wait_for(
                        self.notifier.send_urgent_alert("Forex Scraper Offline", stats_message),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    self.logger.warning("⏰ Timeout sending shutdown notification")
                except Exception as e:
                    self.logger.error(f"❌ Error sending shutdown notification: {e}")
            
            self.logger.log_shutdown()
            self.logger.info(f"✅ Forex cleanup completed. Trading signals processed: {self.trading_signals_processed}")
            
        except Exception as e:
            self.logger.error(f"❌ Cleanup error: {e}")
    
    async def _process_remaining_messages(self):
        """Process remaining messages in queue"""
        while not self.message_queue.empty():
            try:
                message_data = self.message_queue.get_nowait()
                await self.process_single_message(message_data)
                self.message_queue.task_done()
            except asyncio.QueueEmpty:
                break
            except Exception as e:
                self.logger.error(f"❌ Error processing remaining message: {e}")

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"🛑 Signal {signum} received, shutting down forex scraper...")
            self.is_running = False
            # Force exit after cleanup
            raise KeyboardInterrupt("Signal received")
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

# CLI Commands
async def test_components():
    """Test all forex components individually"""
    print("🧪 Testing Forex Message Scraper Components...\n")
    
    # Test config
    print("1. Testing Configuration...")
    config_errors = config.validate_config()
    if config_errors:
        print("❌ Config validation failed:")
        for error in config_errors:
            print(f"   - {error}")
        return False
    else:
        print("✅ Configuration valid")
    
    # Test Telegram
    print("\n2. Testing Telegram Connection...")
    from scrapers.telegram_scraper import test_telegram_connection
    if await test_telegram_connection():
        print("✅ Telegram connection successful")
    else:
        print("❌ Telegram connection failed")
        return False
    
    # Test Forex Gemini AI (UPDATED)
    print("\n3. Testing Forex Gemini AI...")
    from ai_processor.forex_gemini_processor import test_forex_gemini_processor
    if await test_forex_gemini_processor():
        print("✅ Forex Gemini AI working")
    else:
        print("❌ Forex Gemini AI failed")
        return False
    
    # Test Trading Signal Parser
    print("\n4. Testing Trading Signal Parser...")
    try:
        from utils.trading_signal_parser import extract_quick_signal, is_trading_message
        
        # Test with sample forex message
        test_message = "XAUUSD SELL at 2650.50, SL: 2665.00, TP: 2620.00"
        signal = extract_quick_signal(test_message)
        is_forex = is_trading_message(test_message)
        
        if signal['is_valid_signal'] and is_forex:
            print("✅ Trading Signal Parser working")
            print(f"   Sample: {signal['instrument']} {signal['direction']} - Confidence: {int(signal['confidence']*100)}%")
        else:
            print("❌ Trading Signal Parser failed")
            return False
    except Exception as e:
        print(f"❌ Trading Signal Parser error: {e}")
        return False
    
    # Test Notifications
    print("\n5. Testing Trading Notifications...")
    notification_method = config.get('notifications.method', 'fcm')
    
    if notification_method in ['fcm_v1', 'fcm-v1'] and FCM_V1_AVAILABLE:
        print("Testing FCM V1...")
        from notifications.fcm_v1_notifier import test_fcm_v1_notifier
        if await test_fcm_v1_notifier():
            print("✅ FCM V1 notifications working")
        else:
            print("⚠️ FCM V1 failed, trying legacy FCM...")
            from notifications.fcm_notifier import test_fcm_notifier
            if await test_fcm_notifier():
                print("✅ Legacy FCM notifications working")
            else:
                print("⚠️ Legacy FCM failed, trying Pushbullet...")
                from notifications.fcm_notifier import test_pushbullet_notifier
                if await test_pushbullet_notifier():
                    print("✅ Pushbullet notifications working")
                else:
                    print("❌ All notification methods failed")
                    return False
    
    elif notification_method == 'fcm':
        print("Testing legacy FCM...")
        from notifications.fcm_notifier import test_fcm_notifier
        if await test_fcm_notifier():
            print("✅ FCM notifications working")
        else:
            print("⚠️ FCM failed, trying Pushbullet...")
            from notifications.fcm_notifier import test_pushbullet_notifier
            if await test_pushbullet_notifier():
                print("✅ Pushbullet notifications working")
            else:
                print("❌ All notification methods failed")
                return False
    
    elif notification_method == 'pushbullet':
        print("Testing Pushbullet...")
        from notifications.fcm_notifier import test_pushbullet_notifier
        if await test_pushbullet_notifier():
            print("✅ Pushbullet notifications working")
        else:
            print("❌ Pushbullet notifications failed")
            return False
    
    print("\n🎉 All forex components test successful!")
    print("📊 Ready for forex signal analysis and trading notifications!")
    return True

async def show_available_chats():
    """Show available Telegram chats for forex configuration"""
    print("📱 Available Telegram Chats for Forex Monitoring:\n")
    
    from scrapers.telegram_scraper import TelegramScraper
    scraper = TelegramScraper()
    
    if await scraper.initialize():
        print("Chat ID | Chat Name | Type | Forex Potential")
        print("-" * 70)
        
        async for dialog in scraper.client.iter_dialogs(limit=20):
            chat_type = "Private" if dialog.is_user else "Group" if dialog.is_group else "Channel"
            
            # Check if chat name suggests forex content
            forex_keywords = ['forex', 'trading', 'signal', 'fx', 'trade', 'market', 'gold', 'usd', 'eur']
            is_forex_related = any(keyword in dialog.name.lower() for keyword in forex_keywords)
            forex_indicator = "🎯 LIKELY" if is_forex_related else "❓ Unknown"
            
            print(f"{dialog.id} | {dialog.name[:25]:<25} | {chat_type:<7} | {forex_indicator}")
        
        await scraper.stop_monitoring()
        print(f"\n💡 Add forex-related chat IDs to your config.yaml under 'telegram.target_chats'")
        print("🎯 Focus on channels/groups with trading signals for best results")
    else:
        print("❌ Failed to connect to Telegram")

async def send_test_notification():
    """Send a test forex notification"""
    print("📱 Sending test forex notification...")
    
    app = ForexMessageScraperApp()
    if await app.initialize():
        # Create sample trading signal data
        test_trading_data = {
            'is_trading_message': True,
            'trading_signal': {
                'instrument': 'XAUUSD',
                'direction': 'SELL',
                'entry_price': 2650.50,
                'stop_loss': 2665.00,
                'take_profit': [2620.00],
                'confidence': 0.85
            },
            'signal_confidence': 0.85
        }
        
        success = await app.notifier.send_notification(
            "🔔 **FOREX TRADE SIGNAL**\n\n📈 **Instrument**: XAUUSD\n💰 **Entry**: 2650.50\n🛑 **Stop Loss**: 2665.00\n🎯 **Take Profit**: 2620.00\n📱 **Direction**: SELL\n\n---\n🤖 AI Trading Analysis\n⚡ Ready to Trade!",
            test_trading_data
        )
        
        if success:
            print("✅ Test forex notification sent successfully!")
            print("📊 Check your phone for the trading signal alert")
        else:
            print("❌ Test forex notification failed")
        await app.cleanup()
    else:
        print("❌ Failed to initialize forex app")

def show_help():
    """Show forex-enhanced help information"""
    help_text = """
🤖 Forex Message Scraper with AI Trading Analysis

USAGE:
    python src/main.py [COMMAND]

COMMANDS:
    start           Start monitoring forex messages (default)
    test            Test all forex components
    chats           Show available chats with forex potential
    test-notify     Send test forex notification
    help            Show this help

FOREX FEATURES:
    • 📊 Automatic trading signal extraction from text
    • 📈 Chart image analysis for entry/exit points
    • 🎯 Risk/reward ratio calculation
    • 📱 Priority notifications for high-confidence signals
    • 🤖 AI-powered technical analysis
    • 💰 Support for all major forex pairs and commodities

SETUP FOR FOREX TRADING:
    1. Copy config/.env.template to config/.env
    2. Fill in your API credentials in config/.env
    3. Add forex signal channels to config/config.yaml
    4. Configure monitored currency pairs
    5. Run: python src/main.py test
    6. Run: python src/main.py start

GETTING API CREDENTIALS:
    • Telegram: Visit https://my.telegram.org
    • Gemini: Visit https://aistudio.google.com/app/apikey (for AI analysis)
    • Pushbullet: Visit https://www.pushbullet.com (for notifications)

CONFIGURATION FILES:
    • config/config.yaml - Main configuration with forex settings
    • config/.env - API credentials (keep private)
    • logs/forex_scraper.log - Detailed trading logs
    • sessions/ - Telegram session files
    • media/ - Downloaded chart images

FOREX MONITORING:
    • Supports all major currency pairs (EURUSD, GBPUSD, etc.)
    • Gold and Silver (XAUUSD, XAGUSD)
    • Cryptocurrency pairs (BTCUSD, ETHUSD)
    • Automatic signal validation and confidence scoring
    • Chart pattern recognition and technical analysis

TROUBLESHOOTING:
    • Check logs/forex_scraper.log for detailed errors
    • Validate forex config with 'test' command
    • Ensure trading signal channels are accessible
    • Test individual components separately
    """
    print(help_text)

async def main():
    """Main entry point for forex scraper"""
    # Create necessary directories
    os.makedirs("logs", exist_ok=True)
    os.makedirs("sessions", exist_ok=True)
    os.makedirs("media", exist_ok=True)
    os.makedirs("media/charts", exist_ok=True)  # For forex charts
    os.makedirs("config", exist_ok=True)
    
    # Parse command line arguments
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    
    if command == "help" or command == "-h" or command == "--help":
        show_help()
        return
    
    elif command == "test":
        success = await test_components()
        sys.exit(0 if success else 1)
    
    elif command == "chats":
        await show_available_chats()
        return
    
    elif command == "test-notify":
        await send_test_notification()
        return
    
    elif command == "start":
        # Start the forex application
        app = ForexMessageScraperApp()
        app.setup_signal_handlers()
        
        try:
            await app.start_monitoring()
        except KeyboardInterrupt:
            print("\n🛑 Forex scraper interrupted - shutting down gracefully...")
            app.is_running = False
            await app.cleanup()
            print("✅ Forex scraper shutdown complete")
        except Exception as e:
            print(f"❌ Forex application error: {e}")
            if app:
                app.is_running = False
                await app.cleanup()
            sys.exit(1)
    
    else:
        print(f"❌ Unknown command: {command}")
        print("Use 'python src/main.py help' for usage information")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Forex application interrupted - exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal forex scraper error: {e}")
        sys.exit(1)