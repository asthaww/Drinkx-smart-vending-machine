import tkinter as tk
from tkinter import ttk
import subprocess

class GymKiosk(tk.Tk):
    def __init__(self):
        super().__init__()

        # --- Window setup ---
        self.title("Gym Kiosk")
        self.attributes("-fullscreen", True)  # Fullscreen kiosk mode
        self.configure(bg="#073d74")  # Dark blue background

        # Track keypress for exit code
        self.secret_code = ""
        self.exit_code = "vav"

        # --- Style ---
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton",
                        font=("Arial Black", 22, "bold"),
                        padding=40,
                        foreground="white",
                        background="#ff7f32",   # orange button background
                        borderwidth=0)
        style.map("TButton",
                  background=[("active", "#ff944d")])  # brighter orange on press

        # --- Title ---
        title_label = tk.Label(self,
                               text="GYM KIOSK",
                               font=("Arial Black", 48, "bold"),
                               fg="white",
                               bg="#073d74")  # match bg
        title_label.pack(pady=60)

        # --- Buttons Frame (horizontal layout, moved up) ---
        btn_frame = tk.Frame(self, bg="#073d74")
        btn_frame.pack(expand=True, pady=(0, 150))  # push buttons slightly up

        self.create_button(btn_frame, "Start App", self.run_app, 0)
        self.create_button(btn_frame, "Test Motors", self.test_motors, 1)
        self.create_button(btn_frame, "Test Flow", self.test_flow, 2)

        # --- Bind keys for exit ---
        self.bind("<Key>", self.on_key)

    def create_button(self, parent, text, command, col):
        btn = ttk.Button(parent, text=text, command=command)
        btn.grid(row=0, column=col, padx=40, ipadx=30, ipady=20)

    # --- Placeholder commands ---
    def run_app(self):
        subprocess.Popen([
        "lxterminal", 
        "-e", "python3 app.py"
        ])
        

    def test_motors(self):
        subprocess.Popen([
        "lxterminal", 
        "-e", "python3 Testing_motors.py"
        ])

    def test_flow(self):
        subprocess.Popen([
        "lxterminal", 
        "-e", "python3 controller.py --tester"
        ])

    # --- Exit key sequence ---
    def on_key(self, event):
        self.secret_code += event.char.lower()
        if not self.exit_code.startswith(self.secret_code):
            self.secret_code = ""  # Reset if sequence broken
        if self.secret_code == self.exit_code:
            self.destroy()  # Exit kiosk
            print("Exited kiosk mode, back to dev mode.")

if __name__ == "__main__":
    GymKiosk().mainloop()
