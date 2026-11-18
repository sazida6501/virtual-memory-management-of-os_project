"""Generate sample BACKING_STORE.bin and addresses.txt for testing.

If you were given the official BACKING_STORE.bin / addresses.txt by your
instructor, use those instead; this is only so you can run the project now.
"""
import random

random.seed(42)

# 65,536 random bytes
with open("BACKING_STORE.bin", "wb") as f:
    f.write(bytes(random.randrange(256) for _ in range(65536)))

# 1000 addresses with some locality (so the TLB gets hits)
addrs = []
hot = [random.randrange(256) for _ in range(12)]
for _ in range(1000):
    page = random.choice(hot) if random.random() < 0.6 else random.randrange(256)
    addrs.append(page * 256 + random.randrange(256))

with open("addresses.txt", "w") as f:
    f.write("\n".join(map(str, addrs)) + "\n")

print("Wrote BACKING_STORE.bin (65536 bytes) and addresses.txt (1000 addresses)")
