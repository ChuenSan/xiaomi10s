#!/usr/bin/env python3
"""Fail unless ELF is aarch64 ET_EXEC with e_entry inside an RX PT_LOAD."""
import struct
import sys

PF_X, PF_W, PF_R = 1, 2, 4
PT_LOAD = 1


def main(path: str) -> None:
	data = open(path, "rb").read()
	if data[:4] != b"\x7fELF":
		raise SystemExit(f"not ELF: {path}")
	e_type, e_machine = struct.unpack_from("<HH", data, 16)
	if e_type != 2:
		raise SystemExit(f"e_type={e_type} want ET_EXEC(2)")
	if e_machine != 183:
		raise SystemExit(f"e_machine={e_machine} want EM_AARCH64(183)")
	e_entry = struct.unpack_from("<Q", data, 24)[0]
	e_phoff = struct.unpack_from("<Q", data, 32)[0]
	e_phentsize, e_phnum = struct.unpack_from("<HH", data, 54)
	rx = False
	for i in range(e_phnum):
		off = e_phoff + i * e_phentsize
		p_type, p_flags = struct.unpack_from("<II", data, off)
		_p_offset, p_vaddr, _p_paddr, _fsz, p_memsz, _al = struct.unpack_from(
			"<QQQQQQ", data, off + 8
		)
		if p_type != PT_LOAD:
			continue
		if (p_flags & PF_X) and p_vaddr <= e_entry < p_vaddr + p_memsz:
			rx = True
			print(
				f"OK {path} entry={hex(e_entry)} "
				f"pt_load={hex(p_vaddr)}+{hex(p_memsz)} flags={p_flags}"
			)
	if e_entry < 0x10000:
		raise SystemExit(f"e_entry {hex(e_entry)} too low")
	if not rx:
		raise SystemExit(f"e_entry {hex(e_entry)} not inside RX PT_LOAD")


if __name__ == "__main__":
	main(sys.argv[1])
