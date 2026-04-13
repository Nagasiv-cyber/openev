"""
Bloomberg Infrastructure Adapter
Provides an institutional-grade abstraction layer over the official `blpapi` Python SDK.
Connects directly to Bloomberg Server API (B-PIPE) or Desktop API (DAPI).
Falls back to deterministic models if running in a disconnected simulation environment.
"""

import logging
import threading
import time
from typing import Dict, Optional, Callable, Any

logger = logging.getLogger("BloombergAdapter")

# Try to import blpapi gracefully
BLPAPI_AVAILABLE = False
try:
    import blpapi
    BLPAPI_AVAILABLE = True
except ImportError:
    logger.warning("blpapi not installed. Running in Disconnected (Mock) Mode. "
                   "Install using the official Bloomberg pip repository to enable real-time institutional feeds.")


class BloombergSessionManager:
    """Manages the underlying connection session to Bloomberg B-PIPE or DAPI."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(BloombergSessionManager, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self, host: str = "localhost", port: int = 8194):
        if self._initialized:
            return
            
        self.host = host
        self.port = port
        self.session = None
        self.connected = False
        
        if BLPAPI_AVAILABLE:
            self._connect()
        else:
            logger.info("BLPAPI not available - Bypassing Session Initiation.")
            
        self._initialized = True
            
    def _connect(self):
        try:
            sessionOptions = blpapi.SessionOptions()
            sessionOptions.setServerHost(self.host)
            sessionOptions.setServerPort(self.port)
            
            self.session = blpapi.Session(sessionOptions)
            if not self.session.start():
                logger.error(f"Failed to start Bloomberg Session on {self.host}:{self.port}")
                return
                
            self.connected = True
            logger.info("Successfully connected to Bloomberg API infrastructure.")
        except Exception as e:
            logger.error(f"Bloomberg connection error: {e}")
            self.connected = False

    def is_connected(self) -> bool:
        return self.connected


class BloombergPricingFeed:
    """Streams live Level 1 pricing (Bid, Ask, Size) using the //blp/mktdata service."""
    
    def __init__(self):
        self.manager = BloombergSessionManager()
        self.subscriptions = []
        
        if self.manager.is_connected():
            self._open_service()
            
    def _open_service(self):
        try:
            if not self.manager.session.openService("//blp/mktdata"):
                logger.error("Failed to open //blp/mktdata service")
        except Exception as e:
            logger.error(f"Service open error: {e}")

    def subscribe(self, ticker: str, callback: Callable):
        """Subscribe to a ticker (e.g., 'BTCUSD Curncy') and pass events to a callback."""
        if not self.manager.is_connected():
            # Disconnected mode: We just pretend to subscribe.
            return
            
        try:
            # Topic: e.g., //blp/mktdata/ticker
            topic = f"//blp/mktdata/{ticker}"
            subscriptions = blpapi.SubscriptionList()
            subscriptions.add(topic, "BID,ASK,BID_SIZE,ASK_SIZE", "", blpapi.CorrelationId(ticker))
            
            self.manager.session.subscribe(subscriptions)
            
            # Start a background listener thread to consume events for this specific subscription
            # Note: In production, you would run a single central Event Queue consumer.
            self.subscriptions.append((ticker, callback))
            self._start_event_listener(callback)
            logger.info(f"Subscribed to Bloomberg feed: {ticker}")
        except Exception as e:
            logger.error(f"Failed to subscribe to {ticker}: {e}")

    def _start_event_listener(self, callback: Callable):
        def listener():
            while self.manager.is_connected():
                try:
                    event = self.manager.session.nextEvent(500)
                    for msg in event:
                        if event.eventType() == blpapi.Event.SUBSCRIPTION_DATA:
                            if msg.hasElement("BID") and msg.hasElement("ASK"):
                                data = {
                                    "bid": msg.getElementAsFloat("BID"),
                                    "ask": msg.getElementAsFloat("ASK"),
                                    "bid_size": msg.getElementAsFloat("BID_SIZE") if msg.hasElement("BID_SIZE") else 1.0,
                                    "ask_size": msg.getElementAsFloat("ASK_SIZE") if msg.hasElement("ASK_SIZE") else 1.0,
                                }
                                callback(data)
                except Exception as e:
                    logger.debug(f"Event parsing error: {e}")
                    pass
                    
        t = threading.Thread(target=listener, daemon=True)
        t.start()


class BloombergAltDataFeed:
    """Fetches non-pricing indicators using the //blp/refdata service."""
    
    def __init__(self):
        self.manager = BloombergSessionManager()
        if self.manager.is_connected():
            self._open_service()
            
    def _open_service(self):
        try:
            if not self.manager.session.openService("//blp/refdata"):
                logger.error("Failed to open //blp/refdata service")
        except Exception as e:
            logger.error(f"Service open error: {e}")

    def get_reference_data(self, security: str, field: str) -> Optional[float]:
        """Synchronously request a specific macroeconomic or sentiment indicator."""
        if not self.manager.is_connected():
            return None
            
        try:
            refDataService = self.manager.session.getService("//blp/refdata")
            request = refDataService.createRequest("ReferenceDataRequest")
            request.getElement("securities").appendValue(security)
            request.getElement("fields").appendValue(field)
            
            cid = self.manager.session.sendRequest(request)
            
            # Simplified synchronous wait for response
            while True:
                event = self.manager.session.nextEvent(500)
                if event.eventType() == blpapi.Event.RESPONSE or event.eventType() == blpapi.Event.PARTIAL_RESPONSE:
                    for msg in event:
                        if msg.correlationIds()[0].value() == cid.value():
                            securityDataArray = msg.getElement("securityData")
                            for i in range(securityDataArray.numValues()):
                                securityData = securityDataArray.getValueAsElement(i)
                                fieldData = securityData.getElement("fieldData")
                                if fieldData.hasElement(field):
                                    return fieldData.getElementAsFloat(field)
                if event.eventType() == blpapi.Event.RESPONSE:
                    break
        except Exception as e:
            logger.error(f"Error fetching ref data {security} {field}: {e}")
            
        return None
