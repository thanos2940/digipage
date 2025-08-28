import tkinter as tk
from style import Style

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
