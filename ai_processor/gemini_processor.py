import google.generativeai as genai
import asyncio
import time
from typing import Dict, Any, Optional
import os
from PIL import Image
import base64
import io
import sys

# Add project root to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from src.utils.config import config
from src.utils.logger import logger

class GeminiProcessor:
    def __init__(self):
        self.config = config.get_gemini_config()
        self.message_format_template = config.get('message_format.template', '')
        self.max_tokens = self.config.get('max_tokens', 1000)
        self.rate_limit_delay = config.get('system.rate_limit_delay', 2)
        
        # Initialize Gemini
        genai.configure(api_key=self.config['api_key'])
        
        # Models
        self.text_model = genai.GenerativeModel(self.config.get('model', 'gemini-1.5-pro'))
        self.vision_model = genai.GenerativeModel(self.config.get('vision_model', 'gemini-1.5-pro-vision'))
        
        logger.info("🤖 Gemini AI processor initialized")
    
    async def process_text_message(self, message_data: Dict[str, Any]) -> str:
        """Process text message and format it"""
        start_time = time.time()
        
        try:
            # Create prompt for text formatting
            prompt = self._create_text_formatting_prompt(message_data)
            
            # Generate response
            response = await self._generate_response(self.text_model, prompt)
            
            processing_time = time.time() - start_time
            logger.log_ai_processing("text", processing_time)
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Error processing text message: {e}")
            return self._create_fallback_message(message_data)
    
    async def process_image_message(self, message_data: Dict[str, Any]) -> str:
        """Process image message: describe image then format"""
        start_time = time.time()
        
        try:
            # Step 1: Describe the image
            if message_data.get('media_path'):
                image_description = await self._describe_image(message_data['media_path'])
                
                # Add description to message data
                message_data['ai_description'] = image_description
                message_data['content_type'] = 'image_with_description'
            else:
                image_description = "Image could not be processed"
                message_data['ai_description'] = image_description
            
            # Step 2: Format the message with description
            formatted_message = await self._format_image_message(message_data, image_description)
            
            processing_time = time.time() - start_time
            logger.log_ai_processing("image", processing_time)
            
            return formatted_message
            
        except Exception as e:
            logger.error(f"❌ Error processing image message: {e}")
            return self._create_fallback_message(message_data, "Image processing failed")
    
    async def _describe_image(self, image_path: str) -> str:
        """Describe image using Gemini Vision"""
        try:
            # Load and prepare image
            image = Image.open(image_path)
            
            # Create description prompt
            prompt = """
            Analyze this image and provide a detailed but concise description. Focus on:
            1. What is shown in the image
            2. Any text visible in the image
            3. Key objects, people, or scenes
            4. Context or setting
            
            Keep the description informative but under 200 words.
            """
            
            # Generate description
            response = self.vision_model.generate_content([prompt, image])
            description = response.text.strip()
            
            logger.debug(f"🖼️ Image described: {description[:100]}...")
            return description
            
        except Exception as e:
            logger.error(f"❌ Error describing image: {e}")
            return "Unable to analyze image content"
    
    async def _format_image_message(self, message_data: Dict[str, Any], image_description: str) -> str:
        """Format image message with AI description"""
        prompt = f"""
        Format this message notification for a mobile device. Make it clear, concise, and informative.

        Message Details:
        - Source: {message_data['source']} ({message_data['chat_title']})
        - Sender: {message_data['sender_name']}
        - Time: {message_data['timestamp']}
        - Type: Image/Photo
        - AI Description: {image_description}
        - Original Text: {message_data.get('text', 'No text')}

        Requirements:
        - Keep under 400 characters for mobile notification
        - Include source, sender, and key image content
        - Make it urgent/attention-grabbing
        - Use emojis appropriately
        - Format for easy reading on phone

        Template to follow:
        {self.message_format_template}
        """
        
        response = await self._generate_response(self.text_model, prompt)
        return response
    
    def _create_text_formatting_prompt(self, message_data: Dict[str, Any]) -> str:
        """Create prompt for text message formatting"""
        return f"""
        Format this message notification for a mobile device. Make it urgent and attention-grabbing.

        Message Details:
        - Source: {message_data['source']} ({message_data['chat_title']})
        - Sender: {message_data['sender_name']}
        - Time: {message_data['timestamp']}
        - Content: {message_data['text']}

        Requirements:
        - Keep under 400 characters for mobile notification
        - Make it urgent and impossible to ignore
        - Use emojis appropriately
        - Include all key information
        - Format for easy reading on phone

        Template to follow:
        {self.message_format_template}
        """
    
    async def _generate_response(self, model, prompt: str) -> str:
        """Generate response from Gemini with rate limiting"""
        try:
            # Add rate limiting delay
            await asyncio.sleep(self.rate_limit_delay)
            
            # Generate response
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=0.3,
                )
            )
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"❌ Gemini API error: {e}")
            raise
    
    def _create_fallback_message(self, message_data: Dict[str, Any], error_note: str = "") -> str:
        """Create fallback message when AI processing fails"""
        timestamp = message_data['timestamp'].strftime("%H:%M")
        error_suffix = f" ({error_note})" if error_note else ""
        
        if message_data.get('has_media'):
            content = f"[{message_data.get('media_type', 'Media')}]{error_suffix}"
        else:
            content = message_data.get('text', 'No content')
        
        return f"""🔔 **New Message Alert**{error_suffix}
        
📱 **Source**: {message_data['source']} ({message_data['chat_title']})
👤 **From**: {message_data['sender_name']}
🕐 **Time**: {timestamp}

📝 **Content**:
{content}

---
⚠️ Basic formatting (AI unavailable)"""
    
    async def test_connection(self) -> bool:
        """Test Gemini API connection with fallback options"""
        models_to_try = [
            "gemini-1.5-flash",  # Try Flash first (lower quota)
            "gemini-1.5-pro",   # Then Pro
            "gemini-pro"        # Then older Pro
        ]
        
        for model_name in models_to_try:
            try:
                # Create temporary model for testing
                test_model = genai.GenerativeModel(model_name)
                
                test_prompt = "Say 'OK' if you can read this."
                response = test_model.generate_content(
                    test_prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=10,  # Very small for testing
                        temperature=0.1,
                    )
                )
                
                if "ok" in response.text.lower():
                    logger.info(f"✅ Gemini API test successful with {model_name}")
                    # Update our models to use the working one
                    self.text_model = test_model
                    self.vision_model = genai.GenerativeModel(model_name)
                    return True
                
            except Exception as e:
                logger.warning(f"⚠️ Model {model_name} failed: {str(e)[:100]}...")
                if "429" in str(e):  # Rate limit error
                    logger.warning(f"⏳ Rate limited on {model_name}, trying next model...")
                    await asyncio.sleep(2)  # Brief pause
                    continue
                elif "quota" in str(e).lower():
                    logger.warning(f"💰 Quota exceeded on {model_name}, trying next model...")
                    continue
        
        logger.error("❌ All Gemini models failed or rate limited")
        return False
    
    async def get_custom_format_suggestion(self, sample_messages: list) -> str:
        """Get AI suggestion for custom message format based on sample messages"""
        prompt = f"""
        Based on these sample messages, suggest an optimal notification format template:
        
        Sample Messages:
        {sample_messages}
        
        Create a template that:
        1. Is perfect for mobile notifications
        2. Uses emojis effectively
        3. Includes placeholders like {{source}}, {{sender}}, {{content}}, {{timestamp}}
        4. Is urgent and attention-grabbing
        5. Stays under 400 characters
        
        Provide just the template format.
        """
        
        try:
            response = await self._generate_response(self.text_model, prompt)
            return response
        except Exception as e:
            logger.error(f"❌ Error getting format suggestion: {e}")
            return self.message_format_template

# Test function
async def test_gemini_processor():
    """Test Gemini processor functionality"""
    processor = GeminiProcessor()
    
    # Test API connection
    if not await processor.test_connection():
        return False
    
    # Test text processing
    sample_message = {
        'source': 'telegram',
        'chat_title': 'Test Group',
        'sender_name': 'Test User',
        'timestamp': '2025-06-12 10:30:00',
        'text': 'This is a test message for AI processing',
        'has_media': False
    }
    
    try:
        formatted = await processor.process_text_message(sample_message)
        logger.info(f"✅ Text processing test successful:\n{formatted}")
        return True
    except Exception as e:
        logger.error(f"❌ Text processing test failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_gemini_processor())