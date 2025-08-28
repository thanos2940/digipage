import os
import time
import shutil
import tkinter as tk
from tkinter import messagebox
import threading
import queue
import re
from datetime import datetime
from collections import deque
from PIL import Image
from watchdog.observers import Observer

from zoom_pan_canvas import ZoomPanCanvas
from settings_modal import SettingsModal
from file_handler import NewImageHandler
from worker import ScanWorker, natural_sort_key
from style import Style, lighten_color, darken_color
from tooltip import ToolTip
from config import BACKUP_DIR, BOOKS_COMPLETE_LOG_FILE, DEFAULT_IMAGE_LOAD_TIMEOUT_MS, PERFORMANCE_WINDOW_SECONDS, ALLOWED_EXTENSIONS

class ImageScannerApp(tk.Frame):
    # Initializes the main application frame
    def __init__(self, parent, controller, settings):
        super().__init__(parent, bg=Style.BG_COLOR)
        self.controller = controller
        self.scan_directory, self.todays_books_folder = settings["scan"], settings["today"]
        self.city_paths = settings.get("city_paths", {}) # Load city paths config
        self.is_animating = False
        self.image_cache, self.cache_lock = {}, threading.Lock()

        # New state management for modes (crop, split, normal)
        self.current_mode = None # Can be 'crop', 'split', or None
        self.active_canvas = None # The canvas currently being cropped or split

        # Queues for background workers
        self.preload_queue, self.preload_thread = queue.Queue(), threading.Thread(target=self._preload_worker, daemon=True)
        self.preload_thread.start()

        self.scan_worker_command_queue = queue.Queue()
        self.scan_worker_result_queue = queue.Queue()
        self.scan_worker = ScanWorker(self.scan_worker_command_queue, self.scan_worker_result_queue, self.scan_directory, self.todays_books_folder, self.city_paths)
        self.scan_worker.start()

        self.observer = None
        self.is_transfer_active, self.transfer_thread, self.transfer_status_queue = False, None, queue.Queue()

        # Variables for jump button breathing animation
        self.jump_button_breathing_id = None
        self.breathing_step = 0
        self.breathing_total_steps = 25 # Steps for one half-cycle (e.g., from base to target color) - Made faster
        self.breathing_direction = 1 # 1 for increasing lightness, -1 for decreasing
        self.breathing_base_color_rgb = self._hex_to_rgb(Style.BTN_BG)
        self.breathing_target_color_rgb = self._hex_to_rgb(Style.JUMP_BTN_BREATHE_COLOR)

        # For live performance tracking
        self.scan_timestamps = deque()

        # Process queues periodically
        self.after(100, self._process_transfer_queue)
        self.after(100, self._process_scan_queue)

        if "state" in settings and settings["state"]:
            state = settings["state"]
            self.image_files = state.get("image_files", [])
            self.current_index = state.get("current_index", 0)
            self.start_time = state.get("start_time", time.time())
            self.image_load_timeout_ms = settings.get("image_load_timeout_ms", DEFAULT_IMAGE_LOAD_TIMEOUT_MS)
        else:
            self.image_files, self.current_index = [], 0
            self.start_time = time.time()
            self.image_load_timeout_ms = DEFAULT_IMAGE_LOAD_TIMEOUT_MS

        self.setup_ui()
        self.setup_keybinds()
        self.start_watcher()
        self.scan_worker_command_queue.put(('initial_scan', self.scan_directory)) # Trigger initial scan via worker
        self.update_stats()

    def open_settings_modal(self):
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        self.settings_window = SettingsModal(self.controller, self.controller, self)
        self.wait_window(self.settings_window)

    def update_theme(self):
        # This method will be called to apply the current theme to all widgets.
        # --- Main Frames ---
        self.configure(bg=Style.BG_COLOR)
        self.main_app_frame.config(bg=Style.BG_COLOR)
        self.image_display_area.config(bg=Style.BG_COLOR)

        # --- Sidebar ---
        self.sidebar_frame.config(bg=Style.FRAME_BG)
        self.stats_frame.config(bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR)

        for label in [self.scans_min_label, self.current_scans_label, self.books_today_label, self.total_scans_today_label]:
            label.config(bg=Style.FRAME_BG, fg=Style.FG_COLOR)

        self.todays_books_panel.config(bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR)
        self.book_creation_frame.config(bg=Style.FRAME_BG)
        self.book_creation_frame.winfo_children()[0].config(bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR) # label
        self.qr_entry.config(bg=Style.BTN_BG, fg=Style.FG_COLOR, insertbackground=Style.FG_COLOR)
        self.create_book_btn.config(bg=Style.ACCENT_COLOR)

        self.todays_books_canvas.config(bg=Style.FRAME_BG, highlightthickness=0)
        self.todays_books_frame.config(bg=Style.FRAME_BG)
        self.todays_books_scrollbar.config(bg=Style.BTN_BG, troughcolor=Style.BG_COLOR)
        self.transfer_to_data_btn.config(bg=Style.TRANSFER_BTN_COLOR)

        self.settings_btn_frame.config(bg=Style.FRAME_BG)
        self.settings_btn.config(bg=Style.BTN_BG, fg=Style.BTN_FG)

        # --- Control Bar ---
        self.control_frame.config(bg=Style.FRAME_BG)
        self.left_frame.config(bg=Style.FRAME_BG)
        self.status_label.config(bg=Style.FRAME_BG, fg=Style.FG_COLOR)

        self.center_frame.config(bg=Style.FRAME_BG)
        for btn in [self.prev_btn, self.next_btn, self.jump_to_end_btn, self.refresh_btn]:
            btn.config(bg=Style.BTN_BG, fg=Style.BTN_FG)
        self.right_frame.config(bg=Style.FRAME_BG)

        self.delete_pair_btn.config(bg=Style.DESTRUCTIVE_COLOR)
        self.complete_split_btn.config(bg=Style.SUCCESS_COLOR)
        self.cancel_split_btn.config(bg=Style.DESTRUCTIVE_COLOR)

        # --- Image Canvases and Buttons ---
        for i, canvas in enumerate(self.image_canvases):
            canvas.update_theme()
            buttons = self.action_buttons_list[i]

            canvas.master.config(bg=Style.BG_COLOR)
            buttons['crop'].master.master.config(bg=Style.BG_COLOR)
            buttons['crop'].master.config(bg=Style.BG_COLOR)
            buttons['rot_left'].master.config(bg=Style.BG_COLOR)
            buttons['color_adjust_frame'].config(bg=Style.BG_COLOR)

            buttons['crop'].config(bg=Style.CROP_BTN_COLOR)
            buttons['split'].config(bg=Style.BTN_BG, fg=Style.BTN_FG)
            buttons['restore'].config(bg=Style.WARNING_COLOR)
            buttons['delete'].config(bg=Style.DESTRUCTIVE_COLOR)
            buttons['rot_left'].config(bg=Style.BTN_BG, fg=Style.BTN_FG)
            buttons['rot_right'].config(bg=Style.BTN_BG, fg=Style.BTN_FG)
            buttons['save_color'].config(bg=Style.SUCCESS_COLOR)
            buttons['cancel_color'].config(bg=Style.DESTRUCTIVE_COLOR)

            buttons['angle_slider'].config(bg=Style.BG_COLOR, fg=Style.FG_COLOR, troughcolor=Style.BTN_BG)
            buttons['brightness_slider'].config(bg=Style.BG_COLOR, fg=Style.FG_COLOR, troughcolor=Style.BTN_BG)
            buttons['contrast_slider'].config(bg=Style.BG_COLOR, fg=Style.FG_COLOR, troughcolor=Style.BTN_BG)
            for child in buttons['color_adjust_frame'].winfo_children():
                if isinstance(child, tk.Label):
                    child.config(bg=Style.BG_COLOR, fg=Style.FG_COLOR)

        self.breathing_base_color_rgb = self._hex_to_rgb(Style.BTN_BG)
        self.breathing_target_color_rgb = self._hex_to_rgb(Style.JUMP_BTN_BREATHE_COLOR)

        self._update_todays_books_panel()

        if hasattr(self, 'settings_window') and self.settings_window.winfo_exists():
            self.settings_window.update_theme()

    # Converts hex color string to RGB tuple (0-255)
    def _hex_to_rgb(self, hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    # Converts RGB tuple (0-255) to hex color string
    def _rgb_to_hex(self, rgb_tuple):
        return '#%02x%02x%02x' % tuple(int(c) for c in rgb_tuple)

    # Starts the breathing animation for the 'Jump to End' button
    def _start_jump_button_breathing(self):
        if self.jump_button_breathing_id:
            return # Animation already running

        def _breathe_step():
            # Check if button still exists before trying to configure it
            if not self.jump_to_end_btn.winfo_exists():
                self._stop_jump_button_breathing()
                return

            # Calculate interpolation factor (ping-pong effect)
            factor = self.breathing_step / self.breathing_total_steps
            if self.breathing_direction == -1:
                factor = 1.0 - factor

            # Interpolate RGB values
            current_rgb = [
                self.breathing_base_color_rgb[i] + (self.breathing_target_color_rgb[i] - self.breathing_base_color_rgb[i]) * factor
                for i in range(3)
            ]

            self.jump_to_end_btn.config(bg=self._rgb_to_hex(current_rgb))

            self.breathing_step += 1
            if self.breathing_step > self.breathing_total_steps:
                self.breathing_step = 0
                self.breathing_direction *= -1 # Reverse direction

            self.jump_button_breathing_id = self.after(50, _breathe_step) # Schedule next step

        self.breathing_step = 0
        self.breathing_direction = 1
        self.jump_button_breathing_id = self.after(50, _breathe_step) # Start the animation

    # Stops the breathing animation for the 'Jump to End' button
    def _stop_jump_button_breathing(self):
        if self.jump_button_breathing_id:
            self.after_cancel(self.jump_button_breathing_id)
            self.jump_button_breathing_id = None
            if self.jump_to_end_btn.winfo_exists():
                self.jump_to_end_btn.config(bg=Style.BTN_BG) # Reset to original color

    # Sets the editing state of the app (used for auto-navigation)
    def set_editing_state(self, state):
        # This flag now primarily controls auto-navigation.
        # Button visibility is managed by current_mode.
        self.is_editing = state
        self._check_and_update_breathing_animation()

    # Worker thread to preload images
    def _preload_worker(self):
        while True:
            try:
                image_path = self.preload_queue.get()
                if image_path is None: break
                with self.cache_lock:
                    if image_path not in self.image_cache:
                        try:
                            img = Image.open(image_path)
                            img.verify()
                            img = Image.open(image_path)
                            self.image_cache[image_path] = img
                        except Exception as e:
                            print(f"ERROR: Failed to preload {os.path.basename(image_path)}: {e}")
                self.preload_queue.task_done()
            except Exception as e:
                print(f"ERROR: Preload worker error: {e}")
                time.sleep(1)

    # Queues an image for preloading
    def _queue_for_preload(self, image_path):
        if image_path and os.path.exists(image_path):
            with self.cache_lock:
                if image_path not in self.image_cache:
                    self.preload_queue.put(image_path)

    # Cleans the image cache
    def _clean_cache(self, current_paths_to_keep):
        with self.cache_lock:
            paths_to_remove = [path for path in self.image_cache if path not in current_paths_to_keep]
            for path in paths_to_remove:
                img_to_close = self.image_cache.pop(path, None)
                if img_to_close: img_to_close.close()

    # Processes messages from the file transfer thread
    def _process_transfer_queue(self):
        try:
            status, message, operation_type, *extra_data = self.transfer_status_queue.get_nowait() # Unpack extra_data
            self.is_transfer_active = False
            self._set_transfer_buttons_state(tk.NORMAL)
            self.show_snackbar(message, status)
            if status == 'success':
                if operation_type == 'create_book':
                    self.qr_entry.delete(0, tk.END)
                    self.scan_worker_command_queue.put(('initial_scan', self.scan_directory))
                elif operation_type == 'transfer_to_data': # Handle new operation
                    self._update_todays_books_panel() # Refresh the books list
                    self.scan_worker_command_queue.put(('calculate_today_stats', None)) # Update stats after transfer
                elif operation_type == 'delete_pair':
                    self.scan_worker_command_queue.put(('initial_scan', self.scan_directory))
                elif operation_type == 'split_image': # New: Handle split operation result
                    # After successful split, exit the mode and trigger a re-scan
                    self.exit_mode()
                    self.scan_worker_command_queue.put(('initial_scan', self.scan_directory))
            self.transfer_status_queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_transfer_queue)

    # Processes messages from the scan worker thread
    def _process_scan_queue(self):
        try:
            command, data = self.scan_worker_result_queue.get_nowait()
            if command == 'initial_scan_result':
                self.image_files = data
                if self.image_files:
                    # Ensure current_index is valid, especially after file operations
                    if self.current_index >= len(self.image_files):
                        self.current_index = max(0, len(self.image_files) - 2)
                    elif self.current_index < 0 and len(self.image_files) > 0:
                        self.current_index = 0
                else:
                    self.current_index = 0
                self.update_display(animated=False)
                self._check_and_update_breathing_animation() # Re-evaluate breathing after scan
            elif command == 'today_stats_result':
                # Unpack stats
                pages_in_today = data.get("pages_in_today", 0)
                books_in_today = data.get("books_in_today", 0)
                pages_in_data = data.get("pages_in_data", 0)

                # Update UI
                self.current_scans_label.config(text=f"Σαρώσεις σε αναμονή: {len(self.image_files)}")
                self.books_today_label.config(text=f"Βιβλία σε αναμονή: {books_in_today} ({pages_in_today} σελ.)")

                total_pages_today = pages_in_today + pages_in_data + len(self.image_files)
                self.total_scans_today_label.config(text=f"Σύνολο Σελίδων Σήμερα: {total_pages_today}")

                self._update_todays_books_panel() # Also refresh the book list

            elif command == 'error':
                self.show_snackbar(data, 'error')
            self.scan_worker_result_queue.task_done()
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_scan_queue)

    # Checks if the breathing animation should be active and updates it
    def _check_and_update_breathing_animation(self):
        # Condition for starting breathing:
        # 1. Not in any editing mode (crop/split)
        # 2. There are unviewed pages after the current displayed pair
        has_unviewed_pages = (self.current_index + 2 < len(self.image_files))

        if self.current_mode is None and has_unviewed_pages:
            self._start_jump_button_breathing()
        else:
            self._stop_jump_button_breathing()

    # Enables or disables transfer-related buttons
    def _set_transfer_buttons_state(self, state):
        buttons_to_toggle = [
            self.create_book_btn, self.transfer_to_data_btn
        ]
        for btn in buttons_to_toggle:
            if btn.winfo_exists():
                btn.config(state=state)

    # Worker thread for file operations
    def _transfer_operation_worker(self, operation_type, data):
        try:
            if self.observer:
                self.observer.stop()
                self.observer.join()
            status, message = 'success', ""
            if operation_type == 'create_book':
                book_name, scanned_files = data
                new_book_path = os.path.join(self.todays_books_folder, book_name)
                os.makedirs(new_book_path, exist_ok=True)
                for file_path in scanned_files:
                    self.invalidate_cache_for_path(file_path)
                    shutil.move(file_path, new_book_path)
                message = f"{len(scanned_files)} σαρώσεις μεταφέρθηκαν στο '{book_name}'"
            elif operation_type == 'transfer_to_data':
                moves_to_perform = data
                moved_count = 0
                failed_moves = []

                # Load log file once
                try:
                    if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
                        with open(BOOKS_COMPLETE_LOG_FILE, 'r') as f:
                            log_data = json.load(f)
                    else:
                        log_data = {}
                except (IOError, json.JSONDecodeError):
                    log_data = {}

                today_str = datetime.now().strftime('%Y-%m-%d')
                if today_str not in log_data:
                    log_data[today_str] = []

                for move in moves_to_perform:
                    try:
                        # Count pages before moving
                        page_count = self._count_pages_in_folder(move['source'])

                        # Ensure the date-stamped destination folder exists
                        os.makedirs(move['destination_folder'], exist_ok=True)

                        final_book_path = os.path.join(move['destination_folder'], move['book_name'])

                        # Now move the book folder into it
                        shutil.move(move['source'], final_book_path)

                        # Add to log with new detailed format
                        log_entry = {
                            "name": move['book_name'],
                            "pages": page_count,
                            "path": final_book_path,
                            "timestamp": datetime.now().isoformat()
                        }
                        log_data[today_str].append(log_entry)
                        moved_count += 1
                    except Exception as e:
                        failed_moves.append(move['book_name'])
                        print(f"ERROR moving book {move['book_name']}: {e}")

                # Save log file once
                try:
                    with open(BOOKS_COMPLETE_LOG_FILE, 'w') as f:
                        json.dump(log_data, f, indent=4)
                except IOError as e:
                    print(f"Could not write to log file: {e}")

                if not failed_moves:
                    message = f"Μεταφέρθηκαν επιτυχώς {moved_count} βιβλία στα data πόλεων."
                else:
                    message = f"Μεταφέρθηκαν {moved_count} βιβλία. Απέτυχε η μεταφορά για: {', '.join(failed_moves)}"
                    status = 'warning'

            elif operation_type == 'delete_pair':
                files_to_delete = data
                for f_path in files_to_delete:
                    if os.path.exists(f_path):
                        self.invalidate_cache_for_path(f_path)
                        os.remove(f_path)
                message = f"Διαγράφηκαν: {', '.join([os.path.basename(f) for f in files_to_delete])}"
            elif operation_type == 'split_image': # Handle split image operation
                original_path, split_x_coord = data
                try:
                    original_image = Image.open(original_path)
                    img_w, img_h = original_image.size

                    # Ensure split_x_coord is valid (not at the very edges)
                    if split_x_coord <= 0 or split_x_coord >= img_w:
                        raise ValueError("Split line must be within image bounds.")

                    left_image = original_image.crop((0, 0, split_x_coord, img_h))
                    right_image = original_image.crop((split_x_coord, 0, img_w, img_h))

                    base_name, ext = os.path.splitext(original_path)
                    # The left part will overwrite the original file
                    # The right part will get a new name
                    right_path = f"{base_name}_2{ext}"

                    # Close original image before saving to avoid file lock issues
                    original_image.close()

                    # Save the right part first, as it's a new file
                    right_image.save(right_path)

                    # Save the left part, overwriting the original file
                    # This implicitly handles the deletion of the original full image content
                    left_image.save(original_path)

                    # Invalidate cache for both paths
                    self.invalidate_cache_for_path(original_path) # Now contains the left part
                    self.invalidate_cache_for_path(right_path) # The new right part

                    message = f"Εικόνα διαχωρίστηκε σε '{os.path.basename(original_path)}' και '{os.path.basename(right_path)}'."
                    status = 'success'
                except Exception as e:
                    message = f"Αποτυχία διαχωρισμού εικόνας: {e}"
                    status = 'error'

            self.transfer_status_queue.put((status, message, operation_type))
        except Exception as e:
            self.transfer_status_queue.put(('error', f"Σφάλμα κατά τη λειτουργία {operation_type}: {e}", operation_type))
        finally:
            self.start_watcher()

    # Sets up the main UI layout
    def setup_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self.main_app_frame = tk.Frame(self, bg=Style.BG_COLOR)
        self.main_app_frame.grid(row=0, column=0, sticky='nsew')
        self.main_app_frame.grid_rowconfigure(0, weight=1)
        self.main_app_frame.grid_columnconfigure(0, weight=1)
        self.main_app_frame.grid_columnconfigure(1, minsize=250, weight=0) # Increased sidebar width

        self.image_display_area = tk.Frame(self.main_app_frame, bg=Style.BG_COLOR)
        self.image_display_area.grid(row=0, column=0, sticky='nsew')
        self.image_display_area.grid_rowconfigure(0, weight=1)
        self.image_display_area.grid_columnconfigure(0, weight=1)
        self.image_display_area.grid_columnconfigure(1, weight=1)

        self._setup_sidebar(self.main_app_frame)
        self._setup_control_bar()
        self._setup_image_displays()

    # Creates a styled button
    def create_styled_button(self, parent, text, command, bg=Style.BTN_BG, fg=Style.BTN_FG, font_size=10, font_weight="normal", padx=15, pady=8, tooltip=None):
        hover_bg = lighten_color(bg, 0.1)
        press_bg = darken_color(bg, 0.1)
        btn = tk.Button(parent, text=text, bg=bg, fg=fg, activebackground=press_bg, activeforeground=fg,
                        font=Style.get_font(font_size, font_weight), relief=tk.FLAT, borderwidth=0, padx=padx, pady=pady)

        def _command_wrapper():
            if command:
                command()
                btn.after(100, lambda: self._reset_button_color(btn, bg, hover_bg))

        btn.config(command=_command_wrapper)
        btn.bind("<Enter>", lambda e, b=btn, h_bg=hover_bg: b.config(bg=h_bg))
        btn.bind("<Leave>", lambda e, b=btn, o_bg=bg: b.config(bg=o_bg))
        if tooltip: ToolTip(btn, tooltip)
        return btn

    def _reset_button_color(self, btn, original_bg, hover_bg):
        if not btn.winfo_exists(): return
        x, y = btn.winfo_pointerxy()
        widget_under_pointer = btn.winfo_containing(x, y)
        if widget_under_pointer == btn:
            btn.config(bg=hover_bg)
        else:
            btn.config(bg=original_bg)

    # Sets up the sidebar
    def _setup_sidebar(self, parent):
        self.sidebar_frame = tk.Frame(parent, bg=Style.FRAME_BG, padx=15, pady=15)
        self.sidebar_frame.grid(row=0, column=1, sticky='nsw', padx=(0,10), pady=(10,10))
        self.sidebar_frame.grid_rowconfigure(1, weight=1)

        self.stats_frame = tk.LabelFrame(self.sidebar_frame, text="Στατιστικά Απόδοσης", bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(11, 'bold'), bd=1, relief=tk.GROOVE)
        self.stats_frame.pack(fill=tk.X, pady=10)

        self.scans_min_label = tk.Label(self.stats_frame, text="Απόδοση: 0.0 σελ/λεπτό", bg=Style.FRAME_BG, fg=Style.FG_COLOR, font=Style.get_font(10))
        self.scans_min_label.pack(anchor='w', padx=10, pady=2)

        self.current_scans_label = tk.Label(self.stats_frame, text="Σαρώσεις σε αναμονή: 0", bg=Style.FRAME_BG, fg=Style.FG_COLOR, font=Style.get_font(10))
        self.current_scans_label.pack(anchor='w', padx=10, pady=2)

        self.books_today_label = tk.Label(self.stats_frame, text="Βιβλία σε αναμονή: 0 (0 σελ.)", bg=Style.FRAME_BG, fg=Style.FG_COLOR, font=Style.get_font(10))
        self.books_today_label.pack(anchor='w', padx=10, pady=2)

        self.total_scans_today_label = tk.Label(self.stats_frame, text="Σύνολο Σελίδων Σήμερα: 0", bg=Style.FRAME_BG, fg=Style.FG_COLOR, font=Style.get_font(10, 'bold'))
        self.total_scans_today_label.pack(anchor='w', padx=10, pady=(5,5))

        # New: Todays Books Panel
        self.todays_books_panel = tk.LabelFrame(self.sidebar_frame, text="Βιβλία Σήμερα", bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(11, 'bold'), bd=1, relief=tk.GROOVE)
        self.todays_books_panel.pack(fill=tk.BOTH, pady=10, expand=True) # Fill and expand

        # Book creation elements moved here
        self.book_creation_frame = tk.Frame(self.todays_books_panel, bg=Style.FRAME_BG)
        self.book_creation_frame.pack(fill=tk.X, pady=(5, 0), padx=5)
        tk.Label(self.book_creation_frame, text="Όνομα Βιβλίου:", bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(10)).pack(side=tk.LEFT, padx=(0, 5))
        self.qr_entry = tk.Entry(self.book_creation_frame, font=Style.get_font(11), width=15, bg=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT, insertbackground=Style.FG_COLOR)
        self.qr_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        self.create_book_btn = self.create_styled_button(self.book_creation_frame, "Δημιουργία", self.create_new_book, bg=Style.ACCENT_COLOR, tooltip="Δημιουργία νέου φακέλου βιβλίου και μεταφορά όλων των τρεχουσών σαρώσεων σε αυτόν.", pady=5, padx=8) # Shorter text for space
        self.create_book_btn.pack(side=tk.LEFT, padx=(5,0))

        # Canvas for book list
        self.todays_books_canvas = tk.Canvas(self.todays_books_panel, bg=Style.FRAME_BG, highlightthickness=0)
        self.todays_books_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.todays_books_frame = tk.Frame(self.todays_books_canvas, bg=Style.FRAME_BG)
        self.todays_books_canvas.create_window((0, 0), window=self.todays_books_frame, anchor="nw")
        self.todays_books_frame.bind("<Configure>", lambda e: self.todays_books_canvas.configure(scrollregion=self.todays_books_canvas.bbox("all")))

        # Scrollbar for the new panel
        self.todays_books_scrollbar = tk.Scrollbar(self.todays_books_panel, orient="vertical", command=self.todays_books_canvas.yview, bg=Style.BTN_BG, troughcolor=Style.BG_COLOR)
        self.todays_books_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.todays_books_canvas.config(yscrollcommand=self.todays_books_scrollbar.set)

        # New "Transfer to Data" button
        self.transfer_to_data_btn = self.create_styled_button(self.todays_books_panel, "Μεταφορά στα Data Πόλεων", self.transfer_to_data, bg=Style.TRANSFER_BTN_COLOR, tooltip="Μετακίνηση βιβλίων στους φακέλους δεδομένων της αντίστοιχης πόλης.")
        self.transfer_to_data_btn.pack(fill=tk.X, pady=(10,5), padx=10)

        # New "Settings" button at the bottom of the sidebar
        self.settings_btn_frame = tk.Frame(self.sidebar_frame, bg=Style.FRAME_BG)
        self.settings_btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10,0))
        self.settings_btn = self.create_styled_button(self.settings_btn_frame, "⚙️ Ρυθμίσεις", self.open_settings_modal, font_size=11, pady=8)
        self.settings_btn.pack(fill=tk.X, expand=True)


    # Sets up the bottom control bar
    def _setup_control_bar(self):
        self.control_frame = tk.Frame(self, bg=Style.FRAME_BG, pady=10, padx=20)
        self.control_frame.grid(row=1, column=0, sticky='ew')
        self.control_frame.grid_columnconfigure(0, weight=1) # Left side for status
        self.control_frame.grid_columnconfigure(1, weight=1) # Center for navigation
        self.control_frame.grid_columnconfigure(2, weight=1) # Right for delete button

        self.left_frame = tk.Frame(self.control_frame, bg=Style.FRAME_BG)
        self.left_frame.grid(row=0, column=0, sticky='w')
        self.status_label = tk.Label(self.left_frame, text="Φόρτωση...", bg=Style.FRAME_BG, fg=Style.FG_COLOR, font=Style.get_font(12, "bold"))
        self.status_label.pack(anchor='w')

        self.center_frame = tk.Frame(self.control_frame, bg=Style.FRAME_BG)
        self.center_frame.grid(row=0, column=1, sticky='nsew') # Changed column to 1
        self.prev_btn = self.create_styled_button(self.center_frame, "◀ Προηγούμενο", self.prev_pair, tooltip="Μετάβαση στο προηγούμενο ζεύγος (Αριστερό Βέλος)", font_size=12, pady=10)
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        self.next_btn = self.create_styled_button(self.center_frame, "Επόμενο ▶", self.next_pair, tooltip="Μετάβαση στο επόμενο ζεύγος (Δεξί Βέλος)", font_size=12, pady=10)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        self.jump_to_end_btn = self.create_styled_button(self.center_frame, "Μετάβαση στο Τέλος", self.jump_to_end, tooltip="Μετάβαση στο τελευταίο ζεύγος σελίδων.", font_size=12, pady=10)
        self.jump_to_end_btn.pack(side=tk.LEFT, padx=5)

        # Add Refresh button here
        self.refresh_btn = self.create_styled_button(self.center_frame, "Ανανέωση", self.refresh_scan_folder, tooltip="Επανεξέταση φακέλου σάρωσης", font_size=12, pady=10)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)


        # New: Split mode buttons, initially hidden
        self.complete_split_btn = self.create_styled_button(self.center_frame, "Ολοκλήρωση Διαχωρισμού", self.complete_split, bg=Style.SUCCESS_COLOR, tooltip="Ολοκλήρωση της λειτουργίας διαχωρισμού.", font_size=12, pady=10)
        self.cancel_split_btn = self.create_styled_button(self.center_frame, "Ακύρωση Διαχωρισμού", self.cancel_split, bg=Style.DESTRUCTIVE_COLOR, tooltip="Ακύρωση της λειτουργίας διαχωρισμού.", font_size=12, pady=10)
        self.complete_split_btn.pack_forget()
        self.cancel_split_btn.pack_forget()

        self.right_frame = tk.Frame(self.control_frame, bg=Style.FRAME_BG)
        self.right_frame.grid(row=0, column=2, sticky='e') # Changed column to 2
        # Moved delete_pair_btn here
        self.delete_pair_btn = self.create_styled_button(self.right_frame, "Διαγραφή Ζεύγους", self.delete_current_pair, bg=Style.DESTRUCTIVE_COLOR, tooltip="Διαγραφή του τρέχοντος ζεύγους (Delete)", pady=10)
        self.delete_pair_btn.pack(side=tk.RIGHT) # Pack to the right

    # Sets up the image display areas
    def _setup_image_displays(self):
        self.image_canvases = []
        self.action_buttons_list = []
        for i in range(2):
            container = tk.Frame(self.image_display_area, bg=Style.BG_COLOR)
            container.grid(row=0, column=i, sticky='nsew', padx=5, pady=5)
            container.grid_rowconfigure(0, weight=1)
            container.grid_columnconfigure(0, weight=1)

            canvas = ZoomPanCanvas(container, self)
            canvas.grid(row=0, column=0, sticky='nsew')
            self.image_canvases.append(canvas)

            btn_container = tk.Frame(container, bg=Style.BG_COLOR)
            btn_container.grid(row=1, column=0, sticky='ew', pady=(8,0))

            action_frame = tk.Frame(btn_container, bg=Style.BG_COLOR)
            action_frame.pack()

            buttons = {}
            # Crop button now directly applies the crop
            buttons['crop'] = self.create_styled_button(action_frame, "Περικοπή", lambda c=canvas: self.perform_crop(c), bg=Style.CROP_BTN_COLOR, font_size=9, pady=4)
            buttons['split'] = self.create_styled_button(action_frame, "Διαχωρισμός", lambda c=canvas: self.start_mode('split', c), font_size=9, pady=4)
            buttons['restore'] = self.create_styled_button(action_frame, "Επαναφορά", lambda c=canvas: self.perform_restore(c), font_size=9, pady=4, bg=Style.WARNING_COLOR)
            buttons['delete'] = self.create_styled_button(action_frame, "Διαγραφή", lambda c=canvas: self.perform_delete_single(c), bg=Style.DESTRUCTIVE_COLOR, font_size=9, pady=4)

            rotate_frame = tk.Frame(btn_container, bg=Style.BG_COLOR)
            rotate_frame.pack(pady=(5,0))
            buttons['rot_left'] = self.create_styled_button(rotate_frame, "⟲", lambda c=canvas: c.apply_rotation(c.rotation_angle + 90, save_after=True), font_size=12, padx=8, pady=2)
            angle_slider = tk.Scale(rotate_frame, from_=-45, to=45, orient=tk.HORIZONTAL, bg=Style.BG_COLOR, fg=Style.FG_COLOR, highlightthickness=0, troughcolor=Style.BTN_BG, length=150, relief=tk.FLAT, sliderrelief=tk.FLAT, showvalue=0)
            buttons['rot_right'] = self.create_styled_button(rotate_frame, "⟳", lambda c=canvas: c.apply_rotation(c.rotation_angle - 90, save_after=True), font_size=12, padx=8, pady=2)

            buttons['crop'].pack(side=tk.LEFT, padx=3)
            buttons['split'].pack(side=tk.LEFT, padx=3) # Pack the new split button
            buttons['restore'].pack(side=tk.LEFT, padx=3)
            buttons['delete'].pack(side=tk.LEFT, padx=3)
            buttons['rot_left'].pack(side=tk.LEFT)
            angle_slider.pack(side=tk.LEFT, padx=5)
            buttons['rot_right'].pack(side=tk.LEFT)

            angle_slider.config(command=lambda val, c=canvas: c.preview_rotation(val))
            angle_slider.bind("<ButtonRelease-1>", lambda e, c=canvas, s=angle_slider: c.apply_rotation(s.get(), save_after=True))
            canvas.angle_slider = angle_slider
            buttons['angle_slider'] = angle_slider

            # New: Color adjustment controls
            color_adjust_frame = tk.Frame(btn_container, bg=Style.BG_COLOR)
            color_adjust_frame.pack(pady=(5,0))

            tk.Label(color_adjust_frame, text="Φωτεινότητα:", bg=Style.BG_COLOR, fg=Style.FG_COLOR, font=Style.get_font(8)).pack(side=tk.LEFT, padx=(0,2))
            brightness_slider = tk.Scale(color_adjust_frame, from_=-1.0, to=1.0, resolution=0.01, orient=tk.HORIZONTAL, bg=Style.BG_COLOR, fg=Style.FG_COLOR, highlightthickness=0, troughcolor=Style.BTN_BG, length=100, relief=tk.FLAT, sliderrelief=tk.FLAT, showvalue=0)
            brightness_slider.set(0.0)
            brightness_slider.pack(side=tk.LEFT, padx=(0,5))
            brightness_slider.config(command=lambda val, c=canvas: c.set_brightness(val))
            canvas.brightness_slider = brightness_slider
            buttons['brightness_slider'] = brightness_slider

            tk.Label(color_adjust_frame, text="Αντίθεση:", bg=Style.BG_COLOR, fg=Style.FG_COLOR, font=Style.get_font(8)).pack(side=tk.LEFT, padx=(0,2))
            contrast_slider = tk.Scale(color_adjust_frame, from_=0.0, to=2.0, resolution=0.01, orient=tk.HORIZONTAL, bg=Style.BG_COLOR, fg=Style.FG_COLOR, highlightthickness=0, troughcolor=Style.BTN_BG, length=100, relief=tk.FLAT, sliderrelief=tk.FLAT, showvalue=0)
            contrast_slider.set(1.0)
            contrast_slider.pack(side=tk.LEFT, padx=(0,5))
            contrast_slider.config(command=lambda val, c=canvas: c.set_contrast(val))
            canvas.contrast_slider = contrast_slider
            buttons['contrast_slider'] = contrast_slider

            buttons['save_color'] = self.create_styled_button(color_adjust_frame, "Αποθήκευση", lambda c=canvas: self.save_color_adjustments(c), bg=Style.SUCCESS_COLOR, font_size=8, padx=5, pady=2)
            buttons['save_color'].pack(side=tk.LEFT, padx=(0,3))
            buttons['cancel_color'] = self.create_styled_button(color_adjust_frame, "Ακύρωση", lambda c=canvas: self.cancel_color_adjustments(c), bg=Style.DESTRUCTIVE_COLOR, font_size=8, padx=5, pady=2)
            buttons['cancel_color'].pack(side=tk.LEFT)

            buttons['color_adjust_frame'] = color_adjust_frame # Keep reference to the frame

            self.action_buttons_list.append(buttons)

    # Sets up keyboard shortcuts
    def setup_keybinds(self):
        self.controller.bind('<Escape>', self.handle_escape)
        self.controller.bind('<Left>', self.prev_pair)
        self.controller.bind('<Right>', self.next_pair)
        self.controller.bind('<Delete>', self.delete_current_pair)
        self.controller.bind('<MouseWheel>', self.on_mouse_wheel)
        self.controller.bind('<Button-4>', self.on_mouse_wheel)
        self.controller.bind('<Button-5>', self.on_mouse_wheel)

    # Handles the Escape key press
    def handle_escape(self, event=None):
        # self.controller is the root App instance
        if self.controller.is_fullscreen:
            self.controller.toggle_fullscreen() # Use the toggle to exit fullscreen
        else:
            self.exit_app() # The original behavior of closing the app

    # Updates the image display
    def update_display(self, animated=True, direction=0):
        # The 'animated' parameter is now largely ignored as animations are removed.
        if self.is_animating: return
        for i, canvas in enumerate(self.image_canvases):
            path_index = self.current_index + i
            if path_index < len(self.image_files):
                canvas.load_image(self.image_files[path_index], timeout_ms=self.image_load_timeout_ms)
            else:
                canvas.clear()

        paths_to_keep = set()
        for i in range(max(0, self.current_index - 2), min(len(self.image_files), self.current_index + 4)):
            if i < len(self.image_files):
                paths_to_keep.add(self.image_files[i])
                self._queue_for_preload(self.image_files[i])
        self._clean_cache(paths_to_keep)

        if not self.image_files:
            self.status_label.config(text="Αναμονή για εικόνες...")
        else:
            total_pages = len(self.image_files)
            current_page_num = self.current_index + 1
            has_right_page = (self.current_index + 1) < len(self.image_files)
            status_text = f"Σελίδες {current_page_num}-{current_page_num+1} από {total_pages}" if has_right_page else f"Σελίδα {current_page_num} από {total_pages}"
            self.status_label.config(text=status_text)

        self._check_and_update_breathing_animation() # Re-evaluate breathing after display update

    # Shows a snackbar message
    def show_snackbar(self, message, msg_type='info'):
        if hasattr(self, 'snackbar_timer') and self.snackbar_timer: self.after_cancel(self.snackbar_timer)
        if hasattr(self, 'snackbar_label') and self.snackbar_label and self.snackbar_label.winfo_exists(): self.snackbar_label.destroy()
        colors = {'info': Style.SUCCESS_COLOR, 'error': Style.DESTRUCTIVE_COLOR, 'warning': Style.WARNING_COLOR}
        bg_color = colors.get(msg_type, Style.BTN_BG)
        self.snackbar_label = tk.Label(self.controller, text=message, bg=bg_color, fg="#ffffff", font=Style.get_font(11), padx=20, pady=10)
        self.snackbar_label.place(relx=0.5, rely=1.0, anchor='s')
        # No animation for snackbar, just show it instantly
        self.snackbar_label.place_configure(rely=0.95)
        self.snackbar_timer = self.after(3000, lambda: self.snackbar_label.destroy())

    # Creates a backup of a file
    def create_backup(self, file_path):
        if not file_path or not os.path.exists(file_path): return
        os.makedirs(BACKUP_DIR, exist_ok=True)
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(file_path))
        if not os.path.exists(backup_path): shutil.copy(file_path, backup_path)

    # Saves an image to disk
    def save_image_to_disk(self, canvas, image_obj):
        if not canvas.image_path: return
        self.create_backup(canvas.image_path)
        try:
            image_obj.save(canvas.image_path)
            self.show_snackbar(f"Αποθηκεύτηκε: '{os.path.basename(canvas.image_path)}'", 'info')
        except Exception as e:
            self.show_snackbar(f"Αποτυχία αποθήκευσης εικόνας: {e}", 'error')

    # Invalidates the cache for a specific path
    def invalidate_cache_for_path(self, path):
        with self.cache_lock:
            img_to_close = self.image_cache.pop(path, None)
            if img_to_close: img_to_close.close()

    # Starts a specific mode (crop or split)
    def start_mode(self, mode, canvas):
        if self.current_mode: # Already in a mode
            self.show_snackbar(f"Είστε ήδη σε λειτουργία {self.current_mode}. Παρακαλώ ολοκληρώστε ή ακυρώστε πρώτα.", 'warning')
            return

        if not canvas.image_path:
            self.show_snackbar("Δεν υπάρχει εικόνα για επεξεργασία.", 'warning')
            return

        self.current_mode = mode
        self.active_canvas = canvas
        self.set_editing_state(True) # Disable auto-navigation

        # Hide normal navigation/action buttons
        self.prev_btn.pack_forget()
        self.next_btn.pack_forget()
        self.jump_to_end_btn.pack_forget()
        self.delete_pair_btn.pack_forget()
        self.refresh_btn.pack_forget() # Hide refresh button

        # Hide action buttons for all canvases initially
        for i, c in enumerate(self.image_canvases):
            # Hide all action buttons and color adjustment frame
            for btn_name, btn_widget in self.action_buttons_list[i].items():
                if btn_name not in ['angle_slider', 'brightness_slider', 'contrast_slider', 'color_adjust_frame']:
                    btn_widget.pack_forget()
            self.action_buttons_list[i]['rot_left'].master.pack_forget() # Hide rotation frame
            self.action_buttons_list[i]['color_adjust_frame'].pack_forget() # Hide color adjust frame


        if mode == 'split':
            canvas.enter_splitting_mode()
            self.complete_split_btn.pack(side=tk.LEFT, padx=5)
            self.cancel_split_btn.pack(side=tk.LEFT, padx=5)
            self.complete_split_btn.config(state=tk.NORMAL) # Ensure buttons are enabled when entering mode
            self.cancel_split_btn.config(state=tk.NORMAL)
            self.show_snackbar("Λειτουργία διαχωρισμού: Μετακινήστε τη γραμμή και πατήστε 'Ολοκλήρωση Διαχωρισμού'.", 'info')

    # Exits the current mode (crop or split)
    def exit_mode(self):
        if self.current_mode == 'split' and self.active_canvas:
            self.active_canvas.exit_splitting_mode()

        self.current_mode = None
        self.active_canvas = None
        # The overall editing state is now determined by whether any canvas is still edited
        self.set_editing_state(any(c.is_edited for c in self.image_canvases))

        # Show normal navigation/action buttons
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        self.jump_to_end_btn.pack(side=tk.LEFT, padx=5)
        self.refresh_btn.pack(side=tk.LEFT, padx=5) # Show refresh button
        self.delete_pair_btn.pack(side=tk.RIGHT)

        # Hide split/complete buttons
        # Ensure they are re-enabled before packing them away
        self.complete_split_btn.config(state=tk.NORMAL)
        self.cancel_split_btn.config(state=tk.NORMAL)
        self.complete_split_btn.pack_forget()
        self.cancel_split_btn.pack_forget()

        # Show action buttons for all canvases
        for i, c in enumerate(self.image_canvases):
            # Only pack buttons that are relevant (e.g., not the angle slider)
            for btn_name, btn_widget in self.action_buttons_list[i].items():
                if btn_name not in ['angle_slider', 'brightness_slider', 'contrast_slider', 'color_adjust_frame']:
                    btn_widget.pack(side=tk.LEFT, padx=3)
            # Re-pack the rotation frame for each canvas
            self.action_buttons_list[i]['rot_left'].master.pack(pady=(5,0)) # Re-pack the parent frame
            self.action_buttons_list[i]['color_adjust_frame'].pack(pady=(5,0)) # Re-pack color adjust frame

        self.update_display(animated=False) # Refresh display to ensure correct state

    # Performs a crop operation
    def perform_crop(self, canvas):
        if not canvas.image_path: return
        if not canvas.is_cropped_or_rotated: # Check if anything has been changed
            self.show_snackbar("Δεν έχουν γίνει αλλαγές για περικοπή.", 'info')
            return

        coords = canvas.get_crop_coords()
        if not coords:
            self.show_snackbar("Δεν ήταν δυνατή η λήψη συντεταγμένων περικοπής.", 'error')
            return

        # Apply current brightness/contrast to the image before cropping and saving
        img_to_save = canvas._apply_color_filters(canvas.original_image.copy(), canvas.brightness, canvas.contrast)
        img_to_save = img_to_save.crop(coords)

        self.save_image_to_disk(canvas, img_to_save)
        self.invalidate_cache_for_path(canvas.image_path)
        canvas.load_image(canvas.image_path) # Reload to reset adjustments and show saved state
        canvas.is_cropped_or_rotated = False # Reset flag after crop and save
        canvas.is_color_adjusted = False # Reset color adjustments after saving

        # After saving, we need to re-evaluate if any other canvas is still 'edited'
        any_canvas_edited = any(c.is_edited for c in self.image_canvases)
        self.set_editing_state(any_canvas_edited) # Update global editing state

        self.show_snackbar("Εικόνα περικοπήκε και αποθηκεύτηκε.", 'info')

    # Saves color adjustments for a given canvas
    def save_color_adjustments(self, canvas):
        canvas.save_color_adjustments()

    # Cancels color adjustments for a given canvas
    def cancel_color_adjustments(self, canvas):
        canvas.reset_color_adjustments()


    # Completes the split operation
    def complete_split(self):
        if not self.active_canvas or not self.active_canvas.image_path:
            self.show_snackbar("Δεν υπάρχει ενεργή εικόνα για διαχωρισμό.", 'error')
            self.cancel_split() # Exit mode
            return

        split_x_coord = self.active_canvas.get_split_x_coord()
        if split_x_coord is None:
            self.show_snackbar("Δεν ήταν δυνατή η λήψη συντεταγμένων διαχωρισμού.", 'error')
            self.cancel_split() # Exit mode
            return

        original_path = self.active_canvas.image_path

        try:
            original_image = Image.open(original_path)
            img_w, img_h = original_image.size

            # Ensure split_x_coord is valid (not at the very edges)
            if split_x_coord <= 0 or split_x_coord >= img_w:
                self.show_snackbar("Η γραμμή διαχωρισμού πρέπει να βρίσκεται εντός των ορίων της εικόνας.", 'warning')
                return

            # Perform the split in a worker thread
            if self.is_transfer_active: self.show_snackbar("Η λειτουργία βρίσκεται σε εξέλιξη.", 'warning'); return
            self.is_transfer_active = True
            self._set_transfer_buttons_state(tk.DISABLED) # Disable main transfer buttons
            self.complete_split_btn.config(state=tk.DISABLED) # Disable split buttons during operation
            self.cancel_split_btn.config(state=tk.DISABLED)
            self.show_snackbar("Διαχωρισμός εικόνας...", 'info')

            self.transfer_thread = threading.Thread(
                target=self._transfer_operation_worker,
                args=('split_image', (original_path, split_x_coord)),
                daemon=True
            )
            self.transfer_thread.start()

        except Exception as e:
            self.show_snackbar(f"Αποτυχία προετοιμασίας διαχωρισμού: {e}", 'error')
            self.cancel_split() # Exit mode if error
        finally:
            # Exit mode will be called after the worker thread finishes and processes its result
            pass # Do not call exit_mode here directly, let the queue processing handle it

    # Cancels the split operation
    def cancel_split(self):
        if self.active_canvas:
            self.active_canvas.exit_splitting_mode()
        self.show_snackbar("Ο διαχωρισμός ακυρώθηκε.", 'info')
        self.exit_mode()
        # update_display is called by exit_mode

    # Deletes a single image
    def perform_delete_single(self, canvas):
        if not canvas.image_path: return
        file_path = canvas.image_path
        if not messagebox.askyesno("Επιβεβαίωση Διαγραφής", f"Οριστική διαγραφή αυτής της εικόνας;\n\n{os.path.basename(file_path)}"): return
        if self.observer: self.observer.stop(); self.observer.join()
        try:
            original_index = self.image_files.index(file_path)
            os.remove(file_path)
            self.show_snackbar(f"Διαγράφηκε: '{os.path.basename(file_path)}'", 'info')
            self.image_files.pop(original_index)
            if original_index <= self.current_index:
                self.current_index = max(0, self.current_index - 1)
            # After deletion, re-evaluate editing state
            self.set_editing_state(any(c.is_edited for c in self.image_canvases))
            self.update_display(animated=False) # Refresh display after deletion
        except Exception as e:
            self.show_snackbar(f"Αποτυχία διαγραφής εικόνας: {e}", 'error')
        finally:
            self.start_watcher()

    # Restores an image from backup
    def perform_restore(self, canvas):
        if not canvas.image_path: return
        backup_path = os.path.join(BACKUP_DIR, os.path.basename(canvas.image_path))
        if not os.path.exists(backup_path): self.show_snackbar("Δεν βρέθηκε αντίγραφο ασφαλείας.", 'warning'); return
        if not messagebox.askyesno("Επιβεβαίωση Επαναφοράς", "Αντικατάσταση των επεξεργασιών με την αρχική εικόνα;"): return
        try:
            shutil.copy(backup_path, canvas.image_path)
            self.invalidate_cache_for_path(canvas.image_path)
            canvas.load_image(canvas.image_path) # load_image will reset color adjustments
            canvas.is_cropped_or_rotated = False
            # After restore, re-evaluate editing state
            self.set_editing_state(any(c.is_edited for c in self.image_canvases))
            self.show_snackbar("Η εικόνα επαναφέρθηκε από το αντίγραφο ασφαλείας.", 'info')
        except Exception as e:
            self.show_snackbar(f"Αποτυχία επαναφοράς εικόνας: {e}", 'error')

    # Adds a new image to the list
    def add_new_image(self, path):
        self.image_files = [f for f in self.image_files if os.path.exists(f)]
        if path not in self.image_files and os.path.splitext(path)[1].lower() in ALLOWED_EXTENSIONS:
            self.image_files.append(path)
            # Sort using the natural_sort_key
            try: self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            except FileNotFoundError:
                self.image_files = [f for f in self.image_files if os.path.exists(f)]
                self.image_files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))

            # Log timestamp for live performance
            self.scan_timestamps.append(time.time())

            if hasattr(self, 'update_timer') and self.update_timer: self.after_cancel(self.update_timer)
            # Only auto-navigate if not in an editing mode
            if self.current_mode is None:
                self.update_timer = self.after(300, self._update_to_latest_pair)
            else:
                self._check_and_update_breathing_animation() # New image detected while editing

    # Updates the view to the latest pair of images
    def _update_to_latest_pair(self):
        if self.current_mode is not None: return # Do not auto-navigate if in an editing mode
        self.update_timer = None
        new_index = len(self.image_files) - 2 if len(self.image_files) >= 2 else 0
        if new_index < 0 and len(self.image_files) > 0: # Handle case where only one image is left
            new_index = 0
        self.current_index = max(0, new_index)
        self.update_display(direction=1)
        self._check_and_update_breathing_animation() # Re-evaluate breathing after auto-navigation

    # Creates a new book folder and moves scans
    def create_new_book(self):
        book_name = self.qr_entry.get().strip()
        if not book_name: self.show_snackbar("Παρακαλώ δώστε ένα όνομα βιβλίου.", 'warning'); return
        scanned_files = [os.path.join(self.scan_directory, f) for f in os.listdir(self.scan_directory) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
        if not scanned_files: self.show_snackbar("Ο φάκελος σάρωσης είναι άδειος.", 'info'); return
        if self.is_transfer_active: self.show_snackbar("Η μεταφορά βρίσκεται σε εξέλιξη.", 'warning'); return
        self.is_transfer_active = True
        self._set_transfer_buttons_state(tk.DISABLED)
        self.show_snackbar("Δημιουργία νέου βιβλίου...", 'info')
        self.transfer_thread = threading.Thread(target=self._transfer_operation_worker, args=('create_book', (book_name, scanned_files)), daemon=True)
        self.transfer_thread.start()

    # Transfers books to their respective city data folders
    def transfer_to_data(self):
        try:
            books_in_today_folder = [d for d in os.listdir(self.todays_books_folder) if os.path.isdir(os.path.join(self.todays_books_folder, d))]
        except FileNotFoundError:
            self.show_snackbar(f"Ο φάκελος '{self.todays_books_folder}' δεν βρέθηκε.", 'error')
            return

        if not books_in_today_folder:
            self.show_snackbar("Δεν υπάρχουν βιβλία για μεταφορά.", 'info')
            return

        moves_to_confirm = []
        warnings = []

        # Regex to find the 3-digit city code, allowing for no spaces
        code_pattern = re.compile(r'-(\d{3})-')

        for book_name in books_in_today_folder:
            match = code_pattern.search(book_name)
            if not match:
                warnings.append(f"Δεν βρέθηκε κωδικός πόλης για το βιβλίο: {book_name}")
                continue

            city_code = match.group(1)
            city_path = self.city_paths.get(city_code)

            if not city_path:
                warnings.append(f"Δεν υπάρχει ρύθμιση για τον κωδικό πόλης '{city_code}' (Βιβλίο: {book_name})")
                continue

            if not os.path.isdir(city_path):
                warnings.append(f"Ο κατάλογος για τον κωδικό '{city_code}' δεν βρέθηκε: {city_path}")
                continue

            # Check for existing date folder (DD-MM, D-MM, D-M)
            today = datetime.now()
            day, month = today.day, today.month
            date_formats_to_check = [f"{day:02d}-{month:02d}", f"{day}-{month:02d}", f"{day}-{month}"]

            date_folder_path = None
            for fmt in date_formats_to_check:
                path_to_check = os.path.join(city_path, fmt)
                if os.path.isdir(path_to_check):
                    date_folder_path = path_to_check
                    break

            # If no date folder exists, determine the new one to create
            if not date_folder_path:
                new_date_folder_name = today.strftime('%d-%m')
                date_folder_path = os.path.join(city_path, new_date_folder_name)

            source_path = os.path.join(self.todays_books_folder, book_name)
            moves_to_confirm.append({
                'source': source_path,
                'destination_folder': date_folder_path,
                'book_name': book_name
            })

        if not moves_to_confirm and not warnings:
            self.show_snackbar("Δεν βρέθηκαν βιβλία με έγκυρους κωδικούς πόλης.", 'info')
            return

        # Build confirmation message
        confirmation_message = "Θα πραγματοποιηθούν οι παρακάτω μεταφορές:\n\n"
        for move in moves_to_confirm:
            confirmation_message += f"'{move['book_name']}'\n  -> '{move['destination_folder']}'\n"

        if warnings:
            confirmation_message += "\nΠροειδοποιήσεις:\n" + "\n".join(warnings)

        confirmation_message += "\n\nΕίστε σίγουροι ότι θέλετε να συνεχίσετε;"

        if not messagebox.askyesno("Επιβεβαίωση Μεταφοράς", confirmation_message):
            return

        # Start the worker thread
        if self.is_transfer_active: self.show_snackbar("Η λειτουργία βρίσκεται σε εξέλιξη.", 'warning'); return
        self.is_transfer_active = True
        self._set_transfer_buttons_state(tk.DISABLED)
        self.show_snackbar("Μεταφορά βιβλίων στα data πόλεων...", 'info')
        self.transfer_thread = threading.Thread(target=self._transfer_operation_worker, args=('transfer_to_data', moves_to_confirm), daemon=True)
        self.transfer_thread.start()


    # Deletes the current pair of images
    def delete_current_pair(self, event=None):
        if self.is_animating or not self.image_files or self.current_mode is not None: return # Prevent deletion in editing mode
        left_path = self.image_files[self.current_index] if self.current_index < len(self.image_files) else None
        right_path = self.image_files[self.current_index + 1] if (self.current_index + 1) < len(self.image_files) else None
        files_to_delete = [p for p in [left_path, right_path] if p]
        if not files_to_delete: return
        files_str = " και ".join([os.path.basename(f) for f in files_to_delete])
        if not messagebox.askyesno("Επιβεβαίωση Διαγραφής", f"Οριστική διαγραφή\n{files_str};"): return
        if self.is_transfer_active: self.show_snackbar("Η λειτουργία βρίσκεται σε εξέλιξη.", 'warning'); return
        self.is_transfer_active = True
        self._set_transfer_buttons_state(tk.DISABLED)
        self.show_snackbar(f"Διαγράφηκε: {files_str}...", 'info')
        self.transfer_thread = threading.Thread(target=self._transfer_operation_worker, args=('delete_pair', files_to_delete), daemon=True)
        self.transfer_thread.start()

    # Navigates to the previous pair
    def prev_pair(self, event=None):
        if self.is_animating or self.current_index <= 0 or self.current_mode is not None: return # Prevent navigation in editing mode
        self.current_index = max(0, self.current_index - 2)
        self.update_display(direction=-1)
        self._stop_jump_button_breathing() # Stop breathing when navigating away from new pages

    # Navigates to the next pair
    def next_pair(self, event=None):
        if self.is_animating or self.current_index + 2 >= len(self.image_files) or self.current_mode is not None: return # Prevent navigation in editing mode
        self.current_index += 2
        self.update_display(direction=1)
        self._stop_jump_button_breathing() # Stop breathing when navigating to new pages

    # Jumps to the last pair
    def jump_to_end(self):
        if not self.image_files: self.show_snackbar("Δεν υπάρχουν εικόνες για μετάβαση.", 'info'); return
        if self.current_mode is not None: return # Prevent navigation in editing mode
        new_index = len(self.image_files) - 2 if len(self.image_files) >= 2 else 0
        if self.current_index == new_index: self.show_snackbar("Ήδη στο τελευταίο ζεύγος.", 'info'); return
        self.current_index = max(0, new_index)
        self.update_display(animated=False)
        self._stop_jump_button_breathing() # Stop breathing when navigating to the end

    # Handles mouse wheel navigation
    def on_mouse_wheel(self, event):
        if any(canvas.is_zoomed for canvas in self.image_canvases): return "break"
        if self.is_animating or self.current_mode is not None: return # Prevent navigation in editing mode
        if event.num == 4 or event.delta > 0: self.prev_pair()
        elif event.num == 5 or event.delta < 0: self.next_pair()
        return "break"

    # Refreshes the scan folder by triggering an initial scan
    def refresh_scan_folder(self):
        if self.current_mode is not None:
            self.show_snackbar("Παρακαλώ ολοκληρώστε ή ακυρώστε την τρέχουσα λειτουργία επεξεργασίας.", 'warning')
            return
        self.show_snackbar("Ανανέωση φακέλου σάρωσης...", 'info')
        self.scan_worker_command_queue.put(('initial_scan', self.scan_directory))
        # Clear image cache to ensure all images are reloaded
        self._clean_cache(set())
        self.current_index = 0 # Reset index to start after refresh
        self.update_display(animated=False) # Force update display immediately


    # Updates performance stats
    def update_stats(self):
        # Request full stats calculation from worker
        self.scan_worker_command_queue.put(('calculate_today_stats', None))

        # Calculate live performance locally
        now = time.time()
        # Remove timestamps older than the performance window
        while self.scan_timestamps and self.scan_timestamps[0] < now - PERFORMANCE_WINDOW_SECONDS:
            self.scan_timestamps.popleft()

        if self.scan_timestamps:
            # Calculate rate based on the number of scans in the window
            scans_in_window = len(self.scan_timestamps)
            # To be more accurate, calculate the actual time span
            time_span = now - self.scan_timestamps[0] if len(self.scan_timestamps) > 1 else PERFORMANCE_WINDOW_SECONDS
            time_span = max(time_span, 1) # Avoid division by zero
            scans_per_minute = (scans_in_window / time_span) * 60
            self.scans_min_label.config(text=f"Απόδοση: {scans_per_minute:.1f} σελ/λεπτό")
        else:
            # If no recent scans, show 0
            self.scans_min_label.config(text="Απόδοση: 0.0 σελ/λεπτό")

        # Schedule next update
        self.after(2000, self.update_stats) # Update live stats every 2 seconds

    # Counts pages in a given directory
    def _count_pages_in_folder(self, folder_path):
        count = 0
        try:
            if os.path.exists(folder_path) and os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                        count += 1
        except Exception as e:
            print(f"Error counting pages in {folder_path}: {e}")
        return count

    # Updates the Todays Books panel with folder names and page counts
    def _update_todays_books_panel(self):
        # Clear existing content in the frame within the canvas
        for widget in self.todays_books_frame.winfo_children():
            widget.destroy()

        try:
            # 1. Get books currently in the "today" folder
            current_book_folders = {}
            if os.path.isdir(self.todays_books_folder):
                for folder_name in os.listdir(self.todays_books_folder):
                    folder_path = os.path.join(self.todays_books_folder, folder_name)
                    if os.path.isdir(folder_path):
                        current_book_folders[folder_name] = self._count_pages_in_folder(folder_path)

            # 2. Get books already moved to data today from the log file
            moved_today_books = {}
            try:
                if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
                    with open(BOOKS_COMPLETE_LOG_FILE, 'r') as f:
                        log_data = json.load(f)
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    todays_entries = log_data.get(today_str, [])
                    for entry in todays_entries:
                        if isinstance(entry, dict) and "name" in entry:
                            moved_today_books[entry["name"]] = entry.get("pages", 0)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Could not read or parse log file for panel update: {e}")

            # 3. Combine and sort all book names for today
            all_book_names = sorted(list(set(current_book_folders.keys()) | set(moved_today_books.keys())))

            if not all_book_names:
                tk.Label(self.todays_books_frame, text="Δεν υπάρχουν βιβλία για σήμερα.",
                         bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(10)).pack(padx=10, pady=5, anchor='w')
                return

            # 4. Display the combined list
            for folder_name in all_book_names:
                display_name = folder_name[:20] + "..." if len(folder_name) > 20 else folder_name

                entry_frame = tk.Frame(self.todays_books_frame, bg=Style.FRAME_BG)
                entry_frame.pack(fill=tk.X, padx=5, pady=2)

                tk.Label(entry_frame, text=display_name,
                         bg=Style.FRAME_BG, fg=Style.FG_COLOR, font=Style.get_font(10, 'bold')).pack(side=tk.LEFT, anchor='w')

                if folder_name in moved_today_books:
                    page_count = moved_today_books[folder_name]
                    tk.Label(entry_frame, text=f" ({page_count} σελ.)",
                             bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(9)).pack(side=tk.LEFT, padx=(5,0), anchor='w')
                    tk.Label(entry_frame, text=" (DATA)",
                             bg=Style.FRAME_BG, fg=Style.SUCCESS_COLOR, font=Style.get_font(9, 'bold')).pack(side=tk.LEFT, padx=(5,0), anchor='w')
                else: # It must be in the current_book_folders
                    page_count = current_book_folders[folder_name]
                    tk.Label(entry_frame, text=f" ({page_count} σελίδες)",
                             bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(9)).pack(side=tk.LEFT, padx=(5,0), anchor='w')

        except Exception as e:
            tk.Label(self.todays_books_frame, text=f"Σφάλμα φόρτωσης βιβλίων: {e}",
                     bg=Style.FRAME_BG, fg=Style.DESTRUCTIVE_COLOR, font=Style.get_font(10)).pack(padx=10, pady=5, anchor='w')

        # Update scroll region after adding content
        self.todays_books_canvas.update_idletasks()
        self.todays_books_canvas.config(scrollregion=self.todays_books_canvas.bbox("all"))


    # Starts the file system watcher
    def start_watcher(self):
        if hasattr(self, 'observer') and self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
        event_handler = NewImageHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.scan_directory, recursive=False)
        self.observer.start()

    # Exits the application
    def exit_app(self, event=None):
        if hasattr(self, 'observer') and self.observer:
            self.preload_queue.put(None)
            if self.preload_thread.is_alive():
                self.preload_thread.join()
            if self.observer.is_alive():
                self.observer.stop()
                self.observer.join()

            # Stop the scan worker
            self.scan_worker_command_queue.put(('stop', None))
            if self.scan_worker.is_alive():
                self.scan_worker.join()

        self.controller.destroy()
