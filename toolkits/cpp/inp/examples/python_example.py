#!/usr/bin/env python3
"""
Python 使用示例 (ctypes 方法)

此示例展示了如何在 Python 中使用 ctypes 加载 inp_io 库
并解析 Abaqus 输入文件。

运行方法:
python python_example.py [输入文件]
"""

import ctypes
import os
import sys
import platform
import locale


def get_system_encoding():
    """获取系统默认编码，用于正确解码C库返回的字节串"""
    if platform.system() == "Windows":
        # Windows平台通常是GBK/CP936编码
        return "gbk"
    else:
        # 非Windows平台默认使用UTF-8
        return "utf-8"


def decode_bytes(byte_str):
    """根据系统编码解码字节串，处理可能的编码错误"""
    if byte_str is None:
        return ""

    encoding = get_system_encoding()
    try:
        return byte_str.decode(encoding)
    except UnicodeDecodeError:
        # 如果默认编码解码失败，尝试UTF-8
        try:
            return byte_str.decode("utf-8")
        except UnicodeDecodeError:
            # 最后尝试使用latin1（它可以解码任何字节）
            return byte_str.decode("latin1")


def load_library():
    """加载 inp_io 库，处理不同平台的库文件名称"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)

    if platform.system() == "Windows":
        # Windows 用 .dll 扩展名
        lib_paths = [
            os.path.join(current_dir, "lib/inp_io.dll"),  # 相对路径
            os.path.join(
                parent_dir, "build", "Release", "inp_io.dll"
            ),  # CMake 生成路径
            os.path.join(parent_dir, "build", "Debug", "inp_io.dll"),
        ]
    else:
        # Linux/macOS 用 .so 扩展名
        lib_paths = [
            os.path.join(parent_dir, "libinp_io.so"),  # 相对路径
            os.path.join(parent_dir, "build", "libinp_io.so"),  # CMake 生成路径
        ]

    # 尝试加载所有可能的路径
    for lib_path in lib_paths:
        if os.path.exists(lib_path):
            try:
                return ctypes.CDLL(lib_path)
            except OSError:
                continue

    raise RuntimeError(f"无法加载 inp_io 库。尝试以下路径: {lib_paths}")


# 定义数据结构类来匹配 C 结构体定义
class InpParameter(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 80),
        ("value", ctypes.c_char * 256),
        ("has_value", ctypes.c_int),
    ]


class InpDataLine(ctypes.Structure):
    pass  # 前向声明，将在后面完成定义


class InpKeyword(ctypes.Structure):
    pass  # 前向声明，将在后面完成定义


# 完成定义
InpDataLine._fields_ = [
    ("content", ctypes.c_char * 256),
    ("fields", ctypes.POINTER(ctypes.c_char_p)),
    ("field_count", ctypes.c_int),
]

InpKeyword._fields_ = [
    ("name", ctypes.c_char * 80),
    ("parameters", InpParameter * 50),  # 最多50个参数
    ("parameter_count", ctypes.c_int),
    ("data_lines", ctypes.POINTER(InpDataLine)),
    ("data_line_count", ctypes.c_int),
    ("line_number", ctypes.c_int),
]


class InpMetadata(ctypes.Structure):
    _fields_ = [
        ("filename", ctypes.c_char * 256),
        ("total_lines", ctypes.c_int),
        ("keyword_count", ctypes.c_int),
        ("comment_lines", ctypes.c_int),
        ("parse_errors", ctypes.c_char * 1024),
    ]


class InpFile(ctypes.Structure):
    _fields_ = [
        ("keywords", ctypes.POINTER(InpKeyword)),
        ("keyword_count", ctypes.c_int),
        ("metadata", InpMetadata),
    ]


# 结果代码枚举
INP_SUCCESS = 0
INP_ERROR_FILE_NOT_FOUND = -1
INP_ERROR_MEMORY_ALLOCATION = -2
INP_ERROR_INVALID_FORMAT = -3
INP_ERROR_LINE_TOO_LONG = -4
INP_ERROR_INVALID_KEYWORD = -5


class AbaqusInpParser:
    """Abaqus输入文件解析器类，封装 inp_io 库的调用"""

    def __init__(self):
        self.lib = load_library()
        self.setup_function_signatures()
        self.inp_file_ptr = None

    def setup_function_signatures(self):
        """设置函数签名（参数类型和返回类型）"""
        # inp_parse_file
        self.lib.inp_parse_file.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.POINTER(InpFile)),
        ]
        self.lib.inp_parse_file.restype = ctypes.c_int

        # inp_free_file
        self.lib.inp_free_file.argtypes = [ctypes.POINTER(InpFile)]
        self.lib.inp_free_file.restype = None

        # inp_find_keyword
        self.lib.inp_find_keyword.argtypes = [ctypes.POINTER(InpFile), ctypes.c_char_p]
        self.lib.inp_find_keyword.restype = ctypes.POINTER(InpKeyword)

        # inp_print_file_info
        self.lib.inp_print_file_info.argtypes = [ctypes.POINTER(InpFile)]
        self.lib.inp_print_file_info.restype = None

    def parse_file(self, filepath):
        """解析 Abaqus 输入文件"""
        # 释放之前的结果（如果有）
        if self.inp_file_ptr:
            self.free_file()

        # 创建指针
        self.inp_file_ptr = ctypes.POINTER(InpFile)()

        # 调用解析函数
        result = self.lib.inp_parse_file(
            filepath.encode("utf-8"), ctypes.byref(self.inp_file_ptr)
        )

        return result

    def free_file(self):
        """释放内存"""
        if self.inp_file_ptr:
            self.lib.inp_free_file(self.inp_file_ptr)
            self.inp_file_ptr = None

    def print_file_info(self):
        """打印文件信息（使用C库函数）"""
        if self.inp_file_ptr:
            self.lib.inp_print_file_info(self.inp_file_ptr)

    def find_keyword(self, keyword_name):
        """查找关键字"""
        if not self.inp_file_ptr:
            return None

        keyword_ptr = self.lib.inp_find_keyword(
            self.inp_file_ptr, keyword_name.encode("utf-8")
        )

        return keyword_ptr

    def get_keyword_list(self):
        """获取所有关键字列表"""
        if not self.inp_file_ptr:
            return []

        result = []
        for i in range(self.inp_file_ptr.contents.keyword_count):
            keyword = self.inp_file_ptr.contents.keywords[i]  # 提取参数
            params = []
            for j in range(keyword.parameter_count):
                param = keyword.parameters[j]
                if param.has_value:
                    params.append(
                        {
                            "name": decode_bytes(param.name),
                            "value": decode_bytes(param.value),
                        }
                    )
                else:
                    params.append({"name": decode_bytes(param.name)})  # 提取记录
            records = []
            if keyword.data_line_count > 0 and keyword.data_lines:
                for j in range(keyword.data_line_count):
                    data_line = keyword.data_lines[j]
                    content = decode_bytes(data_line.content)
                    records.append(content)  # 创建关键字记录
            result.append(
                {
                    "name": decode_bytes(keyword.name),
                    "line": keyword.line_number,
                    "params": params,
                    "data_lines": records,
                    "data_line_count": keyword.data_line_count,
                }
            )

        return result

    def __del__(self):
        """析构函数，确保内存被释放"""
        self.free_file()


def main():
    # 解析命令行参数
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "./example.inp"

    print(f"=== inp_io Python 使用示例 ===")
    print(f"解析文件: {filepath}\n")

    # 创建解析器
    parser = AbaqusInpParser()

    # 解析文件
    result = parser.parse_file(filepath)
    if result != INP_SUCCESS:
        print(f"解析失败，错误码: {result}")
        return 1

    print("文件已成功解析!")

    # 打印文件信息
    parser.print_file_info()

    # 查找NODE关键字并打印详细数据
    node = parser.find_keyword("NODE")
    if node:
        print("\n节点(NODE)关键字详情:")
        node_content = node.contents
        print(f"  名称: {decode_bytes(node_content.name)}")
        print(f"  行号: {node_content.line_number}")
        print(f"  参数数量: {node_content.parameter_count}")
        print(f"  数据行数量: {node_content.data_line_count}")

        # 打印节点数据
        print("\n节点数据:")
        for i in range(node_content.data_line_count):
            data_line = node_content.data_lines[i]
            print(f"  {decode_bytes(data_line.content)}")

    # 查找特定关键字
    material = parser.find_keyword("MATERIAL")
    if material:
        print("\n材料关键字详情:")
        mat = material.contents
        print(f"  名称: {decode_bytes(mat.name)}")
        print(f"  参数数量: {mat.parameter_count}")
        print(f"  数据行数量: {mat.data_line_count}")

        # 打印参数
        for i in range(mat.parameter_count):
            param = mat.parameters[i]
            if param.has_value:
                print(
                    f"  参数 #{i+1}: {decode_bytes(param.name)} = {decode_bytes(param.value)}"
                )
            else:
                print(f"  参数 #{i+1}: {decode_bytes(param.name)}")
    else:
        print("\n未找到材料关键字")

    # 获取所有关键字
    keywords = parser.get_keyword_list()
    print(f"\n关键字总数: {len(keywords)}")

    # 打印前5个关键字名称
    print("关键字列表 (前5个):")
    for i, kw in enumerate(keywords[:5]):
        print(f"  {i+1}. *{kw['name']}")

    # 释放内存
    parser.free_file()
    print("\n库函数已正确释放内存")


if __name__ == "__main__":
    main()
