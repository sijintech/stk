import logging
import os
import sys
from logging.handlers import RotatingFileHandler


class CustomLogger:
    def __init__(self, name="app"):
        self.logger = logging.getLogger(name)

        # 如果logger已经有处理器，说明已经初始化过，直接返回
        if self.logger.handlers:
            return

        self.logger.setLevel(logging.DEBUG)

        # 创建日志格式
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # 添加控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 创建日志文件目录
        log_dir = os.path.join(os.path.expanduser("~"), ".stk", "logs")
        os.makedirs(log_dir, exist_ok=True)

        # 添加文件处理器
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "app.log"), maxBytes=1024 * 1024, backupCount=5  # 1MB
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def critical(self, message):
        self.logger.critical(message)
