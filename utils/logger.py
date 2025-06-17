import logging
import colorlog
import os
from datetime import datetime
from typing import Optional

class MessageScraperLogger:
    def __init__(self, 
                 log_level: str = "INFO",
                 log_file: Optional[str] = None,
                 console_output: bool = True):
        self.log_level = log_level.upper()
        self.log_file = log_file
        self.console_output = console_output
        self.setup_logger()
    
    def setup_logger(self):
        """Setup logger with both file and console handlers"""
        # Create logger
        self.logger = logging.getLogger('MessageScraper')
        self.logger.setLevel(getattr(logging, self.log_level))
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create formatters
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        console_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        
        # Console handler
        if self.console_output:
            console_handler = colorlog.StreamHandler()
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # File handler
        if self.log_file:
            # Create log directory if it doesn't exist
            log_dir = os.path.dirname(self.log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
            
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message"""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message"""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message"""
        self.logger.critical(message, **kwargs)
    
    def log_message_received(self, source: str, sender: str, content_preview: str):
        """Log when a message is received"""
        preview = content_preview[:50] + "..." if len(content_preview) > 50 else content_preview
        self.info(f"📨 Message from {source} | {sender}: {preview}")
    
    def log_ai_processing(self, message_type: str, processing_time: float):
        """Log AI processing completion"""
        self.info(f"🤖 AI processed {message_type} message in {processing_time:.2f}s")
    
    def log_notification_sent(self, method: str, success: bool):
        """Log notification sending result"""
        status = "✅ sent" if success else "❌ failed"
        self.info(f"📱 Notification {status} via {method}")
    
    def log_rate_limit(self, service: str, wait_time: float):
        """Log rate limiting"""
        self.warning(f"⏳ Rate limited by {service}, waiting {wait_time:.1f}s")
    
    def log_startup(self, config_summary: dict):
        """Log application startup"""
        self.info("🚀 Message Scraper starting up")
        self.info(f"📊 Config: {config_summary}")
    
    def log_shutdown(self):
        """Log application shutdown"""
        self.info("🛑 Message Scraper shutting down")

# Create global logger instance
def create_logger(log_level: str = "INFO", 
                 log_file: Optional[str] = None,
                 console_output: bool = True) -> MessageScraperLogger:
    return MessageScraperLogger(log_level, log_file, console_output)

# Default logger
logger = create_logger()