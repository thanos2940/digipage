import os
import json
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from style import Style
from config import THEMES, CONFIG_FILE, DEFAULT_IMAGE_LOAD_TIMEOUT_MS
from tooltip import ToolTip

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
