import sys
import os
import time
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, font, ttk
from PIL import Image, ImageTk, ImageOps, ImageEnhance
import colorsys
import json
import math
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import queue
import re # Import re for natural sorting
from datetime import datetime # Import datetime for date handling
from collections import deque # Import deque for live performance tracking

# This code only runs when the app is bundled into an .exe
if getattr(sys, 'frozen', False):
    try:
        from tufup.client import Client
        APP_NAME = 'DigiPage'
        REPO_URL = 'https://raw.githubusercontent.com/morphles/MorScanner/main/'
        client = Client(app_name=APP_NAME, repo_url=REPO_URL)
        # Check for updates, but don't block the UI
        if client.update(confirm=False):
            messagebox.showinfo(
                'Διαθέσιμη Ενημέρωση',
                'Μια νέα έκδοση του DigiPage είναι διαθέσιμη και θα εγκαταλλήσει κατά την έξοδο.'
            )
    except Exception as e:
        # Show a non-blocking error message to the user
        messagebox.showerror(
            'Αποτυχία Ελέγχου Ενημέρωσης',
            f"Δεν ήταν δυνατός ο έλεγχος για ενημερώσεις. Παρακαλώ ελέγξτε τη σύνδεσή σας στο διαδρόμο.\n\nΣφάλμα: {e}"
        )

# Helper functions for color manipulation
def lighten_color(hex_color, factor=0.1):
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = min(1.0, hls[1] + factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

def darken_color(hex_color, factor=0.1):
    hex_color = hex_color.lstrip('#')
    rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    hls = colorsys.rgb_to_hls(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    new_l = max(0.0, hls[1] - factor)
    new_rgb = colorsys.hls_to_rgb(hls[0], new_l, hls[2])
    return '#%02x%02x%02x' % (int(new_rgb[0]*255), int(new_rgb[1]*255), int(new_rgb[2]*255))

# --- UI Style Configuration ---
THEMES = {
    "Neutral Grey": {
        "BG_COLOR": "#2b2b2b", "FG_COLOR": "#bbbbbb", "TEXT_SECONDARY_COLOR": "#888888",
        "BTN_BG": "#3c3f41", "BTN_FG": "#f0f0f0",
        "ACCENT_COLOR": "#8A8F94", "FRAME_BG": "#333333", "FRAME_BORDER": "#444444",
        "TOOLTIP_BG": "#252526", "TOOLTIP_FG": "#ffffff",
        # Special buttons
        "SUCCESS_COLOR": "#28a745", "DESTRUCTIVE_COLOR": "#dc3545", "WARNING_COLOR": "#ffc107",
        "JUMP_BTN_BREATHE_COLOR": "#6495ED", "TRANSFER_BTN_COLOR": "#ff8c00", "CROP_BTN_COLOR": "#007bff",
    },
    "Blue": {
        "BG_COLOR": "#262D3F", "FG_COLOR": "#D0D5E8", "TEXT_SECONDARY_COLOR": "#8993B3",
        "BTN_BG": "#3A435E", "BTN_FG": "#E1E6F5",
        "ACCENT_COLOR": "#6C95FF", "FRAME_BG": "#2C354D", "FRAME_BORDER": "#3E486B",
        "TOOLTIP_BG": "#202533", "TOOLTIP_FG": "#ffffff",
        # Special buttons
        "SUCCESS_COLOR": "#33B579", "DESTRUCTIVE_COLOR": "#FF6B6B", "WARNING_COLOR": "#FFD166",
        "JUMP_BTN_BREATHE_COLOR": "#FFD166", "TRANSFER_BTN_COLOR": "#EF9595", "CROP_BTN_COLOR": "#4DB6AC",
    },
    "Pink": {
        "BG_COLOR": "#3D2A32", "FG_COLOR": "#F5DDE7", "TEXT_SECONDARY_COLOR": "#A8939D",
        "BTN_BG": "#5C3F4A", "BTN_FG": "#FCEAF1",
        "ACCENT_COLOR": "#FF80AB", "FRAME_BG": "#4A333D", "FRAME_BORDER": "#664553",
        "TOOLTIP_BG": "#302228", "TOOLTIP_FG": "#ffffff",
        # Special buttons
        "SUCCESS_COLOR": "#50C878", "DESTRUCTIVE_COLOR": "#FF6961", "WARNING_COLOR": "#FFD700",
        "JUMP_BTN_BREATHE_COLOR": "#6495ED", "TRANSFER_BTN_COLOR": "#87CEEB", "CROP_BTN_COLOR": "#9370DB",
    }
}

class DynamicStyle:
    FONT_FAMILY = ('Segoe UI', 'Calibri', 'Helvetica', 'Arial')

    def __init__(self):
        self.theme_name = "Neutral Grey"

    def get_font(self, size=10, weight='normal'):
        return (self.FONT_FAMILY[0], size, weight)

    def load_theme(self, theme_name):
        self.theme_name = theme_name
        theme_data = THEMES.get(theme_name, THEMES["Neutral Grey"])
        for key, value in theme_data.items():
            setattr(self, key, value)

        # Update derived colors
        self.BTN_HOVER_BG = lighten_color(self.BTN_BG, 0.1)
        self.BTN_PRESS_BG = darken_color(self.BTN_BG, 0.1)

Style = DynamicStyle()
Style.load_theme("Neutral Grey") # Load a default theme immediately

# --- App Configuration ---
ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
BACKUP_DIR = "scan_viewer_backups"
CONFIG_FILE = "scan_viewer_config.json"
BOOKS_COMPLETE_LOG_FILE = "books_complete_log.json"
DEFAULT_IMAGE_LOAD_TIMEOUT_MS = 2000
PERFORMANCE_WINDOW_SECONDS = 20 # Window for live performance calculation


class ToolTip:
    # Initializes the tooltip
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.schedule_show)
        self.widget.bind("<Leave>", self.cancel_show)

    # Schedules the tooltip to appear
    def schedule_show(self, event):
        self.id = self.widget.after(500, lambda: self.show_tooltip(event))

    # Hides the tooltip
    def cancel_show(self, event):
        if self.id: self.widget.after_cancel(self.id)
        if self.tooltip_window: self.tooltip_window.destroy()
        self.tooltip_window = None

    # Creates and displays the tooltip window
    def show_tooltip(self, event):
        if self.tooltip_window: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT, background=Style.TOOLTIP_BG, foreground=Style.TOOLTIP_FG, relief=tk.SOLID, borderwidth=1, font=Style.get_font(9))
        label.pack(ipadx=8, ipady=5)
        self.tooltip_window = tw

class ZoomPanCanvas(tk.Canvas):
    # Initializes the canvas for image display, zoom, and pan
    def __init__(self, parent, app_ref):
        super().__init__(parent, bg=Style.BG_COLOR, highlightthickness=0)
        self.app_ref = app_ref
        self.true_original_image = self.original_image = self.image_path = self.photo_image = self.canvas_image_id = None
        self.zoom_level, self.is_zoomed, self.animation_id, self.rotation_angle = 1.0, False, None, 0
        self.crop_rect_id, self.crop_handles, self.drag_info = None, {}, {'item': None, 'x': 0, 'y': 0}
        self.hq_redraw_timer = self.angle_slider = None
        self.is_cropped_or_rotated = False

        # New: Color adjustment attributes
        self.brightness = 0.0 # -1.0 to 1.0
        self.contrast = 1.0   # 0.0 to 2.0
        self.is_color_adjusted = False
        self.brightness_slider = None
        self.contrast_slider = None

        # New: Splitting mode variables
        self.is_splitting_mode = False
        self.split_line_id = None
        self.split_line_x_ratio = 0.5 # Relative position of the split line (0.0 to 1.0)

        self.bind_events()

        # Trail animation properties (reverted to trail)
        self.trail_line_ids = [] # To store IDs of trail segments
        self.trail_animation_id = None # To manage the animation loop
        self.trail_color = "#8cf2ff" # Cornflower Blue
        self.trail_width = 6
        self.trail_glow_color = darken_color(self.trail_color, factor=0.2) # A darker version for the glow
        self.trail_glow_width = 9 # Slightly wider for the glow effect
        self.trail_duration_ms = 1500 # 1 second
        self.trail_segment_ratio = 0.15 # Length of the "snake" relative to half-perimeter (made smaller)

    def update_theme(self):
        self.config(bg=Style.BG_COLOR)
        if self.crop_rect_id:
            self.itemconfig(self.crop_rect_id, outline=Style.ACCENT_COLOR)
            for handle in self.crop_handles.values():
                self.itemconfig(handle, fill=Style.ACCENT_COLOR, outline=Style.BG_COLOR)
        if self.split_line_id:
            self.itemconfig(self.split_line_id, fill=Style.ACCENT_COLOR)
        self.trail_color = Style.ACCENT_COLOR
        self.trail_glow_color = darken_color(self.trail_color, factor=0.2)

    # Property to check if the canvas content is edited (cropped/rotated or color adjusted)
    @property
    def is_edited(self):
        return self.is_cropped_or_rotated or self.is_color_adjusted

    # Binds mouse and keyboard events to canvas methods
    def bind_events(self):
        self.bind("<Double-1>", self.toggle_zoom_instant)
        self.bind("<ButtonPress-1>", self.on_button_press)
        self.bind("<B1-Motion>", self.on_b1_motion)
        self.bind("<ButtonRelease-1>", self.on_button_release)
        self.bind("<Configure>", self.on_resize)
        self.bind('<MouseWheel>', self.on_mouse_wheel_zoom)
        self.bind('<Button-4>', self.on_mouse_wheel_zoom)
        self.bind('<Button-5>', self.on_mouse_wheel_zoom)

    # Loads an image from a path with a timeout
    def load_image(self, path, timeout_ms=DEFAULT_IMAGE_LOAD_TIMEOUT_MS):
        self.image_path = path
        # Reset color adjustments when loading a new image
        self.brightness = 0.0
        self.contrast = 1.0
        self.is_color_adjusted = False
        if self.brightness_slider: self.brightness_slider.set(0.0)
        if self.contrast_slider: self.contrast_slider.set(1.0)

        with self.app_ref.cache_lock:
            if path in self.app_ref.image_cache:
                self.true_original_image = self.app_ref.image_cache[path].copy()
                self.reset_view(show_snackbar=False)
                self._animate_border_trail() # Call animation here
                return

        retry_delay_ms = 50
        max_retries = int(timeout_ms / retry_delay_ms) if timeout_ms > 0 else 1
        for retries in range(max_retries):
            try:
                img_temp = Image.open(path)
                img_temp.verify()
                self.true_original_image = Image.open(path)
                self.reset_view(show_snackbar=False)
                with self.app_ref.cache_lock:
                    self.app_ref.image_cache[path] = self.true_original_image.copy()
                self._animate_border_trail() # Call animation here
                return
            except Exception:
                time.sleep(retry_delay_ms / 1000)

        self.original_image = None
        self.delete("all")

    # Clears the canvas
    def clear(self):
        self.delete("all")
        if self.true_original_image: self.true_original_image.close()
        if self.original_image: self.original_image.close()
        self.true_original_image = self.original_image = self.photo_image = self.canvas_image_id = self.image_path = None
        self.is_cropped_or_rotated = False
        self.is_color_adjusted = False # Clear color adjustment state
        self.is_splitting_mode = False # Clear splitting mode
        if self.split_line_id: self.delete(self.split_line_id); self.split_line_id = None # Clear split line
        # Reset slider positions
        if self.brightness_slider: self.brightness_slider.set(0.0)
        if self.contrast_slider: self.contrast_slider.set(1.0)

        # Also clear and stop trail animation when canvas is cleared
        if self.trail_animation_id:
            self.after_cancel(self.trail_animation_id)
            self.trail_animation_id = None
        for line_id in self.trail_line_ids:
            self.delete(line_id)
        self.trail_line_ids.clear()


    # Displays the image on the canvas
    def show_image(self):
        if not self.original_image: self.clear(); return
        self.is_zoomed = False
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            self.after(100, self.show_image); return
        self.xview_moveto(0); self.yview_moveto(0)
        img_w, img_h = self.original_image.size
        self.zoom_level = min(canvas_w / img_w, canvas_h / img_h)
        self.redraw_image()
        # Only draw crop box if not in splitting mode
        if not self.is_splitting_mode:
            self.draw_crop_box()

    # Redraws the image with a given quality and transparency
    def redraw_image(self, temp_image=None, quality=Image.Resampling.LANCZOS, alpha=255):
        # Apply current color adjustments if not a temporary image (e.g., rotation preview)
        if temp_image is None:
            image_to_draw = self._apply_color_filters(self.original_image.copy(), self.brightness, self.contrast)
        else:
            image_to_draw = self._apply_color_filters(temp_image.copy(), self.brightness, self.contrast)

        if not image_to_draw:
            if self.canvas_image_id: self.delete(self.canvas_image_id)
            self.canvas_image_id = None
            return

        img_w, img_h = image_to_draw.size
        new_width, new_height = int(img_w * self.zoom_level), int(img_h * self.zoom_level)
        if new_width < 1 or new_height < 1:
            if self.canvas_image_id: self.delete(self.canvas_image_id)
            self.canvas_image_id = None
            return

        resized_img = image_to_draw.resize((new_width, new_height), quality)
        if alpha < 255:
            resized_img = resized_img.convert("RGBA")
            alpha_layer = Image.new("L", resized_img.size, alpha)
            resized_img.putalpha(alpha_layer)

        self.photo_image = ImageTk.PhotoImage(resized_img)
        if self.canvas_image_id: self.delete(self.canvas_image_id)
        self.canvas_image_id = self.create_image(self.winfo_width()/2, self.winfo_height()/2, anchor=tk.CENTER, image=self.photo_image)
        try:
            if self.canvas_image_id and self.type(self.canvas_image_id):
                self.tag_lower(self.canvas_image_id)
        except tk.TclError as e:
            print(f"ERROR: TclError during tag_lower: {e}")

    # Draws the crop box with handles
    def draw_crop_box(self):
        self.delete(self.crop_rect_id)
        for handle in self.crop_handles.values(): self.delete(handle)
        self.crop_handles.clear()
        if not self.original_image or self.is_zoomed or self.is_splitting_mode: return # Don't draw if in splitting mode
        img_w, img_h = self.original_image.size
        disp_w, disp_h = img_w * self.zoom_level, img_h * self.zoom_level
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()
        x0, y0 = (canvas_w - disp_w) / 2, (canvas_h - disp_h) / 2
        x1, y1 = x0 + disp_w, y0 + disp_h
        self.crop_rect_id = self.create_rectangle(x0, y0, x1, y1, outline=Style.ACCENT_COLOR, width=2, dash=(6, 4), tags="crop_box")
        handle_size = 10
        handle_tags = {"nw":(x0,y0),"n":((x0+x1)/2,y0),"ne":(x1,y0),"w":(x0,(y0+y1)/2),"e":(x1,(y0+y1)/2),"sw":(x0,y1),"s":((x0+x1)/2,y1),"se":(x1,y1)}
        for tag, (x,y) in handle_tags.items():
            self.crop_handles[tag] = self.create_rectangle(x-handle_size/2, y-handle_size/2, x+handle_size/2, y+handle_size/2, fill=Style.ACCENT_COLOR, outline=Style.BG_COLOR, width=2, tags=("handle", tag))

    # Handles canvas resize events
    def on_resize(self, event):
        if not self.is_zoomed: self.show_image()
        # If in splitting mode, redraw split line on resize
        if self.is_splitting_mode:
            self.redraw_split_line()

    # Handles mouse button press
    def on_button_press(self, event):
        if self.is_zoomed:
            self.scan_mark(event.x, event.y)
            return

        if self.is_splitting_mode:
            # If clicking on the split line itself, allow drag
            item = self.find_closest(event.x, event.y)
            if item and "split_line" in self.gettags(item[0]):
                self._on_split_line_press(event)
            return # Prevent other drag actions when in splitting mode

        item = self.find_closest(event.x, event.y)
        if not item: return
        tags = self.gettags(item[0])
        if "handle" in tags or "crop_box" in tags: # If interacting with crop handles or box
            if self.app_ref.current_mode is None: # Only enter crop mode if not already in a mode
                self.app_ref.set_editing_state(True) # Set editing state for auto-navigation control

        self.drag_info['item'] = tags[1] if "handle" in tags else ("box" if "crop_box" in tags else None)
        self.drag_info['x'], self.drag_info['y'] = event.x, event.y
        # The set_editing_state is now handled above when drag starts
        # if self.drag_info['item']: self.app_ref.set_editing_state(True) # Removed redundant call


    # Handles mouse button release
    def on_button_release(self, event):
        if self.is_splitting_mode and self.drag_info.get('item') == 'split_line':
            self._on_split_line_release(event)
            return

        self.drag_info['item'] = None
        # The app_ref.set_editing_state will be handled by ImageScannerApp's mode management
        # any_canvas_edited = any(c.is_cropped_or_rotated for c in self.app_ref.image_canvases)
        # self.app_ref.set_editing_state(any_canvas_edited)

    # Handles mouse drag motion for crop box or split line
    def on_b1_motion(self, event):
        if self.is_zoomed:
            self.pan_image(event)
            return

        if self.is_splitting_mode and self.drag_info.get('item') == 'split_line':
            self._on_split_line_drag(event)
            return

        if not self.drag_info.get('item') or not self.crop_rect_id or not self.original_image: return
        dx, dy = event.x - self.drag_info['x'], event.y - self.drag_info['y']
        img_w, img_h = self.original_image.size
        disp_w, disp_h = img_w * self.zoom_level, img_h * self.zoom_level
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()
        img_tl_x, img_tl_y = (canvas_w - disp_w) / 2, (canvas_h - disp_h) / 2
        img_br_x, img_br_y = img_tl_x + disp_w, img_tl_y + disp_h
        x0, y0, x1, y1 = self.coords(self.crop_rect_id)
        item = self.drag_info['item']
        if item == "box":
            new_x0, new_y0 = x0 + dx, y0 + dy
            box_width, box_height = x1 - x0, y1 - y0
            constrained_x0 = max(img_tl_x, min(new_x0, img_br_x - box_width))
            constrained_y0 = max(img_tl_y, min(new_y0, img_br_y - box_height))
            self.coords(self.crop_rect_id, constrained_x0, constrained_y0, constrained_x0 + box_width, constrained_y0 + box_height)
        else:
            if 'n' in item: y0 += dy
            if 's' in item: y1 += dy
            if 'w' in item: x0 += dx
            if 'e' in item: x1 += dx
            final_x0, final_y0 = max(img_tl_x, x0), max(img_tl_y, y0)
            final_x1, final_y1 = min(img_br_x, x1), min(img_br_y, y1)
            if final_x1 < final_x0: final_x0, final_x1 = final_x1, final_x0
            if final_y1 < final_y0: final_y0, final_y1 = final_y1, final_y0
            self.coords(self.crop_rect_id, final_x0, final_y0, final_x1, final_y1)
        self.update_crop_handles()
        self.drag_info['x'], self.drag_info['y'] = event.x, event.y
        self.is_cropped_or_rotated = True
        self.app_ref.set_editing_state(True) # This is now handled by app_ref.current_mode

    # Updates crop handle positions
    def update_crop_handles(self):
        x0, y0, x1, y1 = self.coords(self.crop_rect_id)
        handle_size = 10
        coords = {"nw":(x0,y0),"n":((x0+x1)/2,y0),"ne":(x1,y0),"w":(x0,(y0+y1)/2),"e":(x1,(y0+y1)/2),"sw":(x0,y1),"s":((x0+x1)/2,y1),"se":(x1,y1)}
        for tag, (x,y) in coords.items(): self.coords(self.crop_handles[tag], x-handle_size/2, y-handle_size/2, x+handle_size/2, y+handle_size/2)

    # Gets crop coordinates relative to the original image
    def get_crop_coords(self):
        if not self.original_image or not self.crop_rect_id: return None
        img_w, img_h = self.original_image.size
        disp_w, disp_h = img_w * self.zoom_level, img_h * self.zoom_level
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()
        img_tl_x, img_tl_y = (canvas_w - disp_w) / 2, (canvas_h - disp_h) / 2
        cx0, cy0, cx1, cy1 = self.coords(self.crop_rect_id)
        crop_x0 = int((cx0 - img_tl_x) / self.zoom_level)
        crop_y0 = int((cy0 - img_tl_y) / self.zoom_level)
        crop_x1 = int((cx1 - img_tl_x) / self.zoom_level)
        crop_y1 = int((cy1 - img_tl_y) / self.zoom_level)
        return max(0, crop_x0), max(0, crop_y0), min(img_w, crop_x1), min(img_h, crop_y1)

    # Previews image rotation
    def preview_rotation(self, angle_str):
        if not self.true_original_image: return
        try:
            angle = float(angle_str)
            self.is_cropped_or_rotated = (angle % 360 != 0) # Only set to true if angle is not a multiple of 360
            temp_rotated = self._get_rotated_image(angle, self.true_original_image)
            self.redraw_image(temp_image=temp_rotated)
            self.app_ref.set_editing_state(self.is_edited) # Update global editing state
        except (ValueError, tk.TclError): pass

    # Applies rotation to the image
    def apply_rotation(self, angle, save_after=False):
        if not self.true_original_image: return
        self.app_ref.create_backup(self.image_path)
        self.rotation_angle = angle
        self.original_image = self._get_rotated_image(angle, self.true_original_image)
        self.is_cropped_or_rotated = (angle % 360 != 0)
        if save_after:
            # Apply current brightness/contrast to the image before saving
            final_image_to_save = self._apply_color_filters(self.original_image.copy(), self.brightness, self.contrast)
            self.app_ref.save_image_to_disk(self, final_image_to_save)
            self.app_ref.invalidate_cache_for_path(self.image_path)
            self.load_image(self.image_path) # Reload to reset adjustments and show saved state
            self.is_color_adjusted = False # Reset after saving
        else:
            self.show_image()
        self.app_ref.set_editing_state(self.is_edited) # Update global editing state


    # Helper to rotate an image
    def _get_rotated_image(self, angle, source_image, quality=Image.Resampling.BICUBIC):
        return source_image.rotate(angle, resample=quality, expand=True)

    # Resets the view to the original image
    def reset_view(self, show_snackbar=True):
        if not self.true_original_image: return
        self.original_image = self.true_original_image.copy()
        self.rotation_angle = 0
        if self.angle_slider: self.angle_slider.set(0)
        self.is_cropped_or_rotated = False
        self.reset_color_adjustments(show_snackbar=False) # Also reset color adjustments
        self.app_ref.set_editing_state(self.is_edited) # Update global editing state
        self.show_image()
        if show_snackbar: self.app_ref.show_snackbar(f"Η προβολή για το '{os.path.basename(self.image_path)}' έχει επαναφερθεί", 'info')

    # Pans the image
    def pan_image(self, event):
        if self.is_zoomed:
            self.scan_dragto(event.x, event.y, gain=1)

    # Toggles zoom instantly
    def toggle_zoom_instant(self, event):
        if not self.original_image: return
        if self.is_zoomed:
            self.show_image() # Revert to fit-to-canvas view
        else:
            self.is_zoomed = True
            self.delete(self.crop_rect_id)
            if self.crop_handles:
                [self.delete(h) for h in self.crop_handles.values()]
            self.zoom_level *= 1.2 # Minimal zoom
            self.redraw_image()
            # Adjust pan to center on click point
            img_x, img_y = self.canvasx(0) + event.x, self.canvasy(0) + event.y
            target_pan_x, target_pan_y = img_x - (self.winfo_width() / 2), img_y - (self.winfo_height() / 2)
            self.xview_moveto(target_pan_x / (self.winfo_width() * self.zoom_level))
            self.yview_moveto(target_pan_y / (self.winfo_height() * self.zoom_level))

    # Handles mouse wheel zoom
    def on_mouse_wheel_zoom(self, event):
        if not self.is_zoomed: return
        if self.hq_redraw_timer: self.after_cancel(self.hq_redraw_timer)
        factor = 1.1 if (event.num == 4 or event.delta > 0) else 0.9
        self.zoom_level = max(0.1, min(self.zoom_level * factor, 10.0))
        self.redraw_image(quality=Image.Resampling.BILINEAR)
        self.hq_redraw_timer = self.after(250, self.redraw_image)
        return "break"

    # Helper function for easing (quadratic ease-in-out)
    def _ease_in_out_quad(self, t):
        return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2

    # Helper to get point on the perimeter for trail animation
    def _get_point_on_perimeter(self, dist, x0, y0, x1, y1, direction='right'):
        width = x1 - x0
        height = y1 - y0

        # Calculate perimeter segments from top-center, going clockwise (right) or counter-clockwise (left)
        # Top-center to top-right/left
        seg1_len = width / 2
        # Top-right/left to bottom-right/left
        seg2_len = height
        # Bottom-right/left to bottom-center
        seg3_len = width / 2

        total_len = seg1_len + seg2_len + seg3_len

        # Clamp distance to the total length of this half-perimeter path
        dist = max(0.0, min(dist, total_len))

        if direction == 'right':
            # Segment 1: Top-center to Top-right
            if 0 <= dist <= seg1_len:
                x = x0 + width / 2 + dist
                y = y0
            # Segment 2: Top-right to Bottom-right
            elif seg1_len < dist <= seg1_len + seg2_len:
                x = x1
                y = y0 + (dist - seg1_len)
            # Segment 3: Bottom-right to Bottom-center
            else: # seg1_len + seg2_len < dist <= total_len
                x = x1 - (dist - (seg1_len + seg2_len))
                y = y1
        else: # direction == 'left' (counter-clockwise)
            # Segment 1: Top-center to Top-left
            if 0 <= dist <= seg1_len:
                x = x0 + width / 2 - dist
                y = y0
            # Segment 2: Top-left to Bottom-left
            elif seg1_len < dist <= seg1_len + seg2_len:
                x = x0
                y = y0 + (dist - seg1_len)
            # Segment 3: Bottom-left to Bottom-center
            else: # seg1_len + seg2_len < dist <= total_len
                x = x0 + (dist - (seg1_len + seg2_len))
                y = y1
        return x, y

    # Animates a trail around the image border
    def _animate_border_trail(self):
        if not self.original_image: return

        # Cancel any existing animation
        if self.trail_animation_id:
            self.after_cancel(self.trail_animation_id)
            self.trail_animation_id = None

        # Clear existing trail lines
        for line_id in self.trail_line_ids:
            self.delete(line_id)
        self.trail_line_ids.clear()

        img_w, img_h = self.original_image.size
        disp_w, disp_h = int(img_w * self.zoom_level), int(img_h * self.zoom_level)
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()

        if disp_w < 1 or disp_h < 1: return

        x0 = (canvas_w - disp_w) / 2
        y0 = (canvas_h - disp_h) / 2
        x1 = x0 + disp_w
        y1 = y0 + disp_h

        # Path length for one side (from top-center to bottom-center)
        path_length_one_side = (disp_w / 2) + disp_h + (disp_w / 2)
        trail_segment_length = path_length_one_side * self.trail_segment_ratio

        start_time = time.time()

        def _trail_step():
            if not self.winfo_exists(): # Check if canvas still exists
                if self.trail_animation_id:
                    self.after_cancel(self.trail_animation_id)
                    self.trail_animation_id = None
                return

            elapsed_time = time.time() - start_time
            progress = min(elapsed_time / (self.trail_duration_ms / 1000.0), 1.0)
            eased_progress = self._ease_in_out_quad(progress)

            # Clear previous trail lines
            for line_id in self.trail_line_ids:
                self.delete(line_id)
            self.trail_line_ids.clear()

            # Calculate head and tail positions for both directions
            head_dist = eased_progress * path_length_one_side
            tail_dist = max(0, head_dist - trail_segment_length)

            step_size = 1.0 # pixels for drawing segments

            # Draw glow lines first (underneath)
            current_dist = tail_dist
            while current_dist < head_dist:
                p1_left = self._get_point_on_perimeter(current_dist, x0, y0, x1, y1, direction='left')
                next_dist_left = min(current_dist + step_size, head_dist)
                p2_left = self._get_point_on_perimeter(next_dist_left, x0, y0, x1, y1, direction='left')

                p1_right = self._get_point_on_perimeter(current_dist, x0, y0, x1, y1, direction='right')
                next_dist_right = min(current_dist + step_size, head_dist)
                p2_right = self._get_point_on_perimeter(next_dist_right, x0, y0, x1, y1, direction='right')

                if p1_left and p2_left:
                    line_id = self.create_line(p1_left[0], p1_left[1], p2_left[0], p2_left[1],
                                               fill=self.trail_glow_color, width=self.trail_glow_width,
                                               capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="border_trail_glow")
                    self.trail_line_ids.append(line_id)
                    self.tag_lower(line_id) # Ensure glow is behind

                if p1_right and p2_right:
                    line_id = self.create_line(p1_right[0], p1_right[1], p2_right[0], p2_right[1],
                                               fill=self.trail_glow_color, width=self.trail_glow_width,
                                               capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="border_trail_glow")
                    self.trail_line_ids.append(line_id)
                    self.tag_lower(line_id) # Ensure glow is behind

                current_dist = next_dist_left # Use one of them, they should be the same
                if current_dist >= head_dist: break

            # Draw main trail lines (on top of glow)
            current_dist = tail_dist
            while current_dist < head_dist:
                p1_left = self._get_point_on_perimeter(current_dist, x0, y0, x1, y1, direction='left')
                next_dist_left = min(current_dist + step_size, head_dist)
                p2_left = self._get_point_on_perimeter(next_dist_left, x0, y0, x1, y1, direction='left')

                p1_right = self._get_point_on_perimeter(current_dist, x0, y0, x1, y1, direction='right')
                next_dist_right = min(current_dist + step_size, head_dist)
                p2_right = self._get_point_on_perimeter(next_dist_right, x0, y0, x1, y1, direction='right')

                if p1_left and p2_left:
                    line_id = self.create_line(p1_left[0], p1_left[1], p2_left[0], p2_left[1],
                                               fill=self.trail_color, width=self.trail_width,
                                               capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="border_trail")
                    self.trail_line_ids.append(line_id)

                if p1_right and p2_right:
                    line_id = self.create_line(p1_right[0], p1_right[1], p2_right[0], p2_right[1],
                                               fill=self.trail_color, width=self.trail_width,
                                               capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="border_trail")
                    self.trail_line_ids.append(line_id)

                current_dist = next_dist_left
                if current_dist >= head_dist: break


            if progress < 1.0:
                self.trail_animation_id = self.after(20, _trail_step) # 20ms for smoother animation
            else:
                # Animation finished, clear trail
                for line_id in self.trail_line_ids:
                    self.delete(line_id)
                self.trail_line_ids.clear()
                self.trail_animation_id = None

        self.trail_animation_id = self.after(10, _trail_step) # Start animation

    # Applies brightness and contrast filters to an image
    def _apply_color_filters(self, image, brightness_factor, contrast_factor):
        # Brightness: factor of 1.0 means no change, 0.0 is black, 2.0 is double brightness.
        # Our slider is -1.0 to 1.0, so map it to 0.0 to 2.0.
        adjusted_brightness_factor = brightness_factor + 1.0 # Maps -1 to 0, 0 to 1, 1 to 2

        # Contrast: factor of 1.0 means no change, 0.0 is solid grey, 2.0 is double contrast.
        # Our slider is 0.0 to 2.0, which matches PIL's enhancer.

        enhancer = ImageEnhance.Brightness(image)
        image = enhancer.enhance(adjusted_brightness_factor)

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(contrast_factor)

        return image

    # Sets the brightness and redraws the image
    def set_brightness(self, value):
        self.brightness = float(value)
        self.is_color_adjusted = (self.brightness != 0.0 or self.contrast != 1.0)
        self.redraw_image()
        self.app_ref.set_editing_state(self.is_edited) # Update global editing state

    # Sets the contrast and redraws the image
    def set_contrast(self, value):
        self.contrast = float(value)
        self.is_color_adjusted = (self.brightness != 0.0 or self.contrast != 1.0)
        self.redraw_image()
        self.app_ref.set_editing_state(self.is_edited) # Update global editing state

    # Resets color adjustments to default
    def reset_color_adjustments(self, show_snackbar=True):
        self.brightness = 0.0
        self.contrast = 1.0
        self.is_color_adjusted = False
        if self.brightness_slider: self.brightness_slider.set(0.0)
        if self.contrast_slider: self.contrast_slider.set(1.0)
        self.redraw_image()
        self.app_ref.set_editing_state(self.is_edited) # Update global editing state
        if show_snackbar: self.app_ref.show_snackbar(f"Οι ρυθμίσεις χρώματος για το '{os.path.basename(self.image_path)}' έχουν επαναφερθεί", 'info')

    # Saves current color adjustments to the image file
    def save_color_adjustments(self):
        if not self.original_image or not self.image_path: return
        if not self.is_color_adjusted:
            self.app_ref.show_snackbar("Δεν έχουν γίνει αλλαγές χρώματος για αποθήκευση.", 'info')
            return

        self.app_ref.create_backup(self.image_path)
        # Apply adjustments to a copy of the original image
        adjusted_image = self._apply_color_filters(self.true_original_image.copy(), self.brightness, self.contrast)
        self.app_ref.save_image_to_disk(self, adjusted_image)
        self.app_ref.invalidate_cache_for_path(self.image_path)

        # Reload the image to update the 'true_original_image' with the saved version
        self.load_image(self.image_path)
        self.is_color_adjusted = False # Reset flag after saving
        self.app_ref.set_editing_state(self.is_edited) # Update global editing state
        self.app_ref.show_snackbar("Οι ρυθμίσεις χρώματος αποθηκεύτηκαν.", 'info')


    # Enters splitting mode, drawing a vertical line
    def enter_splitting_mode(self):
        if not self.original_image: return
        self.is_splitting_mode = True
        # Hide crop box and handles
        self.delete(self.crop_rect_id)
        for handle in self.crop_handles.values(): self.delete(handle)
        self.crop_handles.clear()

        # Calculate initial split line position (center of image)
        img_w, img_h = self.original_image.size
        disp_w, disp_h = img_w * self.zoom_level, img_h * self.zoom_level
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()

        # Image top-left on canvas
        img_tl_x = (canvas_w - disp_w) / 2
        img_tl_y = (canvas_h - disp_h) / 2

        # Initial split line x-coordinate on canvas
        self.split_line_x_ratio = 0.5 # Start in the middle
        split_x_on_canvas = img_tl_x + disp_w * self.split_line_x_ratio

        self.split_line_id = self.create_line(
            split_x_on_canvas, img_tl_y,
            split_x_on_canvas, img_tl_y + disp_h,
            fill=Style.ACCENT_COLOR, width=3, dash=(8, 4), tags="split_line"
        )
        # Bind events for moving the split line
        self.tag_bind("split_line", "<ButtonPress-1>", self._on_split_line_press)
        self.tag_bind("split_line", "<B1-Motion>", self._on_split_line_drag)
        self.tag_bind("split_line", "<ButtonRelease-1>", self._on_split_line_release)

    # Exits splitting mode, removing the vertical line
    def exit_splitting_mode(self):
        self.is_splitting_mode = False
        if self.split_line_id:
            self.delete(self.split_line_id)
            self.split_line_id = None
        self.draw_crop_box() # Redraw crop box after exiting splitting mode

    # Handles mouse press on the split line
    def _on_split_line_press(self, event):
        self.drag_info['item'] = 'split_line'
        self.drag_info['x'] = event.x
        self.drag_info['y'] = event.y # Not used for vertical line, but keep for consistency

    # Handles mouse drag on the split line
    def _on_split_line_drag(self, event):
        if not self.is_splitting_mode or self.drag_info.get('item') != 'split_line': return

        dx = event.x - self.drag_info['x']

        img_w, img_h = self.original_image.size
        disp_w, disp_h = img_w * self.zoom_level, img_h * self.zoom_level
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()

        img_tl_x = (canvas_w - disp_w) / 2
        img_br_x = img_tl_x + disp_w

        current_x_on_canvas = self.coords(self.split_line_id)[0]
        new_x_on_canvas = current_x_on_canvas + dx

        # Constrain the line within the image display area with a small padding
        padding = 5 # pixels
        new_x_on_canvas = max(img_tl_x + padding, min(new_x_on_canvas, img_br_x - padding))

        self.coords(self.split_line_id, new_x_on_canvas, self.coords(self.split_line_id)[1], new_x_on_canvas, self.coords(self.split_line_id)[3])

        # Update the ratio for saving
        self.split_line_x_ratio = (new_x_on_canvas - img_tl_x) / disp_w
        self.drag_info['x'] = event.x # Update drag start point

    # Handles mouse release on the split line
    def _on_split_line_release(self, event):
        self.drag_info['item'] = None

    # Gets the split x-coordinate relative to the original image pixels
    def get_split_x_coord(self):
        if not self.original_image or not self.split_line_id: return None

        # Get the current x-coordinate of the split line on the canvas
        split_x_on_canvas = self.coords(self.split_line_id)[0]

        img_w, img_h = self.original_image.size
        disp_w, disp_h = img_w * self.zoom_level, img_h * self.zoom_level
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()

        img_tl_x = (canvas_w - disp_w) / 2

        # Convert canvas x-coordinate to original image pixel coordinate
        split_x_on_original_image = int((split_x_on_canvas - img_tl_x) / self.zoom_level)

        # Ensure it's within image bounds
        return max(0, min(split_x_on_original_image, img_w))

    # Redraws the split line (useful on resize)
    def redraw_split_line(self):
        if not self.is_splitting_mode or not self.original_image or not self.split_line_id: return

        img_w, img_h = self.original_image.size
        disp_w, disp_h = img_w * self.zoom_level, img_h * self.zoom_level
        canvas_w, canvas_h = self.winfo_width(), self.winfo_height()

        img_tl_x = (canvas_w - disp_w) / 2
        img_tl_y = (canvas_h - disp_h) / 2

        split_x_on_canvas = img_tl_x + disp_w * self.split_line_x_ratio

        self.coords(self.split_line_id, split_x_on_canvas, img_tl_y, split_x_on_canvas, img_tl_y + disp_h)


class NewImageHandler(FileSystemEventHandler):
    # Initializes the handler for file system events
    def __init__(self, app_ref):
        self.app_ref = app_ref

    # Handles file creation events
    def on_created(self, event):
        if not event.is_directory:
            self.app_ref.add_new_image(event.src_path)

    # Handles file deletion events
    def on_deleted(self, event):
        if not event.is_directory:
            self.app_ref.scan_worker_command_queue.put(('initial_scan', self.app_ref.scan_directory))

# Helper for natural sorting
def natural_sort_key(s):
    # Splits a string into a list of strings and numbers for natural sorting.
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

class ScanWorker(threading.Thread):
    # Initializes the scan worker thread
    def __init__(self, command_queue, result_queue, scan_directory, todays_books_folder, city_paths):
        super().__init__(daemon=True)
        self.command_queue = command_queue
        self.result_queue = result_queue
        self.scan_directory = scan_directory
        self.todays_books_folder = todays_books_folder
        self.city_paths = city_paths
        self._stop_event = threading.Event()

    # Runs the main loop for the worker thread
    def run(self):
        while not self._stop_event.is_set():
            try:
                command, data = self.command_queue.get(timeout=0.1)
                if command == 'stop':
                    break
                elif command == 'initial_scan':
                    self._initial_scan_worker(data)
                elif command == 'calculate_today_stats':
                    self._calculate_today_stats_worker()
                self.command_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"ERROR: ScanWorker error: {e}")
                self.result_queue.put(('error', str(e)))

    # Stops the worker thread
    def stop(self):
        self._stop_event.set()

    # Helper to count image files in a directory
    def _count_pages_in_folder(self, folder_path):
        count = 0
        try:
            if os.path.isdir(folder_path):
                for f in os.listdir(folder_path):
                    if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS:
                        count += 1
        except Exception as e:
            print(f"Error counting pages in {folder_path}: {e}")
        return count

    # Worker function to perform initial scan
    def _initial_scan_worker(self, scan_directory):
        try:
            files = [os.path.join(scan_directory, f) for f in os.listdir(scan_directory) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
            # Sort files using the natural_sort_key
            files.sort(key=lambda x: natural_sort_key(os.path.basename(x)))
            self.result_queue.put(('initial_scan_result', files))
        except Exception as e:
            self.result_queue.put(('error', f"Σφάλμα ανάγνωσης φακέλου σάρωσης: {e}"))

    # Worker function to calculate all stats for today
    def _calculate_today_stats_worker(self):
        try:
            # 1. Stats from "Todays Books" folder
            pages_in_today_folder = 0
            books_in_today_folder = 0
            if os.path.isdir(self.todays_books_folder):
                book_folders = [d for d in os.listdir(self.todays_books_folder) if os.path.isdir(os.path.join(self.todays_books_folder, d))]
                books_in_today_folder = len(book_folders)
                for book_folder in book_folders:
                    pages_in_today_folder += self._count_pages_in_folder(os.path.join(self.todays_books_folder, book_folder))

            # 2. Stats from the log file for today
            pages_in_data_today = 0
            try:
                if os.path.exists(BOOKS_COMPLETE_LOG_FILE):
                    with open(BOOKS_COMPLETE_LOG_FILE, 'r') as f:
                        log_data = json.load(f)
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    todays_entries = log_data.get(today_str, [])
                    for entry in todays_entries:
                        # FIX: Check if entry is a dictionary to support old log formats
                        if isinstance(entry, dict):
                            pages_in_data_today += entry.get("pages", 0)
            except (IOError, json.JSONDecodeError) as e:
                print(f"Could not read or parse log file: {e}")

            stats_result = {
                "pages_in_today": pages_in_today_folder,
                "books_in_today": books_in_today_folder,
                "pages_in_data": pages_in_data_today,
            }
            self.result_queue.put(('today_stats_result', stats_result))

        except Exception as e:
            print(f"Σφάλμα υπολογισμού στατιστικών: {e}")
            self.result_queue.put(('error', f"Σφάλμα υπολογισμού στατιστικών: {e}"))

class SettingsModal(tk.Toplevel):
    def __init__(self, parent, controller, app_ref):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Ρυθμίσεις")
        self.configure(bg=Style.BG_COLOR)

        self.controller = controller
        self.app_ref = app_ref # reference to ImageScannerApp instance

        # Variables for settings
        self.paths = {"scan": tk.StringVar(), "today": tk.StringVar()}
        self.image_load_timeout_var = tk.StringVar(value=str(DEFAULT_IMAGE_LOAD_TIMEOUT_MS))
        self.city_paths = {}
        self.city_code_entry_var = tk.StringVar()
        self.city_path_entry_var = tk.StringVar()
        self.city_listbox = None

        # Center the modal
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        modal_w = 700 # Increased width
        modal_h = 600 # Increased height
        x = parent_x + (parent_w // 2) - (modal_w // 2)
        y = parent_y + (parent_h // 2) - (modal_h // 2)
        self.geometry(f'{modal_w}x{modal_h}+{x}+{y}')

        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.setup_ui()
        self.load_settings() # Load settings after UI is created

    def setup_ui(self):
        # Style for Notebook
        self.style = ttk.Style(self)
        self.style.theme_use('default')
        self.style.configure("TNotebook", background=Style.BG_COLOR, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=Style.BTN_BG, foreground=Style.FG_COLOR, padding=[10, 5], borderwidth=0, font=Style.get_font(10))
        self.style.map("TNotebook.Tab", background=[("selected", Style.ACCENT_COLOR)], foreground=[("selected", Style.BTN_FG)])
        self.style.layout("TNotebook.Tab", [('Notebook.tab', {'sticky': 'nswe', 'children': [('Notebook.padding', {'side': 'top', 'sticky': 'nswe', 'children': [('Notebook.focus', {'side': 'top', 'sticky': 'nswe', 'children': [('Notebook.label', {'side': 'top', 'sticky': ''})]})]})]})])

        self.main_frame = tk.Frame(self, bg=Style.BG_COLOR, padx=20, pady=20)
        self.main_frame.pack(expand=True, fill="both")

        self.notebook = ttk.Notebook(self.main_frame, style="TNotebook")
        self.notebook.pack(expand=True, fill="both", pady=(0, 10))

        self.paths_tab = tk.Frame(self.notebook, bg=Style.BG_COLOR, padx=10, pady=10)
        self.theme_tab = tk.Frame(self.notebook, bg=Style.BG_COLOR, padx=10, pady=10)

        self.notebook.add(self.paths_tab, text="  Διαδρομές & Ροή  ")
        self.notebook.add(self.theme_tab, text="  Θέμα  ")

        self.setup_paths_tab(self.paths_tab)
        self.setup_theme_tab(self.theme_tab)

        # Add Save/Cancel buttons at the bottom
        self.button_frame = tk.Frame(self.main_frame, bg=Style.BG_COLOR)
        self.button_frame.pack(fill='x', side='bottom', pady=(10, 0))

        # Spacer to push buttons to the right
        tk.Frame(self.button_frame, bg=Style.BG_COLOR).pack(side='left', expand=True)

        self.save_btn = self.app_ref.create_styled_button(self.button_frame, "Αποθήκευση & Κλείσιμο", self.save_and_close, bg=Style.SUCCESS_COLOR)
        self.save_btn.pack(side="right", padx=(5,0))

        self.cancel_btn = self.app_ref.create_styled_button(self.button_frame, "Άκυρο", self.destroy)
        self.cancel_btn.pack(side="right", padx=5)

    def setup_paths_tab(self, parent):
        parent.grid_columnconfigure(1, weight=1)

        self.path_title_label = tk.Label(parent, text="Ρύθμιση Καταλόγων Ροής Εργασίας", bg=Style.BG_COLOR, fg=Style.FG_COLOR, font=Style.get_font(14, "bold"))
        self.path_title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20), sticky='w')

        self.path_entries = {}
        labels = {"scan": "1. Φάκελος Σάρωσης (Εισερχόμενα)", "today": "2. Φάκελος Σημερινών Βιβλίων"}
        for i, (name, label_text) in enumerate(labels.items(), 1):
            label = tk.Label(parent, text=label_text, bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(10))
            label.grid(row=i, column=0, sticky='w', pady=(5,2), padx=(0,10))
            entry_frame = tk.Frame(parent, bg=Style.BG_COLOR)
            entry_frame.grid(row=i, column=1, columnspan=2, sticky='ew')
            entry = tk.Entry(entry_frame, textvariable=self.paths[name], state='readonly', width=70, readonlybackground=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5, padx=(0,10))
            btn = self.app_ref.create_styled_button(entry_frame, "Αναζήτηση...", lambda n=name: self.ask_dir(n), pady=4, padx=8, font_size=9)
            btn.pack(side=tk.LEFT)
            self.path_entries[name] = {'label': label, 'frame': entry_frame, 'entry': entry, 'btn': btn}


        self.timeout_label = tk.Label(parent, text="3. Χρόνος Αναμονής Φόρτωσης Εικόνας (ms)", bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(10))
        self.timeout_label.grid(row=3, column=0, sticky='w', pady=(5,2))
        self.timeout_entry = tk.Entry(parent, textvariable=self.image_load_timeout_var, width=15, bg=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT, insertbackground=Style.FG_COLOR)
        self.timeout_entry.grid(row=3, column=1, sticky='w', ipady=5)
        ToolTip(self.timeout_entry, "Ο χρόνος (σε ms) που η εφαρμογή περιμένει ένα αρχείο εικόνας να είναι πλήρως διαθέσιμο.")

        # City Path Configuration UI
        self.city_frame = tk.LabelFrame(parent, text="4. Ρυθμίσεις Πόλεων (Για Μεταφορά στα Data)", bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(11, 'bold'), bd=1, relief=tk.GROOVE, padx=10, pady=10)
        self.city_frame.grid(row=4, column=0, columnspan=3, sticky='ew', pady=(20, 0))
        self.city_frame.grid_columnconfigure(1, weight=1)

        list_frame = tk.Frame(self.city_frame, bg=Style.BG_COLOR)
        list_frame.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(0, 10))
        list_frame.grid_rowconfigure(0, weight=1)
        self.city_listbox = tk.Listbox(list_frame, bg=Style.BTN_BG, fg=Style.FG_COLOR, font=Style.get_font(10), relief=tk.FLAT, selectbackground=Style.ACCENT_COLOR, highlightthickness=0, height=5)
        self.city_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.city_listbox.bind('<<ListboxSelect>>', self._on_city_select)

        self.city_scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.city_listbox.yview, bg=Style.BTN_BG, troughcolor=Style.BG_COLOR)
        self.city_scrollbar.pack(side=tk.RIGHT, fill="y")
        self.city_listbox.config(yscrollcommand=self.city_scrollbar.set)

        controls_frame = tk.Frame(self.city_frame, bg=Style.BG_COLOR)
        controls_frame.grid(row=0, column=1, sticky='ew')

        tk.Label(controls_frame, text="Κωδικός (π.χ. 001):", bg=Style.BG_COLOR, fg=Style.FG_COLOR).grid(row=0, column=0, sticky='w')
        self.city_code_entry = tk.Entry(controls_frame, textvariable=self.city_code_entry_var, width=10, bg=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT)
        self.city_code_entry.grid(row=0, column=1, sticky='w', pady=2)

        tk.Label(controls_frame, text="Διαδρομή Φακέλου:", bg=Style.BG_COLOR, fg=Style.FG_COLOR).grid(row=1, column=0, sticky='w')
        path_entry_frame = tk.Frame(controls_frame, bg=Style.BG_COLOR)
        path_entry_frame.grid(row=1, column=1, sticky='ew')
        self.city_path_entry = tk.Entry(path_entry_frame, textvariable=self.city_path_entry_var, width=40, bg=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT)
        self.city_path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        browse_btn = self.app_ref.create_styled_button(path_entry_frame, "...", self._ask_city_dir, pady=1, padx=4)
        browse_btn.pack(side=tk.LEFT)

        btn_frame = tk.Frame(self.city_frame, bg=Style.BG_COLOR)
        btn_frame.grid(row=1, column=1, sticky='e', pady=(10,0))
        self.add_city_btn = self.app_ref.create_styled_button(btn_frame, "Προσθήκη/Ενημέρωση", self._add_or_update_city, bg=Style.SUCCESS_COLOR)
        self.add_city_btn.pack(side=tk.LEFT, padx=5)
        self.remove_city_btn = self.app_ref.create_styled_button(btn_frame, "Αφαίρεση Επιλογής", self._remove_city, bg=Style.DESTRUCTIVE_COLOR)
        self.remove_city_btn.pack(side=tk.LEFT, padx=5)

    def setup_theme_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        self.theme_title_label = tk.Label(parent, text="Επιλέξτε ένα θέμα για την εφαρμογή.", bg=Style.BG_COLOR, fg=Style.FG_COLOR, font=Style.get_font(12))
        self.theme_title_label.grid(row=0, column=0, pady=(0, 15), sticky='w')

        self.theme_frame = tk.Frame(parent, bg=Style.BG_COLOR)
        self.theme_frame.grid(row=1, column=0, sticky='ew')
        self.theme_frame.grid_columnconfigure(0, weight=1)
        self.theme_frame.grid_columnconfigure(1, weight=1)
        self.theme_frame.grid_columnconfigure(2, weight=1)

        # Create buttons for each theme
        self.blue_theme_btn = self.app_ref.create_styled_button(self.theme_frame, "Μπλε", lambda: self.apply_theme("Blue"), bg=THEMES["Blue"]["ACCENT_COLOR"])
        self.blue_theme_btn.grid(row=0, column=0, padx=10, pady=5, sticky='ew', ipady=10)

        self.pink_theme_btn = self.app_ref.create_styled_button(self.theme_frame, "Ροζ", lambda: self.apply_theme("Pink"), bg=THEMES["Pink"]["ACCENT_COLOR"])
        self.pink_theme_btn.grid(row=0, column=1, padx=10, pady=5, sticky='ew', ipady=10)

        self.grey_theme_btn = self.app_ref.create_styled_button(self.theme_frame, "Ουδέτερο Γκρι", lambda: self.apply_theme("Neutral Grey"), bg=THEMES["Neutral Grey"]["ACCENT_COLOR"])
        self.grey_theme_btn.grid(row=0, column=2, padx=10, pady=5, sticky='ew', ipady=10)

        self.theme_info_label = tk.Label(parent, text="Η αλλαγή του θέματος εφαρμόζεται άμεσα σε όλη την εφαρμογή.", bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(9), wraplength=300, justify=tk.LEFT)
        self.theme_info_label.grid(row=2, column=0, pady=(15, 0), sticky='w')

    def apply_theme(self, theme_name):
        Style.load_theme(theme_name)
        self.save_theme_setting(theme_name)
        self.controller.update_theme()

    def save_theme_setting(self, theme_name):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f: settings = json.load(f)
            else: settings = {}
        except (IOError, json.JSONDecodeError): settings = {}

        settings['theme'] = theme_name
        try:
            with open(CONFIG_FILE, 'w') as f: json.dump(settings, f, indent=4)
        except IOError as e: print(f"ERROR: Could not save theme setting: {e}")

    def update_theme(self):
        self.configure(bg=Style.BG_COLOR)
        self.main_frame.config(bg=Style.BG_COLOR)
        self.button_frame.config(bg=Style.BG_COLOR)
        self.button_frame.winfo_children()[0].config(bg=Style.BG_COLOR) # Spacer

        # Update tabs
        self.paths_tab.config(bg=Style.BG_COLOR)
        self.theme_tab.config(bg=Style.BG_COLOR)
        self.style.configure("TNotebook", background=Style.BG_COLOR)
        self.style.configure("TNotebook.Tab", background=Style.BTN_BG, foreground=Style.FG_COLOR, font=Style.get_font(10))
        self.style.map("TNotebook.Tab", background=[("selected", Style.ACCENT_COLOR)], foreground=[("selected", Style.BTN_FG)])

        # Update Paths Tab
        self.path_title_label.config(bg=Style.BG_COLOR, fg=Style.FG_COLOR)
        for name_vals in self.path_entries.values():
            name_vals['label'].config(bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR)
            name_vals['frame'].config(bg=Style.BG_COLOR)
            name_vals['entry'].config(readonlybackground=Style.BTN_BG, fg=Style.FG_COLOR)
            name_vals['btn'].config(bg=Style.BTN_BG, fg=Style.BTN_FG)
        self.timeout_label.config(bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR)
        self.timeout_entry.config(bg=Style.BTN_BG, fg=Style.FG_COLOR, insertbackground=Style.FG_COLOR)
        self.city_frame.config(bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR)
        for child in self.city_frame.winfo_children(): # Update frames and labels inside city_frame
            child.config(bg=Style.BG_COLOR)
            if child.winfo_class() == 'Label': child.config(fg=Style.FG_COLOR)
        self.city_listbox.config(bg=Style.BTN_BG, fg=Style.FG_COLOR, selectbackground=Style.ACCENT_COLOR)
        self.city_scrollbar.config(bg=Style.BTN_BG, troughcolor=Style.BG_COLOR)
        self.city_code_entry.config(bg=Style.BTN_BG, fg=Style.FG_COLOR)
        self.city_path_entry.config(bg=Style.BTN_BG, fg=Style.FG_COLOR)
        self.add_city_btn.config(bg=Style.SUCCESS_COLOR)
        self.remove_city_btn.config(bg=Style.DESTRUCTIVE_COLOR)

        # Update Theme Tab
        self.theme_title_label.config(bg=Style.BG_COLOR, fg=Style.FG_COLOR)
        self.theme_frame.config(bg=Style.BG_COLOR)
        self.blue_theme_btn.config(bg=THEMES["Blue"]["ACCENT_COLOR"])
        self.pink_theme_btn.config(bg=THEMES["Pink"]["ACCENT_COLOR"])
        self.grey_theme_btn.config(bg=THEMES["Neutral Grey"]["ACCENT_COLOR"])
        self.theme_info_label.config(bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR)

        # Update Main Buttons
        self.save_btn.config(bg=Style.SUCCESS_COLOR)
        self.cancel_btn.config(bg=Style.BTN_BG) # Make cancel less prominent

    def load_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f: settings = json.load(f)
                for key in self.paths: self.paths[key].set(settings.get(key, ""))
                self.image_load_timeout_var.set(str(settings.get("image_load_timeout_ms", DEFAULT_IMAGE_LOAD_TIMEOUT_MS)))
                self.city_paths = settings.get("city_paths", {})
                if self.city_listbox: self._update_city_listbox()
        except (IOError, json.JSONDecodeError) as e: print(f"ERROR: Could not load config for modal: {e}")

    def save_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f: settings = json.load(f)
            else: settings = {}
        except (IOError, json.JSONDecodeError): settings = {}

        path_settings = {key: var.get() for key, var in self.paths.items()}
        settings.update(path_settings)

        try:
            timeout_val = int(self.image_load_timeout_var.get())
            settings["image_load_timeout_ms"] = max(100, timeout_val)
        except ValueError:
            settings["image_load_timeout_ms"] = DEFAULT_IMAGE_LOAD_TIMEOUT_MS

        settings["city_paths"] = self.city_paths

        try:
            with open(CONFIG_FILE, 'w') as f: json.dump(settings, f, indent=4)
            return True
        except IOError as e:
            print(f"ERROR: Could not save config: {e}")
            messagebox.showerror("Σφάλμα Αποθήκευσης", f"Δεν ήταν δυνατή η αποθήκευση των ρυθμίσεων:\n{e}", parent=self)
            return False

    def save_and_close(self):
        if self.save_settings():
            self.app_ref.show_snackbar("Οι ρυθμίσεις διαδρομής αποθηκεύτηκαν. Εφαρμογή...", 'info')

            self.app_ref.scan_directory = self.paths["scan"].get()
            self.app_ref.todays_books_folder = self.paths["today"].get()
            self.app_ref.city_paths = self.city_paths
            try:
                self.app_ref.image_load_timeout_ms = int(self.image_load_timeout_var.get())
            except ValueError:
                self.app_ref.image_load_timeout_ms = DEFAULT_IMAGE_LOAD_TIMEOUT_MS

            self.app_ref.scan_worker.scan_directory = self.app_ref.scan_directory
            self.app_ref.scan_worker.todays_books_folder = self.app_ref.todays_books_folder
            self.app_ref.scan_worker.city_paths = self.app_ref.city_paths

            self.app_ref.start_watcher()
            self.app_ref.refresh_scan_folder()
            self.app_ref.update_stats()

            self.destroy()

    def ask_dir(self, name):
        path = filedialog.askdirectory(title=f"Επιλέξτε Φάκελο {name.replace('_', ' ').title()}")
        if path: self.paths[name].set(path)

    def _ask_city_dir(self):
        path = filedialog.askdirectory(title="Επιλέξτε τον κατάλογο δεδομένων της πόλης")
        if path: self.city_path_entry_var.set(path)

    def _update_city_listbox(self):
        self.city_listbox.delete(0, tk.END)
        for code, path in sorted(self.city_paths.items()):
            self.city_listbox.insert(tk.END, f"{code}: {path}")

    def _on_city_select(self, event):
        selection = self.city_listbox.curselection()
        if not selection: return

        selected_text = self.city_listbox.get(selection[0])
        code, path = selected_text.split(':', 1)

        self.city_code_entry_var.set(code.strip())
        self.city_path_entry_var.set(path.strip())

    def _add_or_update_city(self):
        code = self.city_code_entry_var.get().strip()
        path = self.city_path_entry_var.get().strip()

        if not code or not path:
            messagebox.showwarning("Ελλιπή Στοιχεία", "Παρακαλώ εισάγετε κωδικό και διαδρομή.", parent=self)
            return

        if not re.match(r'^\d{3}$', code):
            messagebox.showwarning("Λάθος Κωδικός", "Ο κωδικός πρέπει να είναι ακριβώς 3 ψηφία.", parent=self)
            return

        self.city_paths[code] = path
        self._update_city_listbox()
        self.city_code_entry_var.set("")
        self.city_path_entry_var.set("")

    def _remove_city(self):
        selection = self.city_listbox.curselection()
        if not selection:
            messagebox.showwarning("Καμία Επιλογή", "Παρακαλώ επιλέξτε μια πόλη για αφαίρεση.", parent=self)
            return

        selected_text = self.city_listbox.get(selection[0])
        code = selected_text.split(':', 1)[0].strip()

        if messagebox.askyesno("Επιβεβαίωση", f"Είστε σίγουροι ότι θέλετε να αφαιρέσετε τον κωδικό '{code}';", parent=self):
            if code in self.city_paths:
                del self.city_paths[code]
                self._update_city_listbox()
                self.city_code_entry_var.set("")
                self.city_path_entry_var.set("")

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

class SettingsFrame(tk.Frame):
    # Initializes the settings frame
    def __init__(self, parent, controller):
        super().__init__(parent, bg=Style.BG_COLOR)
        self.controller = controller
        self.paths = {"scan": tk.StringVar(), "today": tk.StringVar()}
        self.image_load_timeout_var = tk.StringVar(value=str(DEFAULT_IMAGE_LOAD_TIMEOUT_MS))

        # New: City path settings
        self.city_paths = {}
        self.city_code_entry_var = tk.StringVar()
        self.city_path_entry_var = tk.StringVar()
        self.city_listbox = None

        self.setup_ui()
        self.load_settings()

    def update_theme(self):
        # This frame is simple, so we can recursively update it.
        self._recursive_apply_theme(self)
        # Manually update special widgets
        self.start_btn.config(bg=Style.SUCCESS_COLOR)
        for child in self.main_frame.winfo_children():
            if isinstance(child, tk.LabelFrame):
                child.config(bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR)
                self._recursive_apply_theme(child)


    def _recursive_apply_theme(self, widget):
        try:
            widget.configure(bg=Style.BG_COLOR)
        except tk.TclError:
            pass

        if isinstance(widget, (tk.Label, tk.Button)):
            try:
                widget.configure(fg=Style.FG_COLOR)
            except tk.TclError:
                pass
        if isinstance(widget, tk.Entry):
            widget.config(readonlybackground=Style.BTN_BG, fg=Style.FG_COLOR, insertbackground=Style.FG_COLOR)
        if isinstance(widget, tk.Button) and widget != self.start_btn:
             widget.config(bg=Style.BTN_BG, fg=Style.BTN_FG)

        for child in widget.winfo_children():
            self._recursive_apply_theme(child)

    # Sets up the UI for the settings frame
    def setup_ui(self):
        self.pack(expand=True)
        self.main_frame = tk.Frame(self, bg=Style.BG_COLOR, padx=40, pady=30)
        self.main_frame.pack(expand=True)
        self.main_frame.grid_columnconfigure(1, weight=1)

        tk.Label(self.main_frame, text="Ρύθμιση Καταλόγων Ροής Εργασίας", bg=Style.BG_COLOR, fg=Style.FG_COLOR, font=Style.get_font(16, "bold")).grid(row=0, column=0, columnspan=3, pady=(0, 25))

        labels = {"scan": "1. Φάκελος Σάρωσης", "today": "2. Φάκελος Σημερινών Βιβλίων"}
        for i, (name, label_text) in enumerate(labels.items(), 1):
            tk.Label(self.main_frame, text=label_text, bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(10)).grid(row=i, column=0, sticky='w', pady=(10,2), padx=(0,20))
            entry_frame = tk.Frame(self.main_frame, bg=Style.BG_COLOR)
            entry_frame.grid(row=i, column=1, sticky='ew')
            entry = tk.Entry(entry_frame, textvariable=self.paths[name], state='readonly', width=70, readonlybackground=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0,10))
            btn = tk.Button(entry_frame, text="Αναζήτηση...", command=lambda n=name: self.ask_dir(n), bg=Style.BTN_BG, fg=Style.BTN_FG, relief=tk.FLAT, font=Style.get_font(9), padx=10, pady=5, activebackground=lighten_color(Style.BTN_BG), activeforeground=Style.BTN_FG)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=lighten_color(Style.BTN_BG)))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=Style.BTN_BG))
            btn.pack(side=tk.LEFT)

        tk.Label(self.main_frame, text="3. Χρόνος Αναμονής Φόρτωσης Εικόνας (ms)", bg=Style.BG_COLOR, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(10)).grid(row=3, column=0, sticky='w', pady=(10,2))
        timeout_entry = tk.Entry(self.main_frame, textvariable=self.image_load_timeout_var, width=15, bg=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT, insertbackground=Style.FG_COLOR)
        timeout_entry.grid(row=3, column=1, sticky='w', ipady=8)
        ToolTip(timeout_entry, "Ο χρόνος (σε ms) που η εφαρμογή περιμένει ένα αρχείο εικόνας να είναι πλήρως διαθέσιμο.")

        # New: City Path Configuration UI
        city_frame = tk.LabelFrame(self.main_frame, text="4. Ρυθμίσεις Πόλεων", bg=Style.FRAME_BG, fg=Style.TEXT_SECONDARY_COLOR, font=Style.get_font(11, 'bold'), bd=1, relief=tk.GROOVE, padx=10, pady=10)
        city_frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=(20, 0))
        city_frame.grid_columnconfigure(0, weight=1)
        city_frame.grid_columnconfigure(1, weight=1)

        # Listbox to show city code mappings
        list_frame = tk.Frame(city_frame, bg=Style.FRAME_BG)
        list_frame.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(0, 10))
        list_frame.grid_rowconfigure(0, weight=1)
        self.city_listbox = tk.Listbox(list_frame, bg=Style.BTN_BG, fg=Style.FG_COLOR, font=Style.get_font(10), relief=tk.FLAT, selectbackground=Style.ACCENT_COLOR, highlightthickness=0, height=5)
        self.city_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.city_listbox.bind('<<ListboxSelect>>', self._on_city_select)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.city_listbox.yview, bg=Style.BTN_BG, troughcolor=Style.BG_COLOR)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        self.city_listbox.config(yscrollcommand=scrollbar.set)

        # Entry fields and buttons for adding/editing
        controls_frame = tk.Frame(city_frame, bg=Style.FRAME_BG)
        controls_frame.grid(row=0, column=1, sticky='ew')

        tk.Label(controls_frame, text="Κωδικός (XXX):", bg=Style.FRAME_BG, fg=Style.FG_COLOR).grid(row=0, column=0, sticky='w')
        code_entry = tk.Entry(controls_frame, textvariable=self.city_code_entry_var, width=10, bg=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT)
        code_entry.grid(row=0, column=1, sticky='w', pady=2)

        tk.Label(controls_frame, text="Διαδρομή:", bg=Style.FRAME_BG, fg=Style.FG_COLOR).grid(row=1, column=0, sticky='w')
        path_entry_frame = tk.Frame(controls_frame, bg=Style.FRAME_BG)
        path_entry_frame.grid(row=1, column=1, sticky='ew')
        path_entry = tk.Entry(path_entry_frame, textvariable=self.city_path_entry_var, width=40, bg=Style.BTN_BG, fg=Style.FG_COLOR, relief=tk.FLAT)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        browse_btn = tk.Button(path_entry_frame, text="...", command=self._ask_city_dir, bg=Style.BTN_BG, fg=Style.BTN_FG, relief=tk.FLAT, font=Style.get_font(9))
        browse_btn.pack(side=tk.LEFT)

        # Add/Remove buttons
        btn_frame = tk.Frame(city_frame, bg=Style.FRAME_BG)
        btn_frame.grid(row=1, column=1, sticky='e', pady=(10,0))
        add_btn = tk.Button(btn_frame, text="Προσθήκη/Ενημέρωση", command=self._add_or_update_city, bg=Style.SUCCESS_COLOR, fg='white', relief=tk.FLAT)
        add_btn.pack(side=tk.LEFT, padx=5)
        remove_btn = tk.Button(btn_frame, text="Αφαίρεση", command=self._remove_city, bg=Style.DESTRUCTIVE_COLOR, fg='white', relief=tk.FLAT)
        remove_btn.pack(side=tk.LEFT, padx=5)


        self.start_btn = tk.Button(self.main_frame, text="Έναρξη Σάρωσης", command=self.on_ok, bg=Style.SUCCESS_COLOR, fg="#ffffff", font=Style.get_font(12, "bold"), relief=tk.FLAT, padx=20, pady=10, activebackground=lighten_color(Style.SUCCESS_COLOR), activeforeground="#ffffff")
        self.start_btn.grid(row=5, column=0, columnspan=2, pady=(30,0)) # Adjusted row
        self.start_btn.bind("<Enter>", lambda e, b=self.start_btn, c=lighten_color(Style.SUCCESS_COLOR): b.config(bg=c))
        self.start_btn.bind("<Leave>", lambda e, b=self.start_btn, c=Style.SUCCESS_COLOR: b.config(bg=c))

    # Opens a directory selection dialog
    def ask_dir(self, name):
        path = filedialog.askdirectory(title=f"Επιλέξτε Φάκελο {name.replace('_', ' ').title()}")
        if path: self.paths[name].set(path)

    def _ask_city_dir(self):
        path = filedialog.askdirectory(title="Επιλέξτε τον κατάλογο δεδομένων της πόλης")
        if path: self.city_path_entry_var.set(path)

    def _update_city_listbox(self):
        self.city_listbox.delete(0, tk.END)
        for code, path in sorted(self.city_paths.items()):
            self.city_listbox.insert(tk.END, f"{code}: {path}")

    def _on_city_select(self, event):
        selection = self.city_listbox.curselection()
        if not selection: return

        selected_text = self.city_listbox.get(selection[0])
        code, path = selected_text.split(':', 1)

        self.city_code_entry_var.set(code.strip())
        self.city_path_entry_var.set(path.strip())

    def _add_or_update_city(self):
        code = self.city_code_entry_var.get().strip()
        path = self.city_path_entry_var.get().strip()

        if not code or not path:
            messagebox.showwarning("Ελλιπή Στοιχεία", "Παρακαλώ εισάγετε κωδικό και διαδρομή.")
            return

        if not code.isdigit() or len(code) != 3:
            messagebox.showwarning("Λάθος Κωδικός", "Ο κωδικός πρέπει να είναι 3 ψηφία.")
            return

        self.city_paths[code] = path
        self._update_city_listbox()
        self.city_code_entry_var.set("")
        self.city_path_entry_var.set("")

    def _remove_city(self):
        selection = self.city_listbox.curselection()
        if not selection:
            messagebox.showwarning("Καμία Επιλογή", "Παρακαλώ επιλέξτε μια πόλη για αφαίρεση.")
            return

        selected_text = self.city_listbox.get(selection[0])
        code = selected_text.split(':', 1)[0].strip()

        if code in self.city_paths:
            del self.city_paths[code]
            self._update_city_listbox()
            self.city_code_entry_var.set("")
            self.city_path_entry_var.set("")


    # Loads saved settings
    def load_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f: settings = json.load(f)
                for key in self.paths: self.paths[key].set(settings.get(key, ""))
                self.image_load_timeout_var.set(str(settings.get("image_load_timeout_ms", DEFAULT_IMAGE_LOAD_TIMEOUT_MS)))
                self.city_paths = settings.get("city_paths", {})
                if self.city_listbox: self._update_city_listbox()
        except (IOError, json.JSONDecodeError) as e: print(f"ERROR: Could not load config: {e}")

    # Saves current settings
    def save_settings(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f: settings = json.load(f)
            else: settings = {}
        except (IOError, json.JSONDecodeError): settings = {}

        path_settings = {key: var.get() for key, var in self.paths.items()}
        settings.update(path_settings)

        try:
            timeout_val = int(self.image_load_timeout_var.get())
            settings["image_load_timeout_ms"] = max(100, timeout_val)
        except ValueError:
            settings["image_load_timeout_ms"] = DEFAULT_IMAGE_LOAD_TIMEOUT_MS

        settings["city_paths"] = self.city_paths # Save city paths

        try:
            with open(CONFIG_FILE, 'w') as f: json.dump(settings, f, indent=4)
        except IOError as e: print(f"ERROR: Could not save config: {e}")

    # Handles the "Start Scanning" button click
    def on_ok(self):
        self.save_settings()
        app_settings = {key: var.get() for key, var in self.paths.items()}
        try: app_settings["image_load_timeout_ms"] = int(self.image_load_timeout_var.get())
        except ValueError: app_settings["image_load_timeout_ms"] = DEFAULT_IMAGE_LOAD_TIMEOUT_MS

        app_settings["city_paths"] = self.city_paths # Pass city paths to the main app

        if not all(app_settings.values()):
            messagebox.showwarning("Ελλιπής Ρύθμιση", "Παρακαλώ επιλέξτε όλους τους βασικούς καταλόγους.")
            return
        self.controller.show_frame(ImageScannerApp, app_settings)

class App(tk.Tk):
    # Initializes the main application window
    def __init__(self):
        super().__init__()
        self.title("DigiPage Scanner")
        self.load_config_and_apply_theme()
        self.configure(bg=Style.BG_COLOR)
        self._frame = None
        self.is_fullscreen = False
        self.bind("<F11>", self.toggle_fullscreen)
        self.show_frame(SettingsFrame)

    def load_config_and_apply_theme(self):
        theme_name = "Neutral Grey" # Default
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    settings = json.load(f)
                    theme_name = settings.get("theme", "Neutral Grey")
        except (IOError, json.JSONDecodeError):
            pass # Stick to default if config is bad

        Style.load_theme(theme_name)

    def update_theme(self):
        """Recursively updates the theme for the entire application."""
        self.configure(bg=Style.BG_COLOR)
        if self._frame and hasattr(self._frame, 'update_theme'):
            self._frame.update_theme()

    # Toggles fullscreen mode
    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        return "break"

    # Centers the settings window on the screen.
    def center_settings_window(self):
        self.update_idletasks()
        width, height = 800, 700 # Adjusted height
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    # Sets the size for the main application window.
    def set_main_window_size(self):
        self.update_idletasks()
        width, height = 1600, 900
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        # Make sure window is not bigger than screen
        width = min(width, screen_width)
        height = min(height, screen_height)
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    # Displays a new frame in the window
    def show_frame(self, frame_class, settings=None):
        if self._frame: self._frame.destroy()

        self._frame = frame_class(self, self, settings) if settings else frame_class(self, self)
        self._frame.grid(row=0, column=0, sticky='nsew')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        if frame_class == SettingsFrame:
            self.overrideredirect(False)
            self.title("DigiPage Scanner - Ρυθμίσεις")
            self.center_settings_window()
        elif frame_class == ImageScannerApp:
            self.title("DigiPage Scanner")
            self.set_main_window_size()


if __name__ == "__main__":
    app = App()
    app.mainloop()
