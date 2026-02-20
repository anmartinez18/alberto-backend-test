from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum
import httpx
import uuid
import asyncio

app = FastAPI(title="Notification Service (Technical Test)")

class Status(str, Enum):
    queued = "queued"
    processing = "processing"
    sent = "sent"
    failed = "failed"
    
class NotificationRequest(BaseModel):
    to: str
    message: str
    type: Literal["email", "sms", "push"]
    status: Status | None = None

requests_db: dict[str, dict] = {}
request_lock = asyncio.Lock()
    
PROVIDER_URL = "http://localhost:3001"
X_API_KEY = "test-dev-2026"
MAX_CONCURRENT_REQUESTS = 50
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


@app.post("/v1/requests", status_code = 201)
async def register_request(request: NotificationRequest):
    async with request_lock:
        request_id = str(uuid.uuid4())
        requests_db[request_id] = {
            "to": request.to,
            "message": request.message,
            "type": request.type,
            "status": Status.queued.value
        }
        
        return { "id" : request_id }



async def send_request(id):
    
    async with semaphore:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                        f"{PROVIDER_URL}/v1/notify", 
                        json=requests_db[id], 
                        headers={ "X-API-Key": X_API_KEY }
                    )
            
                async with request_lock:
                    if response.status_code == 200:
                        requests_db[id]["status"] = Status.sent.value
                    else:
                        requests_db[id]["status"] = Status.failed.value
                        
        except Exception as e:
            async with request_lock:
                requests_db[id]["status"] = Status.failed.value
            print(f"Error for id: {id}: {e}")
                    


@app.post("/v1/requests/{id}/process", status_code = 202)
async def process_request(id: str, background_tasks: BackgroundTasks):
    async with request_lock:
        if id not in requests_db:
            raise HTTPException(status_code=404, detail="Request ID not found")
        
        requests_db[id]["status"] = Status.processing.value

    background_tasks.add_task(send_request, id)

    
    
@app.get("/v1/requests/{id}", status_code = 200)
async def get_status(id: str):
    async with request_lock:
        if id not in requests_db:
            raise HTTPException(status_code=404, detail="Request ID not found")
        
        return {"id": id, "status": requests_db[id]["status"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
