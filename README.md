# DigiPage Scanner: High-Volume Scanning Assistant

## 1. Primary Goal & Design Philosophy

The **DigiPage Scanner** is a specialized desktop application built to streamline high-volume document digitalization. It's designed for operators in a fast-paced environment, providing immediate tools for quality control and processing right at the point of scanning. This eliminates the need for a separate, time-consuming quality check later, saving significant time and effort.

The application is built around two core operational modes, each tailored to a specific scanning methodology:

*   **Dual Scan Mode:** The classic workflow, designed for scanners that produce two separate image files for the left and right pages of a book spread. The UI presents two large canvases, allowing the operator to inspect and edit both pages simultaneously.

*   **Single Split Mode:** A newer, more automated workflow for scanners that produce a single, wide image of an entire open book. The application intelligently splits this one image into two separate, cropped pages based on a user-defined layout, minimizing manual intervention.

The philosophy is simple: **scan, instantly inspect, correct if needed, and move on.** The interface is designed to be clear, efficient, and operator-focused, keeping mouse clicks and manual steps to a minimum.

## 2. Workflows

The application's workflow is determined by the "Scanner Mode" selected in the Settings.

### Workflow 1: Dual Scan Mode

This is the default mode, intended for processing pairs of images.

1.  **Scan & View:** The operator scans a book spread, and the scanner saves two image files (e.g., `IMG_001.jpg`, `IMG_002.jpg`) to a pre-configured **Scan Folder**. The DigiPage application, which actively monitors this folder, immediately detects the new files and displays them in the large dual-pane canvases.

2.  **Inspect & Correct:** The operator reviews the two large page images for errors like skewed alignment, unwanted margins, or poor color. If corrections are needed, they use the intuitive, per-image toolbars to:
    *   **Rotate:** Make fine-tuned angle adjustments.
    *   **Crop:** Adjust the visible area of the page.
    *   **Adjust Color:** Manually or automatically correct brightness, contrast, and color balance.
    *   **Delete:** Remove the current pair of images if a rescan is needed.
    *   **Replace:** Flag the current pair to be replaced by the next two scanned images, useful for correcting a bad scan without losing your place.

3.  **Iterate:** The operator repeats this process for every page of the book. The application can be configured to automatically advance to the latest pair of scanned pages, allowing for a continuous, uninterrupted workflow.

4.  **Assemble the Book:** Once the entire book is scanned and corrected, the operator scans the book's unique QR code. This code, which represents the book's name (e.g., `BOOK-A-001-12345`), is entered into the "Book Name" field in the sidebar. Clicking **"Create Book"** gathers all the individual page images from the Scan Folder and moves them into a new, named subfolder within a temporary "Today's Books" staging area.

5.  **Archive to Final Destination:** At any time, the operator can click the **"Transfer All to Data"** button. The application intelligently processes every book in the "Today's Books" staging area. For each book, it automatically:
    *   Parses the book's name to find a unique city code (e.g., `-001-`).
    *   Looks up the pre-configured network path for that city code.
    *   Creates a new subfolder named after the current date (e.g., `13-11`) inside the city's main data folder.
    *   Moves the completed book folder into this dated directory, finalizing the archival process.

### Workflow 2: Single Split Mode

This mode is designed for efficiency when the scanner produces one wide image per scan.

1.  **Scan & View:** The operator scans a book spread, and the scanner saves a single wide image (e.g., `SCAN_001.jpg`) to the **Scan Folder**. The application detects the new file and displays it in a single, large viewer.

2.  **Automatic Splitting:** The application automatically performs the following steps:
    *   It loads the crop layout (the positions of the left and right pages) that was used for the *previous* image.
    *   It applies this layout to the new image, splitting it into two separate page images (`SCAN_001_L.jpg` and `SCAN_001_R.jpg`).
    *   These two "final" page images are saved into a `final` subfolder within the Scan Folder.
    *   This automatic processing happens in the background without user interaction.

3.  **Inspect & Adjust Layout:** The operator navigates through the *original* wide-scan images. The viewer shows the defined crop areas for the left and right pages. If the automatic split was incorrect (e.g., the book shifted during scanning), the operator can simply drag the crop boxes to the correct positions.
    *   **Update Layout:** Clicking this button saves the new crop layout and immediately re-processes the image to update the final pages in the `final` folder. This new layout will then be automatically applied to all subsequent scans until it is changed again.
    *   **Toggle Pages:** The operator can disable the left or right page if, for example, they are scanning the first or last page of a book.

4.  **Assemble the Book:** This step is identical to the Dual Scan workflow. The operator enters the book name and clicks **"Create Book"**. The application gathers all the processed images from the `final` subfolder and moves them to the "Today's Books" staging area. It also performs a full cleanup, deleting the original wide-scan images and the `layout_data.json` file, preparing the Scan Folder for the next book.

5.  **Archive to Final Destination:** This step is identical to the Dual Scan workflow.

## 3. Features & User Interface Explained

### The Sidebar: Command & Control

The right-hand sidebar is the central hub for managing the workflow and tracking progress.

*   **Performance Stats:** At a glance, the operator can see:
    *   **Pages/Minute:** A live calculation of scanning speed.
    *   **Pending:** The number of unprocessed images currently in the Scan Folder.
    *   **Total Today:** A running total of all pages processed during the session (including staged and transferred books).

*   **Book Creation:** A simple panel with:
    *   A text field to enter the **Book Name**, typically from a QR code.
    *   The **"Create Book"** button, which assembles all processed images into a book folder in the staging area.

*   **Today's Books Panel:** A scrollable list showing all books created during the current session. It clearly distinguishes between:
    *   **TODAY'S:** Books waiting in the temporary staging folder.
    *   **DATA:** Books that have been successfully transferred to the final network archive.

*   **Workflow Buttons:**
    *   **Transfer All to Data:** The master button to initiate the automated archival process for all staged books.
    *   **View Log:** Opens a dialog showing the complete history of all books transferred to the data archive.
    *   **Settings:** Opens the configuration window.

### The Bottom Bar: Navigation & Actions

This bar contains the primary controls for navigating through images and performing key actions.

*   **Status Label:** Displays the current position (e.g., "Pages 1-2 of 150").
*   **Navigation:** `Previous`, `Next`, and `Jump to End` buttons for moving through the image set. The mouse wheel can also be used for navigation.
*   **Refresh:** Manually rescans the Scan Folder for any changes.
*   **Delete:** Deletes the currently displayed image or pair of images (with confirmation).
*   **Replace:** Toggles "Replace Mode." When active, the next scan(s) will automatically replace the currently displayed image(s). This is a quick way to fix a bad scan without losing your place in the sequence.

## 4. Configuration

The application's behavior is controlled by a few key files:

*   **`config.json`:** The main settings file. This is where the operator configures essential paths like the **Scan Folder**, the **Today's Books Folder**, and the network paths for each **City Code**. It also stores the selected theme and the active **Scanner Mode** (`dual_scan` or `single_split`).

*   **`books_complete_log.json`:** A permanent record of all work. Every time books are transferred to the final archive, a timestamped entry is added to this log, including the book's name, page count, and final destination path.

*   **`layout_data.json`:** (Single Split Mode only) This file is created inside the Scan Folder. It stores the crop layout (the position and size of the left and right page boxes) for each image. When a new book is created, this file is automatically deleted to ensure the next book starts with a fresh, default layout.