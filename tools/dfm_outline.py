"""Esboco estrutural de um DFM texto: arvore de componentes visuais com
classe, alinhamento, geometria, cores e fonte (referencia para recriar a tela).

Uso: python3 -I dfm_outline.py <arquivo.dfm> [profundidade_max]
"""
import re
import sys

OBJ = re.compile(r'^(\s*)(?:object|inherited|inline) (?:(\w+): )?(\w+)')
PROP = re.compile(r'^\s*([\w.]+) = (.*)$')
NAO_VISUAIS = ('TDataSource', 'TFDMemTable', 'TImageList', 'TActionList', 'TAction', 'TTimer', 'TSaveDialog', 'TOpenDialog',
               'TPopupMenu', 'TMainMenu', 'TApplicationEvents', 'TVirtualImageList', 'TImageCollection')
CHAVES = ['Align', 'Left', 'Top', 'Width', 'Height', 'Caption', 'Color', 'Font.Color', 'Font.Height', 'Font.Name', 'Font.Style',
          'BevelOuter', 'BorderStyle', 'Flat', 'DataField', 'Text', 'Hint', 'Visible', 'Alignment', 'Layout', 'ParentColor', 'TabWidth']


def cor(v):
    if re.fullmatch(r'-?\d+', v):
        n = int(v)
        if n >= 0:
            return '#%02x%02x%02x' % (n & 0xFF, (n >> 8) & 0xFF, (n >> 16) & 0xFF)
    return v


def main():
    path = sys.argv[1]
    maxd = int(sys.argv[2]) if len(sys.argv) > 2 else 99
    stack, nos = [], []
    for line in open(path, encoding='latin-1'):
        m = OBJ.match(line)
        if m:
            d = len(m.group(1)) // 2
            no = {'d': d, 'nome': m.group(2), 'cls': m.group(3), 'p': {}}
            nos.append(no)
            stack = stack[:d] + [no]
            continue
        p = PROP.match(line)
        if p and stack and line.startswith('  ' * (stack[-1]['d'] + 1)) and not line.startswith('  ' * (stack[-1]['d'] + 2)):
            stack[-1]['p'][p.group(1)] = p.group(2)
    esconder = None
    for no in nos:
        if esconder is not None and no['d'] > esconder:
            continue
        esconder = None
        if no['cls'] in NAO_VISUAIS or no['cls'].endswith('Field') or no['cls'] == 'TMenuItem':
            esconder = no['d']
            continue
        if no['d'] > maxd:
            continue
        pr = no['p']
        attrs = []
        for k in CHAVES:
            if k in pr:
                v = pr[k]
                if 'Color' in k:
                    v = cor(v)
                attrs.append(f'{k}={v}')
        print('  ' * no['d'] + f"{no['nome']}:{no['cls']} " + ' '.join(attrs))


if __name__ == '__main__':
    main()
