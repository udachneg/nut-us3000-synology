"""Build-time only: emit immutable C bytes from a fixed local source list.

No runtime path/env option, no third-party modules. stdout is a generated header;
the build/test harness owns its destination. No source or workspace modification.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
FILES = ('hook-policy.sh', 'queue-reader.sh', 'queue-parser.sh', 'ram-manager.sh',
         'ram-lifecycle.sh', 'ram-stage.sh', 'ram-start.sh', 'ram-ready.sh',
         'nutus3000_ram.slice.in', 'nut-us3000-ram-driver.service.in',
         'nut-us3000-ram-server.service.in')


def main():
    if len(sys.argv) != 1:
        return 64
    payload = [('identity', b'NUTRAM_CONTROL_1\n')]
    for name in FILES:
        path = HERE / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('payload must be a regular source file: ' + name)
        data = path.read_bytes()
        if not data or len(data) > 262144:
            raise ValueError('invalid payload size: ' + name)
        payload.append((name, data))
    print('/* Generated from fixed source files; do not edit. */')
    print('struct nutram_blob { const char *name; const unsigned char *bytes; size_t length; };')
    for i, (_, data) in enumerate(payload):
        print(f'static const unsigned char nutram_blob_{i}[] = {{')
        for offset in range(0, len(data), 24):
            print(','.join(str(b) for b in data[offset:offset + 24]) + ',')
        print('};')
    print('static const struct nutram_blob nutram_payload[] = {')
    for i, (name, _) in enumerate(payload):
        print(f'{{"{name}", nutram_blob_{i}, sizeof(nutram_blob_{i})}},')
    print('};')
    return 0


if __name__ == '__main__':
    sys.exit(main())
