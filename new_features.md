# Implementation Analysis: New Features

## Feature 1: Thumbnail Panel System

### 1.1 Architecture & Data Flow

**Component Structure:**

```
MainWindow (sidebar)
    └── ThumbnailListWidget (QScrollArea)
        └── ThumbnailContainerWidget (QWidget with QVBoxLayout)
            └── ThumbnailPairWidget[] (individual pair cards)
                ├── ThumbnailLabel (left/first image)
                └── ThumbnailLabel (right/second image)
```

**Critical Design Decision:** Use a **virtual scrolling** approach rather than creating all thumbnail widgets upfront. For 500+ image pairs, creating 1000+ QLabel widgets causes severe performance degradation.

### 1.2 Virtual Scrolling Implementation

**File: `thumbnail_widgets.py` (new file)**

**Method:** Implement a custom `QAbstractScrollArea` subclass that:

1. **Calculates visible range** based on scroll position
2. **Renders only visible thumbnails** (viewport height ÷ thumbnail height + 2 buffer items)
3. **Reuses widget instances** as user scrolls (widget pooling)

**Key Algorithm:**
```python
def _calculate_visible_range(self):
    """
    Determines which thumbnail pairs are currently visible.
    Returns (first_visible_index, last_visible_index)
    """
    viewport_rect = self.viewport().rect()
    scroll_offset = self.verticalScrollBar().value()
    
    # Each pair widget is fixed height (120px in your design)
    PAIR_HEIGHT = 120
    SPACING = 10
    ITEM_HEIGHT = PAIR_HEIGHT + SPACING
    
    first_visible = max(0, (scroll_offset // ITEM_HEIGHT) - 1)  # -1 for buffer
    visible_count = (viewport_rect.height() // ITEM_HEIGHT) + 3  # +3 for buffer
    last_visible = min(self.total_pairs - 1, first_visible + visible_count)
    
    return (first_visible, last_visible)
```

**Widget Pooling Strategy:**
- Maintain `_widget_pool`: list of reusable `ThumbnailPairWidget` instances
- When scrolling reveals new pairs, **reuse** widgets from pool instead of creating new ones
- Update widget content (set new pixmaps, indices) rather than destroy/recreate
- Pool size = `visible_count + 4` (enough for smooth scrolling in either direction)

### 1.3 Thumbnail Generation Pipeline

**Two-Tier Caching System:**

**Tier 1: Full Image Cache** (already exists in `ImageProcessor`)
- Stores full-resolution QPixmap instances
- Size-aware LRU eviction (per your optimization report)

**Tier 2: Thumbnail Cache** (new, in `ImageProcessor`)
```python
class ImageProcessor(QObject):
    def __init__(self):
        # Existing cache for full images
        self._pixmap_cache = {}
        
        # NEW: Separate cache for thumbnails
        self._thumbnail_cache = {}  # path -> QPixmap (90x110px)
        self.MAX_THUMBNAIL_CACHE = 200  # Can cache many more due to small size
        
        # Thumbnail generation queue with priority
        self._thumbnail_queue = PriorityQueue()  # (priority, path)
        self._thumbnail_worker_thread = QThread()
        self._is_generating_thumbnails = False
```

**Priority Queue Strategy:**
- Priority 0: Currently visible thumbnails
- Priority 1: Adjacent to current view (±5 pairs)
- Priority 2: All other thumbnails in background

**Generation Method:**
```python
@Slot(str, int)
def request_thumbnail(self, path, priority=2):
    """
    Requests thumbnail generation with priority.
    
    Args:
        path: Image file path
        priority: 0=immediate, 1=soon, 2=background
    """
    if path in self._thumbnail_cache:
        self.thumbnail_loaded.emit(path, self._thumbnail_cache[path])
        return
    
    self._thumbnail_queue.put((priority, path))
    
    if not self._is_generating_thumbnails:
        self._is_generating_thumbnails = True
        QTimer.singleShot(0, self._process_thumbnail_queue)

def _process_thumbnail_queue(self):
    """Processes thumbnail requests in priority order"""
    if self._thumbnail_queue.empty():
        self._is_generating_thumbnails = False
        return
    
    priority, path = self._thumbnail_queue.get()
    
    # Fast thumbnail generation using PIL
    try:
        with Image.open(path) as img:
            # Use LANCZOS for quality, but on already-small image
            img.thumbnail((90, 110), Image.Resampling.LANCZOS)
            
            # Convert to QPixmap
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            q_img = ImageQt(img)
            thumbnail = QPixmap.fromImage(q_img)
            
            # Cache it
            self._thumbnail_cache[path] = thumbnail
            if len(self._thumbnail_cache) > self.MAX_THUMBNAIL_CACHE:
                # Simple FIFO eviction for thumbnails (they're cheap)
                self._thumbnail_cache.pop(next(iter(self._thumbnail_cache)))
            
            self.thumbnail_loaded.emit(path, thumbnail)
    except Exception as e:
        self.error.emit(f"Thumbnail generation failed: {e}")
    
    # Continue processing queue
    QTimer.singleShot(10, self._process_thumbnail_queue)  # Small delay to not block UI
```

### 1.4 Single Split Mode: Cropped Thumbnail Generation

**Challenge:** In single split mode, thumbnails must show the **cropped regions**, not the full image. This requires:

1. **Layout data dependency** - must wait for layout before generating thumbnail
2. **Re-generation on layout change** - thumbnails must update when crop areas adjust
3. **Toggle state visualization** - dimmed appearance when page is disabled

**Implementation Strategy:**

**File: `ui_modes/single_split_mode.py`**

Add method:
```python
def _request_split_thumbnails(self, source_path):
    """
    Requests thumbnails for both cropped pages.
    Uses current layout data to crop before thumbnailing.
    """
    layout = self.get_layout_for_image(source_path)
    if not layout:
        return
    
    # Emit custom signal with layout info
    self.split_thumbnail_requested.emit(source_path, layout)
```

**File: `workers.py` - ImageProcessor**

Add new slot:
```python
@Slot(str, dict)
def generate_split_thumbnails(self, source_path, layout_data):
    """
    Generates thumbnails for left and right cropped regions.
    
    Emits: split_thumbnail_loaded(source_path, 'left'/'right', QPixmap)
    """
    try:
        with Image.open(source_path) as img:
            w, h = img.size
            
            for side in ['left', 'right']:
                if not layout_data.get(f'{side}_enabled', True):
                    # Emit disabled placeholder
                    self.split_thumbnail_loaded.emit(
                        source_path, side, self._create_disabled_thumbnail()
                    )
                    continue
                
                ratios = layout_data[side]
                crop_box = (
                    int(ratios['x'] * w),
                    int(ratios['y'] * h),
                    int((ratios['x'] + ratios['w']) * w),
                    int((ratios['y'] + ratios['h']) * h)
                )
                
                # Crop first, then thumbnail
                cropped = img.crop(crop_box)
                cropped.thumbnail((90, 110), Image.Resampling.LANCZOS)
                
                # Convert and cache
                if cropped.mode != 'RGB':
                    cropped = cropped.convert('RGB')
                
                q_img = ImageQt(cropped)
                thumbnail = QPixmap.fromImage(q_img)
                
                # Cache with composite key: path + side
                cache_key = f"{source_path}_{side}"
                self._thumbnail_cache[cache_key] = thumbnail
                
                self.split_thumbnail_loaded.emit(source_path, side, thumbnail)
    except Exception as e:
        self.error.emit(f"Split thumbnail generation failed: {e}")

def _create_disabled_thumbnail(self):
    """Creates a dark/dimmed placeholder for disabled pages"""
    pixmap = QPixmap(90, 110)
    pixmap.fill(QColor(40, 40, 40))  # Dark gray
    
    painter = QPainter(pixmap)
    painter.setPen(QColor(100, 100, 100))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "DISABLED")
    painter.end()
    
    return pixmap
```

### 1.5 Thumbnail Update Triggers

**Comprehensive Update Logic:**

1. **On Initial Load:** Request all visible thumbnails (priority 0) and adjacent (priority 1)
2. **On Scroll:** Recalculate visible range, request new visible thumbnails
3. **On Image Edit (Dual Scan):** Invalidate cache for specific path, regenerate
4. **On Layout Change (Single Split):** Invalidate both L/R thumbnails for that source image, regenerate
5. **On Navigation:** Update highlight, ensure current pair visible, request adjacent thumbnails
6. **On File Delete:** Remove from list, shift indices, invalidate cache
7. **On New Scan:** Append to list, generate thumbnail in background

**File: `thumbnail_widgets.py`**

```python
class ThumbnailListWidget(QAbstractScrollArea):
    pair_clicked = Signal(int)  # Emits index when user clicks pair
    
    def sync_with_file_list(self, image_files, current_index, scanner_mode):
        """
        Synchronizes thumbnail list with main image file list.
        
        Args:
            image_files: List of file paths from MainWindow
            current_index: Currently displayed image index
            scanner_mode: 'dual_scan' or 'single_split'
        """
        self.image_files = image_files
        self.current_index = current_index
        self.scanner_mode = scanner_mode
        
        # Calculate total pairs based on mode
        if scanner_mode == 'single_split':
            self.total_pairs = len(image_files)
        else:  # dual_scan
            self.total_pairs = (len(image_files) + 1) // 2
        
        # Update scroll area total height
        ITEM_HEIGHT = 130  # 120px + 10px spacing
        total_height = self.total_pairs * ITEM_HEIGHT
        self.verticalScrollBar().setRange(0, max(0, total_height - self.viewport().height()))
        
        # Request thumbnails for visible range
        self._update_visible_widgets()
    
    def _update_visible_widgets(self):
        """Updates/creates widgets for currently visible pairs"""
        first, last = self._calculate_visible_range()
        
        for pair_index in range(first, last + 1):
            widget = self._get_or_create_widget_for_pair(pair_index)
            
            # Request thumbnails based on mode
            if self.scanner_mode == 'single_split':
                # Request split thumbnails
                source_path = self.image_files[pair_index]
                self.request_split_thumbnail.emit(source_path)
            else:  # dual_scan
                # Request standard thumbnails
                img1_index = pair_index * 2
                if img1_index < len(self.image_files):
                    self.request_thumbnail.emit(self.image_files[img1_index], 0)
                
                img2_index = img1_index + 1
                if img2_index < len(self.image_files):
                    self.request_thumbnail.emit(self.image_files[img2_index], 0)
```

### 1.6 Auto-Scroll to Current Pair

**Method:** Use `QScrollArea.ensureWidgetVisible()` with smooth animation

```python
def scroll_to_current(self, animated=True):
    """
    Scrolls viewport to show currently active pair.
    
    Args:
        animated: If True, uses smooth scroll animation
    """
    if self.current_index < 0:
        return
    
    # Calculate pair index from image index
    if self.scanner_mode == 'single_split':
        pair_index = self.current_index
    else:
        pair_index = self.current_index // 2
    
    # Calculate Y position of this pair
    ITEM_HEIGHT = 130
    target_y = pair_index * ITEM_HEIGHT
    
    if animated:
        # Create smooth scroll animation
        self.scroll_animation = QPropertyAnimation(
            self.verticalScrollBar(), 
            b"value"
        )
        self.scroll_animation.setDuration(300)
        self.scroll_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.scroll_animation.setStartValue(self.verticalScrollBar().value())
        self.scroll_animation.setEndValue(target_y)
        self.scroll_animation.start()
    else:
        self.verticalScrollBar().setValue(target_y)
```

**Integration Point in MainWindow:**

```python
def update_display(self, force_reload=False):
    # ... existing display update logic ...
    
    # Update thumbnail panel
    if hasattr(self, 'thumbnail_panel'):
        self.thumbnail_panel.sync_with_file_list(
            self.image_files,
            self.current_index,
            self.app_config.get("scanner_mode", "dual_scan")
        )
        self.thumbnail_panel.scroll_to_current(animated=True)
```

---

## Feature 2: Search/Navigation by Counter or Filename

### 2.1 UI Component Design

**Location:** Bottom bar, between navigation buttons and status label

**Widget Structure:**
```python
class ImageSearchWidget(QWidget):
    """
    Compact search widget with dual-mode search.
    
    UI: [🔍] [Search input] [x]
         └─ Dropdown: • By Counter (1, 2, 3...)
                      • By Filename (IMG_001.jpg)
    """
    navigate_requested = Signal(int)  # Emits target index
```

**Layout in Bottom Bar:**
```python
# In main_window.py, create_bottom_bar()
self.search_widget = ImageSearchWidget()
self.search_widget.setMaximumWidth(250)
self.search_widget.navigate_requested.connect(self._on_search_navigate)

# Insert between status and navigation buttons
bottom_bar_layout.addWidget(self.status_label)
bottom_bar_layout.addWidget(self.search_widget)  # NEW
bottom_bar_layout.addStretch()
bottom_bar_layout.addWidget(self.prev_btn)
# ... rest of buttons
```

### 2.2 Search Algorithm: Fuzzy Matching

**Challenge:** User might type partial names or approximate counters

**Implementation:**

```python
class ImageSearchWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.search_mode = "counter"  # or "filename"
        self.image_files = []
        self.scanner_mode = "dual_scan"
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by counter or filename...")
        self.search_input.textChanged.connect(self._on_text_changed)
        self.search_input.returnPressed.connect(self._execute_search)
        
        # Completer for autocomplete
        self.completer = QCompleter()
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchContains)
        self.search_input.setCompleter(self.completer)
    
    def update_file_list(self, image_files, scanner_mode):
        """Updates search index when file list changes"""
        self.image_files = image_files
        self.scanner_mode = scanner_mode
        
        # Build autocomplete model
        if self.search_mode == "counter":
            # Counters are 1-indexed display values
            step = 1 if scanner_mode == "single_split" else 2
            suggestions = [str(i + 1) for i in range(0, len(image_files), step)]
        else:  # filename
            suggestions = [os.path.basename(f) for f in image_files]
        
        model = QStringListModel(suggestions)
        self.completer.setModel(model)
    
    def _execute_search(self):
        """Performs search and emits navigation signal"""
        query = self.search_input.text().strip()
        if not query:
            return
        
        target_index = None
        
        if self.search_mode == "counter":
            target_index = self._search_by_counter(query)
        else:
            target_index = self._search_by_filename(query)
        
        if target_index is not None:
            self.navigate_requested.emit(target_index)
            self.search_input.clear()
        else:
            # Visual feedback for not found
            self.search_input.setStyleSheet(
                "QLineEdit { border: 2px solid #C44646; }"
            )
            QTimer.singleShot(1000, lambda: self.search_input.setStyleSheet(""))
    
    def _search_by_counter(self, query):
        """
        Searches by page counter (1-indexed display value).
        Supports:
        - Exact: "42" -> navigates to page 42
        - Range: "40-45" -> navigates to page 40
        - Pair notation: "21-22" in dual mode -> navigates to that pair
        """
        try:
            # Check for range notation
            if '-' in query and query.count('-') == 1:
                start_str, _ = query.split('-')
                target_counter = int(start_str.strip())
            else:
                target_counter = int(query)
            
            if target_counter < 1:
                return None
            
            # Convert 1-indexed counter to 0-indexed array position
            if self.scanner_mode == 'single_split':
                target_index = target_counter - 1
            else:  # dual_scan
                # Counter represents page number, need to find pair
                target_index = (target_counter - 1)
            
            # Validate index
            if 0 <= target_index < len(self.image_files):
                return target_index
            
        except ValueError:
            pass
        
        return None
    
    def _search_by_filename(self, query):
        """
        Searches by filename with fuzzy matching.
        Uses token-based matching for flexibility.
        """
        query_lower = query.lower()
        
        # First try exact match
        for i, filepath in enumerate(self.image_files):
            filename = os.path.basename(filepath).lower()
            if filename == query_lower or os.path.splitext(filename)[0] == query_lower:
                return i
        
        # Then try substring match
        for i, filepath in enumerate(self.image_files):
            filename = os.path.basename(filepath).lower()
            if query_lower in filename:
                return i
        
        # Finally try token matching (handles "IMG 123" matching "IMG_0123.jpg")
        query_tokens = re.findall(r'\w+', query_lower)
        for i, filepath in enumerate(self.image_files):
            filename = os.path.basename(filepath).lower()
            filename_tokens = re.findall(r'\w+', filename)
            
            # Check if all query tokens appear in filename
            if all(any(qt in ft for ft in filename_tokens) for qt in query_tokens):
                return i
        
        return None
```

### 2.3 Visual Search Feedback

**Real-Time Preview:** As user types, show preview of target image

```python
class ImageSearchWidget(QWidget):
    def _on_text_changed(self, text):
        """Shows preview tooltip as user types"""
        if len(text) < 2:
            QToolTip.hideText()
            return
        
        # Perform search without navigating
        if self.search_mode == "counter":
            target_index = self._search_by_counter(text)
        else:
            target_index = self._search_by_filename(text)
        
        if target_index is not None and 0 <= target_index < len(self.image_files):
            # Show preview tooltip
            filepath = self.image_files[target_index]
            filename = os.path.basename(filepath)
            
            # Request thumbnail from cache if available
            preview_text = f"Found: {filename}\nIndex: {target_index + 1}"
            
            global_pos = self.search_input.mapToGlobal(
                QPoint(0, self.search_input.height())
            )
            QToolTip.showText(global_pos, preview_text, self.search_input)
```

### 2.4 Keyboard Shortcuts

**Efficiency Enhancement:**

```python
# In MainWindow.__init__()
from PySide6.QtGui import QShortcut, QKeySequence

# Ctrl+F to focus search
self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
self.search_shortcut.activated.connect(self._focus_search)

# Ctrl+G to switch search mode
self.toggle_search_mode_shortcut = QShortcut(QKeySequence("Ctrl+G"), self)
self.toggle_search_mode_shortcut.activated.connect(
    self.search_widget.toggle_search_mode
)

def _focus_search(self):
    """Focuses search box and selects any existing text"""
    self.search_widget.search_input.setFocus()
    self.search_widget.search_input.selectAll()
```

---

## Feature 3: Improved Crop Area Handles

### 3.1 Problem Analysis

**Current Implementation Issues:**

1. **Small hit targets:** Handles are 10×10px squares
2. **Edge detection tolerance:** Only 10px from exact edge/corner
3. **No visual affordance:** Handles only visible on hover
4. **Competing interactions:** Difficult to distinguish between corner vs. edge vs. move

### 3.2 Enhanced Handle System

**File: `image_viewer.py`**

**Strategy:** Multi-layered interaction zones with visual hierarchy

```python
class ImageViewer(QWidget):
    def __init__(self):
        # ... existing code ...
        
        # NEW: Configurable interaction zones
        self.HANDLE_VISUAL_SIZE = 12  # Visible handle size
        self.HANDLE_CLICK_SIZE = 24   # Actual clickable area (2x larger)
        self.EDGE_TOLERANCE = 20      # Distance from edge to trigger edge drag
        self.CORNER_PRIORITY_ZONE = 35  # Corners take priority in this range
```

**Method 1: Larger Clickable Regions**

Current handle creation:
```python
# OLD
s = 10; s2 = s // 2
self.crop_handles = {
    "top_left": QRect(r.left() - s2, r.top() - s2, s, s),
    # ...
}
```

Enhanced version:
```python
def _update_crop_handles(self):
    """Creates handles with separate visual and interaction rects"""
    r = self.crop_rect_widget
    vs = self.HANDLE_VISUAL_SIZE  # Visual size
    cs = self.HANDLE_CLICK_SIZE   # Click size
    vs2 = vs // 2
    cs2 = cs // 2
    
    # Store both visual and click rectangles
    self.crop_handles = {
        "top_left": {
            'visual': QRect(r.left() - vs2, r.top() - vs2, vs, vs),
            'click': QRect(r.left() - cs2, r.top() - cs2, cs, cs)
        },
        "top_right": {
            'visual': QRect(r.right() - vs2, r.top() - vs2, vs, vs),
            'click': QRect(r.right() - cs2, r.top() - cs2, cs, cs)
        },
        # ... other corners ...
        
        # Edge handles (invisible but functional)
        "top": {
            'visual': QRect(r.center().x() - vs2, r.top() - vs2, vs, vs),
            'click': QRectF(
                r.left() + self.CORNER_PRIORITY_ZONE,
                r.top() - self.EDGE_TOLERANCE,
                r.width() - 2 * self.CORNER_PRIORITY_ZONE,
                2 * self.EDGE_TOLERANCE
            )
        },
        # ... other edges ...
    }
```

**Method 2: Prioritized Hit Testing**

Enhanced `_get_handle_at()` with corner priority:

```python
def _get_handle_at(self, pos):
    """
    Improved handle detection with corner priority.
    
    Algorithm:
    1. Check corners first (highest priority)
    2. Check edges second
    3. Check interior for move operation last
    
    Returns handle name or None
    """
    # Phase 1: Corner detection (highest priority)
    corner_handles = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
    for handle_name in corner_handles:
        if handle_name in self.crop_handles:
            click_rect = self.crop_handles[handle_name]['click']
            if click_rect.contains(pos):
                return handle_name
    
    # Phase 2: Edge detection
    edge_handles = ['top', 'bottom', 'left', 'right']
    for handle_name in edge_handles:
        if handle_name in self.crop_handles:
            click_rect = self.crop_handles[handle_name]['click']
            if isinstance(click_rect, QRectF):
                if click_rect.contains(QPointF(pos)):
                    return handle_name
            elif click_rect.contains(pos):
                return handle_name
    
    # Phase 3: Interior move detection
    if self.crop_rect_widget.contains(pos):
        # Additional check: not too close to edges (prevents accidental moves)
        interior_margin = 15
        interior_rect = self.crop_rect_widget.adjusted(
            interior_margin, interior_margin,
            -interior_margin, -interior_margin
        )
        if interior_rect.contains(pos):
            return "move"
    
    return None
```

### 3.3 Visual Enhancements

**Method 1: Persistent Handle Visibility**

Instead of only showing handles on hover, show them always but with different opacity:

```python
def _draw_cropping_ui(self, painter, pixmap_rect):
    # ... existing overlay drawing ...
    
    # Draw handles with persistent visibility
    painter.setPen(Qt.NoPen)
    
    for handle_name, rects in self.crop_handles.items():
        if 'visual' not in rects:
            continue
        
        visual_rect = rects['visual']
        
        # Color based on handle type
        if handle_name in ['top_left', 'top_right', 'bottom_left', 'bottom_right']:
            # Corners: solid, high visibility
            color = QColor(self.accent_color)
            color.setAlpha(255)
            painter.setBrush(color)
            painter.drawEllipse(visual_rect)  # Circles for corners
            
            # Outer ring for better visibility
            painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
            painter.drawEllipse(visual_rect)
            painter.setPen(Qt.NoPen)
            
        elif handle_name in ['top', 'bottom', 'left', 'right']:
            # Edge handles: semi-transparent, smaller
            color = QColor(self.accent_color)
            color.setAlpha(150)
            painter.setBrush(color)
            painter.drawRect(visual_rect)  # Rectangles for edges
```

**Method 2: Hover State Enhancement**

```python
def mouseMoveEvent(self, event):
    if not self.active_handle:
        # Cursor feedback + visual highlight
        handle = self._get_handle_at(event.pos())
        
        if handle != self._hovered_handle:
            self._hovered_handle = handle
            self.update()  # Repaint to show hover state
        
        # Enhanced cursor shapes
        cursor = Qt.ArrowCursor
        if handle:
            if handle in ["top_left", "bottom_right"]:
                cursor = Qt.SizeFDiagCursor
            elif handle in ["top_right", "bottom_left"]:
                cursor = Qt.SizeBDiagCursor
            elif handle in ["top", "bottom"]:
                cursor = Qt.SizeVerCursor
            elif handle in ["left", "right"]:
                cursor = Qt.SizeHorCursor
            elif handle == "move":
                cursor = Qt.SizeAllCursor
        
        self.setCursor(cursor)
        return
    
    # ... existing drag logic ...
```

**Method 3: Interactive Visual Feedback**

Draw highlighted hover state in `paintEvent`:

```python
def paintEvent(self, event):
    # ... existing drawing ...
    
    # Highlight hovered handle
    if self._hovered_handle and not self.active_handle:
        if self._hovered_handle in self.crop_handles:
            visual_rect = self.crop_handles[self._hovered_handle]['visual']
            
            # Pulsing glow effect
            glow_color = QColor(self.accent_color)
            glow_color.setAlpha(200)
            
            # Draw larger outer circle/rect for glow
            glow_rect = visual_rect.adjusted(-4, -4, 4, 4)
            painter.setPen(QPen(glow_color, 3))
            
            if self._hovered_handle in ['top_left', 'top_right', 'bottom_left', 'bottom_right']:
                painter.drawEllipse(glow_rect)
            else:
                painter.drawRect(glow_rect)
```

### 3.4 Single Split Mode: Dual Rectangle Handles

**Challenge:** Two overlapping rectangles need independent handle systems

**Solution:** Separate handle dictionaries with z-order management

```python
def _update_page_split_handles(self):
    """Enhanced version with larger interaction zones"""
    vs = 14  # Visual size (larger for split mode)
    cs = 28  # Click size
    vs2 = vs // 2
    cs2 = cs // 2
    
    self.page_split_handles = {}
    
    for prefix, r in [('left', self.left_rect_widget), 
                      ('right', self.right_rect_widget)]:
        # Corners
        for corner, (x_pos, y_pos) in [
            ('top_left', (r.left(), r.top())),
            ('top_right', (r.right(), r.top())),
            ('bottom_left', (r.left(), r.bottom())),
            ('bottom_right', (r.right(), r.bottom()))
        ]:
            handle_name = f'{prefix}_{corner}'
            self.page_split_handles[handle_name] = {
                'visual': QRectF(x_pos - vs2, y_pos - vs2, vs, vs),
                'click': QRectF(x_pos - cs2, y_pos - cs2, cs, cs),
                'rect': prefix  # Track which rectangle this belongs to
            }
        
        # Edges with larger tolerance
        edge_tol = 25
        self.page_split_handles[f'{prefix}_top'] = {
            'visual': QRectF(r.center().x() - vs2, r.top() - vs2, vs, vs),
            'click': QRectF(r.left() + 40, r.top() - edge_tol, 
                           r.width() - 80, 2 * edge_tol),
            'rect': prefix
        }
        # ... other edges ...
```

**Z-Order Hit Testing:** Check right rectangle first (drawn on top):

```python
def _get_page_split_handle_at(self, pos):
    """Checks right rect first (top layer), then left"""
    # Priority order: right corners > left corners > right edges > left edges
    
    for prefix in ['right', 'left']:
        # Check corners first
        for corner in ['top_left', 'top_right', 'bottom_left', 'bottom_right']:
            handle_name = f'{prefix}_{corner}'
            if handle_name in self.page_split_handles:
                if self.page_split_handles[handle_name]['click'].contains(QPointF(pos)):
                    return handle_name
    
    # Then check edges
    for prefix in ['right', 'left']:
        for edge in ['top', 'bottom', 'left', 'right']:
            handle_name = f'{prefix}_{edge}'
            if handle_name in self.page_split_handles:
                if self.page_split_handles[handle_name]['click'].contains(QPointF(pos)):
                    return handle_name
    
    return None
```

---

## Feature 4: L/R Labels on Crop Areas

### 4.1 Visual Design Specifications

**Requirements:**
- Very transparent (10-15% opacity)
- Large, centered in each crop rectangle
- Readable but not intrusive
- Should not interfere with image preview

**Typography:**
```
Font: Bold, Sans-serif
Size: Adaptive based on rectangle size (min 48pt, max 120pt)
Color: White with dark outline for contrast
Opacity: 15% fill, 30% outline
```

### 4.2 Implementation in paintEvent

**File: `image_viewer.py`**

```python
def _draw_page_splitting_ui(self, painter, pixmap_rect):
    # ... existing drawing code for overlays and rectangles ...
    
    # NEW: Draw L/R labels
    self._draw_split_labels(painter)

def _draw_split_labels(self, painter):
    """
    Draws large, semi-transparent L and R labels in crop areas.
    Labels scale with rectangle size.
    """
    if self.left_rect_widget.isEmpty() or self.right_rect_widget.isEmpty():
        return
    
    left_enabled = self.current_layout_ratios.get('left_enabled', True)
    right_enabled = self.current_layout_ratios.get('right_enabled', True)
    
    for label_text, rect, enabled in [
        ('L', self.left_rect_widget, left_enabled),
        ('R', self.right_rect_widget, right_enabled)
    ]:
        if not enabled:
            continue  # Don't draw label on disabled page
        
        # Calculate adaptive font size
        # Use 1/3 of rectangle's smaller dimension
        min_dim = min(rect.width(), rect.height())
        font_size = max(48, min(120, int(min_dim / 3)))
        
        font = QFont("Arial", font_size, QFont.Bold)
        painter.setFont(font)
        
        # Measure text to center it precisely
        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(label_text)
        
        # Center position
        text_x = rect.center().x() - text_rect.width() / 2
        text_y = rect.center().y() + text_rect.height() / 2
        
        # Draw outline first (for contrast against any background)
        outline_path = QPainterPath()
        outline_path.addText(text_x, text_y, font, label_text)
        
        outline_color = QColor(0, 0, 0, 80)  # Dark outline, 30% opacity
        painter.strokePath(
            outline_path,
            QPen(outline_color, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        )
        
        # Draw fill
        fill_color = QColor(255, 255, 255, 38)  # White fill, 15% opacity
        painter.fillPath(outline_path, fill_color)
```

### 4.3 Alternative: Numbered Labels (1/2)

For users who prefer numbers over letters:

```python
class ImageViewer(QWidget):
    def __init__(self):
        # ... existing code ...
        self.label_style = "letters"  # or "numbers"
    
    def _draw_split_labels(self, painter):
        # ... same setup code ...
        
        # Determine label text based on style
        if self.label_style == "letters":
            labels = [('L', self.left_rect_widget), ('R', self.right_rect_widget)]
        else:  # numbers
            labels = [('1', self.left_rect_widget), ('2', self.right_rect_widget)]
        
        for label_text, rect, enabled in [
            (labels[0][0], labels[0][1], left_enabled),
            (labels[1][0], labels[1][1], right_enabled)
        ]:
            # ... same drawing code ...
```

### 4.4 Settings Integration

Add label preference to settings dialog:

```python
# In settings_dialog.py, scanner_mode section
label_style_group = QGroupBox("Split Mode Label Style")
label_style_layout = QHBoxLayout()

self.letters_radio = QRadioButton("Letters (L/R)")
self.numbers_radio = QRadioButton("Numbers (1/2)")

label_style_layout.addWidget(self.letters_radio)
label_style_layout.addWidget(self.numbers_radio)
label_style_group.setLayout(label_style_layout)

# Add to config
# DEFAULT_CONFIG["split_label_style"] = "letters"
```

Apply setting:

```python
# In SingleSplitModeWidget.__init__()
label_style = self.app_config.get("split_label_style", "letters")
self.viewer.label_style = label_style
```

### 4.5 Dynamic Opacity Based on Edit State

**Enhancement:** Reduce label opacity during active dragging to improve visibility

```python
def _draw_split_labels(self, painter):
    # Adjust opacity based on interaction state
    if self.active_handle and ('left_' in self.active_handle or 'right_' in self.active_handle):
        # Reduce opacity by 50% during drag
        fill_opacity = 20  # Instead of 38
        outline_opacity = 40  # Instead of 80
    else:
        fill_opacity = 38
        outline_opacity = 80
    
    # ... rest of drawing code with adjusted opacities ...
```

---

## Integration Summary

### MainWindow Modifications

**File: `main_window.py`**

1. **Add thumbnail panel to sidebar:**
```python
def create_sidebar(self):
    # ... existing code ...
    
    # INSERT before stats_group
    thumbnail_group = QGroupBox("Pages")
    thumbnail_layout = QVBoxLayout(thumbnail_group)
    
    self.thumbnail_panel = ThumbnailListWidget()
    self.thumbnail_panel.pair_clicked.connect(self._on_thumbnail_clicked)
    self.thumbnail_panel.request_thumbnail.connect(
        self.image_processor.request_thumbnail
    )
    self.thumbnail_panel.request_split_thumbnail.connect(
        self.image_processor.generate_split_thumbnails
    )
    
    thumbnail_layout.addWidget(self.thumbnail_panel)
    sidebar_layout.insertWidget(0, thumbnail_group)  # Top of sidebar
```

2. **Add search widget to bottom bar:**
```python
def create_bottom_bar(self, main_layout):
    # ... existing code ...
    
    self.search_widget = ImageSearchWidget()
    self.search_widget.navigate_requested.connect(self._on_search_navigate)
    
    # Insert after status_label
    bottom_bar_layout.addWidget(self.search_widget)
```

3. **Connect thumbnail updates:**
```python
def on_initial_scan_complete(self, files):
    # ... existing code ...
    
    # Update thumbnail panel
    self.thumbnail_panel.update_file_list(
        files,
        self.app_config.get("scanner_mode", "dual_scan")
    )
    self.search_widget.update_file_list(
        files,
        self.app_config.get("scanner_mode", "dual_scan")
    )
```

### Performance Considerations

**Memory Budget:**
- 200 thumbnails @ 90×110 RGB = ~6MB
- Virtual scrolling widgets: negligible (20-30 widgets max)
- Total overhead: < 10MB

**CPU Budget:**
- Thumbnail generation: ~5-10ms per image (background thread)
- Search operations: < 1ms (simple string matching)
- Handle hit-testing: < 0.1ms (geometric calculations)

**Expected User Experience:**
- Thumbnail panel scrolls smoothly at 60fps
- Search results appear instantly (< 100ms)
- Crop handle interactions feel responsive (no input lag)
- L/R labels remain readable but unobtrusive