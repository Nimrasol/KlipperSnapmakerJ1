#!/usr/bin/env python3
# Build the icon set of the snapmaker-j1 KlipperScreen theme
#
# Copyright (C) 2026  Nimrasol
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import os, re, shutil, sys

# The KlipperScreen material-dark icons recolored to the grey levels and
# the orange of the stock J1 display
COLORS = {
    'e2e2e2': 'c4c5cc', 'eeeeee': 'c4c5cc', 'e8eaed': 'c4c5cc',
    'd1d1d1': 'c4c5cc', 'ffffff': 'f7f8fa', 'bebebe': '9b9ca6',
    '505050': '595a66', '666666': '737480',
    'b12f35': 'fc5244', 'f14f4f': 'fc5244', '6e0b30': 'f56a00',
}
# The J1 moves the bed on Z: Z- lifts it towards the nozzles, Z+ lowers
# it, so the Z buttons (move, fine tuning) show the direction of the bed
SAME_AS = {'z-closer.svg': 'arrow-up.svg', 'z-farther.svg': 'arrow-down.svg'}


def recolor(text):
    def repl(m):
        color = m.group(1).lower()
        if len(color) == 3:
            color = ''.join(c * 2 for c in color)
        return '#' + COLORS.get(color, color)
    return re.sub(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b', repl, text)


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: make_icons.py <KlipperScreen material-dark images>"
                 " <output directory>")
    src, dest = sys.argv[1:]
    os.makedirs(dest, exist_ok=True)
    for name in sorted(os.listdir(src)):
        path = os.path.join(src, SAME_AS.get(name, name))
        if name.endswith('.svg'):
            with open(path, encoding='utf-8') as f:
                text = f.read()
            with open(os.path.join(dest, name), 'w', encoding='utf-8') as f:
                f.write(recolor(text))
        elif os.path.isfile(path):
            shutil.copy(path, dest)


if __name__ == '__main__':
    main()
