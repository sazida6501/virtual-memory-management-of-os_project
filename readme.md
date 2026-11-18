# Virtual Memory Manager (VMM) Simulation & GUI

A simulation of a demand-paged Virtual Memory Management unit that translates 16-bit virtual addresses into physical addresses, supporting Translation Lookaside Buffer (TLB) caching and configurable page replacement policies (FIFO & LRU).

---

## 1. System Specifications
- **Virtual Address Space:** $2^{16} = 65,536$ bytes (16-bit logical addresses).
- **Page Size:** 256 bytes ($2^8$); Page Number = High 8 bits, Offset = Low 8 bits.
- **Page Table:** 256 entries.
- **Frame Size:** 256 bytes.
- **Physical Memory:** 256 frames (65,536 bytes) by default; supports 128, 64, or 32 frames for page-replacement experiments.
- **TLB:** 16 entries; supports FIFO and LRU caching policies.
- **Backing Store:** `BACKING_STORE.bin` (65,536-byte raw binary secondary storage).

---

## 2. File Organization
```
├── vmm.py                  # Core VMM engine, translation logic, and CLI runner
├── gui.py                  # Tkinter GUI interface (interactive visual simulator)
├── gen_data.py             # Synthetic dataset generator for verification
├── addresses.txt           # Input logical addresses (1,000 references, one per line)
├── BACKING_STORE.bin       # 64 KB secondary storage binary image
├── output.txt              # Default 256-frame CLI translation output
├── output_128_fifo.txt     # 128-frame FIFO page replacement output
├── output_128_lru.txt      # 128-frame LRU page replacement output
└── readme.md               # Execution guide and project documentation
```

---

## 3. How to Run

### A. Graphical User Interface (GUI)
Run the following command in PowerShell, Command Prompt, or your terminal:
```bash
python gui.py
```

#### GUI Controls & Features:
- **Load / Reset:** Initializes memory, loads the selected files, and resets statistics.
- **Step:** Advances the simulation by exactly one logical address reference.
- **Run / Pause:** Automates translation with real-time visual updates.
- **Run to end:** Executes all remaining addresses instantly.
- **Delay Slider:** Adjusts animation speed between steps (0 to 1000 ms).
- **Try an address:** Allows manual lookup of arbitrary decimal or hex addresses (e.g., `16916` or `0x4214`).
- **Export Log & Stats:** Exports full historical translation records and final hit/fault rates to a text file.
- **Color Legend:**
  - `Gray`: Invalid / unallocated page or empty frame.
  - `Green`: Resident page / frame in memory (or TLB hit in log).
  - `Yellow`: Current page / frame being accessed.
  - `Red`: Page fault (page loaded from backing store).

---

### B. Command-Line Interface (CLI)
Run headless simulations directly from the terminal.

1. **Standard 256-Frame Execution (Default FIFO TLB):**
```bash
python vmm.py addresses.txt --backing BACKING_STORE.bin
```

2. **Save Output to File:**
```bash
python vmm.py addresses.txt --backing BACKING_STORE.bin --out output.txt
```

3. **Page Replacement Mode (128 Frames, FIFO vs. LRU Policy):**
```bash
python vmm.py addresses.txt --frames 128 --page-policy FIFO --out output_128_fifo.txt
python vmm.py addresses.txt --frames 128 --page-policy LRU --out output_128_lru.txt
```

4. **Available CLI Arguments:**
- `addresses`: Path to address file (required).
- `--backing`: Path to backing store binary (default: `BACKING_STORE.bin`).
- `--frames`: Number of physical frames (`256`, `128`, `64`, `32`; default: `256`).
- `--tlb-size`: Number of TLB entries (default: `16`).
- `--tlb-policy`: TLB replacement policy (`FIFO` or `LRU`; default: `FIFO`).
- `--page-policy`: Physical page replacement policy (`FIFO` or `LRU`; default: `FIFO`).
- `--out`: Destination file to write outputs (prints to stdout if omitted).

---

## 4. Output Format
For each translated logical address, the program outputs:
```
Virtual address: <addr> Physical address: <p_addr> Value: <byte_val>
```
Followed by final summary statistics:
```
Number of Translated Addresses = 1000
Page Faults = <fault_count>
Page Fault Rate = <rate>
TLB Hits = <hit_count>
TLB Hit Rate = <rate>
```

---

## 5. Benchmark Results Reference
Results below correspond to the included 1,000-reference `addresses.txt` trace and `BACKING_STORE.bin` image (with a 16-entry FIFO TLB):

### 256 Frames (Standard Non-Replacement Mode — `output.txt`)
- **Translated Addresses:** 1000
- **Page Faults:** 206 (Fault Rate: `0.206`)
- **Page Evictions:** 0
- **TLB Hits:** 372 (Hit Rate: `0.372`)

### 128 Frames (Page Replacement Variant)
| Policy | Output File | Page Faults | Fault Rate | Page Evictions | TLB Hits | Hit Rate |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **FIFO** | `output_128_fifo.txt` | 251 | `0.251` | 123 | 378 | `0.378` |
| **LRU** | `output_128_lru.txt` | 240 | `0.240` | 112 | 372 | `0.372` |

---

## 6. Requirements & Dependencies
- Python 3.8 or higher.
- Standard libraries only (`tkinter`, `collections`, `dataclasses`, `argparse`, `sys`, `os`).
- No external `pip` dependencies are required.