"""Extrai formularios Delphi (DFM binario TPF0) dos recursos RCDATA de um PE
usando as posicoes reportadas pelo `rea inspect-pe-resources`, e converte
para o formato texto do DFM.

Uso: python3 -I dfm_extract.py <pe-resources.json> <exe> <saida_dir>
"""
import json
import os
import struct
import sys


class Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def take(self, n):
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def sstr(self):
        n = self.u8()
        return self.take(n).decode('latin-1')

    def i(self, fmt):
        size = struct.calcsize(fmt)
        return struct.unpack('<' + fmt, self.take(size))[0]


def quote(s):
    out, plain = [], False
    for ch in s:
        if 32 <= ord(ch) < 127 and ch != "'":
            if not plain:
                out.append("'")
                plain = True
            out.append(ch)
        else:
            if plain:
                out.append("'")
                plain = False
            if ch == "'":
                out.append("''''")
            else:
                out.append('#%d' % ord(ch))
    if plain:
        out.append("'")
    return ''.join(out) or "''"


def read_value(r, ind):
    t = r.u8()
    if t == 0:
        return 'nil'
    if t == 1:  # list
        items = []
        while r.d[r.p] != 0:
            items.append(read_value(r, ind + 2))
        r.u8()
        return '(' + ' '.join(items) + ')'
    if t == 2:
        return str(r.i('b'))
    if t == 3:
        return str(r.i('h'))
    if t == 4:
        return str(r.i('i'))
    if t == 5:  # extended
        raw = r.take(10)
        mant = int.from_bytes(raw[:8], 'little')
        se = int.from_bytes(raw[8:], 'little')
        exp = (se & 0x7FFF) - 16383
        val = mant / (1 << 63) * (2.0 ** exp) if mant else 0.0
        return repr(-val if se & 0x8000 else val)
    if t in (6, 7):  # string / ident
        return quote(r.sstr()) if t == 6 else r.sstr()
    if t == 8:
        return 'False'
    if t == 9:
        return 'True'
    if t == 10:  # binary
        n = r.i('I')
        return '{%s}' % r.take(n).hex().upper()[:64] + ('...' if n > 32 else '')
    if t == 11:  # set
        items = []
        while True:
            s = r.sstr()
            if not s:
                break
            items.append(s)
        return '[' + ', '.join(items) + ']'
    if t == 12:  # lstring
        n = r.i('I')
        return quote(r.take(n).decode('latin-1'))
    if t == 13:
        return 'nil'
    if t == 14:  # collection
        parts = ['<']
        while r.d[r.p] != 0:
            if r.d[r.p] in (2, 3, 4):
                read_value(r, ind)
            r.u8()  # vaList que abre cada item
            parts.append(' ' * (ind + 2) + 'item')
            while True:
                name = r.sstr()
                if not name:
                    break
                parts.append(' ' * (ind + 4) + name + ' = ' + read_value(r, ind + 4))
            parts.append(' ' * (ind + 2) + 'end')
        r.u8()
        return '\n'.join(parts) + '>'
    if t == 15:
        return repr(r.i('f'))
    if t == 16:
        return str(r.i('q') / 10000)
    if t == 17:
        return repr(r.i('d'))
    if t == 18:  # wstring
        n = r.i('I')
        return quote(r.take(n * 2).decode('utf-16le'))
    if t == 19:
        return str(r.i('q'))
    if t == 20:  # utf8 string
        n = r.i('I')
        return quote(r.take(n).decode('utf-8', 'replace'))
    raise ValueError('tipo desconhecido %d em %d' % (t, r.p))


def read_object(r, ind, out):
    flags = 0
    if r.d[r.p] & 0xF0 == 0xF0:
        flags = r.u8() & 0x0F
        if flags & 2:
            read_value(r, ind)
    cls = r.sstr()
    name = r.sstr()
    kw = 'inherited' if flags & 1 else ('inline' if flags & 4 else 'object')
    out.append(' ' * ind + '%s %s%s' % (kw, name + ': ' if name else '', cls))
    while True:
        prop = r.sstr()
        if not prop:
            break
        out.append(' ' * (ind + 2) + prop + ' = ' + read_value(r, ind + 2))
    while r.d[r.p] != 0:
        read_object(r, ind + 2, out)
    r.u8()
    out.append(' ' * ind + 'end')


def main():
    res_json, exe, outdir = sys.argv[1:4]
    os.makedirs(outdir, exist_ok=True)
    resources = json.load(open(res_json))['normalized_result']['resources']
    data = open(exe, 'rb').read()
    count = 0
    for res in resources:
        if res['type'].get('id') != 10:
            continue
        name = res['name'].get('name') or str(res['name'].get('id'))
        loc = res['payload']['location']
        blob = data[loc['offset']:loc['offset'] + loc['bytes']]
        if not blob.startswith(b'TPF0'):
            with open(os.path.join(outdir, 'rcdata_' + name + '.bin'), 'wb') as f:
                f.write(blob)
            continue
        r = Reader(blob)
        r.p = 4
        out = []
        try:
            read_object(r, 0, out)
        except Exception as e:  # mantem o que foi lido
            out.append('// ERRO DE PARSE: %s' % e)
        with open(os.path.join(outdir, name + '.dfm'), 'w') as f:
            f.write('\n'.join(out) + '\n')
        count += 1
    print('formularios extraidos:', count)


if __name__ == '__main__':
    main()
