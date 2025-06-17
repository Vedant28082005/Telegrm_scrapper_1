import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from typing import List, Dict, Any, Optional, Callable
import os
from datetime import datetime
import sys
import json
import hashlib
import glob
import shutil

# Add project root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from src.utils.config import config
from src.utils.logger import logger

class TelegramScraper:
    def __init__(self):
        self.config = config.get_telegram_config()
        self.client = None
        self.base_session_name = self.config.get('session_name', 'message_scraper')
        # Generate unique session name based on phone number and API ID
        credentials_str = f"{self.config['phone_number']}_{self.config['api_id']}"
        self.session_hash = hashlib.md5(credentials_str.encode()).hexdigest()[:8]
        self.session_name = f"{self.base_session_name}_{self.session_hash}"
        self.target_chats = self.config.get('target_chats', [])
        self.message_callback = None
        self.is_running = False
        
    @staticmethod
    def clear_all_sessions():
        """Clear all session files"""
        try:
            # Remove entire sessions directory and recreate it
            if os.path.exists("sessions"):
                shutil.rmtree("sessions")
            os.makedirs("sessions")
            logger.info("🗑️ Cleared all session files")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to clear sessions: {e}")
            return False
    
    def _get_session_files(self):
        """Get all session-related files for current user"""
        session_base = f"sessions/{self.session_name}"
        return [
            f"{session_base}.session",
            f"{session_base}.session-journal",
            f"{session_base}_creds.json"
        ]
    
    def _clear_current_session(self):
        """Clear current user's session files"""
        for file in self._get_session_files():
            if os.path.exists(file):
                try:
                    os.remove(file)
                    logger.info(f"🗑️ Removed session file: {file}")
                except Exception as e:
                    logger.error(f"❌ Failed to remove {file}: {e}")
    
    async def initialize(self):
        """Initialize Telegram client"""
        try:
            # Always start fresh by clearing all sessions
            self.clear_all_sessions()
            
            # Ensure clean disconnection of any existing client
            if self.client and self.client.is_connected():
                await self.stop_monitoring()
                self.client = None
            
            # Create sessions directory
            os.makedirs("sessions", exist_ok=True)
            
            # Store current credentials
            current_creds = {
                'api_id': str(self.config['api_id']),
                'api_hash': self.config['api_hash'],
                'phone': self.config['phone_number'],
                'session_hash': self.session_hash
            }
            
            creds_file = f"sessions/{self.session_name}_creds.json"
            with open(creds_file, 'w') as f:
                json.dump(current_creds, f)
            
            # Create new client
            self.client = TelegramClient(
                f"sessions/{self.session_name}",
                self.config['api_id'],
                self.config['api_hash'],
                device_model="Forex Trading Bot",
                system_version="Windows",
                app_version="1.0"
            )
            
            logger.info("🔗 Connecting to Telegram...")
            await self.client.start(phone=self.config['phone_number'])
            
            # Get user info
            me = await self.client.get_me()
            logger.info(f"✅ Connected as {me.first_name} ({me.username or 'No username'})")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Telegram client: {e}")
            # Clear session files on error
            self._clear_current_session()
            return False
    
    async def get_chat_info(self, chat_identifier) -> Optional[Dict]:
        """Get information about a chat"""
        try:
            entity = await self.client.get_entity(chat_identifier)
            return {
                'id': entity.id,
                'title': getattr(entity, 'title', getattr(entity, 'first_name', 'Unknown')),
                'type': entity.__class__.__name__,
                'username': getattr(entity, 'username', None)
            }
        except Exception as e:
            logger.error(f"❌ Failed to get chat info for {chat_identifier}: {e}")
            return None
    
    async def validate_target_chats(self) -> List[Dict]:
        """Validate and get info for all target chats"""
        valid_chats = []
        
        for chat in self.target_chats:
            chat_info = await self.get_chat_info(chat)
            if chat_info:
                valid_chats.append(chat_info)
                logger.info(f"✅ Chat validated: {chat_info['title']} (ID: {chat_info['id']})")
            else:
                logger.warning(f"⚠️ Invalid chat: {chat}")
        
        return valid_chats
    
    def set_message_callback(self, callback: Callable):
        """Set callback function for new messages"""
        self.message_callback = callback
    
    async def process_message(self, event):
        """Process incoming message"""
        try:
            message = event.message
            
            # Get chat info
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            # Extract message data
            message_data = {
                'id': message.id,
                'chat_id': chat.id,
                'chat_title': getattr(chat, 'title', getattr(chat, 'first_name', 'Unknown')),
                'sender_id': sender.id if sender else None,
                'sender_name': self._get_sender_name(sender),
                'timestamp': message.date,
                'text': message.text or '',
                'media_type': None,
                'media_path': None,
                'has_media': bool(message.media),
                'source': 'telegram'
            }
            
            # Handle media messages
            if message.media:
                message_data['media_type'] = self._get_media_type(message.media)
                
                # Download media if it's an image
                if isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
                    media_path = await self._download_media(message, chat.id, message.id)
                    message_data['media_path'] = media_path
            
            # Log message receipt
            content_preview = message_data['text'] or f"[{message_data['media_type']}]"
            logger.log_message_received(
                f"Telegram/{message_data['chat_title']}", 
                message_data['sender_name'], 
                content_preview
            )
            
            # Call callback if set
            if self.message_callback:
                await self.message_callback(message_data)
                
        except Exception as e:
            logger.error(f"❌ Error processing Telegram message: {e}")
    
    def _get_sender_name(self, sender) -> str:
        """Get human-readable sender name"""
        if not sender:
            return "Unknown"
        
        if hasattr(sender, 'first_name'):
            name = sender.first_name
            if hasattr(sender, 'last_name') and sender.last_name:
                name += f" {sender.last_name}"
            return name
        elif hasattr(sender, 'title'):
            return sender.title
        elif hasattr(sender, 'username'):
            return f"@{sender.username}"
        else:
            return f"User {sender.id}"
    
    def _get_media_type(self, media) -> str:
        """Determine media type"""
        if isinstance(media, MessageMediaPhoto):
            return "photo"
        elif isinstance(media, MessageMediaDocument):
            if media.document.mime_type.startswith('image/'):
                return "image"
            elif media.document.mime_type.startswith('video/'):
                return "video"
            elif media.document.mime_type.startswith('audio/'):
                return "audio"
            else:
                return "document"
        else:
            return "other"
    
    async def _download_media(self, message, chat_id: int, message_id: int) -> Optional[str]:
        """Download media file"""
        try:
            # Create media directory
            media_dir = f"media/telegram/{chat_id}"
            os.makedirs(media_dir, exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{message_id}_{timestamp}"
            
            # Download file
            file_path = await self.client.download_media(
                message.media,
                file=f"{media_dir}/{filename}"
            )
            
            logger.debug(f"📥 Downloaded media: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"❌ Failed to download media: {e}")
            return None
    
    async def start_monitoring(self):
        """Start monitoring target chats"""
        if not self.client:
            if not await self.initialize():
                return False
        
        # Validate target chats
        valid_chats = await self.validate_target_chats()
        if not valid_chats:
            logger.error("❌ No valid chats to monitor")
            return False
        
        logger.info(f"👀 Starting to monitor {len(valid_chats)} chats...")
        
        # Register event handler for new messages
        @self.client.on(events.NewMessage(chats=self.target_chats))
        async def message_handler(event):
            await self.process_message(event)
        
        self.is_running = True
        logger.info("✅ Telegram monitoring started")
        
        try:
            # Keep client running
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("🛑 Received interrupt signal")
        finally:
            self.is_running = False
            await self.stop_monitoring()
    
    async def stop_monitoring(self):
        """Stop monitoring and cleanup"""
        self.is_running = False
        if self.client:
            try:
                logger.info("🔌 Disconnecting from Telegram...")
                if self.client.is_connected():
                    await self.client.disconnect()
                    await self.client.disconnected
            except Exception as e:
                logger.error(f"❌ Error during disconnect: {e}")
            finally:
                self.client = None
    
    async def send_test_message(self, chat_id: int, message: str):
        """Send a test message (for debugging)"""
        try:
            if not self.client:
                await self.initialize()
            
            await self.client.send_message(chat_id, message)
            logger.info(f"✅ Test message sent to {chat_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to send test message: {e}")
            return False

# Test function
async def test_telegram_connection():
    """Test Telegram connection and list available chats"""
    scraper = TelegramScraper()
    
    if await scraper.initialize():
        logger.info("🔍 Testing Telegram connection...")
        
        # Get list of dialogs (chats)
        async for dialog in scraper.client.iter_dialogs(limit=10):
            logger.info(f"📱 Available chat: {dialog.name} (ID: {dialog.id})")
        
        await scraper.stop_monitoring()
        return True
    else:
        return False

if __name__ == "__main__":
    # Test the scraper
    asyncio.run(test_telegram_connection())