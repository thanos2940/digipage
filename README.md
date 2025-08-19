# DigiPage Scanner - Web UI Version

This is a web-based version of the DigiPage Scanner application, designed for efficient post-scan quality control and processing in high-volume book scanning workflows.

The original Tkinter desktop application has been converted to a modern web application with a Python (FastAPI) backend and a JavaScript (vanilla) frontend.

## Architecture

The application is now split into two main components:

1.  **Backend (`/backend`)**: A Python server built with the **FastAPI** framework. It handles all the core logic:
    *   Watching a designated "Scan Folder" for new images.
    *   Serving image files to the frontend.
    *   Providing a REST API for all actions (listing images, getting stats, creating books, transferring books to data folders).
    *   Using a WebSocket to push real-time updates to the frontend when new images are detected.
    *   Reusing the core business logic from the original application for image manipulation, folder management, and statistics.

2.  **Frontend (`/frontend`)**: A single-page web application built with vanilla **HTML, CSS, and JavaScript**.
    *   It provides a dual-pane view for comparing and inspecting scanned pages.
    *   It communicates with the backend API to fetch data and perform actions.
    *   It connects to the WebSocket to receive live updates, automatically showing new scans as they arrive.
    *   It includes controls for navigation, book creation, and transferring completed books.

## How to Run

### 1. Prerequisites

- Python 3.10+
- `pip` for installing packages

### 2. Installation

All necessary Python packages are listed in `backend/requirements.txt`. Install them with the following command:

```bash
pip install -r backend/requirements.txt
```

### 3. Configuration

Before running the application for the first time, you must create a configuration file named `scan_viewer_config.json` in the root directory of the project.

This file tells the application which folders to use. Here is a template:

```json
{
    "scan": "/path/to/your/scan_folder",
    "today": "/path/to/your/todays_books_folder",
    "city_paths": {
        "123": "/path/to/network/storage/for_city_123",
        "456": "/path/to/network/storage/for_city_456"
    },
    "image_load_timeout_ms": 2000
}
```

**IMPORTANT:**
- Replace the example paths with the **absolute paths** to your actual folders.
- The keys under `city_paths` are the 3-digit city codes that the application will look for in book folder names when transferring.

### 4. Running the Application

Once the dependencies are installed and the configuration is set up, you can start the application by running the `main.py` script:

```bash
python main.py
```

This will start the backend server. You can then access the user interface by opening your web browser and navigating to:

**http://127.0.0.1:8000**

The application will automatically try to open a new tab in your default browser when it starts. To stop the server, press `Ctrl+C` in the terminal where you ran the command.
