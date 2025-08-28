import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox

from style import Style, lighten_color
from config import CONFIG_FILE, DEFAULT_IMAGE_LOAD_TIMEOUT_MS
from tooltip import ToolTip
from image_scanner_app import ImageScannerApp

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
