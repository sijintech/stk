import sys
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt


fig = plt.figure()  # 创建figure
ax = fig.subplots()
t = np.linspace(0, np.pi, 50)
ax.plot(t, np.sin(t))  # 画曲线（在窗口显示之后画也可以）
win = FigureCanvas(fig)  # 创建画布控件
win.show()  # 画布控件作为窗口显示