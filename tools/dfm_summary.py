"""Resume os DFMs extraidos: esquema das tabelas (TFDMemTable/campos) e
textos visiveis por tela (Caption, Hint, itens de menu, colunas de grid).

Uso: python3 -I dfm_summary.py <forms_dir> <saida_dir>
"""
import json
import os
import re
import sys

OBJ = re.compile(r'^(\s*)(?:object|inherited|inline) (?:(\w+): )?(\w+)')
PROP = re.compile(r'^\s*([\w.]+) = (.*)$')
SKIP_FORMS = ('TQR', 'TTEE', 'TBRUSH', 'TPEN', 'TSEARCH', 'TLOGINDIALOG', 'TPASSWORDDIALOG')


def decode(v):
    """Converte literal Delphi ('abc'#231'def') em texto."""
    out, i = [], 0
    while i < len(v):
        c = v[i]
        if c == "'":
            j = i + 1
            while j < len(v):
                if v[j] == "'" and v[j + 1:j + 2] == "'":
                    out.append("'")
                    j += 2
                    continue
                if v[j] == "'":
                    break
                out.append(v[j])
                j += 1
            i = j + 1
        elif c == '#':
            m = re.match(r'#(\d+)', v[i:])
            out.append(chr(int(m.group(1))))
            i += len(m.group(0))
        else:
            return v
    return ''.join(out)


def parse(path):
    root, stack = None, []
    for line in open(path, encoding='latin-1'):
        line = line.rstrip('\n')
        m = OBJ.match(line)
        if m:
            node = {'name': m.group(2), 'cls': m.group(3), 'props': {}, 'children': []}
            depth = len(m.group(1))
            while stack and stack[-1][0] >= depth:
                stack.pop()
            if stack:
                stack[-1][1]['children'].append(node)
            else:
                root = node
            stack.append((depth, node))
            continue
        if line.strip() == 'end':
            continue
        p = PROP.match(line)
        if p and stack:
            stack[-1][1]['props'][p.group(1)] = p.group(2)
    return root


def walk(node):
    yield node
    for c in node['children']:
        yield from walk(c)


def main():
    src, dst = sys.argv[1:3]
    schema, screens = {}, {}
    for fn in sorted(os.listdir(src)):
        if not fn.endswith('.dfm') or fn.startswith(SKIP_FORMS):
            continue
        root = parse(os.path.join(src, fn))
        texts, events = [], set()
        for n in walk(root):
            pr = n['props']
            if n['cls'] in ('TFDMemTable', 'TClientDataSet', 'TFDQuery'):
                fields = []
                for f in n['children']:
                    if f['cls'].endswith('Field'):
                        fields.append({
                            'name': decode(f['props'].get('FieldName', "''")),
                            'type': f['cls'],
                            'size': f['props'].get('Size'),
                            'label': decode(f['props'].get('DisplayLabel', "''")) or None,
                        })
                if fields:
                    schema.setdefault(n['name'], {'form': fn, 'fields': fields})
            for key in ('Caption', 'Hint', 'TextHint', 'Title.Caption', 'Text'):
                if key in pr:
                    t = decode(pr[key]).strip()
                    if t:
                        texts.append('%s.%s [%s]: %s' % (n['name'], key, n['cls'], t))
            for k, v in pr.items():
                if k.startswith('On'):
                    events.add('%s.%s=%s' % (n['name'], k, v))
            for k, v in pr.items():
                if k in ('Columns', 'Items') and 'Title.Caption' in v:
                    for cap in re.findall(r'Title\.Caption = (.*)', v):
                        texts.append('%s.coluna: %s' % (n['name'], decode(cap)))
                    for fld in re.findall(r'FieldName = (.*)', v):
                        texts.append('%s.campo: %s' % (n['name'], decode(fld)))
        screens[fn[:-4]] = {
            'caption': decode(root['props'].get('Caption', "''")),
            'texts': texts,
            'events': sorted(events),
        }
    os.makedirs(dst, exist_ok=True)
    json.dump(schema, open(os.path.join(dst, 'schema.json'), 'w'), indent=1, ensure_ascii=False)
    json.dump(screens, open(os.path.join(dst, 'screens.json'), 'w'), indent=1, ensure_ascii=False)
    with open(os.path.join(dst, 'screens.txt'), 'w') as f:
        for name, s in screens.items():
            f.write('=== %s — %s\n' % (name, s['caption']))
            for t in s['texts']:
                f.write('  ' + t + '\n')
    print('tabelas:', len(schema), 'telas:', len(screens))


if __name__ == '__main__':
    main()
