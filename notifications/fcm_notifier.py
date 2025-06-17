import asyncio
import aiohttp
import json
from typing import Dict, Any, List, Optional
import time
import re
from datetime import datetime
import sys
import os

# Add project root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from src.utils.config import config
from src.utils.logger import logger

class FCMNotifier:
    def __init__(self):
        self.notification_config = config.get_notification_config()
        self.fcm_config = self.notification_config.get('fcm', {})
        self.server_key = self.fcm_config.get('server_key')
        self.device_token = self.fcm_config.get('device_token')
        
        # FCM endpoint
        self.fcm_url = "https://fcm.googleapis.com/fcm/send"
        
        # Notification settings
        self.duration = self.notification_config.get('duration', 30)
        self.priority = self.notification_config.get('priority', 'high')
        self.sound_enabled = self.notification_config.get('sound', True)
        self.vibration_enabled = self.notification_config.get('vibration', True)
        self.voice_enabled = self.notification_config.get('voice_alerts', True)  # NEW: Voice alerts
        
        # Test mode
        self.test_mode = config.is_test_mode()
        
        logger.info("📱 FCM Notifier with Voice Alerts initialized")
    
    def _extract_voice_content(self, formatted_message: str, message_data: Dict[str, Any]) -> str:
        """Extract key trading information for Text-to-Speech"""
        try:
            # Check if it's a forex trading signal
            if 'FOREX' in formatted_message.upper() or 'TRADE' in formatted_message.upper():
                
                # Extract trading details using regex
                instrument_match = re.search(r'\*\*Instrument\*\*:\s*([A-Z]{6,})', formatted_message)
                direction_match = re.search(r'\*\*Direction\*\*:\s*(BUY|SELL)', formatted_message)
                entry_match = re.search(r'\*\*Entry\*\*:\s*([\d,]+\.?\d*)', formatted_message)
                stop_loss_match = re.search(r'\*\*Stop Loss\*\*:\s*([\d,]+\.?\d*)', formatted_message)
                take_profit_match = re.search(r'\*\*Take Profit\*\*:\s*([\d,]+\.?\d*)', formatted_message)
                
                # Build voice message
                voice_parts = ["Urgent Forex Trade Signal."]
                
                if instrument_match:
                    instrument = instrument_match.group(1)
                    # Convert XAUUSD to "Gold US Dollar" for better pronunciation
                    if instrument == "XAUUSD":
                        voice_parts.append("Instrument: Gold US Dollar.")
                    elif instrument == "EURUSD":
                        voice_parts.append("Instrument: Euro US Dollar.")
                    elif instrument == "GBPUSD":
                        voice_parts.append("Instrument: British Pound US Dollar.")
                    else:
                        voice_parts.append(f"Instrument: {instrument}.")
                
                if direction_match:
                    direction = direction_match.group(1)
                    voice_parts.append(f"Direction: {direction}.")
                
                if entry_match:
                    entry = entry_match.group(1).replace(',', '')
                    voice_parts.append(f"Entry price: {entry}.")
                
                if stop_loss_match:
                    stop_loss = stop_loss_match.group(1).replace(',', '')
                    voice_parts.append(f"Stop loss: {stop_loss}.")
                
                if take_profit_match:
                    take_profit = take_profit_match.group(1).replace(',', '')
                    voice_parts.append(f"Take profit: {take_profit}.")
                
                voice_parts.append("Check your phone immediately for full details.")
                
                return " ".join(voice_parts)
            
            else:
                # For non-trading messages, create general alert
                sender = message_data.get('sender_name', 'Unknown')
                chat = message_data.get('chat_title', 'Unknown chat')
                
                return f"New urgent message from {sender} in {chat}. Check your phone immediately."
                
        except Exception as e:
            logger.error(f"❌ Error extracting voice content: {e}")
            return "New urgent message received. Check your phone immediately."
    
    def _create_notification_payload(self, formatted_message: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create FCM notification payload with voice alerts"""
        
        # Extract title and body from formatted message
        lines = formatted_message.strip().split('\n')
        title = lines[0] if lines else "New Message"
        
        # Clean title (remove emojis for title, keep for body)
        clean_title = title.replace('🔔', '').replace('**', '').strip()
        
        # Create voice message for TTS
        voice_message = self._extract_voice_content(formatted_message, message_data) if self.voice_enabled else None
        
        # Create notification payload with voice support
        payload = {
            "to": self.device_token,
            "priority": "high",  # Always high for trading signals
            "notification": {
                "title": clean_title[:50],  # Limit title length
                "body": formatted_message[:300],  # Limit body length
                "sound": "default" if self.sound_enabled else None,
                "badge": 1,
                "tag": f"message_{message_data.get('id', int(time.time()))}",
                "icon": "ic_notification",
                "color": "#FF5722",  # Orange color for attention
                "click_action": "FLUTTER_NOTIFICATION_CLICK"
            },
            "data": {
                "message_id": str(message_data.get('id', '')),
                "source": message_data.get('source', ''),
                "chat_id": str(message_data.get('chat_id', '')),
                "chat_title": message_data.get('chat_title', ''),
                "sender_name": message_data.get('sender_name', ''),
                "timestamp": message_data.get('timestamp', datetime.now()).isoformat(),
                "has_media": str(message_data.get('has_media', False)),
                "media_type": message_data.get('media_type', ''),
                "duration": str(self.duration),
                "type": "message_alert",
                # NEW: Voice-related data
                "speak_text": voice_message if voice_message else "",
                "voice_enabled": str(self.voice_enabled),
                "is_forex_signal": str('FOREX' in formatted_message.upper() or 'TRADE' in formatted_message.upper()),
                "urgency_level": "high" if 'FOREX' in formatted_message.upper() else "normal"
            },
            "android": {
                "priority": "high",
                "ttl": "3600s",
                "notification": {
                    "channel_id": "forex_voice_alerts",  # NEW: Dedicated channel for voice alerts
                    "sound": "default" if self.sound_enabled else None,
                    "vibrate_timings": ["0s", "1s", "0.5s", "1s"] if self.vibration_enabled else None,  # Longer vibration
                    "priority": "max",  # Maximum priority for voice alerts
                    "visibility": "public",
                    "ongoing": True,  # Makes notification persistent
                    "auto_cancel": False,  # Prevents easy dismissal
                    "sticky": True,
                    "local_only": False,
                    "default_sound": True,
                    "default_vibrate": True,
                    "default_light_settings": True,
                    # NEW: Voice-specific settings
                    "bypass_dnd": True,  # Bypass Do Not Disturb
                    "show_when": True,
                    "when": int(time.time() * 1000),  # Current timestamp
                    "timeout_after": self.duration * 1000,  # Timeout in milliseconds
                }
            }
        }
        
        # Add voice-specific payload for custom Android app handling
        if self.voice_enabled and voice_message:
            payload["data"]["tts_config"] = json.dumps({
                "text": voice_message,
                "language": "en-US",
                "pitch": 1.0,
                "speech_rate": 0.8,  # Slightly slower for clarity
                "volume": 1.0,  # Maximum volume
                "repeat_count": 2,  # Repeat the message twice
                "priority": "immediate"
            })
        
        return payload
    
    async def send_notification(self, formatted_message: str, message_data: Dict[str, Any]) -> bool:
        """Send notification via FCM with voice alerts"""
        if not self.server_key or not self.device_token:
            logger.error("❌ FCM server key or device token not configured")
            return False
        
        if self.test_mode:
            logger.info(f"🧪 TEST MODE: Would send voice notification:\n{formatted_message}")
            if self.voice_enabled:
                voice_content = self._extract_voice_content(formatted_message, message_data)
                logger.info(f"🔊 Voice content: {voice_content}")
            return True
        
        try:
            # Create payload with voice support
            payload = self._create_notification_payload(formatted_message, message_data)
            
            # Headers
            headers = {
                "Authorization": f"key={self.server_key}",
                "Content-Type": "application/json"
            }
            
            # Send notification
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.fcm_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    response_text = await response.text()
                    
                    if response.status == 200:
                        response_data = json.loads(response_text)
                        
                        if response_data.get('success', 0) > 0:
                            logger.log_notification_sent("FCM+Voice", True)
                            
                            # Send voice-enhanced persistent notifications for forex signals
                            if self.duration > 5 and ('FOREX' in formatted_message.upper() or 'TRADE' in formatted_message.upper()):
                                asyncio.create_task(self._send_voice_persistent_notifications(
                                    formatted_message, message_data
                                ))
                            
                            return True
                        else:
                            error = response_data.get('results', [{}])[0].get('error', 'Unknown error')
                            logger.error(f"❌ FCM send failed: {error}")
                            return False
                    else:
                        logger.error(f"❌ FCM HTTP error {response.status}: {response_text}")
                        return False
        
        except asyncio.TimeoutError:
            logger.error("❌ FCM notification timeout")
            return False
        except Exception as e:
            logger.error(f"❌ FCM notification error: {e}")
            return False
    
    async def _send_voice_persistent_notifications(self, formatted_message: str, message_data: Dict[str, Any]):
        """Send voice-enhanced follow-up notifications for forex signals"""
        try:
            # For forex signals, send more aggressive follow-ups
            follow_ups = min(self.duration // 3, 8)  # Every 3 seconds, max 8 follow-ups
            
            for i in range(follow_ups):
                await asyncio.sleep(3)  # Wait 3 seconds between notifications
                
                # Create urgent follow-up with different voice message
                urgency_levels = [
                    "🚨 URGENT FOREX ALERT 🚨",
                    "🔊 CRITICAL TRADE SIGNAL 🔊", 
                    "⚠️ IMMEDIATE ACTION REQUIRED ⚠️",
                    "🚨 FOREX SIGNAL WAITING 🚨"
                ]
                
                urgency_prefix = urgency_levels[i % len(urgency_levels)]
                follow_up_message = f"{urgency_prefix}\n\n{formatted_message}"
                
                follow_up_data = message_data.copy()
                follow_up_data['id'] = f"{message_data.get('id', 'unknown')}_voice_followup_{i+1}"
                
                # Create different voice message for each follow-up
                if i == 0:
                    voice_suffix = "This is your first reminder."
                elif i == 1:
                    voice_suffix = "This is your second reminder. Action required."
                elif i == 2:
                    voice_suffix = "This is your third reminder. Don't miss this trade."
                else:
                    voice_suffix = f"This is reminder number {i+1}. Check your phone now."
                
                # Modify voice content for follow-up
                original_voice = self._extract_voice_content(formatted_message, message_data)
                follow_up_voice = f"{original_voice} {voice_suffix}"
                
                # Send follow-up with enhanced voice
                payload = self._create_notification_payload(follow_up_message, follow_up_data)
                payload['notification']['tag'] = f"urgent_forex_{int(time.time())}_{i}"
                payload['data']['speak_text'] = follow_up_voice
                payload['data']['urgency_level'] = "critical"
                
                # Increase priority for later follow-ups
                if i >= 2:
                    payload['android']['notification']['priority'] = "max"
                    payload['android']['notification']['vibrate_timings'] = ["0s", "2s", "1s", "2s"]
                
                headers = {
                    "Authorization": f"key={self.server_key}",
                    "Content-Type": "application/json"
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.fcm_url, json=payload, headers=headers) as response:
                        if response.status == 200:
                            logger.debug(f"🔊 Voice follow-up {i+1} sent")
                        else:
                            logger.warning(f"⚠️ Voice follow-up {i+1} failed")
                            
        except Exception as e:
            logger.error(f"❌ Error sending voice persistent notifications: {e}")
    
    async def send_test_notification(self) -> bool:
        """Send a test notification with voice"""
        test_message = """🔔 **FOREX TRADE SIGNAL**
        
📈 **Instrument**: XAUUSD
💰 **Entry**: 2650.50
🛑 **Stop Loss**: 2665.00
🎯 **Take Profit**: 2620.00
📱 **Direction**: SELL

📝 **Analysis**: Test forex signal for voice alerts
👤 **Source**: System Test

---
🤖 AI Chart Analysis
⚡ Ready to Trade!"""
        
        test_data = {
            'id': 'voice_test_' + str(int(time.time())),
            'source': 'test',
            'chat_id': 'test_chat',
            'chat_title': 'Forex Test',
            'sender_name': 'Voice Test System',
            'timestamp': datetime.now(),
            'has_media': False,
            'media_type': None
        }
        
        logger.info("🧪 Sending FCM test notification with voice...")
        result = await self.send_notification(test_message, test_data)
        
        if result:
            logger.info("✅ FCM voice test notification sent successfully")
            if self.voice_enabled:
                voice_content = self._extract_voice_content(test_message, test_data)
                logger.info(f"🔊 Voice message: {voice_content}")
        else:
            logger.error("❌ FCM voice test notification failed")
        
        return result
    
    async def send_urgent_alert(self, title: str, message: str) -> bool:
        """Send urgent system alert with voice"""
        urgent_message = f"""🚨 **URGENT SYSTEM ALERT**
        
⚠️ **{title}**

{message}

---
🔴 System Alert - {datetime.now().strftime('%H:%M:%S')}"""
        
        alert_data = {
            'id': 'voice_alert_' + str(int(time.time())),
            'source': 'system',
            'chat_id': 'system_alert',
            'chat_title': 'System Alerts',
            'sender_name': 'Forex Scraper',
            'timestamp': datetime.now(),
            'has_media': False,
            'media_type': None
        }
        
        return await self.send_notification(urgent_message, alert_data)
    
    def validate_config(self) -> List[str]:
        """Validate FCM configuration"""
        errors = []
        
        if not self.server_key:
            errors.append("FCM server key is required")
        
        if not self.device_token:
            errors.append("FCM device token is required")
        
        if self.server_key and not self.server_key.startswith('AAAA'):
            errors.append("FCM server key format appears invalid")
        
        if self.device_token and len(self.device_token) < 50:
            errors.append("FCM device token appears too short")
        
        return errors
    
    async def get_device_info(self) -> Optional[Dict]:
        """Get device information"""
        return {
            'device_token': self.device_token[:20] + "..." if self.device_token else None,
            'configured': bool(self.server_key and self.device_token),
            'test_mode': self.test_mode,
            'voice_enabled': self.voice_enabled,
            'sound_enabled': self.sound_enabled,
            'vibration_enabled': self.vibration_enabled,
            'duration': self.duration
        }

# Enhanced Pushbullet notifier with voice instructions
class PushbulletNotifier:
    def __init__(self):
        self.notification_config = config.get_notification_config()
        self.pushbullet_config = self.notification_config.get('pushbullet', {})
        self.access_token = self.pushbullet_config.get('access_token')
        self.api_url = "https://api.pushbullet.com/v2/pushes"
        
        # Voice settings
        self.voice_enabled = self.notification_config.get('voice_alerts', True)
        self.test_mode = config.is_test_mode()
        
        logger.info("📱 Pushbullet Notifier with Voice Instructions initialized")
    
    def _create_voice_instructions(self, formatted_message: str, message_data: Dict[str, Any]) -> str:
        """Create voice instructions for Pushbullet (since it doesn't support TTS directly)"""
        if 'FOREX' in formatted_message.upper() or 'TRADE' in formatted_message.upper():
            return """
🔊 VOICE ALERT INSTRUCTIONS:
1. Enable your phone's text-to-speech
2. Use any TTS app to read this message aloud
3. Set volume to maximum
4. This is a CRITICAL FOREX SIGNAL

📱 Or use Google Assistant: "Hey Google, read my notifications"
"""
        else:
            return """
🔊 VOICE ALERT: Use your phone's accessibility features or TTS apps to hear this message.
"""
    
    async def send_notification(self, formatted_message: str, message_data: Dict[str, Any]) -> bool:
        """Send LOUD notification via Pushbullet with voice instructions"""
        if not self.access_token:
            logger.error("❌ Pushbullet access token not configured")
            return False
        
        if self.test_mode:
            logger.info(f"🧪 TEST MODE: Would send Pushbullet voice notification:\n{formatted_message}")
            return True
        
        try:
            # Extract title from message
            lines = formatted_message.strip().split('\n')
            base_title = lines[0].replace('🔔', '').replace('**', '').strip()
            
            # Create LOUD attention-grabbing notification with voice instructions
            loud_title = f"🚨🔊 URGENT FOREX SIGNAL 🔊🚨"
            
            voice_instructions = self._create_voice_instructions(formatted_message, message_data) if self.voice_enabled else ""
            
            loud_body = f"""🚨 CRITICAL TRADING ALERT 🚨

{formatted_message}

{voice_instructions}

🔊 MAXIMUM VOLUME RECOMMENDED 🔊
⚠️ IMMEDIATE ACTION REQUIRED ⚠️
📱 CHECK YOUR TRADING PLATFORM NOW 📱

Time: {datetime.now().strftime('%H:%M:%S')}"""
            
            payload = {
                "type": "note",
                "title": loud_title[:100],
                "body": loud_body[:1000]
            }
            
            headers = {
                "Access-Token": self.access_token,
                "Content-Type": "application/json"
            }
            
            # Send LOUD notification
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        logger.log_notification_sent("Pushbullet+Voice", True)
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Pushbullet error {response.status}: {error_text}")
                        return False
        
        except Exception as e:
            logger.error(f"❌ Pushbullet notification error: {e}")
            return False
    
    async def send_test_notification(self) -> bool:
        """Send a test notification with voice instructions"""
        test_message = """🔔 **FOREX TRADE SIGNAL TEST**
        
📈 **Instrument**: XAUUSD
💰 **Entry**: 2650.50
📱 **Direction**: SELL

📝 **Content**: This is a voice-enabled test notification.

---
✅ Pushbullet Voice Test"""
        
        test_data = {
            'id': 'pushbullet_voice_test_' + str(int(time.time())),
            'source': 'test',
            'chat_id': 'test_chat',
            'chat_title': 'Voice Test',
            'sender_name': 'Voice Test System',
            'timestamp': datetime.now(),
            'has_media': False,
            'media_type': None
        }
        
        logger.info("🧪 Sending Pushbullet test notification with voice instructions...")
        result = await self.send_notification(test_message, test_data)
        
        if result:
            logger.info("✅ Pushbullet voice test notification sent successfully")
        else:
            logger.error("❌ Pushbullet voice test notification failed")
        
        return result

# Test functions
async def test_fcm_notifier():
    """Test FCM notifier with voice"""
    notifier = FCMNotifier()
    
    # Validate configuration
    config_errors = notifier.validate_config()
    if config_errors:
        logger.error(f"❌ FCM config errors: {config_errors}")
        return False
    
    # Send test notification
    return await notifier.send_test_notification()

async def test_pushbullet_notifier():
    """Test Pushbullet notifier with voice instructions"""
    notifier = PushbulletNotifier()
    
    test_message = """🔔 **FOREX TRADE SIGNAL**
    
📈 **Instrument**: EURUSD
💰 **Entry**: 1.0850
📱 **Direction**: BUY

This is a Pushbullet voice test."""
    
    test_data = {'id': 'test', 'source': 'test', 'sender_name': 'Test', 'chat_title': 'Test'}
    
    return await notifier.send_notification(test_message, test_data)

if __name__ == "__main__":
    # Test both notifiers
    asyncio.run(test_fcm_notifier())
    # asyncio.run(test_pushbullet_notifier())