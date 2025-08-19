import uvicorn
import os
import webbrowser
import threading
import time

def open_browser():
    """
    Opens the web browser to the application's URL after a short delay.
    """
    time.sleep(2) # Give the server a moment to start
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == '__main__':
    print("--- DigiPage Scanner Web UI ---")
    print("\nStarting the backend server...")
    print("The application will be available at: http://127.0.0.1:8000\n")

    # The original request included using python-webview to create a desktop-like
    # application. However, due to issues with installing the necessary GUI
    # dependencies in the current environment, this has been implemented as a
    # standard web application.

    # To run the application, simply execute this script. It will start the
    # backend server. You can then open your web browser and navigate to
    # http://127.0.0.1:8000 to use the application.

    # For convenience, this script can attempt to open your web browser automatically.
    if os.environ.get("DISPLAY"): # Check if a display is available
        threading.Thread(target=open_browser, daemon=True).start()

    # Start the FastAPI server
    # The server will be run in the main thread. To stop it, press Ctrl+C.
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, log_level="info", reload=False)
