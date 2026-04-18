import asyncio
from playwright.async_api import async_playwright
import logging

logger = logging.getLogger(__name__)

class Fetcher:
    def __init__(self, user_agent: str = None):
        self.user_agent = user_agent
        self.playwright = None
        self.browser = None
        self.context = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(
            user_agent=self.user_agent,
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True
        )

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def fetch(self, url: str) -> str:
        if not self.context:
            await self.start()
        
        page = None
        try:
            page = await self.context.new_page()
            # Set a timeout for navigation (30s)
            response = await page.goto(url, wait_until="networkidle", timeout=30000)
            
            if response is None:
                raise Exception(f"Failed to get response for {url}")
                
            if response.status >= 400:
                raise Exception(f"HTTP Error {response.status} for {url}")

            # Optionally wait for some generic dynamic content to load if needed
            # await page.wait_for_timeout(1000)
            
            html = await page.content()
            return html
            
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
        finally:
            if page:
                await page.close()
