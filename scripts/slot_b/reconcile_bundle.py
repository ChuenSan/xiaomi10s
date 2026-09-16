#!/usr/bin/env python3
"""Reconcile the single known objcopy-rewritten GHA ELF export, without rebuilding."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('GitHub Actions required')

ORIGINAL = {
    'Image': '43fb1c9128bdf37a2a77eb88cfff234381340b098ebf1aea1eabb2741180cebb',
    'vmlinux': '42c04b8dc386b2f378e20b2b67bc635e11c681e0e1ba7a3bbe8a076af27ca2ca',
    'System.map': 'e3ed0234692c5dc80188996730bb13f2303fd2ecb573e303134df02b7f61b3ea',
    'kernel.config': 'f947a2e44e60f5818e5e63ed3192d5eeca652b45665c6f4b13b3796cea359bfa',
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def need(value, reason):
    if not value:
        raise SystemExit(reason)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    m = json.loads((a.input / 'bundle.json').read_text())
    need(m['run_id'] == '35036419486', 'NOT_THE_KNOWN_EXPORT')
    need(m['source_commit'] == 'ba870dbdc094bdee08c67e465f229e67c36ac0b6', 'WRONG_SOURCE')
    need(m['files'] == ORIGINAL, 'ORIGINAL_MANIFEST_MISMATCH')
    for name in ('Image', 'System.map', 'kernel.config'):
        need(sha(a.input / name) == ORIGINAL[name], 'NON_ELF_BUNDLE_CHANGE:' + name)
    elf = a.input / 'vmlinux'
    archived_sha = sha(elf)
    work = a.output.with_name(a.output.name + '-proof')
    work.mkdir(parents=True, exist_ok=False)
    reproduced = work / 'Image.reproduced'
    # Exact arch/arm64/boot/Makefile recipe; explicit output protects the ELF.
    subprocess.run(['llvm-objcopy-18', '-O', 'binary', '-R', '.note', '-R', '.note.gnu.build-id',
                    '-R', '.comment', '-S', str(elf), str(reproduced)], check=True)
    need(sha(reproduced) == ORIGINAL['Image'], 'REPRODUCED_IMAGE_MISMATCH')
    nm = subprocess.run(['llvm-nm-18', '-n', str(elf)], check=True, capture_output=True, text=True).stdout
    actual = {tuple(line.split()) for line in nm.splitlines()}
    expected = {tuple(line.split()) for line in (a.input / 'System.map').read_text().splitlines()}
    need(len(expected) > 1000 and expected <= actual, 'SYSTEM_MAP_SYMBOLS_CHANGED')
    need(sha(elf) == archived_sha, 'RECONCILIATION_MUTATED_ELF')
    a.output.mkdir(parents=True, exist_ok=False)
    for name in ORIGINAL:
        shutil.copyfile(a.input / name, a.output / name)
    m['files']['vmlinux'] = archived_sha
    m['elf_export_reconciliation'] = {
        'original_vmlinux_sha256': ORIGINAL['vmlinux'], 'archived_vmlinux_sha256': archived_sha,
        'image_reproduction': 'EXACT_MATCH', 'system_map_entries_matched': len(expected),
        'cause': 'llvm-objcopy --dump-section without output rewrote ELF container in place',
        'rebuild': False, 'run_id': os.environ['GITHUB_RUN_ID'], 'source_commit': os.environ['GITHUB_SHA'],
    }
    (a.output / 'bundle.json').write_text(json.dumps(m, indent=2) + '\n')
    print(json.dumps(m['elf_export_reconciliation'], indent=2))
    print('BUNDLE_EXECUTABLE_AND_SYMBOL_IDENTITIES=EXACT_MATCH')
    print('KERNEL_REBUILD=NO')


if __name__ == '__main__':
    main()
