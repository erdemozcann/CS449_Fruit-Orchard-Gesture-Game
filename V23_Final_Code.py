import cv2
import mediapipe as mp
import tkinter as tk
import random
import threading
import time
import queue

# Global state variables
running = True
hand_present = False
scroll_mode = False
timer_threads = {}
selected_item = None
current_buttons = {}
current_timers = {}
current_button_positions = {}
current_selection_callback = None

canvas = None
cursor_window = None
cursor_label = None

fruits = []
basket = None
dragging_fruit = None
score = 0
score_label = None

last_scroll_time = time.time()
prev_cursor_x = None
prev_cursor_y = None

root = tk.Tk()
root.title("Fruit Orchard")
root.geometry("600x600")
root.configure(bg="#f5f5dc")
root.resizable(False, False)

frame_queue = queue.Queue()

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils

# ---------------------------------------------------------------
# Helper functions for gesture detection and cursor movement
# ---------------------------------------------------------------

def is_finger_extended(hand_landmarks, finger_name):
    """
    Checks if a particular finger is extended.
    For thumb, we compare x-coordinates (tip > pip means extended).
    For other fingers, we compare y-coordinates (tip < pip means extended).
    """
    mp_hands_tips = {
        'thumb': mp_hands.HandLandmark.THUMB_TIP,
        'index': mp_hands.HandLandmark.INDEX_FINGER_TIP,
        'middle': mp_hands.HandLandmark.MIDDLE_FINGER_TIP,
        'ring': mp_hands.HandLandmark.RING_FINGER_TIP,
        'pinky': mp_hands.HandLandmark.PINKY_TIP,
    }
    mp_hands_pips = {
        'thumb': mp_hands.HandLandmark.THUMB_IP,
        'index': mp_hands.HandLandmark.INDEX_FINGER_PIP,
        'middle': mp_hands.HandLandmark.MIDDLE_FINGER_PIP,
        'ring': mp_hands.HandLandmark.RING_FINGER_PIP,
        'pinky': mp_hands.HandLandmark.PINKY_PIP,
    }

    tip = hand_landmarks.landmark[mp_hands_tips[finger_name]]
    pip = hand_landmarks.landmark[mp_hands_pips[finger_name]]
    if finger_name == 'thumb':
        return tip.x > pip.x
    else:
        return tip.y < pip.y

def move_cursor(screen_x, screen_y):
    """
    Moves the on-screen cursor to (screen_x, screen_y).
    If a fruit is being dragged, move it along with the cursor.
    """
    if not running or canvas is None:
        return
    try:
        canvas.coords(cursor_window, screen_x, screen_y)
        if dragging_fruit is not None:
            canvas.coords(dragging_fruit['obj'], screen_x, screen_y)
    except tk.TclError:
        pass

def hide_cursor():
    """
    Hides the cursor by moving it off-screen.
    """
    if not running or canvas is None:
        return
    try:
        canvas.coords(cursor_window, -100, -100)
    except tk.TclError:
        pass

# ---------------------------------------------------------------
# Selection and timer management
# ---------------------------------------------------------------

def reset_selection():
    """
    Resets any currently selected item. Clears timers and reverts button colors.
    """
    global selected_item
    if not running:
        return
    selected_item = None
    for key, label in current_timers.items():
        if label.winfo_exists():
            label.config(text="")
    for btn in current_buttons.values():
        if btn.winfo_exists():
            btn.config(bg="gray")

def start_timer(item_key, callback, duration=2):
    """
    Starts a selection timer for the hovered item.
    If the cursor stays on the same item for 'duration' seconds, triggers callback.
    If user moves away or hand disappears, timer resets.
    """
    if item_key in current_timers:
        for k, l in current_timers.items():
            if k != item_key and l.winfo_exists():
                l.config(text="")
        for i in range(duration, 0, -1):
            if not running:
                return
            if current_timers[item_key].winfo_exists():
                current_timers[item_key].config(text=f"{i}s")
            time.sleep(1)
            if not hand_present or selected_item != item_key or not running:
                if current_timers[item_key].winfo_exists():
                    current_timers[item_key].config(text="")
                return
        if current_timers[item_key].winfo_exists():
            current_timers[item_key].config(text="")
        callback(item_key)

def check_cursor_over_item(x, y, item_positions, callback, duration=2):
    """
    Checks if the cursor is currently hovering over any interactive item.
    If so, starts the timer for that item.
    Otherwise, resets the selection.
    """
    global selected_item, timer_threads
    over_item = None
    for key, pos in item_positions.items():
        ix, iy = pos
        w = 150
        h = 50
        if key.startswith("fruit"):
            w = 30
            h = 30
        if key == "basket":
            w = 100
            h = 60
        if (ix - w/2) <= x <= (ix + w/2) and (iy - h/2) <= y <= (iy + h/2):
            over_item = key
            break

    if over_item:
        if selected_item == over_item:
            return
        for k, btn in current_buttons.items():
            if btn.winfo_exists():
                btn.config(bg="gray")
        for k, l in current_timers.items():
            if l.winfo_exists():
                l.config(text="")
        if over_item in current_buttons and current_buttons[over_item].winfo_exists():
            current_buttons[over_item].config(bg="#add8e6")
        selected_item = over_item
        if over_item not in timer_threads or not timer_threads[over_item].is_alive():
            t = threading.Thread(target=start_timer, args=(over_item, callback, duration))
            timer_threads[over_item] = t
            t.start()
    else:
        reset_selection()

def scroll_canvas(direction):
    """
    Scrolls the canvas in the given direction (up/down/left/right) if triggered by the scroll gesture.
    A minimum interval is required between scrolls to prevent too fast scrolling.
    """
    global last_scroll_time
    if not running or canvas is None:
        return
    current_time = time.time()
    if current_time - last_scroll_time < 0.05:
        return
    last_scroll_time = current_time
    try:
        if direction == 'up':
            canvas.yview_scroll(-1, 'units')
        elif direction == 'down':
            canvas.yview_scroll(1, 'units')
        elif direction == 'left':
            canvas.xview_scroll(-1, 'units')
        elif direction == 'right':
            canvas.xview_scroll(1, 'units')
    except tk.TclError:
        pass

# ---------------------------------------------------------------
# Video processing and gesture handling
# ---------------------------------------------------------------

def process_video():
    """
    Captures video frames from the webcam, detects hand landmarks,
    and interprets gestures. Calls UI updates accordingly.
    """
    global hand_present, scroll_mode, prev_cursor_x, prev_cursor_y, running
    cap = cv2.VideoCapture(0)
    with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.7,
    ) as hands:
        while running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = hands.process(rgb_frame)

            cursor_visible = False

            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                    index_ext = is_finger_extended(hand_landmarks, 'index')
                    middle_ext = is_finger_extended(hand_landmarks, 'middle')
                    ring_ext = is_finger_extended(hand_landmarks, 'ring')
                    pinky_ext = is_finger_extended(hand_landmarks, 'pinky')

                    # Three-finger (index+middle+ring) -> quit
                    if index_ext and middle_ext and ring_ext and not pinky_ext:
                        hand_present = True
                        scroll_mode = False
                        cursor_visible = False
                        root.after(0, on_close)

                    # Two-finger (index+middle) -> move mode
                    elif index_ext and middle_ext and not ring_ext and not pinky_ext:
                        hand_present = True
                        cursor_visible = True
                        scroll_mode = False

                        index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                        middle_tip = hand_landmarks.landmark[mp_hands.HandLandmark.MIDDLE_FINGER_TIP]

                        cx = (index_tip.x + middle_tip.x) / 2
                        cy = (index_tip.y + middle_tip.y) / 2

                        if canvas is not None and running:
                            screen_x = cx * canvas.winfo_width() + canvas.canvasx(0)
                            screen_y = cy * canvas.winfo_height() + canvas.canvasy(0)

                            root.after(0, move_cursor, screen_x, screen_y)
                            if current_button_positions and current_selection_callback:
                                root.after(0, check_cursor_over_item, screen_x, screen_y, current_button_positions, current_selection_callback, 2)
                            prev_cursor_x, prev_cursor_y = None, None

                    # One-finger (index) -> scroll mode
                    elif index_ext and not middle_ext and not ring_ext and not pinky_ext:
                        hand_present = True
                        cursor_visible = False
                        scroll_mode = True

                        index_tip = hand_landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                        cx = index_tip.x
                        cy = index_tip.y

                        if prev_cursor_x is not None and prev_cursor_y is not None and running:
                            dx = cx - prev_cursor_x
                            dy = cy - prev_cursor_y
                            if abs(dx) > abs(dy):
                                if dx > 0.01:
                                    root.after(0, scroll_canvas, 'right')
                                elif dx < -0.01:
                                    root.after(0, scroll_canvas, 'left')
                            else:
                                if dy > 0.01:
                                    root.after(0, scroll_canvas, 'down')
                                elif dy < -0.01:
                                    root.after(0, scroll_canvas, 'up')
                        prev_cursor_x, prev_cursor_y = cx, cy
                        root.after(0, hide_cursor)
                        root.after(0, reset_selection)

                    else:
                        hand_present = False
                        cursor_visible = False
                        scroll_mode = False
                        prev_cursor_x, prev_cursor_y = None, None
                        root.after(0, reset_selection)
                        root.after(0, hide_cursor)
            else:
                hand_present = False
                cursor_visible = False
                scroll_mode = False
                prev_cursor_x, prev_cursor_y = None, None
                root.after(0, reset_selection)
                root.after(0, hide_cursor)

            if not cursor_visible:
                root.after(0, hide_cursor)

            frame_queue.put(frame)

    cap.release()

def show_frame():
    """
    Continuously reads frames from the queue and displays them.
    Pressing ESC closes the application.
    """
    if not running:
        return
    if not frame_queue.empty():
        frame = frame_queue.get()
        cv2.imshow("Gesture Control", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            on_close()
            return
    root.after(10, show_frame)

# ---------------------------------------------------------------
# Menu and instructions logic
# ---------------------------------------------------------------

def menu_selection(item_key):
    """
    Callback for main menu items.
    'play': Start the game
    'instructions': Show instructions screen
    'quit': Close the application
    """
    if item_key == "play":
        show_game()
    elif item_key == "instructions":
        show_instructions_gui()
        reset_selection()
    elif item_key == "quit":
        on_close()

def instructions_selection(item_key):
    """
    Callback for instructions screen.
    'return_main': Return to main menu
    """
    if item_key == "return_main":
        show_menu()

def show_instructions_gui():
    """
    Displays the instructions screen with a return-to-main-menu button.
    Cursor works the same way as in the main menu.
    """
    global current_buttons, current_timers, current_button_positions, current_selection_callback
    current_buttons.clear()
    current_timers.clear()
    current_button_positions.clear()
    current_selection_callback = instructions_selection

    for w in root.winfo_children():
        if w != root:
            w.destroy()

    global canvas, cursor_window, cursor_label
    canvas = tk.Canvas(root, width=600, height=600, bg="#fffaf0")
    canvas.pack(fill="both", expand=True)

    canvas.create_text(300, 50, text="CS449 - Fruit Orchard - Instruction", font=("Arial",16,"bold"), fill="black")

    instructions_text = (
        "Use hand gestures:\n"
        "- INDEX + MIDDLE: Move the cursor.\n"
        "- INDEX only: Scroll the view.\n"
        "- INDEX + MIDDLE + RING: Quit the game.\n\n"
        "Hover 2s over items to select them.\n\n"
        "In the game:\n"
        "- Hover 2s over a fruit to pick it.\n"
        "- Hover 2s over the basket to drop it and gain a point.\n"
        "Scrolling helps you find fruits out of view!"
    )

    instructions_label = tk.Label(canvas, text=instructions_text, font=("Arial",12), bg="#fffaf0")
    canvas.create_window(300, 200, window=instructions_label, width=400)

    current_buttons["return_main"] = tk.Button(canvas, text="Return to Main Menu", font=("Arial",14), bg="gray", fg="black")
    current_timers["return_main"] = tk.Label(canvas, text="", font=("Arial",12), fg="red", bg="#fffaf0")
    current_button_positions["return_main"] = (300,400)

    canvas.create_window(300, 400, window=current_buttons["return_main"], width=200, height=50)
    canvas.create_window(300, 450, window=current_timers["return_main"], width=200, height=20)

    cursor_label = tk.Label(canvas, text="X", font=("Arial",12), fg="red", bg="#fffaf0")
    cursor_window = canvas.create_window(-100, -100, window=cursor_label)
    canvas.lift(cursor_window)

def show_menu():
    """
    Displays the main menu with 'Play Game', 'Instructions', and 'Quit' buttons.
    Also displays the names under the Quit button.
    """
    global current_buttons, current_timers, current_button_positions, current_selection_callback
    current_buttons.clear()
    current_timers.clear()
    current_button_positions.clear()
    current_selection_callback = menu_selection

    for w in root.winfo_children():
        if w != root:
            w.destroy()

    global canvas, cursor_window, cursor_label
    canvas = tk.Canvas(root, width=600, height=600, bg="#fffaf0", scrollregion=(0,0,600,600))
    canvas.pack(fill="both", expand=True)

    canvas.create_text(300, 50, text="CS449 - Fruit Orchard - Main Menu", font=("Arial",16,"bold"), fill="black")

    current_buttons["play"] = tk.Button(canvas, text="Play Game", font=("Arial",14), bg="gray", fg="black")
    current_buttons["instructions"] = tk.Button(canvas, text="Instructions", font=("Arial",14), bg="gray", fg="black")
    current_buttons["quit"] = tk.Button(canvas, text="Quit", font=("Arial",14), bg="gray", fg="black")

    current_timers["play"] = tk.Label(canvas, text="", font=("Arial",12), fg="red", bg="#fffaf0")
    current_timers["instructions"] = tk.Label(canvas, text="", font=("Arial",12), fg="red", bg="#fffaf0")
    current_timers["quit"] = tk.Label(canvas, text="", font=("Arial",12), fg="red", bg="#fffaf0")

    current_button_positions["play"] = (300,200)
    current_button_positions["instructions"] = (300,300)
    current_button_positions["quit"] = (300,400)

    for k in current_buttons:
        x, y = current_button_positions[k]
        canvas.create_window(x, y, window=current_buttons[k], width=150, height=50)
        canvas.create_window(x, y+30, window=current_timers[k], width=150, height=20)

    # Names listed under the quit button
    names_label = tk.Label(canvas, text="Erdem Özcan\tİlyas Yeşilyaprak\nMustafa Adnan Arasan\tZeki Karamuk",
                           font=("Calibri",12), fg="black", bg="#fffaf0", wraplength=400, justify="center")
    canvas.create_window(300, 480, window=names_label, width=400, height=40)

    cursor_label = tk.Label(canvas, text="X", font=("Arial",12), fg="red", bg="#fffaf0")
    cursor_window = canvas.create_window(-100, -100, window=cursor_label)
    canvas.lift(cursor_window)

# ---------------------------------------------------------------
# Game logic
# ---------------------------------------------------------------

def pick_up_fruit(item_key):
    """
    Picks up the fruit so that it moves with the cursor if the user hovers for 2s.
    """
    global dragging_fruit
    for f in fruits:
        if f['key'] == item_key:
            dragging_fruit = f
            break

def drop_fruit(item_key):
    """
    Drops the currently held fruit into the basket, increasing the score.
    """
    global dragging_fruit, score
    if dragging_fruit is not None and running:
        try:
            canvas.delete(dragging_fruit['obj'])
        except tk.TclError:
            pass
        dragging_fruit = None
        score += 1
        update_score_label()

def update_score_label():
    """
    Updates the score label on the game screen.
    """
    if score_label is not None and score_label.winfo_exists():
        score_label.config(text=f"Score: {score}")

def game_selection(item_key):
    """
    Selection callback in the game:
    - If hovering over a fruit for 2s, pick it up.
    - If hovering over the basket for 2s with a fruit picked, drop it.
    """
    if item_key.startswith("fruit"):
        pick_up_fruit(item_key)
    elif item_key == "basket" and dragging_fruit is not None:
        drop_fruit(item_key)

def show_game():
    """
    Displays the game screen with fruits and a basket on a scrollable canvas.
    The basket is centered in the scroll region so that it appears in the middle
    of the screen upon starting.
    """
    global current_buttons, current_timers, current_button_positions, current_selection_callback
    current_buttons.clear()
    current_timers.clear()
    current_button_positions.clear()
    current_selection_callback = game_selection

    for w in root.winfo_children():
        if w != root:
            w.destroy()

    global canvas, cursor_label, cursor_window, fruits, basket, score, dragging_fruit, score_label
    canvas = tk.Canvas(root, width=600, height=600, bg="#fffaf0", scrollregion=(0,0,1200,1200))
    canvas.pack(fill="both", expand=True)

    vbar = tk.Scrollbar(root, orient='vertical', command=canvas.yview)
    vbar.pack(side='right', fill='y')
    hbar = tk.Scrollbar(root, orient='horizontal', command=canvas.xview)
    hbar.pack(side='bottom', fill='x')
    canvas.config(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

    title_label = tk.Label(root, text="Fruit Orchard", font=("Arial",20,"bold"), fg="black", bg="#f5f5dc")
    title_label.place(x=200, y=10)

    info_label = tk.Label(root, text="Hover 2s over a fruit to pick it.\nThen hover 2s over the basket to drop it.\nUse single finger (index) to scroll!",
                          font=("Arial",12), fg="black", bg="#f5f5dc")
    info_label.place(x=120, y=50)

    score_label = tk.Label(root, text=f"Score: {score}", font=("Arial",14,"bold"), fg="black", bg="#f5f5dc")
    score_label.place(x=10, y=10)

    fruits.clear()
    dragging_fruit = None

    for i in range(5):
        fx = random.randint(100,1100)
        fy = random.randint(100,1100)
        fruit_obj = canvas.create_text(fx, fy, text="🍎", font=("Arial",24))
        fruit_key = f"fruit{i}"
        fruits.append({'key': fruit_key, 'obj': fruit_obj, 'x': fx, 'y': fy})
        current_timers[fruit_key] = tk.Label(canvas, text="", font=("Arial",12), fg="red", bg="#fffaf0")
        canvas.create_window(fx, fy+30, window=current_timers[fruit_key], width=30, height=20)
        current_button_positions[fruit_key] = (fx, fy)

    basket_x = 600
    basket_y = 600
    basket_obj = canvas.create_text(basket_x, basket_y, text="🧺", font=("Arial",30))
    basket = {'key':'basket', 'obj':basket_obj, 'x':basket_x, 'y':basket_y}

    current_button_positions['basket'] = (basket_x, basket_y)
    current_timers['basket'] = tk.Label(canvas, text="", font=("Arial",12), fg="red", bg="#fffaf0")
    canvas.create_window(basket_x, basket_y+50, window=current_timers['basket'], width=100, height=20)

    cursor_label = tk.Label(canvas, text="X", font=("Arial",12), fg="red", bg="#fffaf0")
    cursor_window = canvas.create_window(-100, -100, window=cursor_label)
    canvas.lift(cursor_window)

    # Update canvas and center the view so that the basket is in the middle
    canvas.update_idletasks()
    # 1200x1200 total area, we want (600,600) in center of a 600x600 view
    # This means the top-left corner should be at (300,300)
    # 300/1200 = 0.25 fraction
    canvas.xview_moveto(0.25)
    canvas.yview_moveto(0.25)

# ---------------------------------------------------------------
# Application close handling
# ---------------------------------------------------------------

def on_close():
    """
    Safely closes the application and release resources.
    """
    global running
    running = False
    time.sleep(0.5)
    cv2.destroyAllWindows()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

# ---------------------------------------------------------------
# Application start
# ---------------------------------------------------------------

def start_app():
    """
    Starts the application by showing the main menu,
    then instructions, starting the video thread and frame loop.
    """
    show_menu()
    show_instructions_gui()
    video_thread = threading.Thread(target=process_video)
    video_thread.daemon = True
    video_thread.start()
    show_frame()
    root.mainloop()

start_app()
