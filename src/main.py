import sys
from tkinter import messagebox
from main_controller import App

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

if __name__ == "__main__":
    app = App()
    app.mainloop()
