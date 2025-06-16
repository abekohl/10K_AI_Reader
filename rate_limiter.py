import time
import threading
from collections import deque
from typing import Optional
import logging

class SECRateLimiter:
    def __init__(self, requests_per_second: int = 10):
        self.requests_per_second = requests_per_second
        self.tokens = deque(maxlen=requests_per_second)
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def wait_for_token(self) -> None:
        """
        Wait until a token is available, ensuring we don't exceed the rate limit.
        Uses a sliding window approach to track requests.
        """
        with self.lock:
            current_time = time.time()
            
            # Remove tokens older than 1 second
            while self.tokens and current_time - self.tokens[0] >= 1.0:
                self.tokens.popleft()
            
            # If we have 10 tokens in the last second, we need to wait
            if len(self.tokens) >= self.requests_per_second:
                # Calculate how long to wait
                wait_time = 1.0 - (current_time - self.tokens[0])
                if wait_time > 0:
                    self.logger.debug(f"Rate limit reached, waiting {wait_time:.3f} seconds")
                    time.sleep(wait_time)
                    # Update current time after sleep
                    current_time = time.time()
                    # Clean up old tokens again after waiting
                    while self.tokens and current_time - self.tokens[0] >= 1.0:
                        self.tokens.popleft()
            
            # Add current request timestamp
            self.tokens.append(current_time)

# Create a global instance
sec_rate_limiter = SECRateLimiter() 