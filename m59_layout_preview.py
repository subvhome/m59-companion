import tkinter as tk
from tkinter import ttk

class LayoutPreview(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("M59 Companion - Layout Concepts Preview")
        self.geometry("1000x700")
        self.configure(bg="#1E1E1E")
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background="#1E1E1E")
        self.style.configure("TLabel", background="#1E1E1E", foreground="#FFFFFF")
        self.style.configure("TButton", background="#333333", foreground="#FFFFFF")
        self.style.configure("TNotebook", background="#1E1E1E", borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#333333", foreground="#FFFFFF", padding=[10, 5])
        self.style.map("TNotebook.Tab", background=[("selected", "#0078D7")])

        self.edit_mode = False

        # Top controls
        top_bar = ttk.Frame(self)
        top_bar.pack(side="top", fill="x", padx=10, pady=10)
        ttk.Label(top_bar, text="Layout Concept Mode:", font=("Segoe UI", 12, "bold")).pack(side="left", padx=5)
        ttk.Button(top_bar, text="Tabbed + Dock View", command=self.show_tabbed).pack(side="left", padx=5)
        ttk.Button(top_bar, text="One-Page Dashboard View", command=self.show_one_page).pack(side="left", padx=5)

        self.main_container = ttk.Frame(self)
        self.main_container.pack(expand=True, fill="both", padx=10, pady=10)

        self.show_tabbed()

    def clear_container(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()

    def show_tabbed(self):
        self.clear_container()
        
        # Left side: Tabs
        notebook = ttk.Notebook(self.main_container)
        notebook.pack(side="left", expand=True, fill="both", padx=(0, 10))

        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="Dashboard")
        ttk.Label(tab1, text="Main Dashboard area. You can add elements to the dock from here.", font=("Segoe UI", 10)).pack(pady=20)
        ttk.Button(tab1, text="[+] Add Who List to Dock").pack(pady=5)
        ttk.Button(tab1, text="[+] Add Game Time to Dock").pack(pady=5)

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="Vaults")
        ttk.Label(tab2, text="Vault content here.").pack(pady=20)
        ttk.Button(tab2, text="[+] Add Vault Tracking to Dock").pack(pady=5)

        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="Map")
        ttk.Label(tab3, text="Map content here.").pack(pady=20)

        # Right side: Dock
        self.build_dock()

    def show_one_page(self):
        self.clear_container()
        
        # Left side: Grid of elements (Bento box style)
        grid_frame = ttk.Frame(self.main_container)
        grid_frame.pack(side="left", expand=True, fill="both", padx=(0, 10))

        # A 2x2 grid representing the single page
        f1 = tk.Frame(grid_frame, bg="#2D2D2D", bd=1, relief="solid")
        f1.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        ttk.Label(f1, text="Game Time & Stats", background="#2D2D2D").pack(pady=10)

        f2 = tk.Frame(grid_frame, bg="#2D2D2D", bd=1, relief="solid")
        f2.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        ttk.Label(f2, text="Active Who List", background="#2D2D2D").pack(pady=10)

        f3 = tk.Frame(grid_frame, bg="#2D2D2D", bd=1, relief="solid")
        f3.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        ttk.Label(f3, text="Vault Overview", background="#2D2D2D").pack(pady=10)

        f4 = tk.Frame(grid_frame, bg="#2D2D2D", bd=1, relief="solid")
        f4.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        ttk.Label(f4, text="Map / Navigation", background="#2D2D2D").pack(pady=10)

        grid_frame.rowconfigure(0, weight=1)
        grid_frame.rowconfigure(1, weight=1)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        # Right side: Dock
        self.build_dock()

    def build_dock(self):
        dock_frame = tk.Frame(self.main_container, bg="#252525", width=250)
        dock_frame.pack(side="right", fill="y")
        dock_frame.pack_propagate(False)

        header = tk.Frame(dock_frame, bg="#333333")
        header.pack(fill="x")
        ttk.Label(header, text="DOCK", font=("Segoe UI", 10, "bold"), background="#333333").pack(side="left", padx=10, pady=5)
        
        edit_btn = ttk.Button(header, text="✏️ Edit", width=6, command=self.toggle_edit)
        edit_btn.pack(side="right", padx=5, pady=5)
        self.edit_btn = edit_btn

        self.dock_content = tk.Frame(dock_frame, bg="#252525")
        self.dock_content.pack(expand=True, fill="both", padx=5, pady=5)

        self.render_dock_items()

    def toggle_edit(self):
        self.edit_mode = not self.edit_mode
        self.edit_btn.config(text="✅ Done" if self.edit_mode else "✏️ Edit")
        self.render_dock_items()

    def render_dock_items(self):
        for w in self.dock_content.winfo_children():
            w.destroy()
            
        items = ["Time Widget", "Who List Tracker", "Vault Watcher"]
        
        for idx, item in enumerate(items):
            item_frame = tk.Frame(self.dock_content, bg="#3C3C3C", bd=1, relief="solid")
            item_frame.pack(fill="x", pady=5)
            
            if self.edit_mode:
                # Add drag handles and remove buttons in edit mode
                ttk.Label(item_frame, text="↕", background="#3C3C3C", cursor="fleur").pack(side="left", padx=5)
                ttk.Label(item_frame, text=item, background="#3C3C3C").pack(side="left", pady=10, padx=5)
                ttk.Button(item_frame, text="X", width=3).pack(side="right", padx=5)
            else:
                ttk.Label(item_frame, text=item, background="#3C3C3C").pack(side="left", pady=10, padx=15)

if __name__ == "__main__":
    app = LayoutPreview()
    app.mainloop()
