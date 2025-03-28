"""
**pyqode.qt** 是一个针对不同Qt绑定的兼容层。主要用于写跨Qt绑定的库或应用程序。

该兼容层会自动选择第一个可用的API (PyQt5, PyQt4 或最后是PySide)。

你可以通过设置 ``QT_API`` 环境变量来强制使用特定的绑定。

现在我们默认使用PySide6进行所有操作。
"""
import os
import sys
import logging

# Qt绑定的优先级
PYSIDE6 = 'pyside6'
PYSIDE2 = 'pyside2'  
PYSIDE = 'pyside'
PYQT5 = 'pyqt5'
PYQT4 = 'pyqt4'

# 环境变量的名称
QT_API = 'QT_API'

# 绑定API的映射
PYQT4_API = [PYQT4, 'pyqt']
PYQT5_API = [PYQT5]
PYSIDE_API = [PYSIDE, PYSIDE2, PYSIDE6]

# 首选的Qt绑定顺序
API_NAMES = [PYSIDE6, PYQT5, PYSIDE2, PYQT4, PYSIDE]

# 设置默认值
os.environ.setdefault(QT_API, PYSIDE6)

# 确保QT_API为小写
os.environ[QT_API] = os.environ[QT_API].lower()

logging.getLogger(__name__).debug('使用的Qt绑定: %s', os.environ[QT_API])

__version__ = '2.10.0'

class PythonQtError(Exception):
    """
    Error raise if no bindings could be selected
    """
    pass


def setup_apiv2():
    """
    Setup apiv2 when using PyQt4 and Python2.
    """
    # setup PyQt api to version 2
    if sys.version_info[0] == 2:
        logging.getLogger(__name__).debug(
            'setting up SIP API to version 2')
        import sip
        try:
            sip.setapi("QString", 2)
            sip.setapi("QVariant", 2)
        except ValueError:
            logging.getLogger(__name__).critical(
                "failed to set up sip api to version 2 for PyQt4")
            raise ImportError('PyQt4')


def autodetect():
    """
    Auto-detects and use the first available QT_API by importing them in the
    following order:

    1) PySide6
    2) PyQt5
    3) PySide2
    4) PyQt4
    5) PySide
    """
    logging.getLogger(__name__).debug('auto-detecting QT_API')
    for api in API_NAMES:
        try:
            logging.getLogger(__name__).debug('trying %s', api)
            if api == PYSIDE6:
                import PySide6
            elif api == PYSIDE2:
                import PySide2
            elif api == PYSIDE:
                import PySide
            elif api == PYQT5:
                import PyQt5
            elif api == PYQT4:
                setup_apiv2()
                import PyQt4
            os.environ[QT_API] = api
            logging.getLogger(__name__).debug('imported %s', api)
            return
        except ImportError:
            continue
    raise PythonQtError('No Qt bindings could be found')


if QT_API in os.environ:
    # check if the selected QT_API is available
    try:
        if os.environ[QT_API] in API_NAMES:
            logging.getLogger(__name__).debug('importing %s', os.environ[QT_API])
            if os.environ[QT_API] == PYSIDE6:
                import PySide6
            elif os.environ[QT_API] == PYSIDE2:
                import PySide2
            elif os.environ[QT_API] == PYSIDE:
                import PySide
            elif os.environ[QT_API] == PYQT5:
                import PyQt5
            elif os.environ[QT_API] == PYQT4:
                setup_apiv2()
                import PyQt4
            logging.getLogger(__name__).debug('imported %s', os.environ[QT_API])
        else:
            raise ImportError
    except ImportError:
        logging.getLogger(__name__).warning(
            'failed to import the selected QT_API: %s',
            os.environ[QT_API])
        # use the auto-detected API if possible
        autodetect()
else:
    # user did not select a qt api, let's perform auto-detection
    autodetect()

logging.getLogger(__name__).info('using %s' % os.environ[QT_API])
