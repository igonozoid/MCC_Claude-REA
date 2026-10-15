"""Graficos (TChart do original) com QtCharts.

Cores fixas por entidade, paleta validada para daltonismo: receitas azul, despesas
laranja, margem verde-agua. Toda serie tem legenda e dica ao passar o mouse.
"""
from PySide6.QtCharts import (QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QHorizontalBarSeries, QLineSeries,
                              QPieSeries, QValueAxis)
from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QToolTip

from ..core import finance as fin
from .estilo import SERIE

CATEGORICA = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']


def _escala(maximo, minimo=0):
    if maximo == minimo:
        maximo = minimo + 1
    import math
    bruto = (maximo - minimo) / 4
    mag = 10 ** math.floor(math.log10(bruto))
    passo = next(f * mag for f in (1, 2, 5, 10) if f * mag >= bruto)
    lo = math.floor(minimo / passo) * passo
    hi = math.ceil(maximo / passo) * passo
    return lo, hi, int(round((hi - lo) / passo)) + 1


def _compacto(v):
    if abs(v) >= 1e6:
        return f'{v / 1e6:.1f} mi'.replace('.', ',')
    if abs(v) >= 1e3:
        return f'{v / 1e3:.1f} mil'.replace('.', ',').replace(',0 ', ' ')
    return f'{v:.0f}'


class Grafico(QChartView):
    def __init__(self, parent=None, titulo=''):
        super().__init__(QChart(), parent)
        self.setRenderHint(QPainter.Antialiasing)
        ch = self.chart()
        ch.setTitle(titulo)
        ch.setTitleFont(QFont('Segoe UI', 11, QFont.Bold))
        ch.setBackgroundRoundness(0)
        ch.setMargins(QMargins(6, 6, 6, 6))
        ch.legend().setAlignment(Qt.AlignTop)
        ch.legend().setFont(QFont('Segoe UI', 9))
        ch.setAnimationOptions(QChart.NoAnimation)

    def _aviso_vazio(self, vazio):
        from PySide6.QtWidgets import QLabel
        if not hasattr(self, '_lb_vazio'):
            self._lb_vazio = QLabel('Sem valores no período selecionado.', self)
            self._lb_vazio.setStyleSheet('color: #707070; background: transparent; font-size: 14px;')
            self._lb_vazio.setAlignment(Qt.AlignCenter)
        self._lb_vazio.setGeometry(0, 0, self.width(), self.height())
        self._lb_vazio.setVisible(vazio)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, '_lb_vazio'):
            self._lb_vazio.setGeometry(0, 0, self.width(), self.height())

    def limpar(self):
        ch = self.chart()
        ch.removeAllSeries()
        for ax in list(ch.axes()):
            ch.removeAxis(ax)

    def _eixo_valor(self, minimo, maximo):
        if maximo <= 0 and minimo >= 0:
            maximo = 100  # sem valores: escala neutra em vez de 0-1-1-2
        lo, hi, n = _escala(maximo, min(0, minimo))
        ax = QValueAxis()
        ax.setRange(lo, hi)
        ax.setTickCount(min(n, 7))
        ax.setLabelFormat('%.0f')
        ax.setLabelsFont(QFont('Segoe UI', 8))
        ax.setGridLineColor(QColor('#e3e3e3'))
        return ax

    def colunas(self, categorias, series, linha=None, media=None, titulo=None):
        """series: [(nome, cor, valores)]; linha: (nome, cor, valores) no mesmo eixo; media: valor."""
        self.limpar()
        ch = self.chart()
        if titulo is not None:
            ch.setTitle(titulo)
        barras = QBarSeries()
        barras.setBarWidth(0.72)
        todos = [0]
        for nome, cor, valores in series:
            s = QBarSet(nome)
            s.setColor(QColor(cor))
            s.setBorderColor(QColor('#ffffff'))  # 1-2px de folga entre barras vizinhas
            s.append([float(v) for v in valores])
            barras.append(s)
            todos += valores
        barras.hovered.connect(lambda status, i, s: status and QToolTip.showText(
            self.cursor().pos(), f'<b>{categorias[i]}</b><br>{s.label()}: {fin.moeda(s.at(i))}'))
        ch.addSeries(barras)
        ax_x = QBarCategoryAxis()
        ax_x.append(categorias)
        ax_x.setLabelsFont(QFont('Segoe UI', 8))
        ax_x.setGridLineVisible(False)
        extras = []
        if linha:
            nome, cor, valores = linha
            ls = QLineSeries()
            ls.setName(nome)
            ls.setPen(QPen(QColor(cor), 2))
            ls.setPointsVisible(True)
            for i, v in enumerate(valores):
                ls.append(QPointF(i, float(v)))
            ls.hovered.connect(lambda p, st, nome=nome: st and QToolTip.showText(
                self.cursor().pos(), f'<b>{categorias[min(len(categorias) - 1, max(0, round(p.x())))]}</b><br>{nome}: {fin.moeda(p.y())}'))
            extras.append(ls)
            todos += valores
        if media:
            ms = QLineSeries()
            ms.setName(f'Média {fin.moeda(media)}')
            pen = QPen(QColor('#52514e'), 1.5, Qt.DashLine)
            ms.setPen(pen)
            ms.append(QPointF(-0.5, media))
            ms.append(QPointF(len(categorias) - 0.5, media))
            extras.append(ms)
        ax_y = self._eixo_valor(min(todos), max(todos))
        ch.addAxis(ax_x, Qt.AlignBottom)
        ch.addAxis(ax_y, Qt.AlignLeft)
        barras.attachAxis(ax_x)
        barras.attachAxis(ax_y)
        if extras:
            ax_x2 = QValueAxis()  # eixo x numerico invisivel para alinhar a linha ao centro das categorias
            ax_x2.setRange(-0.5, len(categorias) - 0.5)
            ax_x2.setVisible(False)
            ch.addAxis(ax_x2, Qt.AlignBottom)
            for s in extras:
                ch.addSeries(s)
                s.attachAxis(ax_x2)
                s.attachAxis(ax_y)
        ch.legend().setVisible(len(series) + len(extras) >= 2)
        self._aviso_vazio(not any(v for _, _, vs in series for v in vs))

    def linhas(self, categorias, series, titulo=None):
        """FastLineSeries do dashboard linear: series [(nome, cor, valores)]."""
        self.limpar()
        ch = self.chart()
        if titulo is not None:
            ch.setTitle(titulo)
        todos = [0]
        ax_x = QValueAxis()
        ax_x.setRange(0, max(1, len(categorias) - 1))
        ax_x.setVisible(False)
        ax_cat = QBarCategoryAxis()
        ax_cat.append(categorias)
        ax_cat.setLabelsFont(QFont('Segoe UI', 8))
        lista = []
        for nome, cor, valores in series:
            ls = QLineSeries()
            ls.setName(nome)
            ls.setPen(QPen(QColor(cor), 2))
            ls.setPointsVisible(len(valores) <= 31)
            for i, v in enumerate(valores):
                ls.append(QPointF(i, float(v)))
            ls.hovered.connect(lambda p, st, nome=nome: st and QToolTip.showText(
                self.cursor().pos(), f'<b>{categorias[min(len(categorias) - 1, max(0, round(p.x())))]}</b><br>{nome}: {fin.moeda(p.y())}'))
            lista.append(ls)
            todos += valores
        ax_y = self._eixo_valor(min(todos), max(todos))
        ch.addAxis(ax_cat, Qt.AlignBottom)
        ch.addAxis(ax_x, Qt.AlignBottom)
        ch.addAxis(ax_y, Qt.AlignLeft)
        for ls in lista:
            ch.addSeries(ls)
            ls.attachAxis(ax_x)
            ls.attachAxis(ax_y)
        ch.legend().setVisible(len(lista) >= 2)

    def ranking(self, pontos, cor, titulo=None):
        """Parte do todo como barras horizontais (substitui a pizza do original com muitas fatias)."""
        self.limpar()
        ch = self.chart()
        if titulo is not None:
            ch.setTitle(titulo)
        pontos = list(reversed(pontos))  # maior em cima
        s = QBarSet('Valor')
        s.setColor(QColor(cor))
        s.setBorderColor(QColor(cor))
        s.append([float(p['valor']) for p in pontos])
        serie = QHorizontalBarSeries()
        serie.append(s)
        serie.setBarWidth(0.7)
        serie.setLabelsVisible(True)
        serie.setLabelsPosition(QHorizontalBarSeries.LabelsOutsideEnd)
        serie.setLabelsFormat('@value')
        serie.hovered.connect(lambda st, i, _s: st and QToolTip.showText(
            self.cursor().pos(), f"<b>{pontos[i]['rotulo']}</b><br>{fin.moeda(pontos[i]['valor'])} ({str(pontos[i].get('perc', '')).replace('.', ',')}%)"))
        ch.addSeries(serie)
        ax_y = QBarCategoryAxis()
        ax_y.append([f"{p['rotulo'][:28]}  ({str(p.get('perc', 0)).replace('.', ',')}%)" for p in pontos])
        ax_y.setLabelsFont(QFont('Segoe UI', 8))
        ax_y.setGridLineVisible(False)
        maximo = max([p['valor'] for p in pontos] + [1])
        ax_x = self._eixo_valor(0, maximo * 1.18)
        ch.addAxis(ax_y, Qt.AlignLeft)
        ch.addAxis(ax_x, Qt.AlignBottom)
        serie.attachAxis(ax_x)
        serie.attachAxis(ax_y)
        ch.legend().setVisible(False)
        self._aviso_vazio(not pontos)

    def pizza(self, fatias, titulo=None):
        """Pizza de poucas fatias (margem do dashboard): [(nome, valor, cor)]."""
        self.limpar()
        ch = self.chart()
        if titulo is not None:
            ch.setTitle(titulo)
        s = QPieSeries()
        s.setHoleSize(0.45)
        total = sum(max(0, v) for _, v, _ in fatias) or 1
        for nome, valor, cor in fatias:
            if valor <= 0:
                continue
            sl = s.append(f'{nome} {valor / total * 100:.0f}%'.replace('.', ','), float(valor))
            sl.setColor(QColor(cor))
            sl.setBorderColor(QColor('#ffffff'))
            sl.setBorderWidth(2)
            sl.hovered.connect(lambda st, nome=nome, valor=valor: st and QToolTip.showText(self.cursor().pos(), f'<b>{nome}</b><br>{fin.moeda(valor)}'))
        ch.addSeries(s)
        ch.legend().setVisible(True)
        ch.legend().setAlignment(Qt.AlignBottom)
