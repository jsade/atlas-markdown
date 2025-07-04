"""
Browser cleanup utilities to ensure all Chrome processes are terminated
"""

import asyncio
import atexit
import logging
import signal
import sys
from typing import Any
from weakref import WeakSet

from playwright.async_api import Browser, Playwright

logger = logging.getLogger(__name__)


class BrowserCleanupRegistry:
    """Registry to track and cleanup all browser instances"""

    def __init__(self) -> None:
        self._browsers: WeakSet[Browser] = WeakSet()
        self._playwrights: WeakSet[Playwright] = WeakSet()
        self._cleanup_done = False
        self._original_handlers: dict[int, Any] = {}

        # Register cleanup handlers
        self._register_cleanup_handlers()

    def _register_cleanup_handlers(self) -> None:
        """Register signal handlers and exit hooks"""
        # Register atexit handler
        atexit.register(self._sync_cleanup)

        # Register signal handlers for graceful shutdown
        for sig in [signal.SIGINT, signal.SIGTERM]:
            self._original_handlers[sig] = signal.signal(sig, self._signal_handler)

    def register_browser(self, browser: Browser) -> None:
        """Register a browser instance for cleanup"""
        self._browsers.add(browser)
        logger.debug(f"Registered browser for cleanup: {browser}")

    def register_playwright(self, playwright: Playwright) -> None:
        """Register a playwright instance for cleanup"""
        self._playwrights.add(playwright)
        logger.debug(f"Registered playwright for cleanup: {playwright}")

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating cleanup...")
        self._sync_cleanup()

        # Call original handler if it exists
        original_handler = self._original_handlers.get(signum)
        if original_handler and callable(original_handler):
            original_handler(signum, frame)
        else:
            # Default behavior - exit
            sys.exit(128 + signum)

    def _sync_cleanup(self) -> None:
        """Synchronous cleanup wrapper"""
        if self._cleanup_done:
            return

        try:
            # Get the event loop or create a new one
            try:
                loop = asyncio.get_running_loop()
                # If we're in an async context, schedule cleanup
                loop.create_task(self.cleanup())
            except RuntimeError:
                # No running loop, create one for cleanup
                asyncio.run(self.cleanup())
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        finally:
            self._cleanup_done = True

    async def cleanup(self) -> None:
        """Clean up all registered browsers and playwright instances"""
        logger.info("Starting browser cleanup...")

        # Close all browsers
        for browser in list(self._browsers):
            try:
                if not browser.is_connected():
                    continue
                logger.debug(f"Closing browser: {browser}")
                await browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

        # Stop all playwright instances
        for playwright in list(self._playwrights):
            try:
                logger.debug(f"Stopping playwright: {playwright}")
                await playwright.stop()
            except Exception as e:
                logger.error(f"Error stopping playwright: {e}")

        logger.info("Browser cleanup completed")

    def unregister_handlers(self) -> None:
        """Restore original signal handlers"""
        for sig, handler in self._original_handlers.items():
            if handler is not None:
                signal.signal(sig, handler)


# Global registry instance
_cleanup_registry = BrowserCleanupRegistry()


def register_browser(browser: Browser) -> None:
    """Register a browser instance for cleanup"""
    _cleanup_registry.register_browser(browser)


def register_playwright(playwright: Playwright) -> None:
    """Register a playwright instance for cleanup"""
    _cleanup_registry.register_playwright(playwright)


async def cleanup_all_browsers() -> None:
    """Manually trigger cleanup of all browsers"""
    await _cleanup_registry.cleanup()
