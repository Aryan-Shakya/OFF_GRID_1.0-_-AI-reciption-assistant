import asyncio
import logging
from urllib.parse import urlparse
from collections import deque
import time
from typing import Callable, Coroutine, Any, List

from fetcher import Fetcher
from extractor import Extractor
from storage import StorageManager

logger = logging.getLogger(__name__)

class CrawlerEngine:
    def __init__(self, config: dict, on_fact: Callable[[Any], Coroutine[Any, Any, None]] = None):
        self.config = config
        self.max_depth = config.get("max_depth", 3)
        self.max_pages = config.get("max_pages", 100)
        self.delay = config.get("delay_between_requests", 1.0)
        self.output_dir = config.get("output_directory", "data")
        self.concurrency = config.get("concurrent_requests", 5)
        self.user_agent = config.get("user_agent", None)

        self.storage = StorageManager(self.output_dir)
        self.extractor = Extractor(config)
        
        # Callback for real-time progress/fact stream
        self.on_fact = on_fact
        
        self.visited = set()
        self.crawled_count = 0
        self.base_domain = None

        # To manage concurrency limits properly
        self.semaphore = asyncio.Semaphore(self.concurrency)

    async def _crawl_worker(self, fetcher: Fetcher, queue: asyncio.Queue):
        while True:
            try:
                current_url, current_depth = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            if current_url in self.visited or self.crawled_count >= self.max_pages:
                queue.task_done()
                continue
                
            self.visited.add(current_url)

            # Limit concurrency and rate
            async with self.semaphore:
                if self.delay > 0:
                    await asyncio.sleep(self.delay)
                    
                logger.info(f"Crawling: {current_url} (depth={current_depth})")
                try:
                    html = None
                    for attempt in range(3):
                        try:
                            html = await fetcher.fetch(current_url)
                            break
                        except Exception as e:
                            if attempt == 2:
                                logger.error(f"Failed to fetch {current_url} after 3 attempts")
                            else:
                                await asyncio.sleep(2)

                    if html:
                        self.crawled_count += 1
                        
                        # Extract atomic facts
                        extracted_data = self.extractor.extract(current_url, html)
                        facts = extracted_data.get("facts", [])
                        
                        # Save
                        self.storage.save_page(current_url, extracted_data)
                        logger.info(f"Saved: {current_url} with {len(facts)} facts")

                        # Trigger real-time callback
                        if self.on_fact:
                            await self.on_fact({
                                "url": current_url,
                                "crawled_count": self.crawled_count,
                                "facts": facts,
                                "status": "running"
                            })

                        # Enqueue new internal links if within depth
                        links = self._extract_internal_links(current_url, html)
                        if current_depth < self.max_depth:
                            for link in links:
                                if link not in self.visited:
                                    await queue.put((link, current_depth + 1))
                                    
                except Exception as e:
                    logger.error(f"Error processing {current_url}: {e}")
                    
                finally:
                    queue.task_done()

    def _extract_internal_links(self, url: str, html: str) -> List[str]:
        # Simple helper since the extractor now focuses on facts
        from urllib.parse import urljoin, urlparse
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        base_domain = urlparse(url).netloc
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip().split('#')[0]
            absolute_url = urljoin(url, href)
            if urlparse(absolute_url).netloc == base_domain and absolute_url.startswith("http"):
                if absolute_url not in links:
                    links.append(absolute_url)
        return links

    async def crawl(self, start_url: str):
        parsed_start = urlparse(start_url)
        self.base_domain = parsed_start.netloc
        if not self.base_domain:
            raise ValueError("Invalid start URL")

        queue = asyncio.Queue()
        await queue.put((start_url, 0))

        fetcher = Fetcher(user_agent=self.user_agent)
        logger.info(f"Starting crawl for {start_url}")
        
        try:
            await fetcher.start()
            workers = []
            for _ in range(self.concurrency):
                task = asyncio.create_task(self._crawl_worker(fetcher, queue))
                workers.append(task)
                
            await queue.join()
            for w in workers:
                w.cancel()
                
            if self.on_fact:
                await self.on_fact({"status": "completed", "crawled_count": self.crawled_count})
                
            logger.info(f"Crawl completed. Total pages processed: {self.crawled_count}")
        finally:
            await fetcher.stop()
