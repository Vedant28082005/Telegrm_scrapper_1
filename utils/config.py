import yaml
import os
from dotenv import load_dotenv
from typing import Dict, Any, List
import logging

class ConfigLoader:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from YAML file and environment variables"""
        # Load environment variables
        load_dotenv("config/.env")
        
        # Load YAML config
        try:
            with open(self.config_path, 'r', encoding='utf-8') as file:
                self.config = yaml.safe_load(file)
        except FileNotFoundError:
            logging.error(f"Config file not found: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logging.error(f"Error parsing YAML config: {e}")
            raise
        
        # Override with environment variables
        self._override_with_env()
    
    def _override_with_env(self):
        """Override config values with environment variables"""
        env_mappings = {
            'TELEGRAM_API_ID': ['telegram', 'api_id'],
            'TELEGRAM_API_HASH': ['telegram', 'api_hash'],
            'TELEGRAM_PHONE': ['telegram', 'phone_number'],
            'DISCORD_USER_TOKEN': ['discord', 'user_token'],
            'GEMINI_API_KEY': ['gemini', 'api_key'],
            'FCM_SERVER_KEY': ['notifications', 'fcm', 'server_key'],
            'FCM_DEVICE_TOKEN': ['notifications', 'fcm', 'device_token'],
            'PUSHBULLET_TOKEN': ['notifications', 'pushbullet', 'access_token'],
            'WEBHOOK_URL': ['notifications', 'webhook', 'url'],
            'WEBHOOK_TOKEN': ['notifications', 'webhook', 'headers', 'Authorization']
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                self._set_nested_value(self.config, config_path, value)
    
    def _set_nested_value(self, config: Dict, path: List[str], value: Any):
        """Set nested dictionary value using path list"""
        current = config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value
    
    def get(self, path: str, default: Any = None) -> Any:
        """Get config value using dot notation (e.g., 'telegram.api_id')"""
        keys = path.split('.')
        current = self.config
        
        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def get_telegram_config(self) -> Dict[str, Any]:
        """Get Telegram configuration"""
        return self.get('telegram', {})
    
    def get_discord_config(self) -> Dict[str, Any]:
        """Get Discord configuration"""
        return self.get('discord', {})
    
    def get_gemini_config(self) -> Dict[str, Any]:
        """Get Gemini configuration"""
        return self.get('gemini', {})
    
    def get_notification_config(self) -> Dict[str, Any]:
        """Get notification configuration"""
        return self.get('notifications', {})
    
    def get_system_config(self) -> Dict[str, Any]:
        """Get system configuration"""
        return self.get('system', {})
    
    def is_debug_enabled(self) -> bool:
        """Check if debug mode is enabled"""
        return self.get('debug.enabled', False)
    
    def is_test_mode(self) -> bool:
        """Check if test mode is enabled"""
        return self.get('debug.test_mode', False)
    
    def validate_config(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        # Required Telegram settings
        if not self.get('telegram.api_id'):
            errors.append("Telegram API ID is required")
        if not self.get('telegram.api_hash'):
            errors.append("Telegram API Hash is required")
        if not self.get('telegram.phone_number'):
            errors.append("Telegram phone number is required")
        
        # Required Gemini settings
        if not self.get('gemini.api_key'):
            errors.append("Gemini API key is required")
        
        # At least one notification method
        notification_methods = ['fcm', 'pushbullet', 'webhook']
        has_notification = False
        
        for method in notification_methods:
            if method == 'fcm' and self.get(f'notifications.fcm.server_key'):
                has_notification = True
            elif method == 'pushbullet' and self.get(f'notifications.pushbullet.access_token'):
                has_notification = True
            elif method == 'webhook' and self.get(f'notifications.webhook.url'):
                has_notification = True
        
        if not has_notification:
            errors.append("At least one notification method must be configured")
        
        return errors

# Global config instance
config = ConfigLoader()