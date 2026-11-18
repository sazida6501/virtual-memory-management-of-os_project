"""
Virtual Memory Manager (OS project)

Simulates logical -> physical address translation for a 2^16 = 65,536 byte
virtual address space using a TLB and a page table, with demand paging from
a backing store file (BACKING_STORE.bin).

Parameters (defaults match the classic project spec):
    page size        : 256 bytes (2^8)      -> offset = low 8 bits
    page table size  : 256 entries (2^8)    -> page   = high 8 bits
    TLB size         : 16 entries
    frame size       : 256 bytes
    physical frames  : 256 (= 65,536 bytes)  [use 128 for the page-replacement variant]

Usage:
    python vmm.py addresses.txt
    python vmm.py addresses.txt --frames 128 --page-policy LRU --out output.txt
"""
import argparse
import sys
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional

PAGE_SIZE = 256
NUM_PAGES = 256
ADDRESS_MASK = 0xFFFF          # we only use the rightmost 16 bits of an address
BACKING_SIZE = PAGE_SIZE * NUM_PAGES


@dataclass
class Result:
    """Everything that happened while translating one address."""
    logical: int
    page: int
    offset: int
    tlb_hit: bool
    page_fault: bool
    frame: int
    physical: int
    value: int                       # signed byte, like the C `signed char`
    evicted_page: Optional[int] = None   # page removed from memory (replacement)
    tlb_evicted: Optional[int] = None    # page removed from the TLB


class VirtualMemoryManager:
    def __init__(self, backing_path: str, num_frames: int = 256, tlb_size: int = 16,
                 tlb_policy: str = "FIFO", page_policy: str = "FIFO"):
        if not 1 <= num_frames <= NUM_PAGES:
            raise ValueError("num_frames must be between 1 and 256")
        if tlb_size < 1:
            raise ValueError("tlb_size must be >= 1")
        tlb_policy, page_policy = tlb_policy.upper(), page_policy.upper()
        if tlb_policy not in ("FIFO", "LRU") or page_policy not in ("FIFO", "LRU"):
            raise ValueError("policies must be FIFO or LRU")

        self.backing_path = backing_path
        self.num_frames = num_frames
        self.tlb_size = tlb_size
        self.tlb_policy = tlb_policy
        self.page_policy = page_policy

        with open(backing_path, "rb") as f:
            self._store = f.read()
        if len(self._store) < BACKING_SIZE:
            raise ValueError(f"backing store must be at least {BACKING_SIZE} bytes")
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        self.page_table: List[Optional[int]] = [None] * NUM_PAGES   # page -> frame
        self.frame_page: List[Optional[int]] = [None] * self.num_frames  # frame -> page
        self.tlb: "OrderedDict[int, int]" = OrderedDict()           # page -> frame
        self.resident: "OrderedDict[int, int]" = OrderedDict()      # page -> frame (order = victim order)
        self.physical_memory = bytearray(self.num_frames * PAGE_SIZE)
        self.total = 0
        self.tlb_hits = 0
        self.page_faults = 0
        self.replacements = 0

    # ------------------------------------------------------------- statistics
    @property
    def page_fault_rate(self) -> float:
        return self.page_faults / self.total if self.total else 0.0

    @property
    def tlb_hit_rate(self) -> float:
        return self.tlb_hits / self.total if self.total else 0.0

    # ---------------------------------------------------------------- helpers
    def _read_backing_page(self, page: int) -> bytes:
        start = page * PAGE_SIZE
        return self._store[start:start + PAGE_SIZE]

    def _tlb_insert(self, page: int, frame: int) -> Optional[int]:
        evicted = None
        if page in self.tlb:
            self.tlb.pop(page)
        elif len(self.tlb) >= self.tlb_size:
            evicted, _ = self.tlb.popitem(last=False)   # oldest (FIFO) / least recent (LRU)
        self.tlb[page] = frame
        return evicted

    def _load_page(self, page: int):
        """Handle a page fault. Returns (frame, evicted_page)."""
        evicted = None
        if len(self.resident) < self.num_frames:
            frame = len(self.resident)                  # next free frame
        else:
            evicted, frame = self.resident.popitem(last=False)  # FIFO/LRU victim
            self.page_table[evicted] = None
            self.tlb.pop(evicted, None)                 # keep TLB consistent
            self.replacements += 1
        base = frame * PAGE_SIZE
        self.physical_memory[base:base + PAGE_SIZE] = self._read_backing_page(page)
        self.page_table[page] = frame
        self.frame_page[frame] = page
        self.resident[page] = frame
        return frame, evicted

    # -------------------------------------------------------------- translate
    def translate(self, logical_address: int) -> Result:
        logical = logical_address & ADDRESS_MASK
        page = logical >> 8
        offset = logical & 0xFF
        self.total += 1

        tlb_evicted = None
        evicted = None
        fault = False

        if page in self.tlb:                            # 1) TLB hit
            tlb_hit = True
            self.tlb_hits += 1
            frame = self.tlb[page]
            if self.tlb_policy == "LRU":
                self.tlb.move_to_end(page)
        else:                                           # 2) TLB miss -> page table
            tlb_hit = False
            frame = self.page_table[page]
            if frame is None:                           # 3) page fault -> backing store
                fault = True
                self.page_faults += 1
                frame, evicted = self._load_page(page)
            tlb_evicted = self._tlb_insert(page, frame)

        if self.page_policy == "LRU" and page in self.resident:
            self.resident.move_to_end(page)             # mark as most recently used

        physical = frame * PAGE_SIZE + offset
        raw = self.physical_memory[physical]
        value = raw - 256 if raw > 127 else raw
        return Result(logical, page, offset, tlb_hit, fault, frame, physical, value,
                      evicted, tlb_evicted)


# ------------------------------------------------------------------- file I/O
def load_addresses(path: str) -> List[int]:
    addrs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                addrs.append(int(line))
    return addrs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Virtual Memory Manager simulator")
    ap.add_argument("addresses", help="file with one logical address per line")
    ap.add_argument("--backing", default="BACKING_STORE.bin", help="backing store file")
    ap.add_argument("--frames", type=int, default=256, help="physical frames (256 or 128)")
    ap.add_argument("--tlb-size", type=int, default=16)
    ap.add_argument("--tlb-policy", default="FIFO", choices=["FIFO", "LRU", "fifo", "lru"])
    ap.add_argument("--page-policy", default="FIFO", choices=["FIFO", "LRU", "fifo", "lru"])
    ap.add_argument("--out", help="write translations to this file instead of stdout")
    args = ap.parse_args(argv)

    vmm = VirtualMemoryManager(args.backing, args.frames, args.tlb_size,
                               args.tlb_policy, args.page_policy)
    out = open(args.out, "w") if args.out else sys.stdout
    for addr in load_addresses(args.addresses):
        r = vmm.translate(addr)
        out.write(f"Virtual address: {r.logical} Physical address: {r.physical} Value: {r.value}\n")
    out.write(f"Number of Translated Addresses = {vmm.total}\n")
    out.write(f"Page Faults = {vmm.page_faults}\n")
    out.write(f"Page Fault Rate = {vmm.page_fault_rate:.3f}\n")
    out.write(f"TLB Hits = {vmm.tlb_hits}\n")
    out.write(f"TLB Hit Rate = {vmm.tlb_hit_rate:.3f}\n")
    if args.out:
        out.close()


if __name__ == "__main__":
    main()
