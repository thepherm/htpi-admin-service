"""NATS communication service"""

import json
import logging
from typing import Dict, Any, Optional, Callable
import nats
from nats.errors import TimeoutError as NatsTimeoutError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class NATSService:
    """Handle NATS messaging"""
    
    def __init__(self):
        self.nc = None
        self.js = None
        
    async def connect(self):
        """Connect to NATS server"""
        try:
            self.nc = await nats.connect(
                servers=settings.NATS_URL,
                user=settings.NATS_USER,
                password=settings.NATS_PASSWORD,
                name=settings.SERVICE_NAME
            )
            self.js = self.nc.jetstream()
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
            
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise
            
    async def disconnect(self):
        """Disconnect from NATS"""
        if self.nc:
            await self.nc.close()
            logger.info("Disconnected from NATS")
            
    async def publish(self, subject: str, data: Dict[str, Any]):
        """Publish message to NATS"""
        try:
            message = json.dumps(data).encode()
            await self.nc.publish(subject, message)
            logger.debug(f"Published to {subject}: {data}")
            
        except Exception as e:
            logger.error(f"Failed to publish to {subject}: {e}")
            raise
            
    async def request(self, subject: str, data: Dict[str, Any], timeout: float = 5.0) -> Dict[str, Any]:
        """Send request and wait for response"""
        try:
            message = json.dumps(data).encode()
            response = await self.nc.request(subject, message, timeout=timeout)
            return json.loads(response.data.decode())
            
        except NatsTimeoutError:
            logger.error(f"Request timeout for {subject}")
            return {
                'success': False,
                'error': {
                    'code': 'TIMEOUT',
                    'message': 'Request timed out'
                }
            }
        except Exception as e:
            logger.error(f"Request failed for {subject}: {e}")
            return {
                'success': False,
                'error': {
                    'code': 'REQUEST_FAILED',
                    'message': str(e)
                }
            }
            
    async def subscribe(self, subject: str, handler: Callable):
        """Subscribe to a subject"""
        try:
            async def message_handler(msg):
                try:
                    data = json.loads(msg.data.decode())
                    await handler(data, msg)
                except Exception as e:
                    logger.error(f"Error in message handler for {subject}: {e}")
                    
            await self.nc.subscribe(subject, cb=message_handler)
            logger.info(f"Subscribed to {subject}")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {subject}: {e}")
            raise
            
    def is_connected(self) -> bool:
        """Check if connected to NATS"""
        return self.nc is not None and self.nc.is_connected