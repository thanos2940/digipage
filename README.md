DigiPage Scanner: Technical Documentation & Workflow
====================================================

1\. Primary Goal & Design Philosophy
------------------------------------

The **DigiPage Scanner** is a specialized desktop application built with Python and Tkinter, designed to solve a critical bottleneck in high-volume book scanning workflows: **post-scan quality control and processing**.

The core design philosophy is to create an efficient, operator-focused environment that minimizes manual steps and maximizes visual feedback. The main point of the program is to provide an **oversized, dual-pane view of scanned pages**, allowing the operator to inspect and edit them on the fly before they are grouped into books and archived. This prevents errors from propagating downstream and eliminates the need for a separate, time-consuming quality control step after the scanning is complete.

2\. Core Workflow
-----------------

The application guides the user through a clear, linear process:

1.  **Configuration:** On first launch, the operator defines the key folders for the workflow: a **Scan Folder** to be monitored, and a **Today's Books Folder** to serve as a temporary staging area. Crucially, they also map 3-digit **City Codes** to their final network storage paths (e.g., Code 297 -> \\\\server\\data\\Α ΚΟΡΙΝΘΟΥ).
    
2.  **Live Scanning & Viewing:** The operator starts scanning. The application's file watcher immediately detects new images in the Scan Folder and displays them in the dual-pane viewer, automatically advancing to the latest pair.
    
3.  **On-the-Fly Editing:** The operator inspects the two large images. Using the dedicated toolset under each image, they can instantly correct rotation, crop unwanted edges, or adjust brightness/contrast. These edits are destructive and save directly to the image file, ensuring the corrections are permanent.
    
4.  **Book Assembly:** Once all pages for a book are scanned and corrected, the operator enters the book's name (often from a QR code) and clicks "Create." The application gathers all loose image files from the Scan Folder and moves them into a new, named subfolder within the "Today's Books" staging area.
    
5.  **Automated Archival:** At any time, the operator can click "Transfer to Data." The application processes all folders in the staging area. For each book, it:
    
    *   Parses the folder name to find the 3-digit city code.
        
    *   Finds the corresponding destination path from the settings.
        
    *   Creates a subfolder with the current date (e.g., DD-MM) if it doesn't exist.
        
    *   Moves the book folder into this dated directory.
        
    *   Records the entire transaction (book name, page count, final path, timestamp) in books\_complete\_log.json.
        

3\. Feature Breakdown & Implementation Choices
----------------------------------------------

### Class: ImageScannerApp

This is the main class that orchestrates the entire application.

*   **UI Management:** It sets up the main window, including the central image display area, the right-hand sidebar for stats and controls, and the bottom control bar for navigation.
    
*   **Workflow Logic:** It contains the methods for create\_new\_book(), transfer\_to\_data(), and navigation (next\_pair, prev\_pair).
    
*   **Threading & Queues:** To prevent the UI from freezing during file I/O (which can be slow, especially over a network), all significant file operations (moving, deleting, saving) are offloaded to a background thread (\_transfer\_operation\_worker). Communication between the main UI thread and the worker thread is handled safely using queue.Queue. A ScanWorker thread is also used to handle background stat calculations without impacting UI performance.
    
*   **Performance Tracking:**
    
    *   **Live Performance:** A collections.deque (scan\_timestamps) is used to store the timestamps of the last few scans. A recurring function (update\_stats) prunes timestamps older than 20 seconds and calculates the pages/minute based on the remaining count. A deque was chosen for its efficiency in adding and removing items from both ends.
        
    *   **Total Performance:** The total page count for the day is calculated by the ScanWorker thread, which sums the pages in the scan folder, the pages in the "Today's Books" folder, and the pages recorded in the books\_complete\_log.json for the current date. This provides a comprehensive view of the day's total output.
        

### Class: ZoomPanCanvas

This custom Tkinter Canvas is the heart of the application's viewing and editing experience.

*   **Image Display:** It handles loading images from disk (using Pillow/PIL), calculating the correct aspect ratio to fit them within the canvas, and displaying them. An image cache (self.app\_ref.image\_cache) is used to keep recently viewed images in memory for faster navigation.
    
*   **On-the-Fly Editing Implementation:**
    
    *   **Rotation & Color:** These edits are applied to the in-memory Pillow image object. When the user saves (e.g., by releasing the rotation slider or clicking "Save" for color), the save\_image\_to\_disk method is called, which overwrites the original file. A backup of the original is created on the first edit to allow for restoration.
        
    *   **Cropping:** The crop box is a visual overlay drawn on the canvas. When the user initiates a crop, the coordinates of the drawn rectangle are translated into pixel coordinates on the original image, and the Pillow crop() method is used to create the new, smaller image, which then overwrites the original file.
        
*   **Zoom & Pan:** The class includes basic functionality to zoom into an image and pan around, which is essential for close inspection of scan quality.
    

### Class: ScanWorker

A dedicated background thread to handle potentially slow calculations.

*   **Decoupling:** Its primary purpose is to decouple statistics calculation from the main UI thread. It receives commands via a queue (scan\_worker\_command\_queue) and puts results back on another queue (scan\_worker\_result\_queue).
    
*   **Log File Reading:** The logic for reading the books\_complete\_log.json and summing the pages for the current day resides here. This ensures that even a very large log file will not cause the UI to stutter.
    

### Class: SettingsFrame

The initial configuration screen.

*   **Configuration Persistence:** It saves all user-defined paths and settings into a simple scan\_viewer\_config.json file. This makes the application portable and easy to set up on different workstations.
    
*   **City Code Management:** Provides a simple UI for adding, viewing, and removing city code-to-path mappings, which are the core of the automated archival feature.
    
*   **Log File Management:** Includes a "Clear Log File" button. This was added to allow for a clean start or to clear out test data. The action requires user confirmation to prevent accidental data loss.
    

### File Watcher (NewImageHandler & watchdog)

*   **Event-Driven Approach:** The watchdog library is used to monitor the scan folder. This is far more efficient than constantly polling the directory for changes. When watchdog detects a file creation event, it triggers the add\_new\_image method in the main app, which adds the file to the queue and updates the display.
