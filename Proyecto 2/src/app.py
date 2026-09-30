from __future__ import annotations

import tkinter as tk

from ui import CompiscriptApp


def main() -> None:
    root = tk.Tk()
    CompiscriptApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
