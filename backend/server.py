from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel
import os
import asyncio
from . import logic

# --- Pydantic Models for API requests ---
class EditPayload(BaseModel):
    rotation: float | None = None
    brightness: float | None = None
    contrast: float | None = None
    crop: tuple[int, int, int, int] | None = None

class BookPayload(BaseModel):
    book_name: str

class SettingsPayload(BaseModel):
    scan: str
    today: str
    city_paths: dict[str, str]

# --- FastAPI App Setup ---
app = FastAPI()

# --- WebSocket Management ---
connected_clients = set()

async def broadcast_new_image(image_name: str | None):
    """Broadcasts a message to all connected WebSocket clients."""
    # Using a list comprehension to avoid issues with modifying the set while iterating
    for websocket in list(connected_clients):
        try:
            if image_name:
                await websocket.send_json({"type": "new_image", "path": image_name})
            else: # Send a refresh signal on deletion
                await websocket.send_json({"type": "refresh"})
        except WebSocketDisconnect:
            connected_clients.remove(websocket)
        except Exception as e:
            print(f"Error broadcasting to client: {e}")
            connected_clients.remove(websocket)


# --- Application Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    """On startup, load settings and start the file watcher."""
    print("Server starting up...")
    loop = asyncio.get_running_loop()
    logic.load_settings()
    logic.start_watcher(loop, broadcast_new_image)
    # Serve static files from the frontend directory
    # This needs to be done after settings are loaded to know where the scan dir is
    if logic.scan_directory and os.path.isdir(logic.scan_directory):
        app.mount("/images", StaticFiles(directory=logic.scan_directory), name="images")

    # Mount the main frontend directory
    app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.on_event("shutdown")
def shutdown_event():
    """On shutdown, stop the file watcher."""
    print("Server shutting down...")
    logic.stop_watcher()

# --- API Endpoints ---

@app.get("/")
async def read_root():
    """Serve the main frontend HTML file."""
    return FileResponse('frontend/index.html')

@app.get("/api/config")
async def get_config():
    """Get the current application settings."""
    settings = logic.load_settings()
    if not settings:
        raise HTTPException(status_code=404, detail="Config file not found. Please configure the application.")
    return settings

@app.post("/api/config")
async def set_config(settings: SettingsPayload):
    """Save application settings."""
    logic.save_settings(settings.dict())
    # Remount the static directory for images in case it changed
    if logic.scan_directory and os.path.isdir(logic.scan_directory):
         # The name 'images' must be unique. We can't remount.
         # A server restart would be required to change the scan directory.
         # For now, we assume it's set once.
         pass
    return {"status": "success", "message": "Settings saved. A server restart may be required for all changes to take effect."}

@app.get("/api/images")
async def get_images():
    """Get the list of image files in the scan directory."""
    images = logic.get_image_files()
    # Return only the basenames, as the frontend will request them via /images/{basename}
    return {"images": [os.path.basename(p) for p in images]}

@app.get("/api/stats")
async def get_stats():
    """Get performance and folder statistics."""
    return logic.get_stats()

@app.post("/api/books")
async def create_book(payload: BookPayload):
    """Create a new book folder."""
    result = logic.create_new_book(payload.book_name)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/api/transfer")
async def transfer_books():
    """Transfer completed books to data folders."""
    result = logic.transfer_to_data()
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/api/image/{image_name}/edit")
async def edit_image(image_name: str, edits: EditPayload):
    """Apply edits to an image."""
    image_path = os.path.join(logic.scan_directory, image_name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")

    result = logic.apply_edits(image_path, edits.dict(exclude_none=True))
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    return result

# --- WebSocket Endpoint ---
@app.websocket("/ws/new-images")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint for clients to receive real-time updates."""
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"Client connected. Total clients: {len(connected_clients)}")
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"Client disconnected. Total clients: {len(connected_clients)}")
    except Exception as e:
        print(f"WebSocket Error: {e}")
        if websocket in connected_clients:
            connected_clients.remove(websocket)
