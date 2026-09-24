"""STK 2D plots: ``stk.plot/1`` specs (``suan.plot.spec``) rendered by matplotlib (``suan.plot.mpl``).

Rendering uses ``matplotlib.figure.Figure`` + ``FigureCanvasAgg`` only (never
pyplot) and returns PNG/SVG/PDF bytes plus the plotted data as JSON.
Importing this package imports nothing heavy.
"""
