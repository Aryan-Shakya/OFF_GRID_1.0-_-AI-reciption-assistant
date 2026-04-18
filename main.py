import os
import sys
import json
import asyncio
import logging
import argparse
from crawler import CrawlerEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler("error.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def load_config(config_path="config.json"):
    if not os.path.exists(config_path):
        logger.warning(f"Config file {config_path} not found. Using defaults.")
        return {}
    with open(config_path, "r") as f:
        return json.load(f)

async def main():
    parser = argparse.ArgumentParser(description="AI-Powered Web Crawler System")
    parser.add_argument("url", help="The base URL website to crawl")
    parser.add_argument("--config", default="config.json", help="Path to config JSON file")
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    crawler = CrawlerEngine(config)
    
    try:
        await crawler.crawl(args.url)
    except KeyboardInterrupt:
        logger.info("Crawling interrupted by user. Shutting down gracefully...")

if __name__ == "__main__":
    asyncio.run(main())
