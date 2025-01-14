import click
import os
import locale
import glob
import subprocess
import json

@click.group()
def sjob():
    """与sjob插件相关的命令"""
    pass


@sjob.command(name='batCommand')
@click.option('--command', '-c', type=str, default='', help='每个目录中要执行的命令字符串')
@click.option('--folder_pattern', '-f', type=str, default='./*', help='目录通配符，默认为当前目录下的所有子目录')
def batch_all_command(command, folder_pattern):
    """
    遍历所有符合指定模式的目录，并在每个目录中执行指定的命令。
    """

    # 去掉前面的等号
    if folder_pattern.startswith('='):
        folder_pattern = folder_pattern[1:]  # 去掉前面的等号

    # 去掉外层的双引号或单引号
    if (folder_pattern.startswith('"') and folder_pattern.endswith('"')) or \
            (folder_pattern.startswith("'") and folder_pattern.endswith("'")):
        folder_pattern = folder_pattern[1:-1]
    if (command.startswith('"') and command.endswith('"')) or \
            (command.startswith("'") and command.endswith("'")):
        command = command[1:-1]

    # 获取当前工作目录的绝对路径
    current_dir = os.getcwd()
    # 获取系统默认编码
    system_encoding = locale.getpreferredencoding()

    # 使用 glob 模块解析通配符
    folder_list = [f for f in glob.glob(folder_pattern) if os.path.isdir(f)]

    # 遍历所有找到的目录
    for folder in folder_list:
        # 确保路径是一个有效目录
        if os.path.isdir(folder):
            # 切换到目标目录
            os.chdir(folder)

            # 输出正在执行的命令及目录信息
            print(f"-- 在目录 {folder} 中执行命令: {command}")

            try:
                # 使用 subprocess 捕获输出并解码
                result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True,
                                        encoding=system_encoding)
                print(result.stdout)  # 输出正确解码的结果
            except subprocess.CalledProcessError as e:
                # 如果命令执行失败，输出错误信息
                print(f"命令执行失败: {e}")

                # 切换回初始工作目录
            os.chdir(current_dir)


"""
Usage 1: 准备一个 batch.json 配置文件，然后
    htpstudio schedule [json 配置文件]

Usage 2: 直接传递选项代替 JSON 配置文件
    htpstudio schedule -k|--keyword -v|--value [-c|--condition] [-s|--separator] [-f|--format] [-h|--help]

Example:

    htpstudio schedule -k "@FREQ#PERIOD" -v "1e12 1e13#1e12/FREQ" -c "FREQ>1e9" -f "%.2e"
"""
# sjob schedule -k '@FREQ#PERIOD' -v "1e12 1e13#1e12/FREQ" -c "1>0" -f='%s'
@sjob.command(name='schedule')
@click.option('--keyword', '-k', help='输入变量名序列')
@click.option('--value', '-v', help='输入变量值序列')
@click.option('--condition', '-c',default='1>0', show_default=True, help='过滤任务的条件字符串，默认值是 "1>0"。')
@click.option('--separater', '-s',default='+', show_default=True, help='变量之间的分隔符，默认值是 "+"。')
@click.option('--format', '-f', default='%s', show_default=True, help='变量值的格式化样式，默认值是 "%s"。')


def write_batch_list(keyword, value, condition, separater, format):
    """
    生成 batchList.txt 文件，该文件包含创建文件夹和执行命令所需的所有信息
    """
    keyword = keyword.replace("~", "#")
    value = value.replace("~", "#")

    # 设置初始条件字符串
    current_condition = condition
    variable_index = 0
    variable_list_count = value.count("#") + 1
    index = 0

    # 初始化其他变量
    replaced_variable = ""
    replaced_previous = ""
    processed_variable = ""

    # 如果 batchList.txt 文件存在，则删除它
    if os.path.exists("batchList.txt"):
        os.remove("batchList.txt")

    # 写入 batchList.txt 文件的第一行
    with open("batchList.txt", "a") as f:
        f.write(f"{separater}#{keyword}#{condition}\n")

    while variable_index < variable_list_count:
        # 获取当前变量
        variables = value.split("#")
        current_variable = variables[variable_index]

        # 替换关键字字符串
        replaced_variable = current_variable
        while replaced_previous != replaced_variable:
            replaced_previous = replaced_variable
            replaced_variable = replaced_variable.replace("#", keyword)  # 替换

        # 对替换后的变量进行处理
        processed_variable = format % replaced_variable

        # 替换条件字符串中的关键字
        current_condition = current_condition.replace("#", keyword).replace(processed_variable, keyword)

        # 判断条件是否满足
        if eval(current_condition):
            index += 1
            print(f"条件满足: {current_condition}")
            print(f"{index}\t", end="")

            # 写入当前行到 batchList.txt
            with open("batchList.txt", "a") as f:
                f.write(f"{index}#{processed_variable}#{current_condition}\n")
        else:
            print(f"条件不满足: {current_condition}")

        # 更新变量索引，准备处理下一个变量
        variable_index += 1


# sjob create -f='input.in'
@sjob.command(name='create')
@click.option('--file_list', '-f',prompt='请输入需要复制的文件列表', help='需要复制的文件列表，以空格分隔')
@click.option('--start', '-s',default=1, show_default=True, help='起始索引，默认为 1')
@click.option('--end', '-e',default=None, help='结束索引，默认为 batchList.txt 中的总行数')
def make_folders(file_list, start=1, end=None):
    """
    创建文件夹并将文件复制到文件夹中
    """
    if end is None:
        end = len(open('batchList.txt').readlines()) - 1
    for i in range(start, end + 1):
        create_folder_condition_one_line(i, file_list)



@sjob.command(name='execute')
@click.option('--command_string', '-c', prompt='请输入要执行的命令', help='需要执行的命令，使用 {i} 作为索引占位符')
@click.option('--start', '-s',default=1, show_default=True, help='起始索引，默认为 1')
@click.option('--end', '-e',default=None, help='结束索引，默认为 batchList.txt 中的总行数')
def exec_folders(command_string, start=1, end=None):
    """
     在创建的文件夹中执行命令
    """
    if end is None:
        end = len(open('batchList.txt').readlines()) - 1
    for i in range(start, end + 1):
        name = get_folder_name(i)
        temp_cmd = replace_keywords_string_index(command_string, i)
        print(f"Exec command: {command_string} in folder {name}")
        os.chdir(name)
        subprocess.run(temp_cmd, shell=True)
        os.chdir("..")

def get_json_var(file_name, var_name):
    try:
        # 打开 JSON 文件并加载数据
        with open(file_name, 'r') as json_file:
            data = json.load(json_file)

        # 根据变量名执行不同的逻辑处理
        if var_name == "FreeFile":  # 新文件
            return " ".join(["&" + name for name in data[var_name]])
        elif var_name == "FixFile":  # 旧文件
            return " ".join(["@" + name for name in data[var_name]])
        elif var_name == "CopyFile":  # 拷贝文件
            return " ".join(data[var_name])
        elif var_name == "FreeVarName":  # 新变量名
            return "#".join(["&" + name for name in data[var_name]])
        elif var_name == "FixVarName":  # 旧变量名
            return "#".join(["@" + name for name in data[var_name]])
        elif var_name == "DependVarName":  # 依赖变量名
            return "#".join(data[var_name])
        elif var_name == "File":  # 所有文件
            output_list = []
            output_list.append(" ".join(["&" + name for name in data['FreeFile']]))
            output_list.append(" ".join(["@" + name for name in data['FixFile']]))
            output_list.append(" ".join(data['CopyFile']))
            return " ".join(output_list)
        elif var_name == "VarName":  # 所有变量名
            output_list = []
            for var_seq in data['VarSequence']:
                temp = []
                if isinstance(var_seq, list):
                    for var in var_seq:
                        prefix = ""
                        if var in data['FreeVarName']:
                            prefix = "&"
                        elif var in data['FixVarName']:
                            prefix = "@"
                        else:
                            raise ValueError("该关键字不在 Free 或 Fix 变量名中")
                        temp.append(prefix + var)
                    output_list.append("~".join(temp))
                else:
                    output_list.append(var_seq)
            return "#".join(output_list)
        elif var_name == "VarValue":  # 变量值
            output_list = []
            for var_seq in data['VarSequence']:
                temp = []
                if isinstance(var_seq, list):
                    for var in var_seq:
                        temp_val = [":".join(str(val).split()) for val in data['VarValue'][var]]
                        temp.append(" ".join(temp_val))
                    output_list.append("~".join(temp))
                else:
                    temp_val = [":".join(str(val).split()) for val in data['VarValue'][var_seq]]
                    output_list.append(" ".join(temp_val))
            return "#".join(output_list)
        else:
            # 默认返回指定变量名对应的数据
            return data[var_name]
    except KeyError:
        # 捕获 KeyError 异常，变量名不存在
        raise ValueError(f"变量名 '{var_name}' 不存在于 JSON 文件中。")
    except FileNotFoundError:
        # 捕获文件未找到异常
        raise FileNotFoundError(f"文件 '{file_name}' 不存在。")
    except json.JSONDecodeError:
        # 捕获 JSON 文件格式错误异常
        raise ValueError(f"文件 '{file_name}' 不是有效的 JSON 文件。")


def parse_json():
    """
    从 batch.json 提取变量并生成一个 Bash 脚本 batch.sh。
    """
    file = get_json_var('batch.json', 'File')
    var_name = get_json_var('batch.json', 'VarName')
    var_value = get_json_var('batch.json', 'VarValue')
    command = get_json_var('batch.json', 'Command')
    condition = get_json_var('batch.json', 'Condition')
    separator = get_json_var('batch.json', 'Separator')
    file_format = get_json_var('batch.json', 'Format')

    with open('batch.sh', 'w') as script:
        script.write("#!/bin/bash\n")
        script.write(f"files=\"{file}\"\n")
        script.write(f"varName=\"{var_name}\"\n")
        script.write(f"varValue=\"{var_value}\"\n")
        script.write(f"condition=\"{condition}\"\n")
        script.write(f"command=\"{command}\"\n")
        script.write(
            f"htpstudio schedule -k \"${{varName}}\" -v \"${{varValue}}\" -c \"${{condition}}\" -s \"{separator}\" -f \"{file_format}\"\n")
        script.write("htpstudio create -f \"${file}\"\n")
        script.write("htpstudio execute -c \"${command}\"\n")


def get_job_num(user_name=None, command="qstat", header=5):
    """
    获取当前运行的所有任务数量。

    :param user_name: 用户名，默认是当前用户。
    :param command: 用于获取任务状态的命令，默认是 qstat。
    :param header: 任务状态输出的头部行数，默认是 5。
    :return: 当前运行的任务数量。
    """
    if user_name is None:
        user_name = os.getlogin()

    result = subprocess.run([command, "-u", user_name], stdout=subprocess.PIPE, text=True)
    lines = result.stdout.splitlines()
    return max(0, len(lines) - header)


def get_running():
    """
    获取当前由 htpstudio 提交的运行任务数量。

    :return: 当前运行的任务数量。
    """
    user_name = os.getlogin()
    result = subprocess.run(["qstat", "-u", user_name], stdout=subprocess.PIPE, text=True)
    all_running_list = [line.split()[0] for line in result.stdout.splitlines()[5:]]

    try:
        with open("originalList.log", "r") as original_file:
            original_list = original_file.read().splitlines()
    except FileNotFoundError:
        original_list = []

    running_list = set(all_running_list) - set(original_list)

    with open("runningList.log", "w") as running_file:
        running_file.write("\n".join(running_list))

    return len(running_list)


def register_to_run(start=1, end=None, register_folder="."):
    """
    创建一个自动任务提交池。

    :param start: 起始索引，默认值是 1。
    :param end: 结束索引，默认是 batchList.txt 的最后一行。
    :param register_folder: 任务提交的根目录，默认是当前目录。
    """
    batch_list_path = os.path.join(register_folder, "batchList.txt")
    with open(batch_list_path, "r") as batch_list:
        lines = batch_list.readlines()

    if end is None:
        end = len(lines) - 1

    to_run_list = []
    for i in range(start - 1, end):
        folder_name = lines[i].strip()
        to_run_list.append(os.path.abspath(os.path.join(register_folder, folder_name)))

    with open(os.path.expanduser("~/toRunList.log"), "w") as to_run_file:
        to_run_file.write("\n".join(to_run_list))

    with open(os.path.expanduser("~/autoJobSubmission.sh"), "w") as auto_job_file:
        auto_job_file.write(
            "date; echo auto submitting; prepareNextRun 25 \"qsub job.pbs\" >> ~/autoJobSubmission.log\n")


import os
import subprocess


# === FUNCTION ================================================================
#          NAME: oneRun
#   DESCRIPTION: 获取下一个计划的作业（toRunList 中的第一个），并在其文件夹中执行某些命令
#    PARAMETERS:
#         command - 要执行的命令，默认为打印文件夹名称
#       RETURNS: 更新 finishedList.log, toRunList.log
# ===============================================================================
def one_run(command="echo folder_name"):
    folder = None
    with open(os.path.expanduser('~/toRunList.log'), 'r') as f:
        folder = f.readline().strip()

    if folder:
        os.chdir(folder)
        subprocess.run(command, shell=True)
        os.chdir('..')

        # 更新 finishedList.log 和 toRunList.log
        with open(os.path.expanduser('~/toRunList.log'), 'r') as f:
            lines = f.readlines()

        with open(os.path.expanduser('~/finishedList.log'), 'a') as f:
            f.write(lines[0])

        with open(os.path.expanduser('~/toRunList.log'), 'w') as f:
            f.writelines(lines[1:])

        if len(lines) == 1:
            os.remove(os.path.expanduser('~/toRunList.log'))
            os.remove(os.path.expanduser('~/originalList.log'))
            os.remove(os.path.expanduser('~/runningList.log'))
            os.remove(os.path.expanduser('~/allRunningList.log'))
            with open(os.path.expanduser('~/finishedList.log'), 'a') as f:
                f.write("\n" + subprocess.getoutput("date"))


# === FUNCTION ================================================================
#          NAME: prepareNextRun
#   DESCRIPTION: 为下一轮提交准备指定数量的作业
#    PARAMETERS:
#         maxRun - 下一轮提交的最大作业数
#         command - 要执行的命令，默认为 qsub cxx.pbs
#       RETURNS: 打印当前运行作业数和将要提交的作业数
# ===============================================================================
def prepare_next_run(max_run=100, command="qsub cxx.pbs"):
    all_running_number = get_job_num()
    running_number = get_running()
    max_next_submit = max_run - all_running_number
    allow_next_submit = max_run - running_number
    jobs_left = sum(1 for line in open(os.path.expanduser('~/toRunList.log')))
    next_submit = min(max_next_submit, allow_next_submit, jobs_left)

    with open(os.path.expanduser('~/toRunList.log'), 'r') as f:
        for _ in range(next_submit):
            one_run(command)

    print(f"current running={running_number} ({all_running_number}), to be submitted={next_submit}, {command}")


# === FUNCTION ================================================================
#          NAME: checkFinished
#   DESCRIPTION: 进入某个计算文件夹，查找标志计算结束的特定文件
#    PARAMETERS:
#         file_name [required] 标记计算结束的文件
#         check_list [optional] 用于记录完成计算的日志文件，默认为 finishedJobs.log
#       RETURNS: 返回日志文件
# ===============================================================================
def check_finished(file_name, check_list="finishedJobs.log"):
    cur_dir = os.getcwd()
    finished_log = os.path.join(cur_dir, check_list)
    unfinished_log = os.path.join(cur_dir, 'un' + check_list)

    with open(finished_log, 'w') as f_finished, open(unfinished_log, 'w') as f_unfinished:
        for folder in os.listdir(cur_dir):
            folder_path = os.path.join(cur_dir, folder)
            if os.path.isdir(folder_path):
                if os.path.isfile(os.path.join(folder_path, file_name)):
                    f_finished.write(folder_path + '\n')
                else:
                    f_unfinished.write(folder_path + '\n')


# === FUNCTION ================================================================
#          NAME: getFirstString
#   DESCRIPTION: 获取字符串中指定分隔符之前的部分
#    PARAMETERS:
#         parse_string [required] 要拆分的字符串
#         separator [required] 使用的分隔符
#       RETURNS: 返回分隔符之前的部分
# ===============================================================================
def get_first_string(parse_string, separator):
    first = parse_string.split(separator)[0].strip()
    return first


# === FUNCTION ================================================================
#          NAME: getRemainString
#   DESCRIPTION: 获取字符串中指定分隔符之后的部分
#    PARAMETERS:
#         parse_string [required] 要拆分的字符串
#         separator [required] 使用的分隔符
#       RETURNS: 返回分隔符之后的部分
# ===============================================================================
def get_remain_string(parse_string, separator):
    columns = parse_string.split(separator)
    if len(columns) > 1:
        return separator.join(columns[1:]).strip()
    else:
        return ""


# === FUNCTION ================================================================
#          NAME: stdOutWithTab
#   DESCRIPTION: 将命令的输出通过 paste 命令重定向，添加一定的制表符
#    PARAMETERS:
#         level [required] 制表符的级别
#       RETURNS: None
# ===============================================================================
def std_out_with_tab(level):
    tab_string = '\t' * level
    os.dup2(1, 3)
    os.dup2(3, 1)
    return tab_string


# === FUNCTION ================================================================
#          NAME: restoreStdOut
#   DESCRIPTION: 恢复正常的命令输出行为
#    PARAMETERS:
#       RETURNS: None
# ===============================================================================
def restore_std_out():
    os.dup2(1, 3)


# === FUNCTION ================================================================
#          NAME: getColumnOfIndex
#   DESCRIPTION: 获取 batchList.txt 中指定行列的值
#    PARAMETERS:
#             row [required] 行号
#             column [required] 列号
#       RETURNS: 返回 batchList.txt 中指定行列的值
# ===============================================================================
def get_column_of_index(index, column):
    with open("batchList.txt", 'r') as f:
        lines = f.readlines()
    line = lines[index]
    return line.split('|')[column].strip()


# === FUNCTION ================================================================
#          NAME: getVariableOfIndex
#   DESCRIPTION: 获取 batchList.txt 中指定行的所有变量（以 '|' 分隔）
#    PARAMETERS:
#             row [required] 行号
#       RETURNS: 返回 batchList.txt 中指定行的所有变量
# ===============================================================================
def get_variable_of_index(index):
    with open("batchList.txt", 'r') as f:
        lines = f.readlines()
    line = lines[index]
    return line.strip().split('|')[1:-1]


# === FUNCTION ================================================================
#          NAME: getVariableNumber
#   DESCRIPTION: 获取 batchList.txt 中的变量数目，等于列数减去 2（第一列为索引，最后一列为条件）
#    PARAMETERS:
#       RETURNS: 返回 batchList.txt 中的变量数量
# ===============================================================================
def get_variable_number():
    with open("batchList.txt", 'r') as f:
        first_line = f.readline()
        return len(first_line.split('|')) - 2


# === FUNCTION ================================================================
#          NAME: increaseIndex
#   DESCRIPTION: 增加多维索引的关键函数
#    PARAMETERS:
#         index_bound [required] 索引上限
#         current_index [required] 当前索引
#         choice [required] 每个索引的步长
#       RETURNS: 返回增加后的索引
# ===============================================================================
def increase_index(index_bound, current_index, choice):
    current_index = list(map(int, current_index.split()))
    index_bound = list(map(int, index_bound.split()))
    choice = list(map(int, choice.split()))

    index_count = len(current_index)
    increased = False

    hold = 1
    for i in range(index_count - 1, -1, -1):
        if i > 0:
            hold = choice[i - 1]

        if index_bound[i] > current_index[i]:
            increased = True
            current_index[i] += 1
            if choice[i] != hold:
                break
        else:
            current_index[i] = 1

    if not increased:
        return -1
    else:
        return ' '.join(map(str, current_index))


# === FUNCTION ================================================================
#          NAME: replaceKeywordsString
#   DESCRIPTION: 替换字符串中的关键字为相应的值
#    PARAMETERS:
#         string [required] 要处理的字符串
#         keyword_list [required] 关键字列表
#         variable_list [required] 变量列表
#         sep [optional] 关键字和变量列表的分隔符，默认是 '#'
#       RETURNS: 返回处理后的字符串
# ===============================================================================
def replace_keywords_string(string, keyword_list, variable_list, sep="#"):
    keyword = get_first_string(keyword_list, sep)
    keyword_remain = get_remain_string(keyword_list, sep)
    variable = get_first_string(variable_list, sep)
    variable_remain = get_remain_string(variable_list, sep)

    if keyword.startswith('@') or keyword.startswith('&'):
        result = string.replace(keyword[1:], variable)
    else:
        result = string.replace(keyword, variable)

    if keyword_remain:
        result = replace_keywords_string(result, keyword_remain, variable_remain, sep)

    return result


# === FUNCTION ================================================================
#          NAME: replaceKeywordsStringIndex
#   DESCRIPTION: 使用 batchList.txt 文件中指定行的值替换字符串中的关键字
#    PARAMETERS:
#         string [required] 要处理的字符串
#         index [required] batchList.txt 中的行索引
#       RETURNS: 返回处理后的字符串
# ===============================================================================
def replace_keywords_string_index(string, index):
    var_name = get_variable_of_index(0)
    var_val = get_variable_of_index(index)
    return replace_keywords_string(string, var_name, var_val, "|")


import os
import subprocess


# === FUNCTION ================================================================
#          NAME: replace_keywords_file
#   DESCRIPTION: 替换文件中的关键字与值，支持自由格式和固定格式文件
#    PARAMETERS:
#         file [required] - 文件名
#         var_name [required] - 关键字列表
#         var_val [required] - 关键字值列表
#         sep [required] - 关键字和值之间的分隔符
#       RETURNS: 处理后的文件
# ===============================================================================
def replace_keywords_file(file, var_name, var_val, sep):
    columns = len(var_name.split(sep))
    with open(file[1:], 'r+') as f:
        content = f.read()
        for i in range(columns):
            variable_name = var_name.split(sep)[0]
            var_name = sep.join(var_name.split(sep)[1:])
            variable_val = var_val.split(sep)[0]
            var_val = sep.join(var_val.split(sep)[1:])

            if file[0] == "&" or file[0] == "@":
                if file[0] == "&" and variable_name[0] != "@":
                    # 自由格式
                    if variable_name[0] == "&":
                        content = content.replace(f"{variable_name[1:]}", f"{variable_name[1:]} = {variable_val}")
                    else:
                        content = content.replace(f"{variable_name}", f"{variable_name} = {variable_val}")
                else:
                    # 固定格式
                    if variable_name[0] == "@":
                        content = content.replace(f"{variable_name[1:]}", variable_val)
                    else:
                        content = content.replace(f"{variable_name}", variable_val)

        f.seek(0)
        f.write(content)
        f.truncate()


# === FUNCTION ================================================================
#          NAME: replace_keywords_file_index
#   DESCRIPTION: 使用 batchList.txt 中指定行的值替换文件中的关键字
#    PARAMETERS:
#         file [required] - 文件名
#         index [required] - batchList.txt 中的行索引
#       RETURNS: 处理后的文件
# ===============================================================================
def replace_keywords_file_index(file, index):
    var_name = get_variable_of_index(0)
    var_val = get_variable_of_index(index)
    replace_keywords_file(file, var_name, var_val, "|")


# === FUNCTION ================================================================
#          NAME: get_folder_name
#   DESCRIPTION: 根据关键字名称和值对生成文件夹名
#    PARAMETERS:
#         index [required] - batchList.txt 中的行索引
#       RETURNS: 文件夹名称
# ===============================================================================
def get_folder_name(index):
    sep = get_column_of_index(0, 1)
    index_1 = index + 1
    first_line = get_variable_of_index(0)
    line = get_variable_of_index(index)
    columns = len(first_line.split("|"))
    columns_1 = columns - 1
    last_index = len(open('batchList.txt').readlines()) - 1
    digits = len(str(last_index))
    pad_index = f"{index:0{digits}d}"

    if sep == "/":
        name = ""
    else:
        name = f"{pad_index}{sep}"

    for j in range(2, columns):
        var_name = get_column_of_index(0, j).strip()
        if var_name[0] == "@":
            var_name = var_name[1:]
        var_val = get_column_of_index(index, j).strip()
        var_val = "_".join(var_val.split())

        if j == columns_1:
            sep = ""

        name += f"{var_name}_{var_val}{sep}"
    return name


# === FUNCTION ================================================================
#          NAME: create_folder_condition_one_line
#   DESCRIPTION: 根据 batchList.txt 的一行信息创建文件夹并复制文件
#    PARAMETERS:
#         index [required] - batchList.txt 中的行索引
#         file_list [required] - 需要处理并复制到文件夹中的文件列表
#       RETURNS: 创建文件夹并将处理后的文件复制到其中
# ===============================================================================
def create_folder_condition_one_line(index, file_list):
    name = get_folder_name(index)
    print(f"Create folder {name}")
    os.makedirs(name, exist_ok=True)
    for file in file_list:
        if file[0] == "&" or file[0] == "@":
            subprocess.run(f"cp {file[1:]} {name}/{file[1:]}", shell=True)
            replace_keywords_file_index(f"{file[0]}{name}/{file[1:]}", index)
        else:
            subprocess.run(f"cp {file} {name}/{file}", shell=True)
            replace_keywords_file_index(f"{name}/{file}", index)


# === FUNCTION ================================================================
#          NAME: print_info
#   DESCRIPTION: 打印 batchList.txt 文件中的一行信息
#    PARAMETERS:
#         name [required] - 关键字列表，使用 `sep` 分隔
#         val [required] - 对应的值列表，使用 `sep` 分隔
#         sep [required] - 分隔符
#       RETURNS: 打印一行关键字=value 格式的信息
# ===============================================================================
def print_info(name, val, sep):
    first_name = get_first_string(name, sep)
    remain_name = get_remain_string(name, sep)
    first_val = get_first_string(val, sep)
    remain_val = get_remain_string(val, sep)

    if remain_name:
        print(f"{first_name}={first_val} , ", end="")
        print_info(remain_name, remain_val, sep)
    else:
        print(f"{first_name}={first_val}")


# === FUNCTION ================================================================
#          NAME: write_batch_oneline
#   DESCRIPTION: 将一行数据写入 batchList.txt 文件
#    PARAMETERS:
#         line [required] - 包含所有列值的字符串
#       RETURNS: 将一行数据写入 batchList.txt 文件，列值之间用 `|` 分隔
# ===============================================================================
def write_batch_oneline(line):
    first = get_first_string(line, "#", "~")
    remain = get_remain_string(line, "#", "~")
    first_sep = first.replace(":", " ")

    if remain:
        with open("batchList.txt", "a") as f:
            f.write(f"{first_sep} | ")
            write_batch_oneline(remain)
    else:
        with open("batchList.txt", "a") as f:
            f.write(f"{first_sep}\n")








# === FUNCTION ================================================================
#          NAME: exec_folders_silent
#   DESCRIPTION: 静默执行文件夹中的命令
#    PARAMETERS:
#         command_string [required] - 需要执行的命令
#         start [optional] - 初始索引，默认为 1
#         end [optional] - 最后索引，默认为 batchList.txt 中的总行数
#       RETURNS: 无
# ===============================================================================
def exec_folders_silent(command_string, start=1, end=None):
    if end is None:
        end = len(open('batchList.txt').readlines()) - 1
    for i in range(start, end + 1):
        name = get_folder_name(i)
        temp_cmd = replace_keywords_string_index(command_string, i)
        os.chdir(name)
        subprocess.run(temp_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.chdir("..")


# === FUNCTION ================================================================
#          NAME: exec_folders_unfinished
#   DESCRIPTION: 在未完成的文件夹中执行命令
#    PARAMETERS:
#         command_string [required] - 需要执行的命令
#         file_name [required] - 标记任务是否完成的文件
#         start [optional] - 初始索引，默认为 1
#         end [optional] - 最后索引，默认为 batchList.txt 中的总行数
#       RETURNS: 打印执行的命令或已完成的文件夹
# ===============================================================================
def exec_folders_unfinished(command_string, file_name, start=1, end=None):
    if end is None:
        end = len(open('batchList.txt').readlines()) - 1
    for i in range(start, end + 1):
        name = get_folder_name(i)
        temp_cmd = replace_keywords_string_index(command_string, i)
        os.chdir(name)
        if file_name in os.listdir("."):
            print(f"Folder {name}, already finished, see {file_name}")
        else:
            print(f"Exec command: {command_string} in folder {name}")
            subprocess.run(temp_cmd, shell=True)
        os.chdir("..")


import os


# ===  FUNCTION  ================================================================
#          NAME: evaluate_each_field
#   DESCRIPTION: 对每个变量应用格式化
#    PARAMETERS:
#         expression [required] 变量列表，用 "sep" 分隔
#         folder_string [required] 关键字列表
#         sep [required] 分隔符
#         format [optional] 格式样式，可以是一个或多个，使用 "sep" 分隔
#       RETURNS: 格式化后的变量列表
# ===============================================================================
def evaluate_each_field(expression, folder_string, sep, format="%s"):
    remain = expression
    remain_folder = folder_string
    first = "anything"
    first_first = "anything"
    first_folder = "anything"
    hold = ""
    temp = ""
    curr_format = "%s"
    remain_format = format

    while remain:
        first = get_first_string(remain, sep)
        first_folder = get_first_string(remain_folder, sep)
        remain = get_remain_string(remain, sep)
        remain_folder = get_remain_string(remain_folder, sep)
        curr_format = get_first_string(remain_format, sep)
        format = get_remain_string(remain_format, sep)
        if format:
            remain_format = format

        # 以下部分需要根据需求进行调整和优化
        temp = ""
        while first:
            first_first = get_first_string(first, ":")
            first = get_remain_string(first, ":")
            temp += f'{curr_format % first_first}'
            if first:
                temp += ":"

        if hold:
            hold += sep + temp
        else:
            hold = temp

    return hold





# ===  FUNCTION  ================================================================
#          NAME: get_first_string
#   DESCRIPTION: 获取字符串的第一个部分
#    PARAMETERS:
#         string [required] 输入字符串
#         sep [required] 分隔符
#       RETURNS: 字符串的第一部分
# ===============================================================================
def get_first_string(string, sep):
    parts = string.split(sep)
    return parts[0] if parts else ''


# ===  FUNCTION  ================================================================
#          NAME: get_remain_string
#   DESCRIPTION: 获取字符串中剩余部分
#    PARAMETERS:
#         string [required] 输入字符串
#         sep [required] 分隔符
#       RETURNS: 剩余部分的字符串
# ===============================================================================
def get_remain_string(string, sep):
    parts = string.split(sep, 1)
    return parts[1] if len(parts) > 1 else ''


# ===  FUNCTION  ================================================================
#          NAME: replace_keywords_string
#   DESCRIPTION: 替换字符串中的关键字
#    PARAMETERS:
#         current_variable [required] 当前变量
#         folder_string [required] 文件夹字符串
#         original [required] 原始字符串
#         sep [required] 分隔符
#       RETURNS: 替换后的字符串
# ===============================================================================
def replace_keywords_string(current_variable, folder_string, original, sep):
    return original.replace(current_variable, folder_string)


# ===  FUNCTION  ================================================================
#          NAME: eval_condition
#   DESCRIPTION: 根据条件字符串判断条件是否满足
#    PARAMETERS:
#         condition_string [required] 条件字符串
#       RETURNS: 满足条件返回 True，不满足返回 False
# ===============================================================================
def eval_condition(condition_string):
    try:
        return eval(condition_string)
    except Exception as e:
        print(f"Condition evaluation error: {e}")
        return False


# ===  FUNCTION  ================================================================
#          NAME: write_batch_oneline
#   DESCRIPTION: 写入一行数据到 batchList.txt
#    PARAMETERS:
#         line [required] 要写入的行
#       RETURNS: None
# ===============================================================================
def write_batch_oneline(line):
    with open("batchList.txt", "a") as f:
        f.write(line + "\n")


# ===  FUNCTION  ================================================================
#          NAME: print_info
#   DESCRIPTION: 打印文件夹和处理后的变量信息
#    PARAMETERS:
#         folder_string [required] 文件夹字符串
#         processed_variable [required] 处理后的变量
#         sep [required] 分隔符
#       RETURNS: None
# ===============================================================================
def print_info(folder_string, processed_variable, sep):
    print(f"{folder_string}{sep}{processed_variable}")


# ===  FUNCTION  ================================================================
#          NAME: increase_index
#   DESCRIPTION: 增加索引
#    PARAMETERS:
#         variable_list_count [required] 变量列表计数
#         variable_index [required] 当前索引
#         increment_choice [required] 增量选择
#       RETURNS: 新的索引
# ===============================================================================
def increase_index(variable_list_count, variable_index, increment_choice):
    # 示例：增加索引的逻辑，根据具体需求调整
    if variable_index < variable_list_count:
        return variable_index + 1
    return -1




# 测试示例：列出每个目录的内容
if __name__ == "__main__":
    # 指定命令和目录模式
    test_command = "dir"
    test_folder_pattern = "./*"  # 当前目录下的所有子目录

    # 调用批量执行命令函数
    batch_all_command(test_command, test_folder_pattern)
    file_path = "example.json"  # 替换为你的 JSON 文件路径
    variable_name = "FreeFile"  # 替换为所需的变量名
    try:
        result = get_json_var(file_path, variable_name)
        print(result)
    except Exception as e:
        print(f"错误: {e}")
