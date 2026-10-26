import sys

from GUI.main_window import MainWindow


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    MainWindow(path).mainloop()


if __name__ == "__main__":
    main()
