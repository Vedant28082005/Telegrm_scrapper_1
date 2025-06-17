import asyncio
import aiohttp
import json
from typing import Dict, Any, List, Optional
import time
from datetime import datetime, timedelta
import sys
import os

# Add project root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from src.utils.config import config
from src.utils.logger import logger

# Import Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ Firebase Admin SDK not installed. Install with: pip install firebase-admin")
    FIREBASE_AVAILABLE = False

class FCMv1Notifier:
    def __init__(self):
        self.notification_config = config.get_notification_config()
        self.fcm_config = self.notification_config.get('fcm', {})
        
        # V1 API settings - try environment variables first, then config
        self.project_id = os.getenv('FCM_PROJECT_ID') or self.fcm_config.get('project_id')
        self.sender_id = os.getenv('FCM_SENDER_ID') or self.fcm_config.get('sender_id')
        self.service_account_path = os.getenv('FCM_SERVICE_ACCOUNT_PATH') or self.fcm_config.get('service_account_path')
        self.device_token = os.getenv('FCM_DEVICE_TOKEN') or self.fcm_config.get('device_token')
        
        # Notification settings
        self.duration = self.notification_config.get('duration', 30)
        self.priority = self.notification_config.get('priority', 'high')
        self.sound_enabled = self.notification_config.get('sound', True)
        self.vibration_enabled = self.notification_config.get('vibration', True)
        
        # Test mode
        self.test_mode = config.is_test_mode()
        
        # Initialize Firebase Admin
        self.app = None
        self.initialized = False
        
        if FIREBASE_AVAILABLE:
            self._initialize_firebase()
        
        logger.info("📱 FCM V1 Notifier initialized")
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            if not self.service_account_path:
                logger.error("❌ Firebase service account path not configured")
                return False
            
            if not os.path.exists(self.service_account_path):
                logger.error(f"❌ Firebase service account file not found: {self.service_account_path}")
                return False
            
            # Initialize Firebase Admin SDK (only if not already initialized)
            if not firebase_admin._apps:
                cred = credentials.Certificate(self.service_account_path)
                self.app = firebase_admin.initialize_app(cred, {
                    'projectId': self.project_id
                })
                logger.info("✅ Firebase Admin SDK initialized with new app")
            else:
                # Use existing app
                self.app = firebase_admin.get_app()
                logger.info("✅ Using existing Firebase Admin SDK app")
            
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Firebase Admin SDK: {e}")
            return False
    
    def _create_notification_message(self, formatted_message: str, message_data: Dict[str, Any]) -> messaging.Message:
        """Create FCM V1 message"""
        
        # Extract title and body from formatted message
        lines = formatted_message.strip().split('\n')
        title = lines[0] if lines else "New Message"
        
        # Clean title (remove emojis for title, keep for body)
        clean_title = title.replace('🔔', '').replace('**', '').strip()
        
        # Create notification
        notification = messaging.Notification(
            title=clean_title[:50],  # Limit title length
            body=formatted_message[:300]  # Limit body length
        )
        
        # Create Android-specific config
        android_config = messaging.AndroidConfig(
            priority='high',
            ttl=timedelta(seconds=3600),  # 1 hour TTL
            notification=messaging.AndroidNotification(
                title=clean_title[:50],
                body=formatted_message[:200],
                icon='ic_notification',
                color='#FF5722',  # Orange color
                sound='default' if self.sound_enabled else None,
                tag=f"message_{message_data.get('id', int(time.time()))}",
                click_action='FLUTTER_NOTIFICATION_CLICK',
                channel_id='message_alerts',
                priority='high',
                visibility='public',
                sticky=True,
                local_only=False,
                default_sound=True,
                default_vibrate_timings=True,
                default_light_settings=True,
                vibrate_timings_millis=[0, 500, 500, 500] if self.vibration_enabled else None
            )
        )
        
        # Create data payload - ALL VALUES MUST BE STRINGS
        data = {
            'message_id': str(message_data.get('id', '')),
            'source': str(message_data.get('source', '')),
            'chat_id': str(message_data.get('chat_id', '')),
            'chat_title': str(message_data.get('chat_title', '')),
            'sender_name': str(message_data.get('sender_name', '')),
            'timestamp': str(message_data.get('timestamp', datetime.now()).isoformat() if hasattr(message_data.get('timestamp', datetime.now()), 'isoformat') else message_data.get('timestamp', datetime.now())),
            'has_media': str(message_data.get('has_media', False)),
            'media_type': str(message_data.get('media_type', '')),
            'duration': str(self.duration),
            'type': 'message_alert'
        }
        
        # Create the message
        message = messaging.Message(
            notification=notification,
            android=android_config,
            data=data,
            token=self.device_token
        )
        
        return message
    
    async def send_notification(self, formatted_message: str, message_data: Dict[str, Any]) -> bool:
        """Send notification via FCM V1 API"""
        if not FIREBASE_AVAILABLE:
            logger.error("❌ Firebase Admin SDK not available")
            return False
        
        if not self.initialized:
            logger.error("❌ FCM V1 not initialized")
            return False
        
        if not self.device_token:
            logger.error("❌ FCM device token not configured")
            return False
        
        if self.test_mode:
            logger.info(f"🧪 TEST MODE: Would send FCM V1 notification:\n{formatted_message}")
            return True
        
        try:
            # Create message
            message = self._create_notification_message(formatted_message, message_data)
            
            # Send notification
            response = messaging.send(message)
            
            if response:
                logger.log_notification_sent("FCM V1", True)
                logger.info(f"✅ FCM V1 notification sent: {response}")
                
                # Send follow-up notifications for persistence (30-second duration)
                if self.duration > 5:
                    asyncio.create_task(self._send_persistent_notifications(
                        formatted_message, message_data
                    ))
                
                return True
            else:
                logger.error("❌ FCM V1 send failed: No response")
                return False
        
        except messaging.UnregisteredError:
            logger.error("❌ FCM device token is invalid or unregistered")
            return False
        except messaging.SenderIdMismatchError:
            logger.error("❌ FCM sender ID mismatch")
            return False
        except messaging.QuotaExceededError:
            logger.error("❌ FCM quota exceeded")
            return False
        except Exception as e:
            logger.error(f"❌ FCM V1 notification error: {e}")
            return False
    
    async def _send_persistent_notifications(self, formatted_message: str, message_data: Dict[str, Any]):
        """Send follow-up notifications to maintain 30-second duration"""
        try:
            # Calculate number of follow-ups needed
            follow_ups = min(self.duration // 5, 6)  # Max 6 follow-ups
            
            for i in range(follow_ups):
                await asyncio.sleep(5)  # Wait 5 seconds between notifications
                
                # Create follow-up message with slight variation
                follow_up_message = f"🔴 URGENT: {formatted_message}"
                follow_up_data = message_data.copy()
                follow_up_data['id'] = f"{message_data.get('id', 'unknown')}_followup_{i+1}"
                
                # Send follow-up
                try:
                    message = self._create_notification_message(follow_up_message, follow_up_data)
                    response = messaging.send(message)
                    
                    if response:
                        logger.debug(f"📱 Follow-up notification {i+1} sent")
                    else:
                        logger.warning(f"⚠️ Follow-up notification {i+1} failed")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Follow-up notification {i+1} error: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Error sending persistent notifications: {e}")
    
    async def send_test_notification(self) -> bool:
        """Send a test notification"""
        test_message = """🔔 **Test Notification - FCM V1**
        
📱 **Source**: Message Scraper Test
👤 **From**: System
🕐 **Time**: Now

📝 **Content**:
This is a test notification to verify FCM V1 is working correctly.

---
✅ FCM V1 Test Successful"""
        
        test_data = {
            'id': 'test_' + str(int(time.time())),
            'source': 'test',
            'chat_id': 'test_chat',
            'chat_title': 'Test Chat',
            'sender_name': 'Test System',
            'timestamp': datetime.now(),
            'has_media': False,
            'media_type': None
        }
        
        logger.info("🧪 Sending FCM V1 test notification...")
        result = await self.send_notification(test_message, test_data)
        
        if result:
            logger.info("✅ FCM V1 test notification sent successfully")
        else:
            logger.error("❌ FCM V1 test notification failed")
        
        return result
    
    async def send_urgent_alert(self, title: str, message: str) -> bool:
        """Send urgent system alert"""
        urgent_message = f"""🚨 **URGENT ALERT**
        
⚠️ **{title}**

{message}

---
🔴 System Alert - {datetime.now().strftime('%H:%M:%S')}"""
        
        alert_data = {
            'id': 'alert_' + str(int(time.time())),
            'source': 'system',
            'chat_id': 'system_alert',
            'chat_title': 'System Alerts',
            'sender_name': 'Message Scraper',
            'timestamp': datetime.now(),
            'has_media': False,
            'media_type': None
        }
        
        return await self.send_notification(urgent_message, alert_data)
    
    def validate_config(self) -> List[str]:
        """Validate FCM V1 configuration"""
        errors = []
        
        if not FIREBASE_AVAILABLE:
            errors.append("Firebase Admin SDK not installed - run: pip install firebase-admin")
        
        if not self.project_id:
            errors.append("FCM project ID is required")
        
        if not self.sender_id:
            errors.append("FCM sender ID is required")
        
        if not self.service_account_path:
            errors.append("FCM service account path is required")
        elif not os.path.exists(self.service_account_path):
            errors.append(f"FCM service account file not found: {self.service_account_path}")
        
        if not self.device_token:
            errors.append("FCM device token is required")
        elif len(self.device_token) < 50:
            errors.append("FCM device token appears too short")
        
        return errors
    
    async def get_device_info(self) -> Optional[Dict]:
        """Get device information"""
        return {
            'project_id': self.project_id,
            'sender_id': self.sender_id,
            'device_token': self.device_token[:20] + "..." if self.device_token else None,
            'configured': self.initialized,
            'test_mode': self.test_mode,
            'firebase_available': FIREBASE_AVAILABLE,
            'service_account_exists': os.path.exists(self.service_account_path) if self.service_account_path else False
        }

# Test function
async def test_fcm_v1_notifier():
    """Test FCM V1 notifier"""
    logger.info("🧪 Testing FCM V1 Notifier...")
    
    notifier = FCMv1Notifier()
    
    # Validate configuration
    config_errors = notifier.validate_config()
    if config_errors:
        logger.error("❌ FCM V1 config errors:")
        for error in config_errors:
            logger.error(f"   - {error}")
        return False
    
    # Send test notification
    result = await notifier.send_test_notification()
    
    if result:
        logger.info("✅ FCM V1 test completed successfully")
    else:
        logger.error("❌ FCM V1 test failed")
    
    return result

# Configuration helper
def show_fcm_v1_setup():
    """Show FCM V1 setup instructions"""
    setup_text = """
🔥 FCM V1 Setup Instructions:

1. Install Firebase Admin SDK:
   pip install firebase-admin

2. Get your credentials from Firebase Console:
   - Project ID: webscrapper-ce844
   - Sender ID: 572394369263
   - Download service account JSON file

3. Add to config/.env:
   FCM_PROJECT_ID=webscrapper-ce844
   FCM_SENDER_ID=572394369263
   FCM_SERVICE_ACCOUNT_PATH=config/firebase-service-account.json
   FCM_DEVICE_TOKEN=your_device_token_here

4. Update config/config.yaml:
   notifications:
     method: "fcm_v1"

5. Test setup:
   python -c "
   import asyncio
   from src.notifications.fcm_v1_notifier import test_fcm_v1_notifier
   asyncio.run(test_fcm_v1_notifier())
   "
"""
    print(setup_text)

if __name__ == "__main__":
    # Test the notifier
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        show_fcm_v1_setup()
    else:
        asyncio.run(test_fcm_v1_notifier())