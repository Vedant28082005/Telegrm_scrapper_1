import re
from typing import Dict, List, Optional, Any
from datetime import datetime

class TradingSignalParser:
    """Utility class to extract trading information from text messages"""
    
    def __init__(self):
        # Forex pairs patterns
        self.forex_pairs = [
            'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD',
            'EURJPY', 'GBPJPY', 'EURGBP', 'EURAUD', 'EURCHF', 'GBPAUD', 'GBPCHF',
            'AUDJPY', 'CADJPY', 'CHFJPY', 'AUDCAD', 'AUDCHF', 'CADCHF', 'NZDJPY',
            'XAUUSD', 'XAGUSD', 'BTCUSD', 'ETHUSD', 'LTCUSD', 'ADAUSD'
        ]
        
        # Trading direction patterns
        self.direction_patterns = {
            'buy': r'(?:BUY|LONG|BULLISH|UP)',
            'sell': r'(?:SELL|SHORT|BEARISH|DOWN)'
        }
        
        # Price patterns
        self.price_pattern = r'\d+\.?\d*'
        
        # Trading keywords
        self.trading_keywords = {
            'entry': r'(?:ENTRY|ENTER|PRICE|@|AT)',
            'stop_loss': r'(?:SL|STOP\s*LOSS|STOPLOSS|STOP)',
            'take_profit': r'(?:TP|TAKE\s*PROFIT|TAKEPROFIT|TARGET|TGT)',
            'risk_reward': r'(?:RR|RISK\s*REWARD|R:R|RATIO)'
        }
    
    def extract_trading_signal(self, text: str) -> Dict[str, Any]:
        """Extract comprehensive trading signal from text"""
        text_upper = text.upper()
        
        signal = {
            'instrument': self._extract_instrument(text_upper),
            'direction': self._extract_direction(text_upper),
            'entry_price': self._extract_entry_price(text_upper),
            'stop_loss': self._extract_stop_loss(text_upper),
            'take_profit': self._extract_take_profit(text_upper),
            'risk_reward': self._calculate_risk_reward(text_upper),
            'timeframe': self._extract_timeframe(text_upper),
            'confidence': self._calculate_confidence(text_upper),
            'raw_prices': self._extract_all_prices(text),
            'is_valid_signal': False
        }
        
        # Validate if this is a complete trading signal
        signal['is_valid_signal'] = self._validate_signal(signal)
        
        return signal
    
    def _extract_instrument(self, text: str) -> Optional[str]:
        """Extract currency pair or trading instrument"""
        # Look for forex pairs
        for pair in self.forex_pairs:
            # Try with and without separator
            patterns = [
                pair,
                pair[:3] + '/' + pair[3:],
                pair[:3] + ' ' + pair[3:],
                pair[:3] + '-' + pair[3:]
            ]
            
            for pattern in patterns:
                if pattern in text:
                    return pair
        
        # Look for other patterns like EUR/USD, GBP/USD etc.
        forex_pattern = r'([A-Z]{3})[\/\-\s]([A-Z]{3})'
        match = re.search(forex_pattern, text)
        if match:
            return match.group(1) + match.group(2)
        
        return None
    
    def _extract_direction(self, text: str) -> Optional[str]:
        """Extract trading direction (BUY/SELL)"""
        for direction, pattern in self.direction_patterns.items():
            if re.search(pattern, text):
                return direction.upper()
        return None
    
    def _extract_entry_price(self, text: str) -> Optional[float]:
        """Extract entry price"""
        # Look for entry keywords followed by price
        entry_pattern = f"{self.trading_keywords['entry']}[:\s]*({self.price_pattern})"
        match = re.search(entry_pattern, text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        
        # If no specific entry keyword, try to find first price after direction
        direction = self._extract_direction(text)
        if direction:
            # Look for price after direction word
            direction_patterns = self.direction_patterns[direction.lower()]
            pattern = f"{direction_patterns}[:\s@]*({self.price_pattern})"
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass
        
        return None
    
    def _extract_stop_loss(self, text: str) -> Optional[float]:
        """Extract stop loss price"""
        sl_pattern = f"{self.trading_keywords['stop_loss']}[:\s]*({self.price_pattern})"
        match = re.search(sl_pattern, text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None
    
    def _extract_take_profit(self, text: str) -> List[float]:
        """Extract take profit prices (can be multiple)"""
        tp_pattern = f"{self.trading_keywords['take_profit']}[:\s]*({self.price_pattern})"
        matches = re.findall(tp_pattern, text)
        
        take_profits = []
        for match in matches:
            try:
                take_profits.append(float(match))
            except ValueError:
                continue
        
        return take_profits
    
    def _extract_timeframe(self, text: str) -> Optional[str]:
        """Extract chart timeframe"""
        timeframe_patterns = [
            r'(\d+)M(?:IN)?',  # 15M, 30MIN
            r'(\d+)H(?:R)?',   # 1H, 4HR
            r'(\d+)D(?:AY)?',  # 1D, 1DAY
            r'(\d+)W(?:EEK)?', # 1W, 1WEEK
            r'M(\d+)',         # M15, M30
            r'H(\d+)',         # H1, H4
            r'D(\d+)',         # D1
        ]
        
        for pattern in timeframe_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        
        return None
    
    def _calculate_risk_reward(self, text: str) -> Optional[str]:
        """Calculate or extract risk-reward ratio"""
        # Look for explicit R:R ratio
        rr_pattern = r'(?:RR|R:R|RATIO)[:\s]*(\d+\.?\d*)[:\s]*(\d+\.?\d*)'
        match = re.search(rr_pattern, text)
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        
        # Try to calculate from entry, SL, TP
        entry = self._extract_entry_price(text)
        stop_loss = self._extract_stop_loss(text)
        take_profits = self._extract_take_profit(text)
        
        if entry and stop_loss and take_profits:
            risk = abs(entry - stop_loss)
            reward = abs(take_profits[0] - entry)
            if risk > 0:
                ratio = reward / risk
                return f"1:{ratio:.1f}"
        
        return None
    
    def _extract_all_prices(self, text: str) -> List[float]:
        """Extract all price-like numbers from text"""
        price_matches = re.findall(self.price_pattern, text)
        prices = []
        
        for match in price_matches:
            try:
                price = float(match)
                # Filter reasonable forex prices (avoid dates, percentages, etc.)
                if 0.01 <= price <= 100000:
                    prices.append(price)
            except ValueError:
                continue
        
        return prices
    
    def _calculate_confidence(self, text: str) -> float:
        """Calculate confidence score for signal validity"""
        score = 0.0
        
        # Has instrument (+20%)
        if self._extract_instrument(text):
            score += 0.2
        
        # Has direction (+20%)
        if self._extract_direction(text):
            score += 0.2
        
        # Has entry price (+20%)
        if self._extract_entry_price(text):
            score += 0.2
        
        # Has stop loss (+20%)
        if self._extract_stop_loss(text):
            score += 0.2
        
        # Has take profit (+20%)
        if self._extract_take_profit(text):
            score += 0.2
        
        return score
    
    def _validate_signal(self, signal: Dict[str, Any]) -> bool:
        """Validate if signal has minimum required information"""
        required_fields = ['instrument', 'direction']
        
        # Check required fields
        for field in required_fields:
            if not signal.get(field):
                return False
        
        # Should have at least entry price OR stop loss OR take profit
        price_fields = ['entry_price', 'stop_loss', 'take_profit']
        has_price = any(signal.get(field) for field in price_fields)
        
        return has_price and signal.get('confidence', 0) >= 0.4
    
    def format_signal_summary(self, signal: Dict[str, Any]) -> str:
        """Format extracted signal into readable summary"""
        if not signal['is_valid_signal']:
            return "❌ Invalid or incomplete trading signal"
        
        summary = f"📈 **{signal['instrument']}** {signal['direction']}"
        
        if signal['entry_price']:
            summary += f"\n💰 Entry: {signal['entry_price']}"
        
        if signal['stop_loss']:
            summary += f"\n🛑 Stop Loss: {signal['stop_loss']}"
        
        if signal['take_profit']:
            if len(signal['take_profit']) == 1:
                summary += f"\n🎯 Take Profit: {signal['take_profit'][0]}"
            else:
                tp_list = ", ".join(map(str, signal['take_profit']))
                summary += f"\n🎯 Take Profits: {tp_list}"
        
        if signal['risk_reward']:
            summary += f"\n📊 Risk/Reward: {signal['risk_reward']}"
        
        if signal['timeframe']:
            summary += f"\n⏰ Timeframe: {signal['timeframe']}"
        
        confidence_percent = int(signal['confidence'] * 100)
        summary += f"\n🎯 Confidence: {confidence_percent}%"
        
        return summary
    
    def extract_chart_annotations(self, text: str) -> Dict[str, Any]:
        """Extract annotations and technical analysis from chart descriptions"""
        annotations = {
            'support_levels': [],
            'resistance_levels': [],
            'trend_lines': [],
            'patterns': [],
            'indicators': []
        }
        
        # Extract support/resistance levels
        support_pattern = r'SUPPORT[:\s]*({self.price_pattern})'
        resistance_pattern = r'RESISTANCE[:\s]*({self.price_pattern})'
        
        support_matches = re.findall(support_pattern, text.upper())
        resistance_matches = re.findall(resistance_pattern, text.upper())
        
        for match in support_matches:
            try:
                annotations['support_levels'].append(float(match))
            except ValueError:
                continue
        
        for match in resistance_matches:
            try:
                annotations['resistance_levels'].append(float(match))
            except ValueError:
                continue
        
        # Extract common patterns
        pattern_keywords = [
            'TRIANGLE', 'WEDGE', 'FLAG', 'PENNANT', 'HEAD AND SHOULDERS',
            'DOUBLE TOP', 'DOUBLE BOTTOM', 'ASCENDING', 'DESCENDING'
        ]
        
        for pattern in pattern_keywords:
            if pattern in text.upper():
                annotations['patterns'].append(pattern)
        
        # Extract indicators
        indicator_keywords = [
            'RSI', 'MACD', 'MA', 'EMA', 'SMA', 'BOLLINGER', 'STOCHASTIC',
            'FIBONACCI', 'PIVOT', 'VOLUME'
        ]
        
        for indicator in indicator_keywords:
            if indicator in text.upper():
                annotations['indicators'].append(indicator)
        
        return annotations
    
    def is_forex_related(self, text: str) -> bool:
        """Check if text contains forex/trading related content"""
        text_upper = text.upper()
        
        # Check for forex pairs
        if self._extract_instrument(text_upper):
            return True
        
        # Check for trading keywords
        trading_words = [
            'BUY', 'SELL', 'LONG', 'SHORT', 'ENTRY', 'EXIT', 'STOP', 'TARGET',
            'PROFIT', 'LOSS', 'PIPS', 'TRADE', 'SIGNAL', 'ANALYSIS', 'CHART',
            'SUPPORT', 'RESISTANCE', 'TREND', 'BREAKOUT', 'REVERSAL'
        ]
        
        for word in trading_words:
            if word in text_upper:
                return True
        
        return False

# Utility functions for easy integration
def extract_quick_signal(text: str) -> Dict[str, Any]:
    """Quick signal extraction for immediate use"""
    parser = TradingSignalParser()
    return parser.extract_trading_signal(text)

def is_trading_message(text: str) -> bool:
    """Quick check if message is trading-related"""
    parser = TradingSignalParser()
    return parser.is_forex_related(text)

def format_trading_notification(text: str) -> str:
    """Quick format for trading notifications"""
    parser = TradingSignalParser()
    signal = parser.extract_trading_signal(text)
    
    if signal['is_valid_signal']:
        return parser.format_signal_summary(signal)
    else:
        return f"📊 Trading message detected:\n{text[:200]}..."

# Test the parser
if __name__ == "__main__":
    # Test cases
    test_messages = [
        "EURUSD BUY at 1.0850, SL: 1.0800, TP: 1.0950",
        "XAUUSD SELL 2650.50, Stop Loss 2665.00, Take Profit 2620.00",
        "GBP/USD LONG from 1.2750, SL 1.2700, TP1 1.2850, TP2 1.2950",
        "Bitcoin BTCUSD short entry 45000, stop 46000, target 42000"
    ]
    
    parser = TradingSignalParser()
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n--- Test {i} ---")
        print(f"Message: {message}")
        
        signal = parser.extract_trading_signal(message)
        print(f"Extracted: {signal}")
        
        summary = parser.format_signal_summary(signal)
        print(f"Summary:\n{summary}")
        print("-" * 50)