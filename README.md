DigiPage Scanner: High-Volume Scanning Assistant
================================================

1\. Primary Goal & Design Philosophy
------------------------------------

The **DigiPage Scanner** is a specialized desktop application designed to streamline high-volume book and document digitalization workflows. Its primary purpose is to solve a critical bottleneck: **immediate post-scan quality control and processing**.

The application is built around an efficient, operator-focused environment that minimizes manual steps and maximizes visual feedback. The core of the program is an **oversized, dual-pane viewer** that instantly displays newly scanned pages. This allows the operator to inspect, edit, and correct images on the fly, preventing errors from propagating downstream and eliminating the need for a separate, time-consuming quality control stage after all scanning is complete.

2\. Core Operator Workflow
--------------------------

The application is designed to follow a simple, linear process for the operator:

1.  **Scan & View:** The operator presses the "scan" button on their physical scanning machine. The scanner saves the new page images (typically an open-book layout) to a pre-configured "Scan Folder" on the local network. The DigiPage application, which actively monitors this folder, immediately detects the new files and displays them in the large dual-pane canvases for inspection.
    
2.  **Inspect & Correct:** The operator reviews the two large page images for errors (e.g., skewed alignment, unwanted margins, color inaccuracies). If corrections are needed, they use the intuitive, per-image toolset to crop, rotate, or adjust colors.
    
3.  **Iterate:** The operator repeats steps 1 and 2 for every page of the book. The application automatically advances to show the latest pair of scanned pages, allowing for a continuous, uninterrupted workflow.
    
4.  **Assemble the Book:** Once the entire book is scanned and corrected, the operator scans the book's unique QR code. This code, which represents the book's name, is entered into the "Book Name" field. Clicking "Create" gathers all the individual page images from the "Scan Folder" and moves them into a newly created, named subfolder within a temporary "Today's Books" staging area.
    
5.  **Archive to Final Destination:** At any point, the operator can click the **"Transfer to Data"** button. The application intelligently processes every book folder in the "Today's Books" staging area. For each book, it automatically:
    
    *   Parses the book's name to identify a unique city code (e.g., "-001-").
        
    *   Looks up the pre-configured network path corresponding to that city code.
        
    *   Creates a new subfolder named after the current date (e.g., DD-MM) inside the city's main data folder if one doesn't already exist.
        
    *   Moves the completed book folder into this dated directory, finalizing the archival process.
        

3\. Features & User Interface (UI) Explained
--------------------------------------------

### Main Display & Editing Tools

The UI is designed for clarity and immediate access to critical tools.

*   **Dual-Pane Canvases:** The majority of the screen is dedicated to two large canvases that display the left and right pages of a scan. This oversized view is essential for spotting imperfections without needing to zoom in for every page.
    
*   **Contextual Editing Tools:** Positioned directly beneath each image canvas are the tools for editing _that specific image_. This proximity makes the workflow intuitive and fast.
    
    *   **Cropping:** An easy-to-use cropping tool. Clicking the "Crop" button activates draggable handles on the image's border. The operator can adjust the crop box and apply the change with a single click.
        
    *   **Rotation:** Includes buttons for quick 90-degree rotations and a central slider for fine-tuning the angle. Releasing the slider automatically applies and saves the rotation.
        
    *   **Color Correction:** Sliders for **Brightness** and **Contrast** allow for manual adjustments. "Auto" buttons trigger automatic lighting and color balance corrections. Changes can be saved or reverted with dedicated buttons.
        
    *   **Splitting:** A "Split" mode allows the operator to draw a vertical line on a single scanned image (e.g., a full book spread) and have the application automatically cut it into two separate page files.
        
    *   **Deletion:** Destructive actions are clearly marked. A button is available to delete a single page, while a larger button in the main control bar deletes the currently displayed pair of pages. All deletions require confirmation.
        
    *   **Restore:** Each edit creates a backup of the original image. The "Restore" button allows the operator to discard all changes and revert to the original scanned file.
        

### Sidebar & Workflow Management

The right-hand sidebar contains controls for managing the overall workflow and tracking progress.

*   **Performance Stats:** Displays live and session-total statistics, including pages-per-minute, scans pending in the input folder, books staged for transfer, and the total number of pages processed that day.
    
*   **Book Creation:** A simple text entry field for the book name (from the QR code) and a "Create" button to execute the book assembly step.
    
*   **Today's Books Panel:** A scrollable list showing all books processed during the current session. It distinguishes between books waiting in the staging area and books that have already been successfully transferred to the final data destination.
    
*   **Transfer to Data Button:** The master button to initiate the automated archival process for all staged books.
    
*   **Settings:** A gear icon provides access to the settings modal, where folder paths and city code mappings are configured.
    

4\. Technical Implementation
----------------------------

### Core Technologies

*   **Language/Framework:** Python 3 with the built-in **Tkinter** library for the graphical user interface.
    
*   **Image Processing:** The **Pillow (PIL)** library is the workhorse for all image manipulation, including opening, verifying, cropping, rotating, color adjustments, and saving files.
    
*   **Advanced Image Analysis:** **scikit-image** and **NumPy** are used for more complex operations like automatic color correction (white point balancing) and lighting adjustments (histogram matching).
    
*   **File System Monitoring:** The **watchdog** library provides an efficient, event-based mechanism to monitor the scan folder for new files, eliminating the need for performance-intensive polling.
    

### Key Classes & Architecture

The application is built with an object-oriented structure to separate concerns.

*   App(tk.Tk): The root of the application. It manages the main window, theme loading, and switching between the initial SettingsFrame and the main ImageScannerApp.
    
*   ImageScannerApp(tk.Frame): The primary application class that orchestrates the main UI, file watcher, background threads, and all workflow logic (book creation, data transfer, etc.).
    
*   ZoomPanCanvas(tk.Canvas): A custom Tkinter Canvas widget that is the heart of the user experience. It handles loading, displaying, and rendering images, as well as managing all interactive editing UI, such as drawing the crop box, handles, and split line.
    
*   SettingsModal(tk.Toplevel): The modal window for configuring all application settings, including folder paths and the crucial city-code-to-path mappings.
    
*   ScanWorker(threading.Thread): A dedicated background thread to handle statistics calculations. By offloading these potentially slow directory-scanning and log-file-reading tasks, the main UI thread remains responsive at all times.
    
*   NewImageHandler(FileSystemEventHandler): A handler class used by the watchdog observer to react specifically to file creation events in the scan folder.
    

### Concurrency and Performance

To ensure a smooth user experience, especially when dealing with file operations over a network, the application uses a multi-threaded approach.

*   **File Operations Thread:** All potentially blocking I/O operations (moving files, saving edits, deleting images) are executed in a temporary background thread. This prevents the UI from freezing while files are being copied or written to disk.
    
*   **Thread-Safe Communication:** Communication between the main UI thread and background worker threads is handled safely using Python's queue module. This ensures that data is passed between threads without causing race conditions or instability.
    

### Configuration and Logging

*   scan\_viewer\_config.json: A simple JSON file that stores all persistent settings, such as folder paths, theme choice, and city code mappings. This makes the application portable and easy to back up.
    
*   books\_complete\_log.json: Records a timestamped entry for every book successfully transferred to the final data archive, including its name, page count, and destination path. This provides a persistent record of the day's work.
