from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import uuid
import asyncio
import json
from typing import List

import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from crawler import CrawlerEngine
from main import load_config

app = FastAPI()

# Make sure public directory exists
os.makedirs("public", exist_ok=True)
os.makedirs("data", exist_ok=True)

# Mount the static directory
app.mount("/static", StaticFiles(directory="public"), name="static")

class CrawlRequest(BaseModel):
    url: str
    use_ai: bool = False
    api_key: str = None

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Handle stale connections
                continue

manager = ConnectionManager()
tasks = {}

@app.get("/")
async def root():
    return FileResponse("public/index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Just keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/crawl")
async def start_crawl(req: CrawlRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    config = load_config("config.json")
    
    # Override config with request settings if provided
    config["use_ai"] = req.use_ai
    config["gemini_api_key"] = req.api_key

    # WebSocket callback for real-time fact stream
    async def on_fact_callback(data: dict):
        await manager.broadcast({
            "task_id": task_id,
            "type": "fact_discovery" if "facts" in data else "progress",
            **data
        })

    crawler = CrawlerEngine(config, on_fact=on_fact_callback)
    
    tasks[task_id] = {
        "status": "running",
        "crawler": crawler,
        "url": req.url,
        "error": None
    }
    
    async def run_crawler():
        try:
            await crawler.crawl(req.url)
            tasks[task_id]["status"] = "completed"
        except Exception as e:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["error"] = str(e)
            await manager.broadcast({
                "task_id": task_id,
                "type": "error",
                "error": str(e)
            })

    background_tasks.add_task(run_crawler)
    
    return {"task_id": task_id, "message": "Intelligence gathering started"}

@app.get("/api/download")
async def download_kb():
    kb_path = "data/knowledge_base.json"
    if not os.path.exists(kb_path):
        # Return empty list if no KB exists yet
        return []
    return FileResponse(kb_path, media_type="application/json", filename="compiled_knowledge.json")

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
        
    task = tasks[task_id]
    crawler = task["crawler"]
    
    return {
        "task_id": task_id,
        "status": task["status"],
        "url": task["url"],
        "error": task["error"],
        "crawled_count": getattr(crawler, 'crawled_count', 0),
        "max_pages": getattr(crawler, 'max_pages', 0)
    }
