import logging
import sys
import inspect


# 定义颜色
class LogColors:
    DEBUG = "\033[0;37m"  # 白色
    INFO = "\033[0;32m"  # 绿色
    WARNING = "\033[0;33m"  # 黄色
    ERROR = "\033[0;31m"  # 红色
    CRITICAL = "\033[1;31m"  # 高亮红色
    RESET = "\033[0m"  # 重置颜色


# 自定义日志处理器
class ColoredFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.DEBUG:
            record.msg = f"{LogColors.DEBUG}{record.msg}{LogColors.RESET}"
        elif record.levelno == logging.INFO:
            record.msg = f"{LogColors.INFO}{record.msg}{LogColors.RESET}"
        elif record.levelno == logging.WARNING:
            record.msg = f"{LogColors.WARNING}{record.msg}{LogColors.RESET}"
        elif record.levelno == logging.ERROR:
            record.msg = f"{LogColors.ERROR}{record.msg}{LogColors.RESET}"
        elif record.levelno == logging.CRITICAL:
            record.msg = f"{LogColors.CRITICAL}{record.msg}{LogColors.RESET}"

        return super().format(record)


class CustomLogger:
    def __init__(self, name='MyLogger', level=logging.DEBUG):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        # 设置自定义格式化器
        formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)

        # 将处理器添加到记录器
        self.logger.addHandler(console_handler)

    def debug(self, msg, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def _log(self, level, msg, *args, **kwargs):
        # 获取调用该方法的类名和方法名
        frame = inspect.currentframe().f_back.f_back
        caller_class = frame.f_locals.get('self',
                                          None).__class__.__name__ if 'self' in frame.f_locals else 'UnknownClass'
        caller_method = frame.f_code.co_name

        # 添加到日志记录的额外信息
        extra = {'caller_class': caller_class, 'caller_method': caller_method}
        # 调用日志记录方法，注意参数顺序
        self.logger.log(level, f"[{caller_class}.{caller_method}] {msg}", *args, extra=extra, **kwargs)
