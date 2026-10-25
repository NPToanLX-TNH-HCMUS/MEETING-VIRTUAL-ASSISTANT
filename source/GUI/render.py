from tkinter import *
from tkinter import filedialog

def print_input():
    print(text.get("1.0", END))

window = Tk()
window.geometry("400x400")
window.title("Meeting virtual assistant")


icon  = PhotoImage(file = 'image/GUI/app_icon.png')
window.iconphoto(True, icon)


text = Text(window)
text.pack()

submit_button = Button(window, text="Submit", command=print_input)
submit_button.pack();
