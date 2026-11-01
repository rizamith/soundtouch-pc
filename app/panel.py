"""Simple room-based desktop controls. Rendering never changes playback."""
import queue
import threading
import tkinter as tk
import comtypes
from pycaw.pycaw import AudioUtilities


def show(bridge):
    comtypes.CoInitialize()
    root = tk.Tk()
    root.title('SoundTouch')
    root.geometry('580x700')
    root.minsize(480, 550)
    bg, ink, muted, green = '#f5f6f8', '#182224', '#747e85', '#13795b'
    root.configure(bg=bg)
    root.withdraw()
    root.protocol('WM_DELETE_WINDOW', root.withdraw)
    errors = queue.Queue()
    busy = threading.Event()
    message = tk.StringVar()

    def work(fn):
        if busy.is_set():
            return
        busy.set()
        message.set('Working…')
        def run():
            try:
                fn()
                errors.put('')
            except Exception as exc:
                errors.put(str(exc))
            finally:
                busy.clear()
        threading.Thread(target=run, daemon=True).start()

    def label(parent, text, size=10, color=ink, bold=False, background=bg):
        return tk.Label(parent, text=text, bg=background, fg=color,
                        font=('Segoe UI', size, 'bold' if bold else 'normal'), anchor='w')

    def button(parent, text, command, color=ink, background='white'):
        return tk.Button(parent, text=text, command=command, bg=background, fg=color,
                         activebackground='#e8eeeb', activeforeground=ink, relief='flat',
                         bd=0, padx=14, pady=9, cursor='hand2', font=('Segoe UI', 10),
                         highlightthickness=0)

    head = tk.Frame(root, bg=bg)
    head.pack(fill='x', padx=28, pady=(24, 18))
    label(head, 'SoundTouch', 23, bold=True).pack(side='left')
    scan = button(head, '↻  Scan', lambda: work(bridge.scan_network), muted, bg)
    scan.pack(side='right')
    label(root, 'Where do you want to listen?', 11, muted).pack(anchor='w', padx=30)

    # Scroll the room list, keeping volume and feedback visible with many rooms.
    area = tk.Frame(root, bg=bg)
    area.pack(fill='both', expand=True, padx=28, pady=(18, 12))
    canvas = tk.Canvas(area, bg=bg, highlightthickness=0)
    scroll = tk.Scrollbar(area, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    rows = tk.Frame(canvas, bg=bg)
    window = canvas.create_window(0, 0, anchor='nw', window=rows)
    rows.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
    root.bind('<MouseWheel>', lambda e: canvas.yview_scroll(-int(e.delta / 120), 'units'))
    cards = {}

    def make_card(key, title, command, shutdown=None):
        frame = tk.Frame(rows, bg='white', highlightthickness=1, highlightbackground='#e2e6e9')
        frame.pack(fill='x', pady=(0, 10))
        main = button(frame, title, command)
        main.configure(anchor='w', justify='left', font=('Segoe UI', 13, 'bold'), pady=14)
        main.pack(fill='x', padx=4, pady=(3, 0))
        bottom = tk.Frame(frame, bg='white')
        bottom.pack(fill='x', padx=18, pady=(0, 12))
        status = label(bottom, 'Checking…', 9, muted, background='white')
        status.pack(side='left')
        off = None
        if shutdown:
            off = button(bottom, 'Shutdown', shutdown, '#b43f48')
            off.configure(padx=4, pady=2, font=('Segoe UI', 9))
            off.pack(side='right')
        cards[key] = (frame, main, status, off)

    make_card(None, 'This PC', lambda: work(lambda: bridge.route(False)))
    foot = tk.Frame(root, bg=bg)
    foot.pack(fill='x', padx=30, pady=(0, 20))
    line = tk.Frame(foot, bg=bg)
    line.pack(fill='x')
    volume_title = label(line, 'Volume', 10, muted)
    volume_title.pack(side='left')
    volume_value = label(line, '—', 11, bold=True)
    volume_value.pack(side='right')
    volume = tk.Canvas(foot, height=34, bg=bg, highlightthickness=0, cursor='hand2')
    volume.pack(fill='x', pady=(4, 8))
    controls = tk.Frame(foot, bg=bg)
    controls.pack(fill='x')
    mute = button(controls, 'Mute', lambda: toggle_mute(), muted, bg)
    mute.pack(side='left')
    release = button(controls, 'Release speaker', lambda: work(bridge.pause), muted, bg)
    release.pack(side='right')
    feedback = label(foot, '', 9, muted)
    feedback.configure(textvariable=message, wraplength=480)
    feedback.pack(fill='x', pady=(6, 0))
    endpoint = None
    can_volume = False
    level = 0

    def change_volume(event):
        if can_volume and endpoint:
            value = max(0, min(1, (event.x - 9) / max(1, volume.winfo_width() - 18)))
            try:
                endpoint.SetMasterVolumeLevelScalar(value, None)
            except Exception as exc:
                message.set(str(exc))

    def toggle_mute():
        if can_volume and endpoint:
            try:
                endpoint.SetMute(not endpoint.GetMute(), None)
            except Exception as exc:
                message.set(str(exc))

    volume.bind('<Button-1>', change_volume)
    volume.bind('<B1-Motion>', change_volume)

    def update():
        nonlocal endpoint, can_volume, level
        if bridge.stop.is_set():
            root.destroy()
            return
        if bridge.ui_show.is_set():
            bridge.ui_show.clear()
            root.deiconify()
            root.lift()
        while not errors.empty():
            message.set(errors.get_nowait())
        for name in sorted(bridge.cfg['speakers'].copy()):
            if name not in cards:
                make_card(name, name, lambda n=name: work(lambda: bridge.select_speaker(n)),
                          lambda n=name: work(lambda: bridge.shutdown_room(n)))
        active = bool(bridge.enabled and bridge.output_active and bridge.clients)
        for name, (frame, main, state, off) in cards.items():
            if name is None:
                selected = bridge.output_active is False
                main.configure(text='This PC   ' + ('• Listening here' if selected else '→ Listen here'))
                state.configure(text=bridge.local_output_name or 'Local Windows output')
            else:
                info = bridge.room_states.get(name, {})
                selected = active and name == bridge.speaker_name
                connecting = bridge.enabled and name == bridge.speaker_name and not active
                main.configure(text=name + ('   • Listening here' if selected else
                                            '   Connecting…' if connecting else '   → Listen here'))
                state.configure(text=info.get('state', 'Checking…') + '  ·  ' + bridge.cfg['speakers'][name]['model'])
                off.configure(state='normal' if info.get('powered') and not busy.is_set() else 'disabled')
            main.configure(state='disabled' if busy.is_set() else 'normal', fg=green if selected else ink)
            frame.configure(highlightbackground=green if selected else '#e2e6e9')
        scan.configure(text='Scanning…' if bridge.scanning else '↻  Scan',
                       state='disabled' if busy.is_set() else 'normal')
        release.configure(state='normal' if bridge.enabled and not busy.is_set() else 'disabled')
        try:
            device = AudioUtilities.GetSpeakers()
            local = not device.FriendlyName.startswith('SoundTouch')
            endpoint = device.EndpointVolume
            can_volume = local or active
            level = round(endpoint.GetMasterVolumeLevelScalar() * 100)
            volume_value.configure(text=str(level) if can_volume else '—')
            volume_title.configure(text='Volume · ' + (device.FriendlyName if local else bridge.speaker_name))
            mute.configure(text='Unmute' if endpoint.GetMute() else 'Mute', state='normal' if can_volume else 'disabled')
        except Exception:
            can_volume = False
        volume.delete('all')
        width = max(20, volume.winfo_width())
        x = 9 + (width - 18) * level / 100
        volume.create_line(9, 17, width - 9, 17, fill='#dce2e5', width=4, capstyle='round')
        if can_volume:
            volume.create_line(9, 17, x, 17, fill=green, width=4, capstyle='round')
            volume.create_oval(x-7, 10, x+7, 24, fill=green, outline='')
        root.after(400, update)

    # Discovery only reads the network. Opening the panel never starts playback.
    work(bridge.scan_network)
    update()
    try:
        root.mainloop()
    finally:
        comtypes.CoUninitialize()
