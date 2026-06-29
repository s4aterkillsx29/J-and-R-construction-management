"""
Shared desktop UI theme — black + lime green (J & R Construction Manager).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#000000"
PANEL = "#0a0a0a"
CARD = "#111111"
BORDER = "#1f2937"
BORDER_LIGHT = "#374151"
TEXT = "#f5f5f5"
MUTED = "#a3a3a3"
DIM = "#737373"
ACCENT = "#84cc16"
ACCENT_BRIGHT = "#a3e635"
ACCENT_FG = "#000000"
INFO = "#a3e635"
INFO_FG = "#000000"
WARN = "#facc15"
WARN_FG = "#1c1917"
DANGER = "#ef4444"
BUTTON = "#171717"
ENTRY_BG = "#0a0a0a"

FONT = "Segoe UI"
FONT_TITLE = (FONT, 22, "bold")
FONT_HEADING = (FONT, 14, "bold")
FONT_BODY = (FONT, 10)
FONT_SMALL = (FONT, 9)
FONT_BUTTON = (FONT, 10, "bold")
FONT_HERO = (FONT, 16, "bold")

CARD_PADX = 16
CARD_PADY = 14
SIDEBAR_W = 170


def dark_scrollbar(parent: tk.Misc, orient: str = "vertical", **kwargs) -> tk.Scrollbar:
    return tk.Scrollbar(
        parent,
        orient=orient,
        bg=BG,
        troughcolor=PANEL,
        activebackground=BORDER_LIGHT,
        highlightthickness=0,
        bd=0,
        width=10,
        **kwargs,
    )


def nav_button(parent: tk.Misc, text: str, command, *, active: bool = False) -> tk.Button:
    bg = CARD if active else PANEL
    fg = ACCENT if active else MUTED
    border = ACCENT if active else BORDER
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=CARD,
        activeforeground=ACCENT_BRIGHT,
        relief="flat",
        bd=0,
        font=(FONT, 10, "bold"),
        anchor="w",
        padx=16,
        pady=12,
        cursor="hand2",
        highlightthickness=1,
        highlightbackground=border,
        highlightcolor=border,
    )
    btn.pack(fill="x", padx=10, pady=4)
    return btn


def action_card(
    parent: tk.Misc,
    title: str,
    description: str,
    command,
    *,
    variant: str = "secondary",
    wraplength: int = 520,
) -> tk.Frame:
    accent = {
        "primary": ACCENT,
        "info": ACCENT_BRIGHT,
        "warn": WARN,
        "secondary": BORDER_LIGHT,
    }.get(variant, BORDER_LIGHT)

    outer = tk.Frame(parent, bg=BG)
    outer.pack(fill="x", padx=12, pady=6)

    card = tk.Frame(outer, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
    card.pack(fill="x")
    accent_bar = tk.Frame(card, bg=accent, width=4)
    accent_bar.pack(side="left", fill="y")
    inner = tk.Frame(card, bg=CARD, padx=18, pady=14)
    inner.pack(side="left", fill="both", expand=True)

    top = tk.Frame(inner, bg=CARD)
    top.pack(fill="x")
    tk.Label(top, text=title, bg=CARD, fg=TEXT, font=FONT_HEADING, anchor="w").pack(side="left", fill="x", expand=True)
    action_button(top, "Open →", command, variant=variant if variant != "secondary" else "secondary").pack(side="right")

    tk.Label(
        inner,
        text=description,
        bg=CARD,
        fg=MUTED,
        font=FONT_SMALL,
        anchor="w",
        justify="left",
        wraplength=wraplength,
    ).pack(fill="x", pady=(8, 0))
    return outer


def glass_frame(parent: tk.Misc, *, bg: str = CARD, border: bool = True, **pack) -> tk.Frame:
    frame = tk.Frame(
        parent,
        bg=bg,
        highlightthickness=1 if border else 0,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
    )
    if pack:
        frame.pack(**pack)
    return frame


def section_label(parent: tk.Misc, text: str, **grid) -> tk.Label:
    lbl = tk.Label(
        parent,
        text=text.upper(),
        bg=BG,
        fg=ACCENT,
        font=(FONT, 10, "bold"),
        anchor="w",
    )
    if grid:
        lbl.grid(**grid)
    else:
        lbl.pack(anchor="w", padx=4, pady=(8, 4))
    return lbl


def action_button(
    parent: tk.Misc,
    text: str,
    command,
    *,
    variant: str = "secondary",
    width: int | None = None,
    **pack,
) -> tk.Button:
    styles = {
        "primary": (ACCENT, ACCENT_FG),
        "info": (ACCENT_BRIGHT, ACCENT_FG),
        "warn": (WARN, WARN_FG),
        "danger": (DANGER, "#fff"),
        "secondary": (ACCENT, ACCENT_FG),
    }
    bg, fg = styles.get(variant, styles["secondary"])
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=ACCENT_BRIGHT,
        activeforeground=ACCENT_FG,
        relief="flat",
        bd=0,
        font=FONT_BUTTON,
        padx=14,
        pady=11,
        cursor="hand2",
    )
    if width:
        btn.configure(width=width)
    if pack:
        btn.pack(**pack)
    return btn


def styled_entry(parent: tk.Misc, **kwargs) -> tk.Entry:
    opts = dict(
        bg=ENTRY_BG,
        fg=TEXT,
        insertbackground=ACCENT,
        relief="flat",
        font=(FONT, 11),
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
    )
    opts.update(kwargs)
    return tk.Entry(parent, **opts)


def hero_button(parent: tk.Misc, title: str, subtitle: str, command, *, variant: str = "primary") -> tk.Frame:
    card = glass_frame(parent, bg=CARD, padx=CARD_PADX, pady=CARD_PADY)
    color = ACCENT if variant == "primary" else ACCENT_BRIGHT
    tk.Label(card, text=title, bg=CARD, fg=color, font=FONT_HERO, anchor="w").pack(fill="x")
    tk.Label(card, text=subtitle, bg=CARD, fg=MUTED, font=FONT_SMALL, anchor="w", wraplength=280, justify="left").pack(
        fill="x", pady=(4, 12)
    )
    action_button(card, "Open", command, variant=variant).pack(fill="x")
    return card


def configure_ttk(style: ttk.Style) -> None:
    style.theme_use("clam")
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TEXT, font=FONT_BODY)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=FONT_BODY)
    style.configure("Title.TLabel", background=PANEL, foreground=TEXT, font=FONT_TITLE)
    style.configure("Header.TLabel", background=PANEL, foreground=ACCENT, font=(FONT, 14, "bold"))
    style.configure("CardHeader.TLabel", background=CARD, foreground=ACCENT, font=(FONT, 12, "bold"))
    style.configure("TButton", background=BUTTON, foreground=TEXT, borderwidth=0, focusthickness=3, focuscolor=ACCENT, font=FONT_BODY, padding=(10, 6))
    style.map("TButton", background=[("active", BORDER_LIGHT)])
    style.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_FG, font=FONT_BUTTON)
    style.map("Accent.TButton", background=[("active", ACCENT_BRIGHT)])
    style.configure("Info.TButton", background=ACCENT_BRIGHT, foreground=ACCENT_FG, font=FONT_BUTTON)
    style.configure("Danger.TButton", background=DANGER, foreground="#fff")
    style.map("Danger.TButton", background=[("active", "#fca5a5")])
    style.configure(
        "Treeview",
        background=ENTRY_BG,
        foreground=TEXT,
        fieldbackground=ENTRY_BG,
        rowheight=30,
        borderwidth=0,
    )
    style.map("Treeview", background=[("selected", "#1a2e05")])
    style.configure("Treeview.Heading", background=PANEL, foreground=ACCENT, font=(FONT, 10, "bold"))
    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(4, 4, 4, 0))
    style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(16, 10), font=(FONT, 10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", ACCENT)])
    style.configure("TEntry", fieldbackground=ENTRY_BG, foreground=TEXT, insertcolor=ACCENT, bordercolor=BORDER)
    style.configure("TCombobox", fieldbackground=ENTRY_BG, background=ENTRY_BG, foreground=TEXT)


def apply_window_icon(window: tk.Misc, icon_path) -> None:
    try:
        from pathlib import Path

        p = Path(icon_path)
        if p.exists():
            window.iconbitmap(str(p))
    except Exception:
        pass
