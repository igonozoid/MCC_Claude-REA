"""Relatorios no estilo QuickReport do original (FRel1/FRel2 + FPrint): faixas de cabecalho,
titulo com logomarca, colunas, total e rodape coloridas conforme "Cor dos relatorios".
Tambem: parametros (FPeriodo), relatorio analitico (FAnalise), graficos (FChart) e
recibo / duplicata (FRecibo)."""
import csv
import html
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, QMarginsF, QRectF, QSettings, QSizeF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetricsF, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog, QPrintPreviewWidget
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QTabWidget, QVBoxLayout, QWidget, QCalendarWidget)

from ..core import finance as fin
from . import estilo as E
from .base import (BitBtn, Campo, CampoData, CampoValor, ComboDados, ComboLookup, FormBase, Grade, RadioGrupo, SpeedButton, icone,
                   msg_aviso, msg_info, rotulo)
from .graficos import Grafico
from .lancamentos import _bt_cancela, _bt_confirma, _por, _rot


def _fmt(v, fmt):
    if v is None or v == '':
        return ''
    if fmt == 'data':
        return fin.br(str(v))
    if fmt == 'moeda':
        return fin.moeda(v, simbolo=False)
    if fmt in ('int',):
        return str(int(round(float(v))))
    if fmt == 'num':
        return f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return str(v)


def _endereco(emp):
    partes = [emp.get('endereco'), emp.get('bairro'), ' - '.join(x for x in (emp.get('cidade'), emp.get('uf')) if x),
              emp.get('cep') and f"CEP {emp['cep']}"]
    linha2 = '   '.join(x for x in (emp.get('telefone') and f"Fone: {emp['telefone']}", emp.get('email'),
                                     emp.get('documento') and (('CPF: ' if emp.get('pessoa') == 'F' else 'CNPJ: ') + emp['documento'])) if x)
    return ', '.join(x for x in partes if x), linha2


# ---------- motor de impressao ----------

class PintorRelatorio:
    """Desenha um resultado de relatorio (fin.tabela) em paginas, como as faixas do QuickReport."""

    def __init__(self, rel, empresa, logo=None, cor='#d4d0c8', imagem=None):
        self.rel, self.emp, self.cor = rel, empresa, QColor(cor)
        self.logo = QImage.fromData(logo) if logo else None
        self.imagem = imagem  # QImage de grafico, impresso antes da tabela
        self.agora = datetime.now()
        self.paisagem = self._precisa_paisagem()

    def _precisa_paisagem(self):
        larg = sum(self._larg_desejada(c) for c in self.rel['colunas'])
        return larg > 190  # em "unidades de caractere" — retrato comporta ~190

    def _larg_desejada(self, c):
        maior = len(c['rotulo'])
        for l in self.rel['linhas'][:400]:
            if l.get('_tipo') == 'grupo':
                continue
            maior = max(maior, len(_fmt(l.get(c['campo']), c['fmt'])))
        lim = 34 if c['fmt'] not in ('moeda', 'data', 'int', 'num') else 16
        return max(5, min(maior, lim)) + 2

    def configurar(self, printer):
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageOrientation(QPageLayout.Landscape if self.paisagem else QPageLayout.Portrait)
        printer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter)

    def pintar(self, printer):
        p = QPainter(printer)
        if not p.isActive():
            return
        area = printer.pageLayout().paintRectPixels(printer.resolution())
        W, H = area.width(), area.height()
        esc = printer.resolution() / 96.0  # tudo em "pixels de tela" e escalado
        p.scale(esc, esc)
        W, H = W / esc, H / esc
        f_norm = QFont('Arial')
        f_norm.setPixelSize(11)
        f_bold = QFont(f_norm)
        f_bold.setBold(True)
        fm = QFontMetricsF(f_norm)
        cols = self.rel['colunas']
        desej = [self._larg_desejada(c) for c in cols]
        total_d = sum(desej)
        largs = [W * d / total_d for d in desej]
        alt_linha = 17
        pagina = [1]
        linhas = self.rel['linhas']
        n_pag_est = None

        def faixa(y, h, cor=True):
            if cor:
                p.fillRect(QRectF(0, y, W, h), self.cor)
            return y + h

        def cabecalho_pagina():
            y = 0
            faixa(y, 22)
            p.setFont(f_norm)
            p.setPen(Qt.black)
            p.drawText(QRectF(6, y, 300, 22), Qt.AlignVCenter, f"Data: {self.agora.strftime('%d/%m/%Y')}      Hora: {self.agora.strftime('%H:%M')}")
            p.drawText(QRectF(W - 306, y, 300, 22), Qt.AlignVCenter | Qt.AlignRight, 'MCC — controle financeiro')
            y += 26
            if pagina[0] == 1:
                topo = y
                lx = 0
                if self.logo and not self.logo.isNull():
                    img = self.logo.scaled(180, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    p.drawImage(QRectF(0, topo, img.width(), img.height()), img)
                    lx = img.width() + 10
                fn = QFont('Arial')
                fn.setPixelSize(18)
                fn.setUnderline(True)
                p.setFont(fn)
                p.drawText(QRectF(lx, topo, W - lx, 24), Qt.AlignHCenter | Qt.AlignVCenter, self.emp.get('nome', ''))
                end1, end2 = _endereco(self.emp)
                p.setFont(f_norm)
                p.drawText(QRectF(lx, topo + 24, W - lx, 15), Qt.AlignHCenter, end1)
                p.drawText(QRectF(lx, topo + 38, W - lx, 15), Qt.AlignHCenter, end2)
                ft = QFont('Arial')
                ft.setPixelSize(16)
                p.setFont(ft)
                y = max(topo + 58, topo + (self.logo.scaled(180, 80, Qt.KeepAspectRatio).height() if self.logo and not self.logo.isNull() else 0) + 4)
                p.drawText(QRectF(0, y, W, 22), Qt.AlignHCenter | Qt.AlignVCenter, self.rel['titulo'].upper())
                y += 22
                fp = QFont('Arial')
                fp.setPixelSize(12)
                p.setFont(fp)
                p.drawText(QRectF(0, y, W, 18), Qt.AlignHCenter | Qt.AlignVCenter, self.rel.get('subtitulo') or '')
                y += 24
                if self.imagem is not None and not self.imagem.isNull():
                    img = self.imagem.scaled(int(W), int(H * 0.45), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    p.drawImage(QRectF((W - img.width()) / 2, y, img.width(), img.height()), img)
                    y += img.height() + 8
            # cabecalho das colunas
            faixa(y, 22)
            p.setFont(f_bold)
            x = 0
            for c, w in zip(cols, largs):
                al = Qt.AlignRight if c['fmt'] in ('moeda', 'int', 'num') else Qt.AlignLeft
                p.drawText(QRectF(x + 3, y, w - 6, 22), al | Qt.AlignVCenter, fm.elidedText(c['rotulo'], Qt.ElideRight, w - 6))
                x += w
            return y + 24

        def rodape():
            y = H - 22
            faixa(y, 22)
            p.setFont(f_norm)
            p.setPen(Qt.black)
            p.drawText(QRectF(6, y, 200, 22), Qt.AlignVCenter, f'Página {pagina[0]}')
            p.drawText(QRectF(W - 406, y, 400, 22), Qt.AlignVCenter | Qt.AlignRight, self.emp.get('nome', ''))

        y = cabecalho_pagina()
        limite = H - 26
        zebra = False
        for l in linhas:
            if y + alt_linha > limite - (alt_linha if l is linhas[-1] else 0):
                rodape()
                printer.newPage()
                pagina[0] += 1
                y = cabecalho_pagina()
            if l.get('_tipo') == 'grupo':
                p.fillRect(QRectF(0, y, W, alt_linha), QColor('#e8e8e8'))
                p.setFont(f_bold)
                p.setPen(Qt.black)
                p.drawText(QRectF(4 + 14 * l.get('_nivel', 0), y, W - 8, alt_linha), Qt.AlignVCenter, l.get('data_mov', ''))
                y += alt_linha
                continue
            sub = l.get('_tipo') == 'subtotal'
            if zebra and not sub:
                p.fillRect(QRectF(0, y, W, alt_linha), QColor('#f6f6f6'))
            zebra = not zebra
            p.setFont(f_bold if sub else f_norm)
            x = 0
            for c, w in zip(cols, largs):
                v = l.get(c['campo'])
                t = _fmt(v, c['fmt'])
                al = Qt.AlignRight if c['fmt'] in ('moeda', 'int', 'num') else Qt.AlignLeft
                p.setPen(QColor('#b00000') if c['fmt'] == 'moeda' and isinstance(v, (int, float)) and v < 0 else Qt.black)
                p.drawText(QRectF(x + 3, y, w - 6, alt_linha), al | Qt.AlignVCenter, fm.elidedText(t, Qt.ElideRight, w - 6))
                x += w
            if sub:
                p.setPen(QPen(QColor('#808080'), 0.8))
                p.drawLine(0, y + alt_linha, W, y + alt_linha)
            y += alt_linha
        if not linhas:
            p.setFont(f_norm)
            p.drawText(QRectF(0, y + 6, W, 20), Qt.AlignHCenter, 'Nenhum registro para os parâmetros informados.')
            y += 30
        tot = self.rel.get('totais') or {}
        if tot:
            if y + 26 > limite:
                rodape()
                printer.newPage()
                pagina[0] += 1
                y = cabecalho_pagina()
            faixa(y + 2, 24)
            p.setFont(f_bold)
            p.setPen(Qt.black)
            x = 0
            for i, (c, w) in enumerate(zip(cols, largs)):
                if c['campo'] in tot:
                    p.drawText(QRectF(x + 3, y + 2, w - 6, 24), Qt.AlignRight | Qt.AlignVCenter,
                               _fmt(tot[c['campo']], 'num' if c['fmt'] == 'int' else c['fmt']) if c['fmt'] != 'int' else str(int(tot[c['campo']])))
                elif i == 0:
                    p.drawText(QRectF(x + 3, y + 2, w * 2, 24), Qt.AlignVCenter, f"Total ({sum(1 for l in linhas if not l.get('_tipo'))} registros)")
                x += w
        rodape()
        p.end()


# ---------- FPrint (preview no estilo do original) ----------

class JanelaPreview(QDialog):
    def __init__(self, parent, pintor, titulo, rel=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        from .base import caber_na_tela
        caber_na_tela(self, 1000, 720)
        self.pintor, self.rel = pintor, rel
        self.printer = QPrinter(QPrinter.HighResolution)
        pintor.configurar(self.printer)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        barra = QFrame()
        barra.setFixedHeight(66)
        h = QHBoxLayout(barra)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(3)
        self.preview = QPrintPreviewWidget(self.printer)
        self.preview.paintRequested.connect(pintor.pintar)
        for texto, ic, fn in (('&Primeira', 'fa6s.backward-step', lambda: self.preview.setCurrentPage(1)),
                              ('&Anterior', 'fa6s.caret-left', lambda: self.preview.setCurrentPage(self.preview.currentPage() - 1)),
                              ('P&róxima', 'fa6s.caret-right', lambda: self.preview.setCurrentPage(self.preview.currentPage() + 1)),
                              ('&Última', 'fa6s.forward-step', lambda: self.preview.setCurrentPage(self.preview.pageCount())),
                              ('&Imprimir', 'fa6s.print', self.imprimir), ('&Exportar', 'fa6s.file-export', self.exportar),
                              ('&Opções', 'fa6s.magnifying-glass-plus', self.opcoes), ('&Fechar', 'fa6s.door-open', self.reject)):
            b = SpeedButton(texto, icone(ic, '#1f3f73'), glyph_top=True, tam_icone=22)
            b.setFixedSize(66, 58)
            b.clicked.connect(fn)
            if texto == '&Exportar':
                self.bt_exp = b
            h.addWidget(b)
        h.addStretch()
        v.addWidget(barra)
        v.addWidget(self.preview, 1)
        self.lb_pag = rotulo('', px=12, nome='Segoe UI')
        self.lb_pag.setAlignment(Qt.AlignRight)
        self.lb_pag.setContentsMargins(0, 2, 10, 2)
        v.addWidget(self.lb_pag)
        self.preview.previewChanged.connect(self._pag)
        self.preview.fitToWidth()

    def _pag(self):
        self.lb_pag.setText(f'Página {self.preview.currentPage()} de {self.preview.pageCount()}')

    def imprimir(self):
        dlg = QPrintDialog(self.printer, self)
        if dlg.exec() == QDialog.Accepted:
            self.pintor.pintar(self.printer)

    def opcoes(self):
        m = QMenu(self)
        m.addAction('Ajustar à largura', self.preview.fitToWidth)
        m.addAction('Página inteira', self.preview.fitInView)
        m.addAction('Aumentar zoom', self.preview.zoomIn)
        m.addAction('Diminuir zoom', self.preview.zoomOut)
        m.addSeparator()
        m.addAction('Retrato', lambda: (self.preview.setPortraitOrientation()))
        m.addAction('Paisagem', lambda: (self.preview.setLandscapeOrientation()))
        m.exec(self.cursor().pos())

    def exportar(self):
        m = QMenu(self)
        m.addAction(icone('fa6s.file-pdf'), 'Arquivo PDF', lambda: exportar_pdf(self, self.pintor, self.windowTitle()))
        if self.rel:
            m.addAction(icone('fa6s.file-csv'), 'Planilha CSV (Excel/LibreOffice)', lambda: exportar_csv(self, self.rel))
            m.addAction(icone('fa6s.file-code'), 'Página HTML', lambda: exportar_html(self, self.rel, self.pintor.emp))
        m.exec(self.cursor().pos())


def _nome_arquivo(titulo):
    return ''.join(c for c in titulo if c.isalnum() or c in ' -_').strip().replace(' ', '_')[:60] or 'relatorio'


def exportar_pdf(parent, pintor, titulo, abrir=True):
    caminho, _ = QFileDialog.getSaveFileName(parent, 'Gerar arquivo PDF', str(Path.home() / f'{_nome_arquivo(titulo)}.pdf'), 'PDF (*.pdf)')
    if not caminho:
        return None
    pr = QPrinter(QPrinter.HighResolution)
    pintor.configurar(pr)
    pr.setOutputFormat(QPrinter.PdfFormat)
    pr.setOutputFileName(caminho)
    pintor.pintar(pr)
    if abrir:
        QDesktopServices.openUrl(QUrl.fromLocalFile(caminho))
    return caminho


def exportar_csv(parent, rel):
    caminho, _ = QFileDialog.getSaveFileName(parent, 'Exportar CSV', str(Path.home() / f"{_nome_arquivo(rel['titulo'])}.csv"), 'CSV (*.csv)')
    if not caminho:
        return
    with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow([c['rotulo'] for c in rel['colunas']])
        for l in rel['linhas']:
            if l.get('_tipo') == 'grupo':
                w.writerow([l.get('data_mov')])
                continue
            w.writerow([(f'{v:.2f}'.replace('.', ',') if isinstance(v, float) else _fmt(v, c['fmt']) if c['fmt'] == 'data' else ('' if v is None else v))
                        for c in rel['colunas'] for v in [l.get(c['campo'])]])
    msg_info(parent, f'Arquivo gravado: {caminho}')


def html_relatorio(rel, emp, cor):
    num = lambda c: c['fmt'] in ('moeda', 'int', 'num')
    th = ''.join(f"<th style='text-align:{'right' if num(c) else 'left'}'>{html.escape(c['rotulo'])}</th>" for c in rel['colunas'])
    linhas = []
    for l in rel['linhas']:
        if l.get('_tipo') == 'grupo':
            linhas.append(f"<tr class='g'><td colspan='{len(rel['colunas'])}'>{html.escape(str(l.get('data_mov')))}</td></tr>")
            continue
        cls = " class='s'" if l.get('_tipo') else ''
        linhas.append(f'<tr{cls}>' + ''.join(f"<td style='text-align:{'right' if num(c) else 'left'}'>{html.escape(_fmt(l.get(c['campo']), c['fmt']))}</td>"
                                              for c in rel['colunas']) + '</tr>')
    tot = rel.get('totais') or {}
    tf = ''.join(f"<td style='text-align:right'>{html.escape(_fmt(tot[c['campo']], c['fmt']))}</td>" if c['campo'] in tot else
                 ('<td>Total</td>' if i == 0 else '<td></td>') for i, c in enumerate(rel['colunas'])) if tot else ''
    e1, e2 = _endereco(emp)
    return f"""<!doctype html><meta charset='utf-8'><title>{html.escape(rel['titulo'])}</title>
<style>body{{font-family:Arial,sans-serif;font-size:12px;margin:20px}} .faixa{{background:{cor};padding:4px 8px}}
h1{{text-align:center;font-size:18px;text-decoration:underline;margin:8px 0 2px}} h2{{text-align:center;font-size:15px;margin:10px 0 2px}}
p{{text-align:center;margin:0}} table{{width:100%;border-collapse:collapse;margin-top:8px}} th{{background:{cor};padding:4px}}
td{{padding:2px 4px;border-bottom:1px solid #eee}} tr.g td{{background:#e8e8e8;font-weight:bold}} tr.s td{{font-weight:bold}}
tfoot td{{background:{cor};font-weight:bold;padding:4px}}</style>
<div class='faixa'>Data: {datetime.now():%d/%m/%Y} &nbsp; Hora: {datetime.now():%H:%M}</div>
<h1>{html.escape(emp.get('nome', ''))}</h1><p>{html.escape(e1)}</p><p>{html.escape(e2)}</p>
<h2>{html.escape(rel['titulo'].upper())}</h2><p>{html.escape(rel.get('subtitulo') or '')}</p>
<table><thead><tr>{th}</tr></thead><tbody>{''.join(linhas)}</tbody><tfoot><tr>{tf}</tr></tfoot></table>"""


def exportar_html(parent, rel, emp):
    caminho, _ = QFileDialog.getSaveFileName(parent, 'Exportar HTML', str(Path.home() / f"{_nome_arquivo(rel['titulo'])}.html"), 'HTML (*.html)')
    if caminho:
        cor = E.CORES_RELATORIO.get(QSettings('MCC', 'MCC').value('cor_relatorio', 'cinza_claro'), E.CORES_RELATORIO['cinza_claro'])[1]
        Path(caminho).write_text(html_relatorio(rel, emp, cor), encoding='utf-8')
        QDesktopServices.openUrl(QUrl.fromLocalFile(caminho))


# ---------- FPeriodo: escolha do periodo ----------

class FormPeriodo(FormBase):
    """Definir periodo: atalhos (Este ano ... Mes que vem), calendarios e demais parametros do relatorio."""

    def __init__(self, parent, titulo, extras=None, campo_data=False, de=None, ate=None, so_data=False):
        super().__init__(parent, titulo, 825, 470)
        self.extras = extras or []
        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(rotulo('Selecione o período desejado:' if not so_data else 'Selecione a data:', px=15, nome='Arial'))
        topo.addStretch()
        self.cb_campo = ComboDados(px=13, opcoes=[('Filtrar por data de movimento', 'data_mov'), ('Filtrar por data de vencimento ou pagamento', 'vencimento')])
        self.cb_campo.setFixedWidth(331)
        self.cb_campo.setVisible(campo_data)
        topo.addWidget(self.cb_campo)
        v.addLayout(topo)
        hoje = date.today()
        if not so_data:
            atalhos = QHBoxLayout()
            atalhos.setSpacing(3)
            ini_sem = hoje - timedelta(days=(hoje.weekday() + 1) % 7)
            mes_ant_fim = hoje.replace(day=1) - timedelta(days=1)
            prox_mes = (hoje.replace(day=28) + timedelta(days=4)).replace(day=1)
            import calendar
            fim_mes = lambda d: d.replace(day=calendar.monthrange(d.year, d.month)[1])
            for texto, a, b, dica in (('Este ano', date(hoje.year, 1, 1), date(hoje.year, 12, 31), 'Este ano de janeiro a dezembro'),
                                      ('Mês anterior', mes_ant_fim.replace(day=1), mes_ant_fim, 'Mês anterior'),
                                      ('Este mês', hoje.replace(day=1), fim_mes(hoje), 'Mês atual'),
                                      ('Semana passada', ini_sem - timedelta(days=7), ini_sem - timedelta(days=1), 'Semana anterior iniciando de Domingo a Sábado'),
                                      ('Esta semana', ini_sem, ini_sem + timedelta(days=6), 'Semana atual de Domingo a Sábado'),
                                      ('Ontem', hoje - timedelta(days=1), hoje - timedelta(days=1), 'Ontem'), ('Hoje', hoje, hoje, 'Hoje'),
                                      ('Amanhã', hoje + timedelta(days=1), hoje + timedelta(days=1), 'Amanhã'),
                                      ('Semana que vem', ini_sem + timedelta(days=7), ini_sem + timedelta(days=13), 'Próxima semana iniciando de Domingo a Sábado'),
                                      ('Mês que vem', prox_mes, fim_mes(prox_mes), 'Próximo mês')):
                b_ = SpeedButton(texto, dica=dica)
                b_.setStyleSheet('QToolButton { border: 1px solid #adadad; background: #f3f3f3; padding: 4px 6px; }')
                b_.setFixedHeight(30)
                b_.clicked.connect(lambda _=False, a=a, b=b: self._definir(a, b))
                atalhos.addWidget(b_)
            atalhos.addStretch()
            v.addLayout(atalhos)
        cal = QHBoxLayout()
        self.cal_i, self.cal_f = QCalendarWidget(), QCalendarWidget()
        for i, (cw, rot) in enumerate(((self.cal_i, 'Data inicial:' if not so_data else 'Data:'), (self.cal_f, 'Data final:'))):
            col = QVBoxLayout()
            col.addWidget(rotulo(rot, px=15, nome='Arial'))
            cw.setGridVisible(True)
            cw.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
            col.addWidget(cw)
            w = QWidget()
            w.setLayout(col)
            cal.addWidget(w)
            if so_data and i == 1:
                w.hide()
        v.addLayout(cal, 1)
        self.campos_extra = {}
        if self.extras:
            g = QHBoxLayout()
            for chave, rotulo_, widget in self.extras:
                caixa = QVBoxLayout()
                caixa.addWidget(rotulo(rotulo_, px=12, nome='Arial'))
                caixa.addWidget(widget)
                g.addLayout(caixa)
                self.campos_extra[chave] = widget
            g.addStretch()
            v.addLayout(g)
        base = QHBoxLayout()
        base.addStretch()
        bc = BitBtn('&Cancelar', icone('fa6s.xmark', '#b02a2a'))
        bc.setFixedSize(113, 39)
        ba = BitBtn('&Avançar', icone('fa6s.arrow-right', '#1a7f37'))
        ba.setFixedSize(156, 39)
        ba.setDefault(True)
        base.addWidget(bc)
        base.addWidget(ba)
        v.addLayout(base)
        bc.clicked.connect(self.reject)
        ba.clicked.connect(self.accept)
        self._definir(date.fromisoformat(de) if de else date(hoje.year, hoje.month, 1),
                      date.fromisoformat(ate) if ate else hoje)

    def _definir(self, a, b):
        self.cal_i.setSelectedDate(QDate(a.year, a.month, a.day))
        self.cal_f.setSelectedDate(QDate(b.year, b.month, b.day))

    def valores(self):
        d = {'de': self.cal_i.selectedDate().toString('yyyy-MM-dd'), 'ate': self.cal_f.selectedDate().toString('yyyy-MM-dd')}
        if self.cb_campo.isVisible():
            d['campo_data'] = self.cb_campo.valor()
        for k, w in self.campos_extra.items():
            d[k] = w.valor() if hasattr(w, 'valor') else (w.isChecked() if isinstance(w, QCheckBox) else w.currentData())
        return d


# ---------- FAnalise ----------

class FormAnalitico(FormBase):
    def __init__(self, ctrl, ult=None):
        super().__init__(ctrl.j, 'Relatorio Analitico', 640, 520, cor=E.FUNDO_CADASTRO)
        s = ctrl.s
        self.s = s
        u = ult or {}
        hoje = date.today()
        tipos = [(t, d) for t, d in (('&Despesas', 'D'), ('&Receitas', 'R'), ('&Todos', 'T'))
                 if (d == 'T' and s.nivel('despesas') and s.nivel('receitas')) or (d != 'T' and s.nivel_tipo(d))]
        self.rg_tip = RadioGrupo('Analisar', tipos, self, px=12)
        self.rg_tip.setGeometry(15, 10, 300, 48)
        self.rg_tip.definir(u.get('tipo', tipos[0][1]))
        self.rg_sit = RadioGrupo('Com situação igual a', [('&Pago', 'V'), ('&Em aberto', 'P'), ('T&odos', '')], self, px=12)
        self.rg_sit.setGeometry(325, 10, 300, 48)
        self.rg_sit.definir(u.get('situacao', ''))
        g = QGroupBox('Analisar período por', self)
        g.setGeometry(15, 66, 610, 60)
        self.cb_per = _por(ComboDados(px=13, opcoes=[('Data de movimento', 'data_mov'), ('Data de vencimento/Pagamento', 'vencimento')]), g, 10, 24, 230, 26)
        self.cb_per.definir(u.get('campo_data'))
        _rot('entre', g, 255, 29, px=12)
        self.de = _por(CampoData(px=13), g, 290, 24, 130, 26)
        self.de.definir(u.get('de') or f'{hoje.year}-01-01')
        _rot('a', g, 430, 29, px=12)
        self.ate = _por(CampoData(px=13), g, 445, 24, 130, 26)
        self.ate.definir(u.get('ate') or f'{hoje.year}-12-31')
        _rot('Descrição da despesa ou receita', self, 15, 134, px=12)
        self.ed_des = _por(ComboLookup(px=13), self, 15, 151, 300, 26)
        self.ed_des.definir_itens(sorted({x for t in ('D', 'R') if s.nivel_tipo(t) for x in s.itens_descricoes(t)}, key=str.lower))
        self.ed_des.setEditText(u.get('descricao') or '')
        self.ed_des.lineEdit().setPlaceholderText('INDIFERENTE')
        _rot('Nome do cliente ou fornecedor', self, 325, 134, px=12)
        self.ed_pes = _por(ComboLookup(px=13), self, 325, 151, 300, 26)
        self.ed_pes.definir_itens([p['nome'] for p in s.listar('pessoas')])
        self.ed_pes.setEditText(u.get('pessoa') or '')
        self.ed_pes.lineEdit().setPlaceholderText('INDIFERENTE')
        _rot('Da conta', self, 15, 184, px=12)
        self.cb_con = _por(ComboDados(px=13, opcoes=[('INDIFERENTE', None)] + [(c['descricao'], c['id']) for c in s.listar('contas')]), self, 15, 201, 300, 26)
        self.cb_con.definir(u.get('conta_id'))
        _rot('Centro de custo', self, 325, 184, px=12)
        self.cb_cen = _por(ComboDados(px=13, opcoes=[('TODOS', None)] + [(c['nome'], c['id']) for c in s.listar('centros')]), self, 325, 201, 300, 26)
        self.cb_cen.definir(u.get('centro_id'))
        agr = [('(nenhum)', ''), ('Descrição', 'item'), ('Cliente/fornecedor', 'pessoa'), ('Conta', 'conta'), ('Centro de custo', 'centro'),
               ('Mês', 'mes'), ('Situação', 'situacao'), ('Tipo (despesa/receita)', 'tipo')]
        _rot('Agrupar por', self, 15, 234, px=12)
        self.cb_a1 = _por(ComboDados(px=13, opcoes=agr), self, 15, 251, 300, 26)
        self.cb_a1.definir(u.get('agrupar1', ''))
        _rot('Depois por', self, 325, 234, px=12)
        self.cb_a2 = _por(ComboDados(px=13, opcoes=agr), self, 325, 251, 300, 26)
        self.cb_a2.definir(u.get('agrupar2', ''))
        _rot('Ordenar por', self, 15, 284, px=12)
        self.cb_ord = _por(ComboDados(px=13, opcoes=[('Data de movimento', 'data'), ('Data de vencimento/pagamento', 'vencimento'),
                                                     ('Nome do cliente ou fornecedor', 'pessoa'), ('Descrição da despesa/receita', 'descricao'),
                                                     ('Observação', 'observacao'), ('Documento', 'documento'), ('Valor', 'valor')]), self, 15, 301, 300, 26)
        self.cb_ord.definir(u.get('ordem'))
        self.ck_dec = QCheckBox('Decrescente', self)
        self.ck_dec.setGeometry(325, 304, 150, 20)
        self.ck_dec.setChecked(bool(u.get('decrescente')))
        self.rg_mod = RadioGrupo('Tipo de relatório', [('Descritivo', 'descritivo'), ('Totalizado', 'totalizado')], self, px=12)
        self.rg_mod.setGeometry(15, 336, 300, 48)
        self.rg_mod.definir(u.get('modo', 'descritivo'))
        self.rg_mod.mudou.connect(lambda m: (self.cb_ord.setEnabled(m != 'totalizado'), self.ck_dec.setEnabled(m != 'totalizado')))
        _rot('Título do relatório', self, 15, 394, px=12)
        self.ed_tit = _por(Campo(px=13), self, 15, 411, 610, 26)
        self.ed_tit.definir(u.get('titulo') or 'Relatório de Movimentos')
        ln = QFrame(self)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(15, 452, 610, 2)
        _por(BitBtn('Fechar', icone('fa6s.xmark', '#b02a2a')), self, 15, 466, 110, 39).clicked.connect(self.reject)
        b = _por(BitBtn('&Submeter', icone('fa6s.check', '#1a7f37'), dica='Gerar relatório'), self, 131, 466, 140, 39)
        b.setDefault(True)
        b.clicked.connect(self._ok)

    def _ok(self):
        if self.rg_mod.valor() == 'totalizado' and not (self.cb_a1.valor() or self.cb_a2.valor()):
            msg_aviso(self, 'Escolha ao menos um agrupamento para o relatório totalizado.')
            return
        self.accept()

    def valores(self):
        return {'tipo': self.rg_tip.valor(), 'situacao': self.rg_sit.valor(), 'campo_data': self.cb_per.valor(), 'de': self.de.valor(),
                'ate': self.ate.valor(), 'descricao': self.ed_des.valor(), 'pessoa': self.ed_pes.valor(), 'conta_id': self.cb_con.valor(),
                'centro_id': self.cb_cen.valor(), 'agrupar1': self.cb_a1.valor(), 'agrupar2': self.cb_a2.valor(), 'ordem': self.cb_ord.valor(),
                'decrescente': '1' if self.ck_dec.isChecked() else '', 'modo': self.rg_mod.valor(), 'titulo': self.ed_tit.valor()}


# ---------- FChart ----------

class JanelaGrafico(QDialog):
    def __init__(self, ctrl, g, tipo=None, refazer=None):
        super().__init__(ctrl.j)
        self.ctrl, self.g = ctrl, g
        self.setWindowTitle(g['titulo'])
        from .base import caber_na_tela
        caber_na_tela(self, 1000, 680)
        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        cab = rotulo(f"{g['titulo']}   —   {g['subtitulo']}" + (f"   ·   Total: {fin.moeda(g['total'])}" if g.get('total') is not None else '')
                     + (f"   ·   Média mensal: {fin.moeda(g['media'])}" if g.get('media') is not None else ''), px=14, nome='Segoe UI Semibold', negrito=True)
        topo.addWidget(cab)
        topo.addStretch()
        for texto, ic, fn in (('Alterar parâmetros', 'fa6s.sliders', lambda: (self.reject(), refazer and refazer())),
                              ('Imprimir / PDF', 'fa6s.print', self.imprimir), ('Fechar', 'fa6s.xmark', self.reject)):
            b = BitBtn(texto, icone(ic, E.NAVY))
            b.clicked.connect(fn)
            topo.addWidget(b)
        v.addLayout(topo)
        self.graf = Grafico()
        if g['forma'] == 'ranking':
            self.graf.ranking(g['pontos'], E.SERIE.get(tipo or 'D'), titulo='')
            cols = [('rotulo', 'Descrição', 400), ('valor', 'Valor', 150, 'moeda'), ('perc', '%', 80, 'num')]
            linhas = g['pontos']
        else:
            cats = [p['rotulo'] for p in g['pontos']]
            if g.get('linha'):
                series = [('Receitas', E.SERIE['R'], [p['valores'][0] for p in g['pontos']]), ('Despesas', E.SERIE['D'], [p['valores'][1] for p in g['pontos']])]
                self.graf.colunas(cats, series, linha=('Margem', E.SERIE['M'], [p['margem'] for p in g['pontos']]), titulo='')
                cols = [('rotulo', 'Período', 150), ('r', 'Receitas', 150, 'moeda'), ('d', 'Despesas', 150, 'moeda'), ('m', 'Margem', 150, 'moeda')]
                linhas = [{'rotulo': p['rotulo'], 'r': p['valores'][0], 'd': p['valores'][1], 'm': p['margem']} for p in g['pontos']]
            else:
                self.graf.colunas(cats, [(g['series'][0], E.SERIE.get(tipo or 'D'), [p['valores'][0] for p in g['pontos']])], media=g.get('media'), titulo='')
                cols = [('rotulo', 'Período', 200), ('v', g['series'][0], 200, 'moeda')]
                linhas = [{'rotulo': p['rotulo'], 'v': p['valores'][0]} for p in g['pontos']]
        v.addWidget(self.graf, 3)
        self.tabela = Grade(cols, px=12, ordenar=False)
        self.tabela.setFont(E.fonte('Segoe UI', 12))
        self.tabela.definir(linhas)
        v.addWidget(self.tabela, 1)
        self.rel = fin.tabela(g['titulo'], g['subtitulo'], [(c[0], c[1], c[3] if len(c) > 3 else None) for c in cols], linhas, [])

    def imprimir(self):
        img = self.graf.grab().toImage()
        self.ctrl.mostrar(self.rel, imagem=img, forcar_tela=True)


# ---------- FRecibo ----------

class FormRecibo(FormBase):
    def __init__(self, ctrl, l):
        super().__init__(ctrl.j, 'Emissão de Recibo / Duplicata', 384, 474, cor=E.FUNDO_CADASTRO)
        self.ctrl, self.s, self.l = ctrl, ctrl.s, l
        emp = self.s.empresa()
        self.emp = emp
        pes = next((p for p in self.s.listar('pessoas') if p['nome'] == l.get('pessoa')), {}) if l.get('pessoa') else {}
        self.cfg = QSettings('MCC', 'MCC')
        abas = QTabWidget(self)
        abas.setGeometry(0, 16, 384, 458)
        abas.setFont(E.fonte('Verdana', 11, negrito=True))
        f = lambda w: (w.setFont(E.fonte('Verdana', 11)), w)[1]
        # recibo
        t1 = QWidget()
        abas.addTab(t1, 'Emissão de recibo')
        despesa = l['tipo'] == 'D'
        _rot('Pagamento para: Nome:', t1, 20, 12, px=11, nome='Verdana', negrito=True)
        self.ed_nom = _por(f(QLineEdit(l.get('pessoa') or '' if despesa else emp['nome'])), t1, 20, 27, 340, 22)
        _rot('Recebido de', t1, 20, 61, px=11, nome='Verdana', negrito=True)
        self.ed_rec = _por(f(QLineEdit(emp['nome'] if despesa else l.get('pessoa') or '')), t1, 20, 75, 340, 22)
        _rot('Valor', t1, 20, 107, px=11, nome='Verdana', negrito=True)
        self.ed_val = _por(CampoValor(px=12), t1, 22, 122, 95, 22)
        self.ed_val.definir(l['valor'])
        _rot('Data', t1, 134, 107, px=11, nome='Verdana', negrito=True)
        self.ed_dat = _por(CampoData(px=12), t1, 134, 122, 110, 22)
        self.ed_dat.definir(l.get('data_pagamento') or date.today().isoformat())
        _rot('Documento', t1, 256, 107, px=11, nome='Verdana', negrito=True)
        self.ed_doc = _por(f(QLineEdit(l.get('documento') or '')), t1, 256, 122, 104, 22)
        self.lb_ext = QLabel(t1)
        self.lb_ext.setGeometry(20, 153, 340, 51)
        self.lb_ext.setWordWrap(True)
        self.lb_ext.setStyleSheet('background: #e5e5e5; padding: 3px;')
        self.lb_ext.setFont(E.fonte('Arial', 11, negrito=True))
        _rot('Referênte a', t1, 20, 214, px=11, nome='Verdana', negrito=True)
        self.ed_ref = _por(f(QLineEdit(l['descricao'])), t1, 20, 229, 340, 22)
        _rot('Observação:', t1, 20, 259, px=11, nome='Verdana', negrito=True)
        self.ed_obs = _por(f(QLineEdit(l.get('observacao') or '')), t1, 20, 274, 340, 22)
        _rot('Número de vias:', t1, 204, 339, px=11, nome='Verdana', negrito=True)
        self.cb_vias = _por(ComboDados(px=11, opcoes=[('1', 1), ('2', 2)]), t1, 313, 335, 47, 22)
        self.cb_vias.definir(int(self.cfg.value('recibo/vias', 1)))
        for texto, x, w, fn in (('&Voltar', 20, 76, self.reject), ('&PDF', 100, 80, lambda: self.gerar('recibo', pdf=True)),
                                ('&Imprimir', 263, 97, lambda: self.gerar('recibo'))):
            b = _por(SpeedButton(texto, icone({'&Voltar': 'fa6s.arrow-left', '&PDF': 'fa6s.file-pdf', '&Imprimir': 'fa6s.print'}[texto], E.NAVY)), t1, x, 384, w, 28)
            b.setFont(E.fonte('Tahoma', 11, negrito=True))
            b.setStyleSheet(f'QToolButton {{ color: {E.NAVY}; border: 1px solid #adadad; background: #f3f3f3; }}')
            b.clicked.connect(fn)
        self.ed_val.textChanged.connect(self._ext)
        self._ext()
        # duplicata
        t2 = QWidget()
        abas.addTab(t2, 'Emissão de duplicata')
        _rot('Fatura Num.', t2, 15, 13, px=11, nome='Verdana', negrito=True)
        self.ed_fat = _por(f(QLineEdit(l.get('documento') or str(l['id']))), t2, 15, 28, 98, 22)
        _rot('Num. Ordem', t2, 137, 13, px=11, nome='Verdana', negrito=True)
        self.ed_ord = _por(f(QLineEdit(f"{l.get('parcela') or 1}/{l.get('total_parcelas') or 1}")), t2, 137, 28, 102, 22)
        _rot('Vencimento', t2, 263, 13, px=11, nome='Verdana', negrito=True)
        self.ed_ven = _por(CampoData(px=12), t2, 262, 28, 106, 22)
        self.ed_ven.definir(l['vencimento'])
        self.rg_dup = RadioGrupo('Tipo de duplicata', [('Venda Mercantil', 'DM'), ('Prestação de serviço', 'DS')], t2, px=11)
        self.rg_dup.setGeometry(15, 56, 353, 46)
        self.rg_dup.definir('DM')
        _rot('CNPJ / CPF', t2, 15, 111, px=11, nome='Verdana', negrito=True)
        self.ed_doc1 = _por(f(QLineEdit(pes.get('documento') or '')), t2, 15, 127, 137, 22)
        _rot('Valor', t2, 155, 109, px=11, nome='Verdana', negrito=True)
        self.ed_vdup = _por(CampoValor(px=12), t2, 156, 127, 104, 22)
        self.ed_vdup.definir(l['valor'])
        _rot('CEP', t2, 263, 109, px=11, nome='Verdana', negrito=True)
        self.ed_cep = _por(f(QLineEdit(pes.get('cep') or '')), t2, 266, 127, 102, 22)
        _rot('Sacado', t2, 15, 156, px=11, nome='Verdana', negrito=True)
        self.ed_sac = _por(f(QLineEdit(l.get('pessoa') or '')), t2, 15, 172, 353, 22)
        _rot('Endereço', t2, 15, 201, px=11, nome='Verdana', negrito=True)
        self.ed_end = _por(f(QLineEdit(pes.get('endereco') or '')), t2, 15, 218, 353, 22)
        _rot('Bairro', t2, 15, 245, px=11, nome='Verdana', negrito=True)
        self.ed_bai = _por(f(QLineEdit(pes.get('bairro') or '')), t2, 15, 260, 353, 22)
        _rot('Municipio-UF', t2, 15, 290, px=11, nome='Verdana', negrito=True)
        self.ed_mun = _por(f(QLineEdit(' - '.join(x for x in (pes.get('cidade'), pes.get('uf')) if x))), t2, 15, 305, 181, 22)
        _rot('Praça', t2, 202, 290, px=11, nome='Verdana', negrito=True)
        self.ed_pra = _por(f(QLineEdit(pes.get('cidade') or '')), t2, 202, 305, 166, 22)
        _rot('Observação:', t2, 15, 333, px=11, nome='Verdana', negrito=True)
        self.ed_odup = _por(f(QLineEdit(l.get('observacao') or '')), t2, 15, 348, 353, 22)
        for texto, x, fn in (('&Voltar', 15, self.reject), ('&PDF', 106, lambda: self.gerar('duplicata', pdf=True)),
                             ('&Imprimir', 207, lambda: self.gerar('duplicata'))):
            b = _por(SpeedButton(texto, icone({'&Voltar': 'fa6s.arrow-left', '&PDF': 'fa6s.file-pdf', '&Imprimir': 'fa6s.print'}[texto], E.NAVY)), t2, x, 384, 100, 28)
            b.setFont(E.fonte('Tahoma', 11, negrito=True))
            b.setStyleSheet(f'QToolButton {{ color: {E.NAVY}; border: 1px solid #adadad; background: #f3f3f3; }}')
            b.clicked.connect(fn)
        # configuracoes
        t3 = QWidget()
        abas.addTab(t3, 'Configurações')
        g = QGroupBox('Configuração de Impressão', t3)
        g.setGeometry(16, 24, 300, 153)
        self.marg = {}
        for chave, rot, x, y, pad in (('sup', 'Margem superior', 14, 32, 1.5), ('dir', 'Margem esquerda', 160, 32, 1.5), ('inf', 'Margem inferior', 14, 97, 1.5)):
            _rot(rot, g, x, y, px=11, nome='Verdana')
            e = _por(CampoValor(px=12), g, x, y + 16, 84, 22)
            e.definir(float(self.cfg.value(f'recibo/{chave}', pad)))
            _rot('cm', g, x + 88, y + 20, px=11, nome='Verdana')
            self.marg[chave] = e
        _por(BitBtn('Ca&ncela'), t3, 16, 203, 90, 29).clicked.connect(self.reject)
        _por(BitBtn('&Confirma'), t3, 116, 203, 90, 29).clicked.connect(self._salvar_cfg)

    def _ext(self):
        v = self.ed_val.valor()
        self.lb_ext.setText(f'({fin.extenso(v)})' if v else '')

    def _salvar_cfg(self):
        for k, e in self.marg.items():
            self.cfg.setValue(f'recibo/{k}', e.valor() or 0)
        self.cfg.setValue('recibo/vias', self.cb_vias.valor())
        msg_info(self, 'Configurações gravadas.')

    def _pintar_recibo(self, p, W, H):
        cidade = self.emp.get('cidade') or ''
        d = date.fromisoformat(self.ed_dat.valor() or date.today().isoformat())
        data_ext = f"{cidade + ', ' if cidade else ''}{d.day} de {fin.MESES_LONGOS[d.month - 1].lower()} de {d.year}"
        vias = self.cb_vias.valor() or 1
        alt = H / 2 if vias == 2 else H
        for via in range(vias):
            y0 = via * alt
            p.setPen(QPen(Qt.black, 1.2))
            p.drawRect(QRectF(0, y0, W, min(alt - 20, 430)))
            ft = QFont('Arial')
            ft.setPixelSize(28)
            ft.setBold(True)
            p.setFont(ft)
            p.drawText(QRectF(0, y0 + 14, W, 36), Qt.AlignHCenter, 'R E C I B O')
            fv = QFont('Arial')
            fv.setPixelSize(18)
            fv.setBold(True)
            p.setFont(fv)
            p.drawRect(QRectF(W - 190, y0 + 18, 170, 32))
            p.drawText(QRectF(W - 190, y0 + 18, 170, 32), Qt.AlignCenter, fin.moeda(self.ed_val.valor() or 0))
            if self.ed_doc.text():
                fn = QFont('Arial')
                fn.setPixelSize(12)
                p.setFont(fn)
                p.drawText(QRectF(20, y0 + 26, 200, 20), Qt.AlignLeft, f'Nº {self.ed_doc.text()}')
            fb = QFont('Arial')
            fb.setPixelSize(15)
            p.setFont(fb)
            texto = (f"Recebi(emos) de {self.ed_rec.text()} a importância de {fin.moeda(self.ed_val.valor() or 0)} "
                     f"({fin.extenso(self.ed_val.valor() or 0)}) referente a {self.ed_ref.text()}"
                     f"{(' — ' + self.ed_obs.text()) if self.ed_obs.text() else ''}.\n\nPara maior clareza firmo(amos) o presente.")
            p.drawText(QRectF(24, y0 + 70, W - 48, 200), Qt.TextWordWrap, texto)
            p.drawText(QRectF(24, y0 + 270, W - 48, 22), Qt.AlignRight, data_ext)
            p.drawLine(int(W / 2 - 170), int(y0 + 350), int(W / 2 + 170), int(y0 + 350))
            fn = QFont('Arial')
            fn.setPixelSize(13)
            p.setFont(fn)
            p.drawText(QRectF(0, y0 + 354, W, 20), Qt.AlignHCenter, self.ed_nom.text())
            p.drawText(QRectF(0, y0 + 372, W, 20), Qt.AlignHCenter, self.emp.get('documento') or '' if self.l['tipo'] == 'R' else '')

    def _pintar_duplicata(self, p, W, H):
        emp = self.emp
        p.setPen(QPen(Qt.black, 1.2))
        p.drawRect(QRectF(0, 0, W, 520))
        ft = QFont('Arial')
        ft.setPixelSize(16)
        ft.setBold(True)
        p.setFont(ft)
        p.drawText(QRectF(10, 8, W - 20, 22), Qt.AlignLeft, emp['nome'])
        fn = QFont('Arial')
        fn.setPixelSize(11)
        p.setFont(fn)
        e1, e2 = _endereco(emp)
        p.drawText(QRectF(10, 30, W - 20, 16), Qt.AlignLeft, e1)
        p.drawText(QRectF(10, 45, W - 20, 16), Qt.AlignLeft, e2)
        ft.setPixelSize(20)
        p.setFont(ft)
        tipo = 'DUPLICATA DE VENDA MERCANTIL' if self.rg_dup.valor() == 'DM' else 'DUPLICATA DE PRESTAÇÃO DE SERVIÇO'
        p.drawText(QRectF(0, 70, W, 28), Qt.AlignHCenter, tipo)
        celulas = [('Fatura Nº', self.ed_fat.text()), ('Valor', fin.moeda(self.ed_vdup.valor() or 0)), ('Nº de ordem', self.ed_ord.text()),
                   ('Vencimento', fin.br(self.ed_ven.valor()))]
        cw = W / 4
        for i, (rot, val) in enumerate(celulas):
            r = QRectF(i * cw, 110, cw, 52)
            p.drawRect(r)
            p.setFont(fn)
            p.drawText(r.adjusted(6, 4, -6, 0), Qt.AlignLeft | Qt.AlignTop, rot)
            fb = QFont('Arial')
            fb.setPixelSize(15)
            fb.setBold(True)
            p.setFont(fb)
            p.drawText(r.adjusted(6, 0, -6, -6), Qt.AlignLeft | Qt.AlignBottom, val)
        y = 180
        p.setFont(fn)
        for rot, val in (('Sacado:', self.ed_sac.text()), ('CNPJ/CPF:', self.ed_doc1.text()), ('Endereço:', self.ed_end.text()),
                         ('Bairro:', self.ed_bai.text()), ('Município-UF:', f'{self.ed_mun.text()}    CEP: {self.ed_cep.text()}'),
                         ('Praça de pagamento:', self.ed_pra.text()), ('Observação:', self.ed_odup.text())):
            p.drawText(QRectF(14, y, 150, 18), Qt.AlignLeft, rot)
            fb = QFont('Arial')
            fb.setPixelSize(13)
            fb.setBold(True)
            p.setFont(fb)
            p.drawText(QRectF(150, y - 1, W - 160, 18), Qt.AlignLeft, val)
            p.setFont(fn)
            y += 24
        p.drawRect(QRectF(10, y + 6, W - 20, 50))
        p.drawText(QRectF(18, y + 10, W - 36, 44), Qt.TextWordWrap, f'Valor por extenso: {fin.extenso(self.ed_vdup.valor() or 0)}')
        y += 80
        p.drawText(QRectF(10, y, W - 20, 36), Qt.TextWordWrap,
                   'Reconheço(cemos) a exatidão desta DUPLICATA, na importância acima, que pagarei(emos) à '
                   f"{emp['nome']} ou à sua ordem na praça e vencimento indicados.")
        y += 70
        p.drawLine(20, int(y), int(W / 2 - 20), int(y))
        p.drawLine(int(W / 2 + 20), int(y), int(W - 20), int(y))
        p.drawText(QRectF(20, y + 4, W / 2 - 40, 18), Qt.AlignHCenter, 'Data do aceite')
        p.drawText(QRectF(W / 2 + 20, y + 4, W / 2 - 40, 18), Qt.AlignHCenter, 'Assinatura do sacado')

    def gerar(self, qual, pdf=False):
        cfg = self.cfg
        sup, esq, inf = (float(self.marg[k].valor() or 0) * 10 for k in ('sup', 'dir', 'inf'))

        def pintar(printer):
            p = QPainter(printer)
            area = printer.pageLayout().paintRectPixels(printer.resolution())
            esc = printer.resolution() / 96.0
            p.scale(esc, esc)
            W, H = area.width() / esc, area.height() / esc
            (self._pintar_recibo if qual == 'recibo' else self._pintar_duplicata)(p, W, H)
            p.end()
        pr = QPrinter(QPrinter.HighResolution)
        pr.setPageSize(QPageSize(QPageSize.A4))
        pr.setPageMargins(QMarginsF(esq, sup, esq, inf), QPageLayout.Millimeter)
        if pdf:
            caminho, _ = QFileDialog.getSaveFileName(self, 'Gerar arquivo PDF', str(Path.home() / f'{qual}_{self.l["id"]}.pdf'), 'PDF (*.pdf)')
            if not caminho:
                return
            pr.setOutputFormat(QPrinter.PdfFormat)
            pr.setOutputFileName(caminho)
            pintar(pr)
            QDesktopServices.openUrl(QUrl.fromLocalFile(caminho))
            return
        dlg = QPrintPreviewDialog(pr, self)
        dlg.setWindowTitle('Recibo' if qual == 'recibo' else 'Duplicata')
        dlg.paintRequested.connect(pintar)
        from .base import caber_na_tela
        caber_na_tela(dlg, 900, 700)
        dlg.exec()


# ---------- controlador ----------

RELS_PERIODO = {'lancamentos', 'totais_item', 'por_pessoa', 'pontualidade', 'fluxo_dia', 'fluxo', 'fechamento', 'extrato', 'centros', 'centro_itens',
                'fluxo_centros', 'dre'}


class Relatorios:
    def __init__(self, janela):
        self.j = janela

    @property
    def s(self):
        return self.j.s

    def _cor(self):
        chave = QSettings('MCC', 'MCC').value('cor_relatorio', 'cinza_claro')
        return E.CORES_RELATORIO.get(chave, E.CORES_RELATORIO['cinza_claro'])[1]

    def mostrar(self, rel, imagem=None, forcar_tela=False):
        emp = self.s.empresa()
        pintor = PintorRelatorio(rel, emp, self.s.logo(), self._cor(), imagem)
        modo = 'tela' if forcar_tela else QSettings('MCC', 'MCC').value('geracao_relatorio', 'tela')
        if modo == 'pdf':
            exportar_pdf(self.j, pintor, rel['titulo'])
        elif modo == 'html':
            exportar_html(self.j, rel, emp)
        elif modo == 'preview':
            pr = QPrinter(QPrinter.HighResolution)
            pintor.configurar(pr)
            dlg = QPrintPreviewDialog(pr, self.j)
            dlg.setWindowTitle(rel['titulo'])
            dlg.paintRequested.connect(pintor.pintar)
            from .base import caber_na_tela
            caber_na_tela(dlg, 1000, 720)
            dlg.exec()
        else:
            JanelaPreview(self.j, pintor, rel['titulo'], rel).exec()

    def _executar(self, nome, q):
        try:
            rel = self.s.relatorio(nome, **q)
        except Exception as e:
            msg_aviso(self.j, str(e))
            return
        self.mostrar(rel)

    def abrir(self, nome, **fixos):
        """Pede os parametros (como o FPeriodo/FObterData do original) e gera o relatorio."""
        q = dict(fixos)
        extras = []
        if nome == 'lancamentos':
            if 'situacao' not in fixos:
                extras.append(('situacao', 'Situação', ComboDados(px=13, opcoes=[('Pagas ou em aberto', ''), ('Pagas', 'V'), ('Em aberto', 'P')])))
            extras.append(('conta_id', 'Conta', ComboDados(px=13, opcoes=[('Todas', None)] + [(c['descricao'], c['id']) for c in self.s.listar('contas')])))
        if nome in ('totais_item', 'por_pessoa') and 'situacao' not in fixos:
            extras.append(('situacao', 'Situação', ComboDados(px=13, opcoes=[('Pagas ou em aberto', ''), ('Pagas', 'V'), ('Em aberto', 'P')])))
        if nome == 'extrato':
            contas = [c for c in self.s.listar('contas') if not fixos.get('tipo_conta') or c['tipo'] == fixos['tipo_conta']]
            if not contas:
                msg_aviso(self.j, 'Nenhuma conta cadastrada para este extrato.')
                return
            extras.append(('conta_id', 'Conta', ComboDados(px=13, opcoes=[(c['descricao'], c['id']) for c in contas])))
            if fixos.get('previsao'):
                hoje = date.today()
                q.setdefault('de', hoje.isoformat())
        if nome in RELS_PERIODO:
            f = FormPeriodo(self.j, 'Definir período', extras, campo_data=nome == 'lancamentos' and 'campo_data' not in fixos)
            if f.exec() != QDialog.Accepted:
                return
            q.update(f.valores())
        elif nome == 'saldos':
            f = FormPeriodo(self.j, 'Saldo das contas em', so_data=True)
            if f.exec() != QDialog.Accepted:
                return
            q['data'] = f.valores()['de']
        elif nome == 'comparativo_saldos':
            f = FormPeriodo(self.j, 'Comparar saldos entre as datas')
            if f.exec() != QDialog.Accepted:
                return
            v = f.valores()
            q.update(data1=v['de'], data2=v['ate'])
        elif nome == 'demonstrativo':
            from PySide6.QtWidgets import QInputDialog
            ano, ok = QInputDialog.getInt(self.j, 'Demonstrativo anual', 'Ano:', date.today().year, 2001, 2100)
            if not ok:
                return
            q['ano'] = ano
        q.pop('tipo_conta', None)
        self._executar(nome, q)

    def extrato(self, conta_id):
        f = FormPeriodo(self.j, 'Extrato da conta — período')
        if f.exec() == QDialog.Accepted:
            self._executar('extrato', {'conta_id': conta_id, **f.valores()})

    def analitico(self):
        f = FormAnalitico(self, getattr(self, '_ult_analitico', None))
        if f.exec() != QDialog.Accepted:
            return
        self._ult_analitico = f.valores()
        self._executar('analitico', self._ult_analitico)

    def grafico(self, nome, **fixos):
        q = dict(fixos)
        extras = [('situacao', 'Situação', ComboDados(px=13, opcoes=[('Pagas e em aberto', ''), ('Somente pagas', 'V'), ('Somente em aberto', 'P')]))]
        if nome == 'evolucao':
            opcoes = self.s.grafico('opcoes', **fixos)
            if not opcoes:
                msg_aviso(self.j, 'Ainda não há lançamentos para comparar.')
                return
            cb = ComboLookup(px=13, itens=opcoes)
            cb.setMinimumWidth(320)
            rot = ('Fornecedor' if fixos.get('tipo') == 'D' else 'Cliente') if fixos.get('agrupar') == 'pessoa' else 'Ítem'
            extras.insert(0, ('valor', rot, cb))
        hoje = date.today()
        f = FormPeriodo(self.j, 'Gráfico — período', extras, campo_data=True, de=f'{hoje.year}-01-01', ate=f'{hoje.year}-12-31')
        if f.exec() != QDialog.Accepted:
            return
        q.update(f.valores())
        try:
            g = self.s.grafico(nome, **q)
        except Exception as e:
            msg_aviso(self.j, str(e))
            return
        JanelaGrafico(self, g, fixos.get('tipo'), refazer=lambda: self.grafico(nome, **fixos)).exec()

    def recibo(self, l):
        FormRecibo(self, self.s.lancamento(l['id'])).exec()

    def exportar_grade(self, grade, titulo):
        cols = [(c[0], c[1].strip(), c[3] if len(c) > 3 else None) for c in grade.modelo.colunas]
        rel = fin.tabela(titulo, '', cols, grade.modelo.linhas, [])
        exportar_csv(self.j, rel)
