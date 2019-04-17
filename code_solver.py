# Create onefile executable
#   pyinstaller --onefile --noconsole --icon=resources\instech.ico --name=InstechCodeSolver_v1_0 code_solver.py

from PIL import Image, ImageTk, ImageGrab
from pytesseract import pytesseract
from ascii_table import ascii_table
import re
from datetime import datetime
import logging
import traceback
from urllib import request, error
from tkinter import Tk, Frame, Label, Entry, TOP, RIGHT, BOTTOM, LEFT, YES, NO, NW, E, W, S, X, BOTH, END, \
    Button, Canvas, Text, DISABLED, NORMAL, ALL, Scale, Y, N, SUNKEN, Radiobutton, IntVar, Checkbutton, BooleanVar
from ctypes import windll
import configparser


class CodeSolver:
    should_i_apply = True

    # Program config
    config = {
        'system parameters': {
            'set_dpi_awareness': 'True',
            'tesseract_directory': r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        },
        'window settings': {
            'transparent_on_lost_focus': 'True',
            'default_transparency_alpha': '0.4',
            'set_topmost': 'True',
            'window_width': '700',
            'window_height': '550',
            'center_image_on_canvas': 'True'
        }
    }
    sys_cfg = config['system parameters']  # Short names
    win_cfg = config['window settings']
    config_parser = None

    # Image params/vars
    use_local_image = False
    new_image = False
    image = None
    tk_image = None
    img = None
    img_id = None
    aspect_ratio = None
    canvas_width = 0
    canvas_height = 0
    image_width = None
    image_height = None
    image_scale = None
    image_x_offset = None
    image_y_offset = None
    bounding_boxes = None
    resize_threshold = 1  # Prevents resizing on small canvas changes
    last_resize = None
    pending_boxes = False

    # Settings
    render_boxes = None
    mode = None

    # Widgets
    root = None
    frame_url = None
    entry_url = None
    canvas = None
    lbl_status = None
    btn_crack = None
    txt_output = None
    scale_slider = None
    transparency_overlay = None

    # Lookup
    ascii_lookup = None

    # List of chars that commonly incorrectly translate ordered by priority
    # Keys should be caps and value must be a set of valid hexadecimal symbols
    ambiguous_chars = {'G': '6',
                       'S': '5',
                       'H': '4',
                       'Z': '7',
                       'B': '8',  # These are both hexadecimal chars
                       '8': 'B'}

    def __init__(self):
        # Read config
        self.read_config()

        # Necessary to get PIL to work correctly on high DPI scaling
        if self.sys_cfg['set_dpi_awareness'] == 'True':
            user32 = windll.user32
            user32.SetProcessDPIAware()

        # Load and structure lookup
        self.ascii_lookup = {}
        for row in ascii_table:
            row = row.split(',')
            self.ascii_lookup[row[3].upper()] = row[4]

        # Start gui
        self.init_gui()

    def read_config(self):
        try:
            # Set up parser
            self.config_parser = configparser.ConfigParser()

            # Read from file
            self.config_parser.read('config.ini')

            # Read all parameters specified in config
            print('Reading config')
            for key, sub_dict in self.config.items():
                try:
                    for sub_key in sub_dict:
                        val = self.config_parser[key][sub_key]
                        self.config[key][sub_key] = val
                        print('set config[{}][{}] to {}'.format(key, sub_key, val))
                except KeyError:
                    pass
        except:
            traceback.print_exc()

    def write_config(self):
        # List all parameters that should be written
        try:
            for key, sub_dict in self.config.items():
                self.config_parser.setdefault(key, {})
                for sub_key, val in sub_dict.items():
                    self.config_parser[key][sub_key] = str(val)

            # Write to file
            with open('config.ini', 'w') as configfile:
                self.config_parser.write(configfile)
        except:
            traceback.print_exc()

    def window_close(self):
        self.write_config()
        self.root.destroy()

    def init_gui(self):
        # Root config
        self.root = Tk()
        self.root.report_callback_exception = lambda a, b, c: self.elevate_error()
        self.root.title('Instech Code Solver v1.0 by Eivind Brate Midtun')
        self.root.minsize(700, 550)
        self.root.geometry('{}x{}'.format(self.win_cfg['window_width'], self.win_cfg['window_height']))
        if self.win_cfg['transparent_on_lost_focus'] == 'True':
            self.root.bind("<FocusIn>", lambda e: self.set_root_alpha(1))
            self.root.bind("<FocusOut>", lambda e: self.set_root_alpha(
                float(self.win_cfg['default_transparency_alpha'])))
        if self.win_cfg['set_topmost'] == 'True':
            self.root.wm_attributes('-topmost', True)
        self.root.protocol("WM_DELETE_WINDOW", self.window_close)
        self.center_window(self.root)

        # Main frame
        frame_main = Frame(self.root)
        frame_main.pack(expand=YES, fill=BOTH)

        # URL frame
        self.frame_url = Frame(frame_main)
        label_url = Label(self.frame_url, text='image url:')
        self.entry_url = Entry(self.frame_url)
        self.entry_url.insert(0, "https://images.finncdn.no/dynamic/1280w/2019/4/vertical-1/10/4/144/681/364_714666085.jpg")
        btn_grab = Button(self.frame_url, text='screen grab', width=10, command=lambda: self.image_grab())
        btn_grab.bind("<Enter>", lambda e: self.set_root_alpha(float(self.win_cfg['default_transparency_alpha']), 1))
        btn_grab.bind("<Leave>", lambda e: self.set_root_alpha(1, 2))
        btn_grab.pack(side=RIGHT, anchor=E)
        Button(self.frame_url, text='url grab', width=10,
               command=lambda: self.get_image('from_url')).pack(side=RIGHT, anchor=E, padx=5)
        label_url.pack(side=LEFT, anchor=W)
        self.entry_url.pack(side=LEFT, anchor=W, expand=YES, fill=X)

        # Input frame
        frame_input = Frame(frame_main)

        # Canvas frame
        frame_canvas = Frame(frame_input)
        self.canvas = Canvas(frame_canvas, bg='gray')
        self.canvas.pack(side=TOP, fill=BOTH, expand=YES)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        # Settings frame
        frame_settings = Frame(frame_input, borderwidth=1, relief=SUNKEN)
        self.render_boxes = BooleanVar()
        self.render_boxes.set(True)
        Checkbutton(frame_settings, text='Box', font='TkDefaultFont 8',
                    variable=self.render_boxes, command=self.redraw).pack(anchor=W)
        Label(frame_settings, text='Overlay\nalpha', font='TkDefaultFont 8').pack(side=TOP, anchor=N)
        self.scale_slider = Scale(frame_settings, command=lambda e: self.set_transparency())
        self.mode = IntVar()
        self.scale_slider.pack(side=TOP, anchor=N)
        Label(frame_settings, text='Mode:', font='TkDefaultFont 8').pack(anchor=W)
        Radiobutton(frame_settings, text="Hex", font='TkDefaultFont 8', variable=self.mode, value=0).pack(anchor=W)
        Radiobutton(frame_settings, text="Dec", font='TkDefaultFont 8', variable=self.mode, value=1).pack(anchor=W)
        Radiobutton(frame_settings, text="Bin", font='TkDefaultFont 8', variable=self.mode, value=2).pack(anchor=W)
        Radiobutton(frame_settings, text="Sym", font='TkDefaultFont 8', variable=self.mode, value=3).pack(anchor=W)
        Radiobutton(frame_settings, text="Oct", font='TkDefaultFont 8', variable=self.mode, value=4).pack(anchor=W)

        # Input frame continue
        lbl_input = Label(frame_input, text='Input:')
        lbl_input.pack(side=TOP, anchor=W)
        frame_settings.pack(side=LEFT, expand=NO, fill=Y, pady=(2, 2))
        frame_canvas.pack(side=RIGHT, expand=YES, fill=BOTH, padx=(2, 0))

        # Button frame
        frame_buttons = Frame(frame_main)
        self.btn_crack = Button(frame_buttons, state=DISABLED, width=15, text='crack code',
                                command=lambda: self.start_cracking(self.image))
        self.lbl_status = Label(frame_buttons, text='Status: Awaiting user', fg='blue')
        self.btn_crack.pack(side=RIGHT, anchor=E)
        self.lbl_status.pack(side=LEFT, anchor=W)

        # Output frame
        frame_output = Frame(frame_main)
        lbl_output = Label(frame_output, text='Output:')
        self.txt_output = Text(frame_output, state=DISABLED, height=6, fg='#FFFFFF', bg='#4C4A48')
        lbl_output.pack(side=TOP, anchor=W)
        self.txt_output.pack(side=BOTTOM, fill=X, expand=YES)

        # Pack frames
        if self.use_local_image:
            Label(frame_main, text='Using local image', fg='red').pack(side=TOP)
        self.frame_url.pack(side=TOP, fill=X, padx=20, pady=(10, 0))
        frame_buttons.pack(side=BOTTOM, anchor=S, fill=X, expand=NO, padx=20, pady=10)
        frame_output.pack(side=BOTTOM, anchor=S, fill=X, expand=NO, padx=20)
        frame_input.pack(side=TOP, expand=YES, fill=BOTH, padx=20)

        # Start mainloop
        self.root.mainloop()

    def image_grab(self):
        self.set_root_alpha(0)
        self.get_image('from_screen')
        self.set_root_alpha(1)

    def set_root_alpha(self, alpha, clear_canvas=0):
        self.root.wm_attributes('-alpha', alpha)
        if clear_canvas == 1:
            self.canvas.delete(ALL)
        elif clear_canvas == 2:
            self.redraw()

    def set_transparency(self):
        self.redraw(False)

    def elevate_error(self):
        logging.basicConfig(filename='errors.log', level=logging.ERROR)
        self.set_status('Error occurred, see error.log', 'red')
        logging.error(traceback.format_exc())
        traceback.print_exc()

    @staticmethod
    def center_window(win):
        win.update_idletasks()
        width = win.winfo_width()
        frm_width = win.winfo_rootx() - win.winfo_x()
        win_width = width + 2 * frm_width
        height = win.winfo_height()
        titlebar_height = win.winfo_rooty() - win.winfo_y()
        win_height = height + titlebar_height + frm_width
        x = win.winfo_screenwidth() // 2 - win_width // 2
        y = win.winfo_screenheight() // 2 - win_height // 2
        win.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    def get_image(self, mode='from_url'):
        try:
            if mode == 'from_screen':
                x0, y0 = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
                x1, y1 = x0 + self.canvas.winfo_width(), y0 + self.canvas.winfo_height()

                bbox = (x0, y0, x1, y1)
                self.image = ImageGrab.grab(bbox)
                print('grabbed image x0:{}, y0:{}, x1:{}, y1:{}:'.format(x0, y0, x1, y1))

            elif mode == 'from_url':
                image = r'resources\test_img1.jpg' if self.use_local_image else request.urlopen(self.entry_url.get())
                self.image = Image.open(image)

            else:
                return

            w, h = self.image.size
            self.aspect_ratio = w / h
            self.tk_image = ImageTk.PhotoImage(self.image)
            self.new_image = True
            self.redraw()
            self.btn_crack.configure(state=NORMAL)
            self.set_status('Loaded image URL', 'blue')

            # Delete bounding box data and clear output
            self.bounding_boxes = None
            self.txt_output.config(state=NORMAL)
            self.txt_output.delete(1.0, END)
            self.txt_output.config(state=DISABLED)
            return

        except error.HTTPError:
            self.set_status('Invalid image URL', 'red')

        except FileNotFoundError:
            self.set_status('Did not find specified local image', 'red')

        self.frame_url.configure(highlightcolor='red', highlightbackground='red', highlightthickness=2)
        self.root.after(1500, self.timed_highlight)

    def timed_highlight(self):
        # Toggles off the highlight after a set amount of time
        self.frame_url.configure(highlightthickness=0)

    def set_status(self, text, fg):
        self.lbl_status.configure(text='Status: ' + text, fg=fg)

    def redraw(self, rescale_image=True):
        # Save window size
        self.win_cfg['window_width'], self.win_cfg['window_height'] = self.root.winfo_width(), self.root.winfo_height()

        # Check if image has been loaded
        if not self.image:
            return

        # Log last resize
        self.last_resize = datetime.now()

        if rescale_image:
            # Read new canvas size
            canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()

            # Resize if canvas has changed more than threshold since last resize
            if (self.new_image
                    or self.resize_threshold < abs(self.canvas_width - canvas_width)
                    or self.resize_threshold < abs(self.canvas_height - canvas_height)):
                # Save new canvas size
                self.canvas_width, self.canvas_height = canvas_width, canvas_height

                # Calculate width, height
                if self.aspect_ratio < self.canvas_width / self.canvas_height:
                    self.image_width, self.image_height = int(self.canvas_height * self.aspect_ratio), self.canvas_height
                else:
                    self.image_width, self.image_height = self.canvas_width, int(self.canvas_width / self.aspect_ratio)

                # Calculate image scale
                w, h = self.image.size
                self.image_scale = self.image_width / w

                # Calculate offsets
                if self.win_cfg['center_image_on_canvas'] == 'True':
                    self.image_x_offset = (self.canvas_width - self.image_width) // 2
                    self.image_y_offset = (self.canvas_height - self.image_height) // 2
                else:
                    self.image_x_offset, self.image_y_offset = 0, 0

                # Resize image
                self.img = ImageTk.PhotoImage(self.image.resize((self.image_width, self.image_height)))

                self.new_image = False

        # Clear canvas
        self.canvas.delete(ALL)

        # Draw new image
        self.img_id = self.canvas.create_image(self.image_x_offset, self.image_y_offset, image=self.img, anchor=NW)

        # Create overlay for adjusting contrast
        overlay_alpha = int(self.scale_slider.get() / 100 * 255)
        if 0 < overlay_alpha:
            self.transparency_overlay = ImageTk.PhotoImage(
                Image.new('RGBA', (self.image_width, self.image_height), (30, 30, 30, overlay_alpha)))
            self.canvas.create_image(self.image_x_offset, self.image_y_offset,
                                     image=self.transparency_overlay, anchor='nw')

        # Redraw bounding boxes if there are any
        if self.render_boxes.get():
            self.call_boxing()

    def call_boxing(self):
        # Start one update worker for box updating
        if not self.pending_boxes:
            self.pending_boxes = True
            self.root.after(500, self.delay_boxing)

    def delay_boxing(self):
        # Wait by updating till after user has stopped resizing
        if 0.25 < (datetime.now() - self.last_resize).seconds:
            self.draw_boxes_on_canvas()
            self.pending_boxes = False
        else:
            self.root.after(250, self.delay_boxing)

    def draw_boxes_on_canvas(self):
        if not self.bounding_boxes:
            return

        for box in self.bounding_boxes.split('\n'):
            # Split data
            box = box.split(' ')
            c = box[0]
            box = box[1:5]

            # Convert box data to int
            box = [int(x) for x in box]

            # Scale boxes
            box = [x * self.image_scale for x in box]

            # Flip data vertically and apply offsets
            x0 = box[0] + self.image_x_offset
            y0 = self.image_height - box[1] + self.image_y_offset
            x1 = box[2] + self.image_x_offset
            y1 = self.image_height - box[3] + self.image_y_offset

            # Draw on canvas
            self.canvas.create_rectangle((x0, y0, x1, y1), outline='red')
            self.canvas.create_text(x0 + (x1 - x0) // 2, y0 + 6, text=c, fill='orange', font="Times 12")

    def start_cracking(self, image):
        raw_data = self.get_data_from_image(image)
        if raw_data:
            clean_data = self.interpret_by_regex(raw_data)
            self.translate_and_apply(clean_data)

    def interpret_by_regex(self, data):
        special_cases = ''
        for key in self.ambiguous_chars:
            special_cases += key
        p = re.compile('[0-9a-fA-F' + special_cases + ']{2}')
        return p.findall(data)

    def get_data_from_image(self, image):
        try:
            pytesseract.tesseract_cmd = self.sys_cfg['tesseract_directory']
            self.bounding_boxes = pytesseract.image_to_boxes(image)
            self.redraw(False)
            return pytesseract.image_to_string(image)

        except pytesseract.TesseractNotFoundError:
            self.set_status('Did not find tesseract.exe at specified directory', 'red')

    def translate_and_apply(self, data):
        output_str = ''
        for hex_num in data:
            try:
                hex_num = hex_num.upper()

                # Replace chars ordered by priority until one makes a key match
                for key in self.ambiguous_chars:
                    if hex_num in self.ascii_lookup.keys():
                        break

                    for c in self.ambiguous_chars[key]:
                        replacement = c
                        print('attempting to replace \'{}\' with \'{}\''.format(key, replacement))
                        hex_num = hex_num.replace(key, replacement)
                        if hex_num in self.ascii_lookup.keys():
                            print('new key match: {}'.format(hex_num))
                            break

                raw_str = self.ascii_lookup[hex_num]
                output_str += raw_str.replace('SPACE', ' ')

            except KeyError:
                print('Did not find symbol for {}'.format(hex_num))

        challenges = [
            'Software Architecture',
            'Third-party Integration',
            'Team Management']

        if self.should_i_apply:
            output_str += ('\n\nI believe the three most difficult challenges are {}'
                           .format(', '.join(challenges)))

        self.txt_output.config(state=NORMAL)
        self.txt_output.delete(1.0, END)
        self.txt_output.insert(END, output_str)
        self.txt_output.config(state=DISABLED)
        self.set_status('Cracked code!', 'green')


if __name__ == "__main__":
    CodeSolver()
