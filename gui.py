"""
Tkinter GUI for the Virtual Memory Manager.

Run:  python gui.py
Shows, step by step: address breakdown, TLB contents, page table (16x16 grid),
physical memory frames (grid), a translation log and live statistics.
Now includes an Export button to dump the translation log and statistics.
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from vmm import NUM_PAGES, VirtualMemoryManager, load_addresses

HERE = os.path.dirname(os.path.abspath(__file__))
CELL = 15
C_EMPTY, C_RES, C_CUR, C_FAULT = "#e5e7eb", "#86efac", "#fbbf24", "#f87171"
MONO = ("Consolas", 10, "bold")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Virtual Memory Manager - Address Translation Simulator")
        self._fit_to_screen()
        ttk.Style(self).configure("Treeview", rowheight=18)
        self.vmm = None
        self.addresses = []
        self.idx = 0
        self.running = False
        self.cur_page = None
        self.cur_frame = None
        self.last_fault = False

        self.backing_var = tk.StringVar(value=os.path.join(HERE, "BACKING_STORE.bin"))
        self.addr_var = tk.StringVar(value=os.path.join(HERE, "addresses.txt"))
        self.frames_var = tk.IntVar(value=256)
        self.tlb_var = tk.IntVar(value=16)
        self.tlb_pol = tk.StringVar(value="FIFO")
        self.page_pol = tk.StringVar(value="FIFO")
        self.delay_var = tk.IntVar(value=100)
        self.manual_var = tk.StringVar()

        self._build_controls()
        self._build_body()
        self.load()

    def _fit_to_screen(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.minsize(900, 560)
        self.geometry(f"{min(1280, sw - 40)}x{min(720, sh - 90)}+10+10")
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------ UI
    def _build_controls(self):
        f = ttk.LabelFrame(self, text="Setup")
        f.pack(fill="x", padx=8, pady=(4, 2))
        ttk.Label(f, text="Backing store:").grid(row=0, column=0, sticky="e")
        ttk.Entry(f, textvariable=self.backing_var, width=45).grid(row=0, column=1)
        ttk.Button(f, text="Browse", command=lambda: self._browse(self.backing_var)).grid(row=0, column=2)
        ttk.Label(f, text="Addresses:").grid(row=1, column=0, sticky="e")
        ttk.Entry(f, textvariable=self.addr_var, width=45).grid(row=1, column=1)
        ttk.Button(f, text="Browse", command=lambda: self._browse(self.addr_var)).grid(row=1, column=2)

        ttk.Label(f, text="Frames:").grid(row=0, column=3, sticky="e", padx=(14, 2))
        ttk.Combobox(f, textvariable=self.frames_var, values=[256, 128, 64, 32],
                     width=6, state="readonly").grid(row=0, column=4)
        ttk.Label(f, text="TLB size:").grid(row=1, column=3, sticky="e", padx=(14, 2))
        ttk.Spinbox(f, from_=1, to=64, textvariable=self.tlb_var, width=6).grid(row=1, column=4)
        ttk.Label(f, text="TLB policy:").grid(row=0, column=5, sticky="e", padx=(14, 2))
        ttk.Combobox(f, textvariable=self.tlb_pol, values=["FIFO", "LRU"], width=6,
                     state="readonly").grid(row=0, column=6)
        ttk.Label(f, text="Page replacement:").grid(row=1, column=5, sticky="e", padx=(14, 2))
        ttk.Combobox(f, textvariable=self.page_pol, values=["FIFO", "LRU"], width=6,
                     state="readonly").grid(row=1, column=6)
        ttk.Button(f, text="Load / Reset", command=self.load).grid(row=0, column=7, rowspan=2, padx=14)

        r = ttk.Frame(self)
        r.pack(fill="x", padx=8, pady=2)
        ttk.Button(r, text="Step", command=self.step).pack(side="left")
        self.run_btn = ttk.Button(r, text="Run", command=self.toggle_run)
        self.run_btn.pack(side="left", padx=4)
        ttk.Button(r, text="Run to end", command=self.run_all).pack(side="left")
        ttk.Label(r, text="  Delay (ms):").pack(side="left")
        ttk.Scale(r, from_=0, to=1000, variable=self.delay_var, length=140).pack(side="left")
        ttk.Label(r, text="   Try an address:").pack(side="left")
        e = ttk.Entry(r, textvariable=self.manual_var, width=10)
        e.pack(side="left")
        e.bind("<Return>", lambda _e: self.manual())
        ttk.Button(r, text="Translate", command=self.manual).pack(side="left", padx=4)
        self.progress = ttk.Label(r, text="")
        self.progress.pack(side="right")

    def _build_body(self):
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=4)
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        # ---- left column: current translation + statistics
        cf = ttk.LabelFrame(left, text="Current translation")
        cf.pack(fill="x")
        self.lbl = {}
        for i, k in enumerate(["Logical address", "Binary (16-bit)", "Page number", "Offset",
                               "TLB", "Page table", "Frame number", "Physical address", "Value"]):
            ttk.Label(cf, text=k + ":").grid(row=i, column=0, sticky="e", padx=4)
            self.lbl[k] = ttk.Label(cf, text="-", font=MONO, width=36)
            self.lbl[k].grid(row=i, column=1, sticky="w")

        sf = ttk.LabelFrame(left, text="Statistics")
        sf.pack(fill="x", pady=6)
        self.stat = {}
        for i, k in enumerate(["Translated", "Page faults", "Page-fault rate", "TLB hits",
                               "TLB hit rate", "Replacements"]):
            ttk.Label(sf, text=k + ":").grid(row=i, column=0, sticky="e", padx=4)
            self.stat[k] = ttk.Label(sf, text="0", font=MONO)
            self.stat[k].grid(row=i, column=1, sticky="w")

        # ---- right column, top row: page table | frames | TLB
        top = ttk.Frame(right)
        top.pack(fill="x")
        pf = ttk.LabelFrame(top, text="Page table (page = row*16 + col)")
        pf.pack(side="left", anchor="n", padx=(0, 8))
        self.page_canvas = tk.Canvas(pf, width=16 * CELL, height=16 * CELL, bg="white", highlightthickness=0)
        self.page_canvas.pack(padx=4, pady=4)
        self.page_rects = self._make_grid(self.page_canvas, NUM_PAGES)

        ff = ttk.LabelFrame(top, text="Physical frames (frame = row*16 + col)")
        ff.pack(side="left", anchor="n", padx=(0, 8))
        self.frame_canvas = tk.Canvas(ff, width=16 * CELL, height=16 * CELL, bg="white", highlightthickness=0)
        self.frame_canvas.pack(padx=4, pady=4)
        self.frame_rects = []

        tf = ttk.LabelFrame(top, text="TLB (oldest at top)")
        tf.pack(side="left", anchor="n", fill="y")
        self.tlb_tree = ttk.Treeview(tf, columns=("page", "frame"), show="headings", height=14)
        self.tlb_tree.heading("page", text="Page")
        self.tlb_tree.heading("frame", text="Frame")
        self.tlb_tree.column("page", width=70, anchor="center")
        self.tlb_tree.column("frame", width=70, anchor="center")
        tsb = ttk.Scrollbar(tf, command=self.tlb_tree.yview)
        self.tlb_tree.configure(yscrollcommand=tsb.set)
        self.tlb_tree.pack(side="left", fill="y")
        tsb.pack(side="left", fill="y")

        ttk.Label(right, text="green = in memory, yellow = current, red = page fault").pack(anchor="w", pady=2)

        # ---- right column, bottom: translation log with export button
        lf = ttk.LabelFrame(right, text="Translation log")
        lf.pack(fill="both", expand=True)

        log_top = ttk.Frame(lf)
        log_top.pack(fill="x", padx=4, pady=(2, 2))
        ttk.Label(log_top, text="Recent references (newest first)").pack(side="left")
        ttk.Button(log_top, text="Export Log & Stats", command=self.export_log).pack(side="right")

        cols = ("n", "logical", "page", "tlb", "fault", "frame", "physical", "value")
        self.log = ttk.Treeview(lf, columns=cols, show="headings", height=6)
        for c, w in zip(cols, (50, 80, 60, 60, 60, 60, 80, 60)):
            self.log.heading(c, text=c.capitalize())
            self.log.column(c, width=w, anchor="center", stretch=True)
        self.log.tag_configure("hit", background="#dcfce7")
        self.log.tag_configure("fault", background="#fee2e2")
        sb = ttk.Scrollbar(lf, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

    def _make_grid(self, canvas, n):
        rects = []
        for i in range(n):
            x, y = (i % 16) * CELL, (i // 16) * CELL
            rects.append(canvas.create_rectangle(x + 1, y + 1, x + CELL - 1, y + CELL - 1,
                                                 fill=C_EMPTY, outline="#9ca3af"))
        return rects

    # ----------------------------------------------------------- actions
    def _browse(self, var):
        p = filedialog.askopenfilename()
        if p:
            var.set(p)

    def load(self):
        self.running = False
        self.run_btn.config(text="Run")
        try:
            self.vmm = VirtualMemoryManager(self.backing_var.get(), int(self.frames_var.get()),
                                            int(self.tlb_var.get()), self.tlb_pol.get(),
                                            self.page_pol.get())
            self.addresses = load_addresses(self.addr_var.get())
        except Exception as e:
            self.vmm = None
            messagebox.showerror("Cannot load",
                                 f"{e}\n\nTip: run `python gen_data.py` to create sample files.")
            return
        self.idx = 0
        self.cur_page = self.cur_frame = None
        self.log.delete(*self.log.get_children())
        self.frame_canvas.delete("all")
        self.frame_rects = self._make_grid(self.frame_canvas, self.vmm.num_frames)
        for v in self.lbl.values():
            v.config(text="-")
        self.refresh(None)

    def step(self):
        if not self.vmm:
            return False
        if self.idx >= len(self.addresses):
            self.running = False
            self.run_btn.config(text="Run")
            return False
        self._do(self.addresses[self.idx], self.idx + 1)
        self.idx += 1
        return True

    def manual(self):
        if not self.vmm:
            return
        try:
            a = int(self.manual_var.get(), 0)
        except ValueError:
            messagebox.showerror("Invalid", "Enter a number, e.g. 16916 or 0x4214")
            return
        self._do(a, "*")

    def toggle_run(self):
        self.running = not self.running
        self.run_btn.config(text="Pause" if self.running else "Run")
        if self.running:
            self._tick()

    def _tick(self):
        if self.running and self.step():
            self.after(int(self.delay_var.get()), self._tick)

    def run_all(self):
        while self.step():
            pass
        self.refresh(None)

    def export_log(self):
        if not self.vmm or self.vmm.total == 0:
            messagebox.showwarning("Warning", "No translation records to export yet.")
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                 filetypes=[("Text File", "*.txt"), ("All Files", "*.*")])
        if not save_path:
            return
        try:
            with open(save_path, "w") as f:
                f.write(f"VMM Translation Summary\n")
                f.write(f"=====================\n")
                f.write(f"Total Translated : {self.vmm.total}\n")
                f.write(f"Page Faults      : {self.vmm.page_faults} (Rate: {self.vmm.page_fault_rate:.3f})\n")
                f.write(f"TLB Hits         : {self.vmm.tlb_hits} (Rate: {self.vmm.tlb_hit_rate:.3f})\n")
                f.write(f"Replacements     : {self.vmm.replacements}\n\n")
                f.write("Log Entries (Newest First):\n")
                f.write(f"{'#':<6}{'Logical':<10}{'Page':<8}{'TLB':<8}{'Fault':<8}{'Frame':<8}{'Physical':<10}{'Value':<8}\n")
                f.write("-" * 68 + "\n")
                for child in self.log.get_children():
                    vals = self.log.item(child)["values"]
                    f.write(f"{vals[0]:<6}{vals[1]:<10}{vals[2]:<8}{vals[3]:<8}{vals[4]:<8}{vals[5]:<8}{vals[6]:<10}{vals[7]:<8}\n")
            messagebox.showinfo("Export Successful", f"Records exported successfully to:\n{save_path}")
        except Exception as ex:
            messagebox.showerror("Export Failed", str(ex))

    # ------------------------------------------------------- translation
    def _do(self, addr, n):
        r = self.vmm.translate(addr)
        self.cur_page, self.cur_frame, self.last_fault = r.page, r.frame, r.page_fault
        tag = "fault" if r.page_fault else ("hit" if r.tlb_hit else "")
        self.log.insert("", 0, values=(n, r.logical, r.page, "HIT" if r.tlb_hit else "miss",
                                       "FAULT" if r.page_fault else "-", r.frame,
                                       r.physical, r.value), tags=(tag,))
        kids = self.log.get_children()
        if len(kids) > 1000:
            self.log.delete(kids[-1])
        self.refresh(r)

    def refresh(self, r):
        v = self.vmm
        if r:
            self.lbl["Logical address"].config(text=f"{r.logical}  (0x{r.logical:04X})")
            b = f"{r.logical:016b}"
            self.lbl["Binary (16-bit)"].config(text=f"{b[:8]} | {b[8:]}")
            self.lbl["Page number"].config(text=f"{r.page}  (high 8 bits)")
            self.lbl["Offset"].config(text=f"{r.offset}  (low 8 bits)")
            self.lbl["TLB"].config(text="HIT" if r.tlb_hit else "MISS")
            self.lbl["Page table"].config(
                text="not consulted" if r.tlb_hit else ("PAGE FAULT -> loaded from disk" if r.page_fault else "valid entry"))
            ev = f"  (evicted page {r.evicted_page})" if r.evicted_page is not None else ""
            self.lbl["Frame number"].config(text=f"{r.frame}{ev}")
            self.lbl["Physical address"].config(
                text=f"{r.physical} (0x{r.physical:04X}) = {r.frame}*256+{r.offset}")
            self.lbl["Value"].config(text=str(r.value))
        self.stat["Translated"].config(text=str(v.total))
        self.stat["Page faults"].config(text=str(v.page_faults))
        self.stat["Page-fault rate"].config(text=f"{v.page_fault_rate:.3f}")
        self.stat["TLB hits"].config(text=str(v.tlb_hits))
        self.stat["TLB hit rate"].config(text=f"{v.tlb_hit_rate:.3f}")
        self.stat["Replacements"].config(text=str(v.replacements))
        self.progress.config(text=f"{self.idx}/{len(self.addresses)} addresses")

        self.tlb_tree.delete(*self.tlb_tree.get_children())
        for p, f in v.tlb.items():
            self.tlb_tree.insert("", "end", values=(p, f))

        for p in range(NUM_PAGES):
            col = C_RES if v.page_table[p] is not None else C_EMPTY
            if p == self.cur_page:
                col = C_FAULT if self.last_fault else C_CUR
            self.page_canvas.itemconfig(self.page_rects[p], fill=col)
        for f in range(v.num_frames):
            col = C_RES if v.frame_page[f] is not None and v.page_table[v.frame_page[f]] == f else C_EMPTY
            if f == self.cur_frame:
                col = C_FAULT if self.last_fault else C_CUR
            self.frame_canvas.itemconfig(self.frame_rects[f], fill=col)


if __name__ == "__main__":
    App().mainloop()