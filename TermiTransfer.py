import os
import json
import logging
import threading
import time
import paramiko
import copy

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog

# ─── Config Path ───

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".termi_transfer_config.json")
FONT = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 11, "bold")
FONT_TEXT = ("Microsoft YaHei UI", 11)

# ─── Default Profiles ───

DEFAULT_PROFILES = {
    "Default": {
        "host": "",
        "port": "22",
        "user": "",
        "key": "",
        "presets": {
            "~/": "~/",
        },
        "remote_files": "",
        "local_dest": "",
    },
}

def load_config():
    """Load config from disk. Password is never persisted."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            logging.warning(f"Config load error: {e}")
            return {"profiles": dict(DEFAULT_PROFILES), "active_profile": "Default"}
        # Merge missing default presets into existing profiles
        saved_profiles = cfg.get("profiles", {})
        for name, defaults in DEFAULT_PROFILES.items():
            if name in saved_profiles:
                for key, val in defaults.items():
                    if key not in saved_profiles[name]:
                        saved_profiles[name][key] = val
                    elif key == "presets" and isinstance(val, dict):
                        for pk, pv in val.items():
                            if pk not in saved_profiles[name]["presets"]:
                                saved_profiles[name]["presets"][pk] = pv
            else:
                saved_profiles[name] = dict(defaults)
        # Strip legacy password field if present (password is never saved)
        for _pd in cfg.get("profiles", {}).values():
            _pd.pop("password", None)
        return cfg
    return {"profiles": dict(DEFAULT_PROFILES), "active_profile": "Default"}

def save_config(config):
    """Save config to disk. Password is intentionally excluded."""
    try:
        cfg_copy = copy.deepcopy(config)
        # Remove password before writing to disk
        for _pd in cfg_copy.get("profiles", {}).values():
            _pd.pop("password", None)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg_copy, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.warning(f"Config save error: {e}")

class RoundedTabBar:
    """Rounded-corner tab bar using tk.Button that switches associated Frames."""
    PAD_X = 20

    def __init__(self, parent, theme):
        self.parent = parent
        self.theme = theme
        self.tabs = []
        self.selected = 0
        self.bar = tk.Frame(parent)
        self.bar.pack(fill=tk.X, padx=4, pady=(4, 0))
        self.content = ttk.Frame(parent)
        self.content.pack(fill=tk.BOTH, expand=True)

    def add(self, frame, text="", underline=-1):
        frame.pack_forget()
        btn = tk.Button(
            self.bar, text=text, relief="flat", bd=0, highlightthickness=0, takefocus=0, cursor="hand2",
            padx=self.PAD_X, pady=4, font=FONT_BOLD,
            activeforeground="#ffffff", underline=underline,
        )
        btn.pack(side=tk.LEFT, padx=(0, 4))
        idx = len(self.tabs)
        btn.configure(command=lambda i=idx: self.select(i))
        btn.bind("<Enter>", lambda e, i=idx: self._hover(i))
        btn.bind("<Leave>", lambda e, i=idx: self._unhover(i))
        self.tabs.append((text, frame, btn))
        self._style_btn(btn, selected=(idx == self.selected))
        if idx == 0:
            frame.pack(in_=self.content, fill=tk.BOTH, expand=True)

    def select(self, idx):
        if idx == self.selected and len(self.tabs) > 1:
            return
        _, old_frame, old_btn = self.tabs[self.selected]
        old_frame.pack_forget()
        self._style_btn(old_btn, selected=False)
        self.selected = idx
        _, new_frame, new_btn = self.tabs[idx]
        new_frame.pack(in_=self.content, fill=tk.BOTH, expand=True)
        self._style_btn(new_btn, selected=True)

    def set_theme(self, theme):
        self.theme = theme
        self.bar.configure(bg=theme["bg"])
        for i, (_, _, btn) in enumerate(self.tabs):
            self._style_btn(btn, selected=(i == self.selected))

    def _style_btn(self, btn, selected):
        t = self.theme
        if selected:
            btn.configure(bg=t["accent"], fg="#ffffff", activebackground=t["accent"])
        else:
            btn.configure(bg=t["btn_bg"], fg=t["btn_fg"],
                          activebackground=t.get("btn_hover", t["accent"]))

    def _hover(self, idx):
        if idx != self.selected:
            self.tabs[idx][2].configure(bg=self.theme.get("btn_hover", self.theme["accent"]))

    def _unhover(self, idx):
        if idx != self.selected:
            self.tabs[idx][2].configure(bg=self.theme["btn_bg"])

class TermuxTransferApp:

    def __init__(self, root):
        self.root = root
        self.root.title("⇄ TermiTransfer")
        self.root.minsize(1000, 750)
        # Maximize on open
        try:
            self.root.state("zoomed")  # Windows
        except Exception:
            try:
                self.root.attributes("-zoomed", True)  # Linux
            except Exception:
                pass
        # Load config
        self.config = load_config()
        self.profiles = self.config.get("profiles", dict(DEFAULT_PROFILES))
        self.active_profile = self.config.get("active_profile", "Default")
        if self.active_profile not in self.profiles:
            self.active_profile = list(self.profiles.keys())[0]
        self.dest_vars = {}
        self._dynamic_frame = None
        self._conn_collapsed = False  # connection settings default expanded
        self.current_theme = self.config.get("theme", "dark")
        if self.current_theme not in self.THEMES:
            self.current_theme = "dark"
        self._ssh_cache = {}  # SSH connection cache: (host, port, user) -> client
        self.setup_ui()
        self.setup_shortcuts()
        self._apply_theme(self.current_theme)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    THEMES = {
        "dark": {
            "bg": "#1e1e1e", "fg": "#d4d4d4", "entry_bg": "#2d2d2d",
            "entry_fg": "#d4d4d4", "btn_bg": "#3c3c3c", "btn_fg": "#d4d4d4",
            "frame_bg": "#1e1e1e", "accent": "#569cd6",
        },
        "light": {
            "bg": "#ffffff", "fg": "#1e1e1e", "entry_bg": "#ffffff",
            "entry_fg": "#1e1e1e", "btn_bg": "#e1e1e1", "btn_fg": "#1e1e1e",
            "frame_bg": "#ffffff", "accent": "#0066cc",
        },
    }

    def _make_btn(self, parent, text, command=None, width=None, **kw):
        """Create a borderless tk.Button matching the tab bar style."""
        t = self.THEMES[self.current_theme]
        btn = tk.Button(
            parent, text=text, command=command, relief="flat", bd=0,
            highlightthickness=0, takefocus=0, cursor="hand2",
            padx=10, pady=3, font=FONT_BOLD,
            bg=t["btn_bg"], fg=t["btn_fg"],
            activebackground=t.get("btn_hover", t["accent"]),
            activeforeground="#ffffff",
        )
        if width:
            btn.configure(width=width)
        btn.configure(**kw)

        def on_enter(e):
            if btn["state"] != "disabled":
                btn.configure(bg=t.get("btn_hover", t["accent"]))

        def on_leave(e):
            if btn["state"] != "disabled":
                btn.configure(bg=t["btn_bg"])

        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn

    def _restyle_buttons(self, t):
        """Update all tk.Button children with current theme colors."""
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Button):
                    c.configure(bg=t["btn_bg"], fg=t["btn_fg"],
                                activebackground=t.get("btn_hover", t["accent"]),
                                activeforeground="#ffffff")
                walk(c)
        walk(self.root)

    def _toggle_theme(self):
        self._apply_theme("light" if self.current_theme == "dark" else "dark")

    def _apply_ttk_styles(self, t):
        """Apply theme colors to ttk.Style."""
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=t["bg"], foreground=t["fg"],
                        fieldbackground=t["entry_bg"], insertcolor=t["fg"])
        style.configure("TFrame", background=t["bg"])
        style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        style.configure("TButton", background=t["btn_bg"], foreground=t["btn_fg"],
                        fieldbackground=t["btn_bg"])
        style.configure("TCheckbutton", background=t["bg"], foreground=t["fg"])
        style.configure("TLabelframe", background=t["bg"], foreground=t["fg"],
                        bordercolor=t["bg"], relief="flat")
        style.configure("TLabelframe.Label", background=t["bg"], foreground=t["accent"])
        style.configure("TCombobox", fieldbackground=t["entry_bg"],
                        foreground=t["entry_fg"], background=t["btn_bg"],
                        selectbackground=t["accent"], selectforeground="#ffffff")
        style.map("TCombobox",
                  fieldbackground=[("readonly", t["entry_bg"]),
                                   ("focus", t["entry_bg"]),
                                   ("disabled", t["bg"])],
                  foreground=[("readonly", t["entry_fg"]),
                              ("focus", t["entry_fg"]),
                              ("disabled", t["fg"])],
                  background=[("readonly", t["btn_bg"]),
                              ("focus", t["btn_bg"])])
        style.configure("TEntry", fieldbackground=t["entry_bg"],
                        foreground=t["entry_fg"])
        style.map("TEntry",
                  fieldbackground=[("focus", t["entry_bg"]),
                                   ("disabled", t["bg"])],
                  foreground=[("focus", t["entry_fg"]),
                              ("disabled", t["fg"])])
        style.configure("TNotebook", background=t["bg"])
        style.configure("TNotebook.Tab", background=t["btn_bg"], foreground=t["btn_fg"])
        style.map("TNotebook.Tab",
                  background=[("selected", t["accent"])],
                  foreground=[("selected", "#ffffff")])
        style.map("TButton",
                  background=[("active", t["accent"])],
                  foreground=[("active", "#ffffff")])

    def _apply_widget_styles(self, t):
        """Apply theme colors to named and dynamic widgets."""
        # Text widgets (ScrolledText)
        for wname in ("log_output", "file_text", "remote_files_input", "config_preview"):
            w = getattr(self, wname, None)
            if w is not None:
                try:
                    w.configure(bg=t["entry_bg"], fg=t["entry_fg"],
                                insertbackground=t["fg"], font=FONT_TEXT)
                except Exception:
                    pass
        # Force Entry/Combobox widgets to pick up dark colors
        for wname in ("host_entry", "port_entry", "user_entry", "key_entry",
                      "local_dest_entry"):
            w = getattr(self, wname, None)
            if w is not None:
                try:
                    w.configure(foreground=t["entry_fg"], background=t["entry_bg"],
                                fieldbackground=t["entry_bg"],
                                insertbackground=t["fg"], font=FONT)
                except Exception:
                    pass
        # Combobox: profile selector
        if getattr(self, "profile_combo", None) is not None:
            try:
                self.profile_combo.configure(
                    foreground=t["entry_fg"], background=t["entry_bg"],
                    fieldbackground=t["entry_bg"], font=FONT)
            except Exception:
                pass
        # Recursively apply theme to ALL Entry descendants (incl. dynamic presets)
        def _style_entries(parent):
            for w in parent.winfo_children():
                if isinstance(w, ttk.Entry):
                    try:
                        w.configure(foreground=t["entry_fg"],
                                    fieldbackground=t["entry_bg"],
                                    insertbackground=t["fg"], font=FONT)
                    except Exception:
                        pass
                _style_entries(w)
        _style_entries(self.root)

    def _apply_theme(self, theme_name):
        """Apply a color theme to the entire app."""
        t = self.THEMES.get(theme_name, self.THEMES["dark"])
        self.current_theme = theme_name
        self.root.configure(bg=t["bg"])
        self._apply_ttk_styles(t)
        self._apply_widget_styles(t)
        self._restyle_buttons(t)
        if getattr(self, "tab_bar", None) is not None:
            self.tab_bar.set_theme(t)
        self.config["theme"] = theme_name

    def on_close(self):
        self.save_current_profile()
        save_config(self.config)
        # Close cached SSH connections
        for client, _ in self._ssh_cache.values():
            try:
                client.close()
            except Exception:
                pass
        self._ssh_cache.clear()
        self.root.destroy()

    def setup_shortcuts(self):
        # Tab navigation
        self.root.bind("<Alt-Up>", lambda e: self.tab_bar.select(0))
        self.root.bind("<Alt-Down>", lambda e: self.tab_bar.select(1))
        self.root.bind("<Alt-c>", lambda e: self.tab_bar.select(2))

        # Upload tab
        self.root.bind("<Alt-a>", lambda e: self.add_files())
        self.root.bind("<Alt-f>", lambda e: self.file_text.focus_set())
        self.root.bind("<Alt-l>", lambda e: self.clear_files())
        self.root.bind("<Alt-s>", lambda e: self.execute_upload())

        # Download tab
        self.root.bind("<Alt-b>", lambda e: self.browse_local_dest())
        self.root.bind("<Alt-d>", lambda e: self.execute_download())
        self.root.bind("<Alt-u>", lambda e: self._focus_first_preset())

        # Profile management
        self.root.bind("<Alt-p>", lambda e: self._cycle_profile())
        self.root.bind("<Alt-Insert>", lambda e: self._add_profile())

        self.root.bind("<Alt-m>", lambda e: self._remove_profile())

        # Config tab
        self.root.bind("<Alt-i>", lambda e: self._import_config())
        self.root.bind("<Alt-e>", lambda e: self._export_config())
        self.root.bind("<Alt-plus>", lambda e: self._add_profile())

        # Connection fields focus
        self.root.bind("<Alt-h>", lambda e: self.host_entry.focus_set())
        self.root.bind("<Alt-t>", lambda e: self.port_entry.focus_set())
        self.root.bind("<Alt-r>", lambda e: self.user_entry.focus_set())
        self.root.bind("<Alt-k>", lambda e: self.key_entry.focus_set())
        self.root.bind("<Alt-w>", lambda e: self.password_entry.focus_set())

        # Theme toggle
        self.root.bind("<Control-Alt-m>", lambda e: self._toggle_theme())


    def setup_ui(self):
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        # Connection Settings (always visible, not rebuilt on profile switch)
        self._build_connection_frame()
        # Dynamic area: tabs (built once, data refreshed on profile switch)
        self._build_tabs()
        # Log (created once, never destroyed)
        self._build_log_area()

    def _build_connection_frame(self):
        conn_frame = ttk.LabelFrame(
            self.main_frame, text="⚙ Connection Settings", padding="5"
        )
        conn_frame.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Profile selector + toggle button
        row1 = ttk.Frame(conn_frame)
        row1.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(row1, text="📋 Profile:", font=FONT_BOLD).pack(side=tk.LEFT, padx=5)
        self.profile_var = tk.StringVar(value=self.active_profile)
        profile_names = list(self.profiles.keys())
        self.profile_combo = ttk.Combobox(
            row1, textvariable=self.profile_var,
            values=profile_names, state="readonly", width=18,
        )
        self.profile_combo.pack(side=tk.LEFT, padx=5)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_change)

        # Add / Remove / Cycle profile buttons
        self._make_btn(row1, text="＋ Add", underline=0, command=self._add_profile).pack(side=tk.LEFT, padx=2)
        self._make_btn(row1, text="✕ Remove", underline=4, command=self._remove_profile).pack(side=tk.LEFT, padx=2)
        self._make_btn(row1, text="⇅ Cycle Profile", underline=8, command=self._cycle_profile).pack(side=tk.LEFT, padx=2)

        # Connection toggle button
        self._conn_toggle_btn = self._make_btn(row1, text="▶ Show Connection", command=self._toggle_conn_fields)
        self._conn_toggle_btn.pack(side=tk.LEFT, padx=(10, 2))

        # Connection summary label (shown when collapsed)
        self._conn_summary_var = tk.StringVar()
        self._conn_summary = ttk.Label(row1, textvariable=self._conn_summary_var, foreground="#888888")
        self._conn_summary.pack(side=tk.LEFT, padx=5)

        # Theme toggle (top-right area)
        theme_frame = ttk.Frame(row1)
        theme_frame.pack(side=tk.RIGHT, padx=5)
        ttk.Label(theme_frame, text="Theme:").pack(side=tk.LEFT)
        for tname, tlabel in [("dark", "☽ Dark"), ("light", "☼ Light")]:
            self._make_btn(theme_frame, tlabel, width=7, command=lambda n=tname: self._apply_theme(n)).pack(side=tk.LEFT, padx=1)

        # Row 2: Host / Port / User / Key / Password (collapsible)
        self._row2_frame = ttk.Frame(conn_frame)

        row2 = self._row2_frame
        ttk.Label(row2, text="🖥 Host:", underline=3).pack(side=tk.LEFT, padx=5)
        self.host_entry = ttk.Entry(row2)
        self.host_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.host_entry.bind("<KeyRelease>", lambda e: self._on_conn_field_edit())
        ttk.Label(row2, text="🔌 Port:", underline=6).pack(side=tk.LEFT, padx=5)
        self.port_entry = ttk.Entry(row2, width=10)
        self.port_entry.pack(side=tk.LEFT, padx=5)
        self.port_entry.bind("<KeyRelease>", lambda e: self._on_conn_field_edit())
        ttk.Label(row2, text="👤 User:", underline=6).pack(side=tk.LEFT, padx=5)
        self.user_entry = ttk.Entry(row2)
        self.user_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.user_entry.bind("<KeyRelease>", lambda e: self._on_conn_field_edit())

        ttk.Label(row2, text="🔑 Key:", underline=3).pack(side=tk.LEFT, padx=5)
        self.key_entry = ttk.Entry(row2)
        self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.key_entry.bind("<KeyRelease>", lambda e: self._on_conn_field_edit())
        ttk.Label(row2, text="🔒 Password:", underline=7).pack(side=tk.LEFT, padx=5)
        self.password_entry = ttk.Entry(row2, show="*")
        self.password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.password_entry.bind("<KeyRelease>", lambda e: self._on_conn_field_edit())

        # Fill fields from active profile
        self._load_profile_fields()
        # Apply initial collapsed state
        self._update_conn_summary()
        if self._conn_collapsed:
            self._conn_toggle_btn.configure(text="▶ Show Connection")
            self._conn_summary.pack(side=tk.LEFT, padx=5)
        else:
            self._row2_frame.pack(fill=tk.X)
            self._conn_toggle_btn.configure(text="▼ Hide Connection")
            self._conn_summary.pack_forget()

    def _toggle_conn_fields(self):
        self._conn_collapsed = not self._conn_collapsed
        if self._conn_collapsed:
            self._row2_frame.pack_forget()
            self._conn_toggle_btn.configure(text="▶ Show Connection")
            self._update_conn_summary()
            self._conn_summary.pack(side=tk.LEFT, padx=5)
        else:
            self._conn_summary.pack_forget()
            self._row2_frame.pack(fill=tk.X)
            self._conn_toggle_btn.configure(text="▼ Hide Connection")

    def _update_conn_summary(self):
        user = self.user_entry.get().strip() or "?"
        host = self.host_entry.get().strip() or "?"
        port = self.port_entry.get().strip() or "22"
        self._conn_summary_var.set(f"{user}@{host}:{port}")

    def _refresh_all_ui(self):
        """Refresh all UI elements from current profile data."""
        self._load_profile_fields()
        self._refresh_presets()
        self._refresh_download_fields()
        self._refresh_config_preview()
        self._update_conn_summary()

    def _on_conn_field_edit(self):
        """Sync connection field edits to profile dict and refresh preview."""
        self._update_conn_summary()
        p = self._get_profile()
        p["host"] = self.host_entry.get().strip()
        p["port"] = self.port_entry.get().strip()
        p["user"] = self.user_entry.get().strip()
        p["key"] = self.key_entry.get().strip()
        p["password"] = self.password_entry.get().strip()
        self._refresh_config_preview()

    def _build_tabs(self):
        """Destroy and recreate tabs (called only from setup_ui)."""
        if self._dynamic_frame is not None:
            self._dynamic_frame.destroy()
        self._dynamic_frame = ttk.Frame(self.main_frame)
        self._dynamic_frame.pack(fill=tk.BOTH, expand=True)

        # Rounded-corner tab bar
        self.tab_bar = RoundedTabBar(self._dynamic_frame, self.THEMES[self.current_theme])

        self.upload_tab = ttk.Frame(self._dynamic_frame)
        self._build_upload_tab()
        self.tab_bar.add(self.upload_tab, text="⬆ Upload", underline=0)

        self.download_tab = ttk.Frame(self._dynamic_frame)
        self._build_download_tab()
        self.tab_bar.add(self.download_tab, text="⬇ Download", underline=0)

        self.config_tab = ttk.Frame(self._dynamic_frame)
        self._build_config_tab()
        self.tab_bar.add(self.config_tab, text="⚙ Config", underline=2)

        self._apply_theme(self.current_theme)

    def _build_log_area(self):
        """Create log area once (never destroyed)."""
        log_frame = ttk.LabelFrame(self.main_frame, text="📋 Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        # Clear button in the label frame
        clear_btn = self._make_btn(log_frame, text="🗑 Clear", command=self._clear_log)
        clear_btn.pack(anchor="e", pady=(0, 2))
        self.log_output = scrolledtext.ScrolledText(log_frame, state="disabled", height=10)
        self.log_output.pack(fill=tk.BOTH, expand=True)
        # Log color tags
        self.log_output.tag_configure("error", foreground="#f44747")
        self.log_output.tag_configure("success", foreground="#6a9955")
        self.log_output.tag_configure("warning", foreground="#d7ba7d")
        self.log_output.tag_configure("info", foreground="#569cd6")
        # Progress bar (hidden by default)
        self.progress_frame = ttk.Frame(log_frame)
        self.progress_frame.pack(fill=tk.X, pady=(2, 0))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self.progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.progress_label = ttk.Label(self.progress_frame, text="", width=20)
        self.progress_label.pack(side=tk.RIGHT, padx=(5, 0))
        self.progress_frame.pack_forget()  # Hidden initially

    def _build_upload_tab(self):
        layout = ttk.Frame(self.upload_tab, padding="10")
        layout.pack(fill=tk.BOTH, expand=True)

        # Left: Files
        left = ttk.Frame(layout)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        ttk.Label(left, text="📄 Selected Files (one per line):", underline=12).pack(anchor="w")
        self.file_text = scrolledtext.ScrolledText(left, height=10)
        self.file_text.pack(fill=tk.BOTH, expand=True, pady=5)
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=tk.X)
        self._make_btn(btn_frame, text="＋ Add Files", underline=2, command=self.add_files).pack(side=tk.LEFT, padx=(0, 5))
        self._make_btn(btn_frame, text="🗑 Clear", underline=4, command=self.clear_files).pack(side=tk.LEFT)

        # Right: Destinations
        right = ttk.Frame(layout)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Preset container (structure created once, data refreshed)
        self._dest_group = ttk.LabelFrame(right, text="📁 Upload to:", padding="5", underline=3)
        self._dest_group.pack(fill=tk.X, pady=5)

        # Preset rows container (inside dest_group)
        self._preset_rows_frame = ttk.Frame(self._dest_group)
        self._preset_rows_frame.pack(fill=tk.X)

        # Add Preset button (persistent)
        add_preset_frame = ttk.Frame(self._dest_group)
        add_preset_frame.pack(fill=tk.X, pady=(5, 0))
        self._make_btn(add_preset_frame, text="＋ Add Preset", command=self._add_preset).pack(side=tk.LEFT)

        # Upload button
        self.upload_btn = self._make_btn(right, "⬆ Start Upload", underline=2, command=self.execute_upload)
        self.upload_btn.pack(pady=20, fill=tk.X)

        # Populate preset data
        self._refresh_presets()

    def _refresh_presets(self):
        """Rebuild preset rows from current profile data. Reuse widgets when count matches."""
        profile = self._get_profile()
        presets = profile.get("presets", {})
        saved_preset_sel = profile.get("_preset_selected", {})
        preset_names = list(presets.keys())
        preset_paths = list(presets.values())

        # Get existing rows
        existing_rows = self._preset_rows_frame.winfo_children()

        # If count matches, reuse existing widgets
        if len(existing_rows) == len(preset_names):
            self.dest_vars = {}
            self._preset_entries = {}
            self._preset_remove_btns = {}
            for i, (name, path) in enumerate(zip(preset_names, preset_paths)):
                row = existing_rows[i]
                children = row.winfo_children()
                # children: [Checkbutton, Entry, Button]
                var = tk.BooleanVar(value=saved_preset_sel.get(name, False))
                self.dest_vars[name] = var
                children[0].configure(variable=var)  # Checkbutton
                children[1].delete(0, tk.END)
                children[1].insert(0, path)  # Entry
                self._preset_entries[name] = children[1]
                children[2].configure(command=lambda n=name: self._remove_preset(n))  # Remove button
                self._preset_remove_btns[name] = children[2]
        else:
            # Count changed, destroy and recreate
            for w in existing_rows:
                w.destroy()
            self.dest_vars = {}
            self._preset_entries = {}
            self._preset_remove_btns = {}
            for name, path in zip(preset_names, preset_paths):
                var = tk.BooleanVar(value=saved_preset_sel.get(name, False))
                self.dest_vars[name] = var
                row = ttk.Frame(self._preset_rows_frame)
                row.pack(fill=tk.X, anchor="w")
                ttk.Checkbutton(row, variable=var).pack(side=tk.LEFT)
                ent = ttk.Entry(row)
                ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 4))
                ent.insert(0, path)
                self._preset_entries[name] = ent
                rm_btn = self._make_btn(row, "✕", width=2, command=lambda n=name: self._remove_preset(n))
                rm_btn.pack(side=tk.RIGHT)
                self._preset_remove_btns[name] = rm_btn

        # Apply theme to entries
        t = self.THEMES[self.current_theme]
        font_spec = FONT
        for ent in self._preset_entries.values():
            try:
                ent.configure(foreground=t["entry_fg"], fieldbackground=t["entry_bg"],
                              insertbackground=t["fg"], font=font_spec)
            except Exception:
                pass

    def _refresh_download_fields(self):
        """Refresh download tab fields from current profile data."""
        profile = self._get_profile()
        if hasattr(self, "remote_files_input"):
            self.remote_files_input.delete("1.0", tk.END)
            saved_remote = profile.get("remote_files", "")
            if saved_remote:
                self.remote_files_input.insert("1.0", saved_remote)
        if hasattr(self, "local_dest_entry"):
            self.local_dest_entry.delete(0, tk.END)
            saved_local = profile.get("local_dest", "")
            self.local_dest_entry.insert(0, saved_local if saved_local else os.getcwd())

    def _build_download_tab(self):
        layout = ttk.Frame(self.download_tab, padding="10")
        layout.pack(fill=tk.BOTH, expand=True)

        profile = self._get_profile()
        ttk.Label(layout, text="🌐 Remote File Paths (one per line):").pack(anchor="w")
        self.remote_files_input = scrolledtext.ScrolledText(layout, height=8)
        self.remote_files_input.pack(fill=tk.X, pady=5)
        saved_remote = profile.get("remote_files", "")
        if saved_remote:
            self.remote_files_input.insert("1.0", saved_remote)

        local_frame = ttk.Frame(layout)
        local_frame.pack(fill=tk.X, pady=10)
        ttk.Label(local_frame, text="💾 Save to:").pack(side=tk.LEFT)
        self.local_dest_entry = ttk.Entry(local_frame)
        self.local_dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        saved_local = profile.get("local_dest", "")
        self.local_dest_entry.insert(0, saved_local if saved_local else os.getcwd())
        self._make_btn(local_frame, text="📂 Browse Folder", underline=3, command=self.browse_local_dest).pack(side=tk.LEFT)

        self.download_btn = self._make_btn(layout, "⬇ Start Download", underline=8, command=self.execute_download)
        self.download_btn.pack(pady=10, fill=tk.X)

    def _build_config_tab(self):
        """Config import/export tab."""
        layout = ttk.Frame(self.config_tab, padding="20")
        layout.pack(fill=tk.BOTH, expand=True)

        ttk.Label(layout, text="💾 Config File Management",
                  font=FONT_BOLD).pack(anchor="w", pady=(0, 10))
        cfg_frame = ttk.Frame(layout)
        cfg_frame.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(cfg_frame, text="Current config:", foreground="#888888").pack(side=tk.LEFT)
        cfg_entry = ttk.Entry(cfg_frame)
        cfg_entry.insert(0, CONFIG_PATH)
        cfg_entry.configure(state="readonly")
        cfg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        btn_row = ttk.Frame(layout)
        btn_row.pack(fill=tk.X, pady=5)
        self._make_btn(btn_row, text="📥 Import Config", underline=3, command=self._import_config).pack(side=tk.LEFT, padx=(0, 10))
        self._make_btn(btn_row, text="📤 Export Config", underline=3, command=self._export_config).pack(side=tk.LEFT)

        # Preview area
        ttk.Label(layout, text="📋 Config Preview:").pack(anchor="w", pady=(15, 5))
        self.config_preview = scrolledtext.ScrolledText(layout, state="disabled", height=18, wrap="word")
        self.config_preview.pack(fill=tk.BOTH, expand=True)
        copy_btn = self._make_btn(layout, text="📋 Copy to Clipboard", command=self._copy_config_preview)
        copy_btn.pack(anchor="e", pady=(5, 0))
        self._refresh_config_preview()

    def _copy_config_preview(self):
        """Copy config preview text to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.config_preview.get("1.0", tk.END).strip())

    def _refresh_config_preview(self):
        """Show current config JSON in preview area."""
        if not hasattr(self, "config_preview"):
            return
        self.config_preview.configure(state="normal")
        self.config_preview.delete("1.0", tk.END)
        preview_cfg = copy.deepcopy(self.config)
        for _pd in preview_cfg.get("profiles", {}).values():
            if _pd.get("password"):
                _pd["password"] = "***"
        self.config_preview.insert("1.0", json.dumps(preview_cfg, indent=2, ensure_ascii=False))

        self.config_preview.configure(state="disabled")

    def _import_config(self):
        """Import a JSON config file and merge it into current config."""
        path = filedialog.askopenfilename(
            title="Import Config",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                imported = json.load(f)
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to read file:\n{e}")
            return
        if not isinstance(imported, dict):
            messagebox.showerror("Import Error", "Config file must be a JSON object.")
            return
        # Replace current config entirely
        self.config = imported
        self.profiles = self.config.get("profiles", {})
        self.active_profile = self.config.get("active_profile", "")
        if self.active_profile not in self.profiles:
            self.active_profile = list(self.profiles.keys())[0] if self.profiles else ""
        self.config["active_profile"] = self.active_profile
        # Save to disk immediately
        save_config(self.config)

        # Refresh UI
        self.profile_combo["values"] = list(self.profiles.keys())
        self.profile_var.set(self.active_profile)
        self._refresh_all_ui()

        self.log("✅ Config imported successfully.", "success")

        messagebox.showinfo("Import Complete",

                            f"Config imported from:\n{path}\n\nCurrent config replaced.")

    def _export_config(self):
        """Export current config to a JSON file (password excluded)."""
        path = filedialog.asksaveasfilename(
            title="Export Config", defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="termi_transfer_config.json")
        if not path:
            return
        try:
            export = copy.deepcopy(self.config)
            for _pd in export.get("profiles", {}).values():
                _pd.pop("password", None)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to write file:\n{e}")
            return
        self.log(f"✅ Config exported to: {path}", "success")
        messagebox.showinfo("Export Complete", f"Config saved to:\n{path}")

    # ──────────── Profile Management ────────────

    def _get_profile(self):
        return self.profiles.get(self.active_profile, {})

    def _load_profile_fields(self):
        """Fill connection fields from active profile."""
        p = self._get_profile()
        for entry, key in [
            (self.host_entry, "host"),
            (self.key_entry, "key"),
            (self.port_entry, "port"),
            (self.user_entry, "user"),
            (self.password_entry, "password"),
        ]:
            entry.delete(0, tk.END)
            entry.insert(0, p.get(key, ""))

    def save_current_profile(self):
        """Dump current UI values into active profile dict."""
        p = self._get_profile()
        p["host"] = self.host_entry.get().strip()
        p["port"] = self.port_entry.get().strip()
        p["user"] = self.user_entry.get().strip()
        p["key"] = self.key_entry.get().strip()
        p["password"] = self.password_entry.get().strip()
        # Preset checkbox states
        p["_preset_selected"] = {
            name: var.get() for name, var in self.dest_vars.items()
        }

        # Save edited preset paths from entries

        if hasattr(self, "_preset_entries"):
            for pname, pent in self._preset_entries.items():
                new_path = pent.get().strip()
                if new_path and pname in p.get("presets", {}):
                    p["presets"][pname] = new_path
        # Download tab
        if hasattr(self, "remote_files_input"):
            p["remote_files"] = self.remote_files_input.get("1.0", tk.END).strip()
        if hasattr(self, "local_dest_entry"):
            p["local_dest"] = self.local_dest_entry.get().strip()
    def _on_profile_change(self, event=None):
        self.save_current_profile()
        save_config(self.config)
        self.active_profile = self.profile_var.get()
        self.config["active_profile"] = self.active_profile
        self._refresh_all_ui()

    def _add_profile(self):
        """Add a new profile by name."""
        name = simpledialog.askstring(
            "New Profile", "Profile name:", parent=self.root
        )
        if not name or name in self.profiles:
            return
        self.save_current_profile()
        self.profiles[name] = {
            "host": "", "port": "22", "user": "", "key": "",
            "presets": {"~/": "~/"}, "remote_files": "", "local_dest": "",
        }
        self.config["active_profile"] = name
        self.active_profile = name
        self.profile_combo["values"] = list(self.profiles.keys())
        self.profile_var.set(name)
        self._refresh_all_ui()

    def _remove_profile(self):
        """Remove current profile (cannot remove last one)."""
        if len(self.profiles) <= 1:
            self.log("Cannot remove the last profile.", "warning")
            return
        name = self.active_profile
        if not messagebox.askyesno("Remove Profile", f"Are you sure you want to remove profile '{name}'?"):
            return
        del self.profiles[name]
        self.active_profile = list(self.profiles.keys())[0]
        self.config["active_profile"] = self.active_profile
        self.profile_combo["values"] = list(self.profiles.keys())
        self.profile_var.set(self.active_profile)
        self._refresh_all_ui()

    def _cycle_profile(self):
        """Alt+P: cycle to next profile."""
        names = list(self.profiles.keys())
        idx = names.index(self.active_profile)
        self.save_current_profile()
        save_config(self.config)
        self.active_profile = names[(idx + 1) % len(names)]
        self.config["active_profile"] = self.active_profile
        self.profile_var.set(self.active_profile)
        self._refresh_all_ui()

    def _focus_first_preset(self):
        """Focus the first preset entry widget."""
        for ent in self._preset_entries.values():
            ent.focus_set()
            return


    def _add_preset(self):
        """Add a new preset path to current profile."""
        path = simpledialog.askstring(
            "Add Preset", "Remote path:", parent=self.root
        )
        if not path:
            return
        self.save_current_profile()
        profile = self._get_profile()
        profile.setdefault("presets", {})[path] = path
        sel = profile.get("_preset_selected", {})
        sel[path] = False
        save_config(self.config)
        self._refresh_presets()

    def _remove_preset(self, name):
        """Remove a preset from current profile."""
        self.save_current_profile()
        profile = self._get_profile()
        presets = profile.get("presets", {})
        if name in presets:
            del presets[name]
            sel = profile.get("_preset_selected", {})
            sel.pop(name, None)
        save_config(self.config)
        self._refresh_presets()

    # ─

    def _edit_preset(self, old_name, old_path):
        """Edit an existing preset name and path."""
        new_name = simpledialog.askstring(
            "Edit Preset", "Display name:", initialvalue=old_name, parent=self.root
        )
        if not new_name:
            return
        new_path = simpledialog.askstring(
            "Edit Preset", "Remote path:", initialvalue=old_path, parent=self.root
        )
        if not new_path:
            return
        self.save_current_profile()
        profile = self._get_profile()
        presets = profile.get("presets", {})
        if old_name != new_name and old_name in presets:
            del presets[old_name]
            sel = profile.get("_preset_selected", {})
            sel.pop(old_name, None)
        presets[new_name] = new_path
        save_config(self.config)
        self._refresh_presets()

    # ──────────── UI Actions ────────────

    def browse_local_dest(self):
        path = filedialog.askdirectory(title="Select Download Folder")
        if path:
            self.local_dest_entry.delete(0, tk.END)
            self.local_dest_entry.insert(0, path)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Select Files")
        if paths:
            current_text = self.file_text.get("1.0", tk.END).strip()
            new_paths = "\n".join(paths)
            if current_text:
                self.file_text.insert(tk.END, "\n" + new_paths)
            else:
                self.file_text.insert(tk.END, new_paths)

    def clear_files(self):
        self.file_text.delete("1.0", tk.END)

    def log(self, msg, level="default"):
        self.log_output.configure(state="normal")
        if level == "error":
            self.log_output.insert(tk.END, msg + "\n", "error")
        elif level == "success":
            self.log_output.insert(tk.END, msg + "\n", "success")
        elif level == "warning":
            self.log_output.insert(tk.END, msg + "\n", "warning")
        elif level == "info":
            self.log_output.insert(tk.END, msg + "\n", "info")
        else:
            self.log_output.insert(tk.END, msg + "\n")
        self.log_output.see(tk.END)
        self.log_output.configure(state="disabled")

    def _clear_log(self):
        self.log_output.configure(state="normal")
        self.log_output.delete("1.0", tk.END)
        self.log_output.configure(state="disabled")

    # ──────────── Transfer Logic ────────────

    def get_conn_args(self):
        return (
            self.port_entry.get().strip(),
            self.key_entry.get().strip(),
            self.user_entry.get().strip(),
            self.host_entry.get().strip(),
            self.password_entry.get().strip(),
        )

    def _make_ssh_client(self, port, key, user, host, password):
        """Create and connect an SSH client via paramiko."""
        client = paramiko.SSHClient()
        # NOTE: AutoAddPolicy accepts unknown host keys automatically.
        # This is convenient but vulnerable to MITM attacks on first connection.
        # For production use, consider using RejectPolicy or loading known_hosts.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kw = dict(
            hostname=host,
            port=int(port) if port else 22,
            username=user,
        )
        if password:
            connect_kw["password"] = password
        if key:
            connect_kw["key_filename"] = key
        client.connect(**connect_kw)
        return client

    def _make_progress_callback(self, filename, direction):
        """Create a progress callback for sftp.put/get that updates the progress bar."""
        last_update = [0]
        def callback(bytes_transferred, total_bytes):
            # Throttle updates to avoid overwhelming the UI
            now = time.time()
            if now - last_update[0] < 0.1 and bytes_transferred < total_bytes:
                return
            last_update[0] = now
            if total_bytes > 0:
                pct = int(bytes_transferred * 100 / total_bytes)
                def update():
                    self.progress_label.configure(text=f"{filename} {pct}% ({bytes_transferred}/{total_bytes} bytes)")
                self.root.after(0, update)
        return callback

    def _sftp_put_recursive(self, sftp, local_path, remote_path, progress_callback=None):
        """Recursively upload a file or directory via SFTP."""
        if os.path.isfile(local_path):
            self.root.after(0, lambda: self.log(f"  -> {remote_path}", "info"))
            callback = self._make_progress_callback(os.path.basename(local_path), "upload")
            sftp.put(local_path, remote_path, callback=callback)
        elif os.path.isdir(local_path):
            try:
                sftp.stat(remote_path)
            except FileNotFoundError:
                sftp.mkdir(remote_path)
                self.root.after(0, lambda: self.log(f"  mkdir {remote_path}", "info"))
            for item in os.listdir(local_path):
                local_item = os.path.join(local_path, item)
                remote_item = remote_path.rstrip("/") + "/" + item
                self._sftp_put_recursive(sftp, local_item, remote_item)
        else:
            self.root.after(0, lambda: self.log(f"  SKIP (not found): {local_path}", "warning"))

    def _sftp_get_recursive(self, sftp, remote_path, local_path, progress_callback=None):
        """Recursively download a file or directory via SFTP."""
        try:
            sftp.stat(remote_path)
        except FileNotFoundError:
            self.root.after(0, lambda: self.log(f"  SKIP (not found): {remote_path}", "warning"))
            return
        # Check if directory by attempting to list
        try:
            entries = sftp.listdir_attr(remote_path)
            # It's a directory
            if not os.path.isdir(local_path):
                os.makedirs(local_path, exist_ok=True)
                self.root.after(0, lambda: self.log(f"  mkdir {local_path}", "info"))
            for entry in entries:
                remote_item = remote_path.rstrip("/") + "/" + entry.filename
                local_item = os.path.join(local_path, entry.filename)
                self._sftp_get_recursive(sftp, remote_item, local_item)
        except IOError:
            # It's a file
            self.root.after(0, lambda: self.log(f"  <- {local_path}", "info"))
            callback = self._make_progress_callback(os.path.basename(local_path), "download")
            sftp.get(remote_path, local_path, callback=callback)

    def _get_cached_ssh(self, port, key, user, host, password):
        """Get or create a cached SSH client for (host, port, user, password)."""
        cache_key = (host, int(port) if port else 22, user, password)
        cached = self._ssh_cache.get(cache_key)
        if cached is not None:
            client, _ = cached
            # Test if connection is still alive
            try:
                client.exec_command("echo ok", timeout=5)
                return client, True  # reused
            except Exception:
                # Connection dead, remove from cache
                try:
                    client.close()
                except Exception:
                    pass
                del self._ssh_cache[cache_key]
        # Create new connection
        client = self._make_ssh_client(port, key, user, host, password)
        self._ssh_cache[cache_key] = (client, None)
        return client, False

    def _run_sftp(self, port, key, user, host, password, files, dests, direction="upload"):
        """Run SFTP transfer in a background thread."""
        btn = self.upload_btn if direction == "upload" else self.download_btn
        btn_text = "Uploading..." if direction == "upload" else "Downloading..."

        def start_transfer():
            btn.configure(state="disabled", text=btn_text)
            self.progress_var.set(0)
            self.progress_label.configure(text="0%")
            self.progress_frame.pack(fill=tk.X, pady=(2, 0))
        self.root.after(0, start_transfer)

        def task():
            try:
                client, reused = self._get_cached_ssh(port, key, user, host, password)
                if reused:
                    self.root.after(0, lambda: self.log(f"Reusing connection to {user}@{host}:{port}", "info"))
                else:
                    self.root.after(0, lambda: self.log(f"Connecting to {user}@{host}:{port}...", "info"))
                sftp = client.open_sftp()
                self.root.after(0, lambda: self.log("SFTP connected.", "success"))
                remote_home = sftp.normalize(".")

                def resolve_remote(p):
                    if p.startswith("~/"):
                        return remote_home + p[1:]
                    elif p == "~":
                        return remote_home
                    return p

                def update_progress(idx, total, name):
                    pct = int(idx * 100 / total) if total > 0 else 0
                    def do_update():
                        self.progress_var.set(pct)
                        self.progress_label.configure(text=f"{pct}% ({idx}/{total})")
                    self.root.after(0, do_update)

                if direction == "upload":
                    total = len(files) * len(dests)
                    idx = 0
                    for dest in dests:
                        dest = resolve_remote(dest)
                        for fpath in files:
                            idx += 1
                            fname = os.path.basename(fpath)
                            remote_path = dest.rstrip("/") + "/" + fname
                            self.root.after(0, lambda rp=remote_path: self.log(f"[{idx}/{total}] -> {rp}", "info"))
                            update_progress(idx, total, fname)
                            self._sftp_put_recursive(sftp, fpath, remote_path)
                else:
                    total = len(files)
                    local_dir = dests[0] if dests else "."
                    for idx, rpath in enumerate(files, 1):
                        rpath = resolve_remote(rpath)
                        fname = os.path.basename(rpath.rstrip("/"))
                        local_path = os.path.join(local_dir, fname)
                        self.root.after(0, lambda lp=local_path, i=idx, t=total: self.log(f"[{i}/{t}] <- {lp}", "info"))
                        update_progress(idx, total, fname)
                        self._sftp_get_recursive(sftp, rpath, local_path)

                sftp.close()
                # Keep client cached for reuse (don't close)
                self.root.after(0, lambda: self.log("Transfer complete.", "success"))
                self.root.after(0, lambda: self.progress_var.set(100))
                self.root.after(0, lambda: self.progress_label.configure(text="100% Complete"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"Error: {e}", "error"))
            finally:
                orig_text = "⬆ Start Upload" if direction == "upload" else "⬇ Start Download"
                def finish():
                    btn.configure(state="normal", text=orig_text)
                    self.root.after(3000, lambda: self.progress_frame.pack_forget())
                self.root.after(0, finish)

        threading.Thread(target=task, daemon=True).start()

    def execute_upload(self):
        # Auto-sync UI state to profile before executing
        self.save_current_profile()
        save_config(self.config)
        port, key, user, host, password = self.get_conn_args()
        files_text = self.file_text.get("1.0", tk.END)
        files = [line.strip() for line in files_text.split("\n") if line.strip()]
        if not files:
            self.log("No files selected!", "warning")
            return
        # Read destinations from UI entries (not stale profile cache)
        dests = []
        for name, var in self.dest_vars.items():
            if var.get() and name in self._preset_entries:
                dests.append(self._preset_entries[name].get().strip())
        if not dests:
            self.log("No destination selected!", "warning")
            return
        # Confirmation dialog
        file_list = "\n".join(f"  • {os.path.basename(f)}" for f in files[:5])
        if len(files) > 5:
            file_list += f"\n  ... and {len(files) - 5} more"
        dest_list = "\n".join(f"  • {d}" for d in dests)
        if not messagebox.askyesno("Confirm Upload",
                                   f"Upload {len(files)} file(s) to {len(dests)} destination(s)?\n\n"
                                   f"Files:\n{file_list}\n\nDestinations:\n{dest_list}"):
            return
        self._run_sftp(port, key, user, host, password, files, dests, direction="upload")

    def execute_download(self):
        # Auto-sync UI state to profile before executing
        self.save_current_profile()
        save_config(self.config)
        port, key, user, host, password = self.get_conn_args()
        remote_files_text = self.remote_files_input.get("1.0", tk.END)
        remote_files = [line.strip() for line in remote_files_text.split("\n") if line.strip()]
        local_dir = self.local_dest_entry.get().strip()
        if not remote_files:
            self.log("No remote files specified!", "warning")
            return
        # Confirmation dialog
        file_list = "\n".join(f"  • {os.path.basename(r)}" for r in remote_files[:5])
        if len(remote_files) > 5:
            file_list += f"\n  ... and {len(remote_files) - 5} more"
        if not messagebox.askyesno("Confirm Download",
                                   f"Download {len(remote_files)} file(s)?\n\n"
                                   f"Files:\n{file_list}\n\nSave to:\n  {local_dir or '.'}"):
            return
        self._run_sftp(port, key, user, host, password, remote_files, [local_dir or "."], direction="download")

if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = TermuxTransferApp(root)
    root.mainloop()