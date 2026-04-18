import os
import json
from urllib.parse import urlparse
import time
from typing import List, Dict, Any

class StorageManager:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.index_file = os.path.join(self.output_dir, "index.json")
        self.kb_file = os.path.join(self.output_dir, "knowledge_base.json")
        self.domain_dirs = {}
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
            
        self.index = self._load_json(self.index_file, {"urls": {}, "total_pages": 0})
        self.knowledge_base = self._load_json(self.kb_file, [])

    def _load_json(self, file_path: str, default: Any) -> Any:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return default
        return default

    def _save_json(self, file_path: str, data: Any):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _get_domain_dir(self, url: str) -> str:
        parsed = urlparse(url)
        domain = parsed.netloc.replace(":", "_")
        if not domain:
            domain = "unknown_domain"
            
        if domain not in self.domain_dirs:
            domain_path = os.path.join(self.output_dir, domain)
            os.makedirs(domain_path, exist_ok=True)
            self.domain_dirs[domain] = domain_path
            
        return self.domain_dirs[domain]

    def save_facts(self, facts: List[Dict[str, str]]):
        """Appends new facts to the consolidated knowledge base."""
        if not facts:
            return
            
        # The user wants to KEEP ALL VARIATIONS, so we just extend
        # We start IDs from the current length + 1 to keep them clean and sequential if possible
        start_id = len(self.knowledge_base) + 1
        for i, fact in enumerate(facts):
            fact["id"] = str(start_id + i)
            self.knowledge_base.append(fact)
            
        self._save_json(self.kb_file, self.knowledge_base)

    def save_page(self, url: str, data: dict):
        """Saves a page-centric JSON and updates its facts in the KB."""
        domain_path = self._get_domain_dir(url)
        
        # Save page-specific data for debugging/history
        if url in self.index["urls"]:
            page_id = self.index["urls"][url]["page_id"]
        else:
            self.index["total_pages"] += 1
            page_id = f"page_{self.index['total_pages']}"
            
        file_path = os.path.join(domain_path, f"{page_id}.json")
        self._save_json(file_path, data)
        
        # Extract facts if available in the data dictionary
        if "facts" in data:
            self.save_facts(data["facts"])
            
        # Update index
        self.index["urls"][url] = {
            "page_id": page_id,
            "filepath": file_path,
            "title": data.get("title", ""),
            "crawled_at": time.time()
        }
        self._save_json(self.index_file, self.index)
        return file_path
