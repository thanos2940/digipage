import tkinter as tk
import time
import os
from PIL import Image, ImageTk, ImageEnhance

from style import Style, darken_color
from config import DEFAULT_IMAGE_LOAD_TIMEOUT_MS


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
