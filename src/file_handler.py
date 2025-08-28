from watchdog.events import FileSystemEventHandler

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
