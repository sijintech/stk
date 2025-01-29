import json
import subprocess
import os
import shutil
from datetime import datetime
import sys
import re
import argparse

#===============================================================================
#
#          FILE:  htpstudio
#
#         USAGE:  htpstudio [schedule|create|execute] [batch json file]
#
#   DESCRIPTION:  creating high-throughput jobs for high performance calculation
#
#       OPTIONS:  schedule, create, execute
#  REQUIREMENTS:  ---
#          BUGS:  ---
#         NOTES:  ---
#        AUTHOR:  Wen Tan, xiaotantanwo@gmail.com
#       COMPANY:
#       VERSION:  1.0
#       CREATED:  01/26/2025
#      REVISION:  ---
#===============================================================================

#===  FUNCTION  ================================================================
#          NAME: getJsonVar
#   DESCRIPTION: Use python to parse the json file and obtain the value of chosen
#                 keyword.
#    PARAMETERS:
#       Json file - String file name
#       Keyword - File, VarName, VarValue, Command, Condition, Separator, Format
#       RETURNS: Decorated string for the given keyword.
#===============================================================================


def getJsonVar(file_name, var_name):
    # open and read json file
    with open(file_name, 'r') as json_data:
        data = json.load(json_data)

    if var_name == "FreeFile":  # NewFile
        output = " ".join(["&" + name for name in data['FreeFile']])
    elif var_name == "FixFile":  # OldFile
        output = " ".join(["@" + name for name in data['FixFile']])
    elif var_name == "CopyFile":  # CopyFile
        output = " ".join(data['CopyFile'])
    elif var_name == "FreeVarName":  # New varName
        output = "#".join(["&" + name for name in data['FreeVarName']])
    elif var_name == "FixVarName":  # Old varName
        output = "#".join(["@" + name for name in data['FixVarName']])
    elif var_name == "DependVarName":  # Old varName
        output = "#".join(data['DependVarName'])
    elif var_name == "File":  # all files
        output_list = []
        output_list.append(" ".join(["&" + name for name in data['FreeFile']]))
        output_list.append(" ".join(["@" + name for name in data['FixFile']]))
        output_list.append(" ".join(data['CopyFile']))
        output = " ".join(output_list)
    elif var_name == "VarName":  # all var name
        output_list = []
        for var_seq in data['VarSequence']:
            temp = []
            prefix = ""
            if isinstance(var_seq, list):
                for var in var_seq:
                    if var in data['FreeVarName']:
                        prefix = "&"
                    elif var in data['FixVarName']:
                        prefix = "@"
                    else:
                        raise ValueError("The keyword not in Free or Fix VarName")
                    new_var = prefix + var
                    temp.append(new_var)
                output_list.append("~".join(temp))
            else:
                output_list.append(var_seq)
        output = "#".join(output_list)
    elif var_name == "VarValue":  # Var value
        output_list = []
        for var_seq in data['VarSequence']:
            temp = []
            if isinstance(var_seq, list):
                for var in var_seq:
                    temp_val = []
                    for val in data['VarValue'][var]:
                        temp_val.append(":".join(str(val).split()))
                    temp.append(" ".join(temp_val))
                output_list.append("~".join(temp))
            else:
                for val in data['VarValue'][var_seq]:
                    temp_val = ":".join(str(val).split())
                    temp.append(temp_val)
                output_list.append(" ".join(temp))
        output = "#".join(output_list)
    else:
        output = data.get(var_name, "")

    return output


#===  FUNCTION  ================================================================
#          NAME: parseJson
#   DESCRIPTION: Call getJsonVar to get needed values, and create a script for
#                 generating folder structures. Input json is batch.json
#    PARAMETERS: None
#       RETURNS: batch.sh script for generating htp jobs
#===============================================================================


def parseJson():
    file = getJsonVar('batch.json', 'File')
    varName = getJsonVar('batch.json', 'VarName')
    varValue = getJsonVar('batch.json', 'VarValue')
    command = getJsonVar('batch.json', 'Command')
    condition = getJsonVar('batch.json', 'Condition')
    separator = getJsonVar('batch.json', 'Separator')
    format = getJsonVar('batch.json', 'Format')

    schedule_args = {'k': varName, 'v': varValue, 'c': condition, 's': separator, 'f': format}
    create_args = {'f': file}
    execute_args = {'c': command}

    scheduleCommand(schedule_args)
    createCommand(create_args)
    executeCommand(execute_args)


#===  FUNCTION  ================================================================
#          NAME: getJobNum
#   DESCRIPTION: Get the amount of jobs currently you're running, including jobs from other sources
#                 The number is obtained by counting the number lines when using qstat command,
#                 if in your system, you have a different command please set the 2nd arguement. And we have a 5 lines
#                 of header for the qstat output, if when you qstat you have different amount of header lines
#                 please set the 3rd arguement to the number you need.
#    PARAMETERS:
#      User name [optional] String name, default value is `whoami`
#       RETURNS: Total number of all jobs.
#===============================================================================


def getJobNum(user_name=None, command="qstat", header=5):
    # 如果没有提供用户名，则使用当前用户
    if user_name is None:
        user_name = subprocess.getoutput("whoami")

    # 执行命令并获取输出
    try:
        result = subprocess.check_output([command, "-u", user_name], text=True)
        # 计算行数，减去 header 数量
        number_of_lines = len(result.splitlines())
        out = number_of_lines - header
        return out
    except subprocess.CalledProcessError as e:
        print(f"Error executing command {command}: {e}")
        return None


#===  FUNCTION  ================================================================
#          NAME: getRunning
#   DESCRIPTION: Get the amount of jobs currently you're running of only jobs submitted by htpstudio
#    PARAMETERS: None
#       RETURNS: Total number of running jobs.
#===============================================================================


def getRunning():
    # 获取当前用户
    user_name = subprocess.getoutput("whoami")

    # 获取 qstat 输出
    try:
        qstat_output = subprocess.check_output(["qstat", "-u", user_name], text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing qstat command: {e}")
        return None

    # 提取第6行之后的作业ID并保存到 allRunningList.log
    all_running_list_path = os.path.expanduser('~/allRunningList.log')
    with open(all_running_list_path, 'w') as file:
        lines = qstat_output.splitlines()[5:]  # 跳过前五行
        for line in lines:
            job_id = line.split()[0]  # 取作业ID，假设作业ID在第一列
            file.write(job_id + '\n')

    # 读取 originalList.log 和 allRunningList.log 进行 diff 比较
    original_list_path = os.path.expanduser('~/originalList.log')
    running_list_path = os.path.expanduser('~/runningList.log')

    try:
        with open(all_running_list_path, 'r') as all_file, open(original_list_path, 'r') as original_file:
            all_lines = set(all_file.readlines())
            original_lines = set(original_file.readlines())

        # 计算差异：allRunningList.log 中有，而 originalList.log 中没有的内容
        running_lines = all_lines - original_lines

        # 将差异保存到 runningList.log 文件
        with open(running_list_path, 'w') as running_file:
            running_file.writelines(running_lines)

        # 返回运行作业的数量
        running_number = len(running_lines)
        return running_number

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return None


#===  FUNCTION  ================================================================
#          NAME: registerToRun
#   DESCRIPTION: If the amount of jobs is too many, for example 1000, and your account
#                 can only submit 100 jobs at a time. You can create a job submission
#                 pool with this command, and automatically keep submiting new jobs once
#                 old ones are finished.
#    PARAMETERS:
#         Starting index - The initial calculation index as in batchList.txt file, default 1
#         Ending index - The ending calculation index in batchList.txt file, default last line
#         Registered folder - Identify the folder for auto job submission, default is current folder
#       RETURNS: Create a autoJobSubmission.sh file in your root directory.
#===============================================================================


def registerToRun(start=1, end=None, register_folder="."):
    # 设置文件路径
    to_run_list_path = os.path.expanduser('~/toRunList.log')
    finished_list_path = os.path.expanduser('~/finishedList.log')
    original_list_path = os.path.expanduser('~/originalList.log')
    auto_job_submission_script_path = os.path.expanduser('~/autoJobSubmission.sh')

    # 如果 ~/toRunList.log 文件存在，删除它并重新创建
    if os.path.exists(to_run_list_path):
        os.remove(to_run_list_path)

    # 创建 ~/toRunList.log 和 ~/finishedList.log 文件
    with open(to_run_list_path, 'w'), open(finished_list_path, 'w'):
        pass  # 创建空文件

    # 切换到指定的目录
    os.chdir(register_folder)

    # 获取当前目录
    current_folder = os.getcwd()

    # 如果 end 为 None，计算 end
    if end is None:
        try:
            with open('batchList.txt', 'r') as file:
                lines = file.readlines()
            end = len(lines) - 1
        except FileNotFoundError:
            print("batchList.txt not found.")
            return

    # 生成 toRunList.log 文件内容
    with open(to_run_list_path, 'a') as to_run_file:
        for i in range(start, end + 1):
            folder_name = getFolderName(i)
            to_run_file.write(f"{current_folder}/{folder_name}\n")

    # 执行 qstat 命令并保存输出到 ~/originalList.log
    try:
        qstat_output = subprocess.check_output(["qstat", "-u", "xuc116"], text=True)
        with open(original_list_path, 'w') as original_list_file:
            for line in qstat_output.splitlines()[5:]:  # 跳过前五行
                job_id = line.split()[0]  # 假设作业 ID 在第一列
                original_list_file.write(f"{job_id}\n")
    except subprocess.CalledProcessError as e:
        print(f"Error executing qstat command: {e}")
        return

    # 创建 autoJobSubmission.sh 脚本
    with open(auto_job_submission_script_path, 'w') as script_file:
        script_file.write('date;echo auto submitting;prepareNextRun 25 "qsub job.pbs" >> ~/autoJobSubmission.log\n')

    print(f"Files have been set up in {register_folder}.")
    print("Registration process completed.")


#===  FUNCTION  ================================================================
#          NAME: oneRun
#   DESCRIPTION: Get the next scheduled jobs (1st in toRun list) and perform some command in its folder
#    PARAMETERS:
#         Command - The command that you want to execute, default is echo folder name
#       RETURNS: Update the finishedList.log, toRunList.log
#===============================================================================
def oneRun(command="echo $folder"):
    to_run_list_path = os.path.expanduser('~/toRunList.log')
    finished_list_path = os.path.expanduser('~/finishedList.log')
    temp_list_path = os.path.expanduser('~/temp.log')
    original_list_path = os.path.expanduser('~/originalList.log')
    running_list_path = os.path.expanduser('~/runningList.log')
    all_running_list_path = os.path.expanduser('~/allRunningList.log')

    # Step 1: Read the first folder path from toRunList.log
    if os.path.exists(to_run_list_path):
        with open(to_run_list_path, 'r') as file:
            folder = file.readline().strip()
    else:
        print(f"{to_run_list_path} does not exist.")
        return

    # Step 2: Change to the folder and execute the command
    current_folder = os.getcwd()  # Store the current working directory
    os.chdir(folder)

    try:
        # Execute the provided command
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error executing the command: {e}")
        os.chdir(current_folder)  # Change back to the original directory
        return

    # Step 3: Return to the original folder
    os.chdir(current_folder)

    # Step 4: Update the toRunList.log and finishedList.log
    with open(to_run_list_path, 'r') as file:
        lines = file.readlines()

    # Add the first folder path to finishedList.log
    with open(finished_list_path, 'a') as finished_file:
        finished_file.write(f"{folder}\n")

    # Remove the first line from toRunList.log and update it
    with open(temp_list_path, 'w') as temp_file:
        temp_file.writelines(lines[1:])

    # Replace toRunList.log with the updated version
    shutil.move(temp_list_path, to_run_list_path)

    # Step 5: Check if toRunList.log is empty and clean up if necessary
    if os.stat(to_run_list_path).st_size == 0:
        os.remove(to_run_list_path)
        os.remove(original_list_path)
        os.remove(running_list_path)
        os.remove(all_running_list_path)

        # Add the current date to finishedList.log
        with open(finished_list_path, 'a') as finished_file:
            finished_file.write(f"Finished at: {datetime.now()}\n")

    print(f"Process completed for {folder}")


#===  FUNCTION  ================================================================
#          NAME: prepareNextRun
#   DESCRIPTION: Prepare the designated number jobs for next round of submission
#    PARAMETERS:
#         maxRun - Total number of jobs for next round of submission
#         Command - The command that you want to execute, default is echo folder name
#       RETURNS: Print in console number of current running jobs, and jobs to be run
#===============================================================================


def prepare_next_run(max_run=100, command="qsub cxx.pbs"):
    """根据当前作业数量决定是否提交新作业"""
    # 获取所有作业和当前正在运行的作业数量
    all_running_number = getJobNum()
    running_number = getRunning()

    # 计算最大可以提交的新作业数
    max_next_submit = max(0, 100 - all_running_number)
    allow_next_submit = max(0, max_run - running_number)

    # 获取待提交的作业数量
    to_run_list_path = os.path.expanduser('~/toRunList.log')

    with open(to_run_list_path, 'r') as file:
        jobs_left = sum(1 for _ in file.readlines())  # 计算 toRunList.log 中的行数

    next_submit = min(max_next_submit, allow_next_submit, jobs_left)

    print(f"Current running jobs: {running_number} ({all_running_number}), "
          f"to be submitted: {next_submit}, command: {command}")

    # 提交作业
    for _ in range(next_submit):
        oneRun(command)

    print(f"Process completed. Submitted {next_submit} jobs.")


#===  FUNCTION  ================================================================
#          NAME: checkFinished
#   DESCRIPTION: Go into one calculation folder and look or a specific file that mark the end of a calculation
#    PARAMETERS:
#         fileName [required] The file that marked the end of a calculation
#         checkList [optional] Text log file for recording the finished calculations, default is finishedJobs.log
#       RETURNS: The log file
#===============================================================================


def checkFinished(file_name, check_list="finishedJobs.log"):
    # 当前目录
    cur_dir = os.getcwd()

    # 删除文件
    if os.path.exists(check_list):
        os.remove(check_list)
    uncheck_list = f"un{check_list}"
    if os.path.exists(uncheck_list):
        os.remove(uncheck_list)

    # 假设你有一个目录列表，要检查每个目录中的文件
    # 对于每个目录，检查文件是否存在
    directories = []  # 需要处理的目录列表
    for folder in directories:
        folder_path = os.path.join(cur_dir, folder)

        # 检查文件是否存在
        if os.path.isfile(file_name):
            with open(check_list, 'a') as check_file:
                check_file.write(f"{folder_path}\n")
        else:
            with open(uncheck_list, 'a') as uncheck_file:
                uncheck_file.write(f"{folder_path}\n")

    print(f"Finished checking. Logs are saved in {check_list} and {uncheck_list}.")


#===  FUNCTION  ================================================================
#          NAME: getFirstString
#   DESCRIPTION: Get the part of string before a specific separator
#    PARAMETERS:
#         parse_string [required] The string that you want to split
#         separator [required] The separator you use
#       RETURNS: The string before the separator in the string you passed to this function
#===============================================================================


def getFirstString(parse_string, separator):
    # 使用 split() 分割字符串，获取第一个部分，并去除首尾空格
    first = parse_string.split(separator)[0].strip()
    return first


#===  FUNCTION  ================================================================
#          NAME: getRemainString
#   DESCRIPTION: Get the rest part of string after a specific separator
#    PARAMETERS:
#         parse_string [required] The string that you want to split
#         separator [required] The separator you use
#       RETURNS: The string after the separator in the string you passed to this function
#===============================================================================


def getRemainString(parse_string, separator):
    # 按照 separator 分割字符串
    parts = parse_string.split(separator)

    # 如果分割后的部分大于 1，表示有剩余部分
    if len(parts) > 1:
        # 返回分隔符后的部分，去除首尾空格
        return separator.join(parts[1:]).strip()
    else:
        # 如果没有分隔符，返回空字符串
        return ""


#===  FUNCTION  ================================================================
#          NAME: stdOutWithTab
#   DESCRIPTION: redirect the command output through paste command that add certain level of tab before
#    PARAMETERS:
#         level [required] tab levels
#       RETURNS: None
#===============================================================================
def stdOutWithTab(level):
    # 生成指定数量的 tab 字符
    tab_string = '\t' * level

    # 重定向标准输出，输出时加上 tab 字符
    def custom_print(*args, **kwargs):
        print(tab_string, end="")
        print(*args, **kwargs)

    # 替换原有的 print 函数
    sys.stdout = type(sys.stdout)(custom_print)


#===  FUNCTION  ================================================================
#          NAME: restoreStdOut
#   DESCRIPTION: restore the normal command output behaviour
#    PARAMETERS:
#       RETURNS: None
#===============================================================================
def restoreStdOut(origin_stdout):
    sys.stdout = origin_stdout


#===  FUNCTION  ================================================================
#          NAME: getColumnOfIndex
#   DESCRIPTION: Get the value of specific row and column in batchList.txt
#    PARAMETERS:
#             row [required] the row number, or the index number at column 1
#             column [required] the column number
#       RETURNS: the value at row, column in batchList.txt
#===============================================================================


def getColumnOfIndex(index, column, file_path="batchList.txt"):
    with open(file_path, 'r') as file:
        # 读取所有行并按行存储
        lines = file.readlines()

    # 获取指定的行（index从0开始，所以直接使用index）
    line = lines[index].strip()  # .strip() 用于去掉行末的换行符

    # 按 '|' 分割字段
    fields = line.split('|')

    # 获取指定列（注意 column 是从 1 开始的，所以要减去1进行索引）
    if column <= len(fields):
        var = fields[column - 1].strip()  # 去掉可能的空格
        return var
    else:
        return None  # 如果列号超出了行的字段数，则返回 None


#===  FUNCTION  ================================================================
#          NAME: getVariableOfIndex
#   DESCRIPTION: Get the value of specific row in batchList.txt, the variables are separted by '|'
#    PARAMETERS:
#             row [required] the row number, or the index number at column 1
#       RETURNS: all the variables at row in batchList.txt
#===============================================================================


def getVariableOfIndex(index, file_path="batchList.txt"):
    # 读取文件
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # 获取指定行 (index 从 0 开始，所以我们直接取 index 行)
    line = lines[index].strip()  # 去掉行末的空白字符

    # 根据 '|' 分割字符串，并获取从第二列开始的部分
    columns = line.split('|')[1:-1]

    # 重新合并列
    result = '|'.join([col[::1] for col in columns])

    return result


#===  FUNCTION  ================================================================
#          NAME: getVariableNumber
#   DESCRIPTION: Get the amount of variables in batchList.txt, which equals to number of columns -2
#                 since the first column is index, and the last column is condition
#    PARAMETERS:
#       RETURNS: Total number of variables listed in batchList.txt, column number - 2
#===============================================================================


def getVariableNumber(file_path="batchList.txt"):
    try:
        with open(file_path, 'r') as file:
            # 读取文件的第一行
            line = file.readline().strip()

            # 按照 '|' 分割这行
            columns = line.split('|')

            # 返回列数减去2
            return len(columns) - 2

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return None


#===  FUNCTION  ================================================================
#          NAME: increaseIndex
#   DESCRIPTION: One of the key function for batch job creation, for incrementing a multidimensional index
#                 $1 is the current index, $2 is the boundary of the index
#                 e.g. $1=1 1 1, $2=2 2 2, and the result will be 1 1 2
#                 e.g. $1=1 1 2, $2=2 2 2, and the result will be 1 2 1
#                 when the largest value is given, then the output will be -1
#                 e.g. $1=2 2 2, $2=2 2 2, and the result will be -1
#    PARAMETERS:
#         index_bound [required] the upper limits of indices, for example 2 2 2
#         current_index [required] the current indices, for example 1 1 1
#         choice [required] set the level of for each index, same number means at the same level
#                           only adjacent indices can be at the same level, for example 1 1 2 2 3, there are 3 levels
#       RETURNS: the incremeted indices
#===============================================================================


def increaseIndex(index_bound, current_index, choice):
    index_count = len(current_index)
    increased = False
    hold = 1

    # 从右向左遍历索引
    for i in range(index_count - 1, -1, -1):
        # 在第一轮时，hold保持选择的值
        if i > 0:
            hold = choice[i - 1]

        # 如果当前索引小于上限
        if index_bound[i] > current_index[i]:
            increased = True
            current_index[i] += 1  # 增加当前索引

            # 如果选择不等于hold，则终止
            if choice[i] != hold:
                break
        else:
            current_index[i] = 1  # 重置为1

    # 如果没有增加任何索引，返回 -1
    if not increased:
        return -1
    else:
        return current_index


#===  FUNCTION  ================================================================
#          NAME: replaceKeywordsString
#   DESCRIPTION: replacing the keywords in a string with the values provided
#    PARAMETERS:
#         string [required] the string you want to process
#         keyword_list [required] the list of keywords separated by 'separator'
#         variable_list [required] the list of variables separated by 'separator'
#         sep [optional] the separator char for keyword list an dvariable list, default is #
#       RETURNS: The processed string
#===============================================================================


def replaceKeywordsString(string, keyword_list, variable_list, sep="#", sep2="~"):
    keyword_list = keyword_list.split(sep)
    variable_list = variable_list.split(sep)
    # print("keyword_list", keyword_list)
    out = string

    for index, keyword in enumerate(keyword_list):
        variable = variable_list[index]
        # print("keyword", keyword)
        # print("variable_list", variable_list)
        # print(keyword.strip().startswith('@'))
        if keyword.strip().startswith('@') or keyword.strip().startswith('&'):
            out = (re.sub(re.escape(keyword.strip()[1:]), variable, out))
        else:
            out = (re.sub(re.escape(keyword.strip()), variable, out))

    return out


#===  FUNCTION  ================================================================
#          NAME: replaceKeywordsStringIndex
#   DESCRIPTION: replacing the keywords in a string with the values of specific line in batchList.txt file
#                 The keywords are obtained from the first line of the batchList.txt file
#    PARAMETERS:
#         string [required] the string you want to process
#         index [required] the line index in batchList.txt
#       RETURNS: The processed string
#===============================================================================


def replaceKeywordsStringIndex(string, index, file_path="batchList.txt"):
    # 获取变量
    var_name = getVariableOfIndex(0, file_path)
    var_val = getVariableOfIndex(index, file_path)
    # print("string", string)
    # print("var_name", var_name)
    # print("var_val", var_val)
    # 使用 replaceKeywordsString 来替换字符串中的关键字

    return replaceKeywordsString(string, var_name, var_val, sep="|")


#===  FUNCTION  ================================================================
#          NAME: replaceKeywordsFile
#   DESCRIPTION: replacing the keywords in a file with the values provided
#                 & sign before file name means its a free format file,
#                 that follows "keyword = value" format, and the value will be substitutes
#                 @ sign before file name means its a fix format file, they keyword
#                 $ sign before variable name (keyword) means substituting this variable with the free format style
#                 @ sign before variable name (keyword) means substituting this variable with the fix format style
#                 itself will be replaced.
#                 free format file can have both free format style variable and fix format variable
#                 fix format file can only have fix format variable
#    PARAMETERS:
#         file [required] file name
#         var_name [required] keyword list
#         var_val [required] keyword value list for substitution
#         sep [required] separator between keywords and keywords values
#       RETURNS: The processed file
#===============================================================================


def replaceKeywordsFile(file, var_name, var_val, sep):
    # 获取 var_name 和 var_val 的列数
    columns = len(var_name.split(sep))
    if file[0] == '&' or file[0] == '@':
        with open(file[1:], 'r') as f:
            content = f.read()
    else:
        with open(file, 'r') as f:
            content = f.read()

    for i in range(columns):
        # 获取 var_name 和 var_val 的每个部分
        variable_name = getFirstString(var_name, sep)
        var_name = getRemainString(var_name, sep)

        variable_val = getFirstString(var_val, sep)
        var_val = getRemainString(var_val, sep)

        # 处理替换规则
        if file[0] == '&' or file[0] == '@':
            if file[0] == '&' and variable_name[0] != '@':
                # Free format (直接替换)
                if variable_name[0] == '&':
                    content = re.sub(f"{re.escape(variable_name[1:])}", f"{variable_name[1:]} = {variable_val}", content)
                else:
                    content = re.sub(f"{re.escape(variable_name)}", f"{variable_name} = {variable_val}", content)
            else:
                # Fix format (逐行替换)
                if variable_name[0] == '@':
                    content = re.sub(f"{re.escape(variable_name[1:])}", variable_val, content)
                else:
                    content = re.sub(f"{re.escape(variable_name)}", variable_val, content)

    # 写回修改后的内容到文件
    if file[0] == '&' or file[0] == '@':
        with open(file[1:], 'w') as f:
            f.write(content)
    else:
        with open(file, 'w') as f:
            f.write(content)


#===  FUNCTION  ================================================================
#          NAME: replaceKeywordsFileIndex
#   DESCRIPTION: replace the keywords in file with value from a row in batchList.txt
#    PARAMETERS:
#         file [required] file name
#         index [required] line index of batchList.txt that to be substitute
#       RETURNS: The processed file
#===============================================================================


def replaceKeywordsFileIndex(file, index):
    # 获取 var_name 和 var_val
    var_name = getVariableOfIndex(0)
    var_val = getVariableOfIndex(index)

    # 调用 replace_keywords_file 函数进行替换
    replaceKeywordsFile(file, var_name, var_val, "|")


#===  FUNCTION  ================================================================
#          NAME: getFolderName
#   DESCRIPTION: generate the folder name based on variable name and value pairs
#                 for the separator between key-value pair, you may use "/" to create subfolders
#    PARAMETERS:
#         index [required] line index of batchList.txt that to be substitute
#       RETURNS: the folder name for one htp calculation which is named by keyword, value pairs
#===============================================================================


def getFolderName(index, file_path="batchList.txt"):
    # 读取 batchList.txt 文件
    try:
        with open(file_path, 'r') as file:
            columns = len(file.readline().strip().split('|'))
            lines = file.readlines()

        # 获取分隔符和其他必要的值
        sep = getColumnOfIndex(0, 1).strip()
        index_1 = index + 1
        first_line = getVariableOfIndex(0)
        line = getVariableOfIndex(index)

        # columns = len(line.split('|'))

        columns_1 = columns - 1
        last_index = len(lines)
        digits = len(str(last_index))

        # 格式化 pad_index
        pad_index = str(index).zfill(digits)

        if sep == "/":
            name = ""
        else:
            name = f"{pad_index}{sep}"

        for j in range(2, columns):
            var_name = getColumnOfIndex(0, j).strip()
            if var_name.startswith("@"):
                var_name = var_name[1:]

            var_val = getColumnOfIndex(index, j).strip().replace(" ", "_")

            if j == columns_1:
                sep = ""
            name += f"{var_name}_{var_val}{sep}"

        return name

    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        return None
    except IndexError:
        print(f"Error: Invalid index or file structure.")
        return None


#===  FUNCTION  ================================================================
#          NAME: createFolderConditionOneLine
#   DESCRIPTION: create the one folder based on information of one row in the batchList.txt
#                 and then copy the files into the folder
#    PARAMETERS:
#         index [required] line index of batchList.txt that to be substitute
#         fiel_list [required] list of files to be processed and copied into the folder
#       RETURNS: a folder with htp processed input files copied into it
#===============================================================================


def createFolderConditionOneLine(index, file_list, file_path="batchList.txt"):
    # 获取文件夹名称
    name = getFolderName(index, file_path)
    print(f"Create folder  {name}")
    file_list = file_list.split(' ')

    # 创建文件夹
    os.makedirs(name, exist_ok=True)
    # 遍历文件列表并进行处理
    for file in file_list:
        if file == '':
            pass
        elif file[0] == "&" or file[0] == "@":
            # 特殊处理路径前缀
            src_file = file[1:]
            dest_file = os.path.join(name, src_file)
            shutil.copy(src_file, dest_file)
            replaceKeywordsFileIndex(f"{file[0]}{dest_file}", index)
        else:
            # 正常处理
            dest_file = os.path.join(name, file)
            shutil.copy(file, dest_file)
            replaceKeywordsFileIndex(dest_file, index)


#===  FUNCTION  ================================================================
#          NAME: printInfo
#   DESCRIPTION: print the information when writing the batchList.txt file
#    PARAMETERS:
#         name [required] keywords list, separated by 'sep'
#         val [required] corresponding value list, separated by 'sep'
#         sep [required] separator char for keywords and values
#       RETURNS: print one line of keyword=value, for example printInfo "AAA#BBB" "111#222" "#"
#                will give output of AAA=111 , BBB=222
#===============================================================================


def printInfo(name, val, sep):
    # 获取第一个部分和剩余部分
    first_name, remain_name = getFirstString(name, sep), getRemainString(name, sep)
    first_val, remain_val = getFirstString(val, sep), getRemainString(val, sep)

    # 替换冒号为一个空格（类似于 Bash 中的 sed 's/:/ /g'）
    first_sep = first_val.replace(":", " ")

    # 打印当前部分
    if remain_name:
        # 如果还有剩余部分，打印当前部分并继续递归
        print(f"{first_name}={first_val} , ", end="")
        printInfo(remain_name, remain_val, sep)
    else:
        # 如果没有剩余部分，打印当前部分并换行
        print(f"{first_name}={first_val}")


#===  FUNCTION  ================================================================
#          NAME: writeBatchOneline
#   DESCRIPTION: Write one line of the batchList.txt file
#    PARAMETERS:
#         $1 [required] The string lists for the line, could be either the keywords or keyword values
#       RETURNS: write one line of variables into batchList.txt file, separated by "|"
#===============================================================================


def writeBatchOneline(columns, file_path="batchList.txt"):
    # 获取第一个部分和剩余部分
    first = getFirstString(columns, "#")
    remain = getRemainString(columns, "#")
    file = open(file_path, 'a')
    while remain:
        first_sep = first.replace(":", " ")
        file.write(f"{first_sep:15} | ")
        first = getFirstString(remain, '#')
        remain = getRemainString(remain, '#')

    file.write(f"{first:15}\n")
    file.close()

    # # 替换冒号为一个空格（类似于 Bash 中的 sed 's/:/ /g'）
    # first_sep = first.replace(":", " ")
    # print('first', first)
    # print('first_sep', first_sep)
    # with open(file_path, 'a') as file:
    #     if remain:
    #         # 打印当前部分并继续递归
    #         file.write(f"{first_sep:15} | ")
    #         writeBatchOneline(remain, file_path)
    #     else:
    #         # 打印当前部分并换行
    #         file.write(f"{first:15}\n")


#===  FUNCTION  ================================================================
#          NAME: makeFolders
#   DESCRIPTION: create all folders and copy the files into the folders
#    PARAMETERS:
#         file_list [required] the file list that need to be copied
#         start [optional] the initial index, default is 1
#         end [optional] the last index, default is total number of rows
#       RETURNS: None
#===============================================================================


def makeFolders(file_list, start=None, end=None, batch_list_file="batchList.txt"):
    # 计算文件的总行数
    if start is None:
        start = 1
    try:
        with open(batch_list_file, 'r') as f:
            lines = f.readlines()
            last_index = len(lines) - 1
    except FileNotFoundError:
        print(f"Error: The file '{batch_list_file}' was not found.")
        return

    # 如果没有指定 end, 则使用最后一行的索引
    if end is None:
        end = last_index

    # 循环处理每一行
    for i in range(start, end + 1):
        createFolderConditionOneLine(i, file_list)


#===  FUNCTION  ================================================================
#          NAME: execFolders
#   DESCRIPTION: execute commands inside the folders created from batchList.txt file
#    PARAMETERS:
#         command_string [required] the command to exec, notice you can use the keywords in the header line of batchList.txt file
#                                    and it will be substituted by the variable values for each folder
#         start [optional] the initial index, default is 1
#         end [optional] the last index, default is total number of rows
#       RETURNS: Print the command executed to screen
#===============================================================================


def execFolders(command_string, start=1, end=None, batch_list_file="batchList.txt"):
    origin_stdout = sys.stdout

    last_index = getEndIndex(batch_list_file)

    # 如果没有指定 end, 则使用最后一行的索引
    if end is None:
        end = last_index

    # 获取当前工作目录
    current_pwd = os.getcwd()

    temp_cmd = "temp command"

    for i in range(start, end + 1):
        # 获取文件夹名称
        folder_name = getFolderName(i)

        # 替换命令中的占位符
        temp_cmd = replaceKeywordsStringIndex(command_string, i)
        print("temp_cmd", temp_cmd)
        print(f"Exec command: {command_string} in folder {folder_name}")

        # 输出缩进（模仿 stdOutWithTab 进行缩进）
        print(stdOutWithTab(1))

        # 切换到目标文件夹
        os.chdir(folder_name)

        try:
            # 执行命令
            subprocess.run(temp_cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error executing command in folder {folder_name}: {e}")

        # 返回到原来的工作目录
        os.chdir(current_pwd)

        # 恢复标准输出
        restoreStdOut(origin_stdout)


#===  FUNCTION  ================================================================
#          NAME: execFoldersSilent
#   DESCRIPTION: execute commands inside the folders created from batchList.txt file silently
#    PARAMETERS:
#         command_string [required] the command to exec, notice you can use the keywords in the header line of batchList.txt file
#                                    and it will be substituted by the variable values for each folder
#         start [optional] the initial index, default is 1
#         end [optional] the last index, default is total number of rows
#       RETURNS: None
#===============================================================================


def execFoldersSilent(command_string, start=1, end=None, batch_list_file="batchList.txt"):
    origin_stdout = sys.stdout
    try:
        # 计算 batchList.txt 的总行数
        with open(batch_list_file, 'r') as f:
            lines = f.readlines()
            last_index = len(lines) - 1
    except FileNotFoundError:
        print(f"Error: The file '{batch_list_file}' was not found.")
        return

    # 如果没有指定 end, 则使用最后一行的索引
    end = end or last_index

    # 获取当前工作目录
    current_pwd = os.getcwd()

    for i in range(start, end + 1):
        # 获取文件夹名称
        folder_name = getFolderName(i)

        # 替换命令中的占位符
        temp_cmd = replaceKeywordsStringIndex(command_string, i)

        # 输出缩进（模仿 stdOutWithTab）
        stdOutWithTab(1)

        # 切换到目标文件夹
        os.chdir(folder_name)

        try:
            # 执行命令
            subprocess.run(temp_cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error executing command in folder {folder_name}: {e}")

        # 返回到原来的工作目录
        os.chdir(current_pwd)

        # 恢复标准输出
        restoreStdOut(origin_stdout)


#===  FUNCTION  ================================================================
#          NAME: execFoldersUnfinished
#   DESCRIPTION: execute commands inside the folders created from batchList.txt file silently
#    PARAMETERS:
#         command_string [required] the command to exec, notice you can use the keywords in the header line of batchList.txt file
#                                    and it will be substituted by the variable values for each folder
#         fileName [required] the file that marks the finish of a job
#         start [optional] the initial index, default is 1
#         end [optional] the last index, default is total number of rows
#       RETURNS: Print either "folder already finished" or "exec command" to screen
#===============================================================================


def execFoldersUnfinished(command_string, file_name, start=1, end=None, batch_list_file="batchList.txt"):
    origin_stdout = sys.stdout
    try:
        # 计算 batchList.txt 的总行数
        with open(batch_list_file, 'r') as f:
            lines = f.readlines()
            last_index = len(lines) - 1
    except FileNotFoundError:
        print(f"Error: The file '{batch_list_file}' was not found.")
        return

    # 如果没有指定 end, 则使用最后一行的索引
    end = end or last_index

    # 获取当前工作目录
    current_pwd = os.getcwd()

    for i in range(start, end + 1):
        # 获取文件夹名称
        folder_name = getFolderName(i)

        # 替换命令中的占位符
        temp_cmd = replaceKeywordsStringIndex(command_string, i)

        # 切换到目标文件夹
        os.chdir(folder_name)

        # 检查 batchList.txt 文件中是否包含当前文件夹路径
        if os.path.isfile(f"../{file_name}"):
            with open(f"../{file_name}", 'r') as file:
                lines = file.readlines()
                folder_path = os.path.abspath(folder_name)  # 获取当前文件夹的绝对路径
                if folder_path in [line.strip() for line in lines]:
                    print(f"Folder {folder_name}, already finished, see {file_name}")
                    os.chdir(current_pwd)
                    continue

        # 执行命令
        print(f"Exec command: {command_string} in folder {folder_name}")
        stdOutWithTab(1)

        try:
            subprocess.run(temp_cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error executing command in folder {folder_name}: {e}")

        # 恢复标准输出
        restoreStdOut(origin_stdout)

        # 返回到原来的工作目录
        os.chdir(current_pwd)


#===  FUNCTION  ================================================================
#          NAME: evaluateEachField
#   DESCRIPTION: apply the format to each of the variables
#    PARAMETERS:
#         expression [required] The variable list separated by "sep"
#         folder_string [required]  The keyword list
#         sep [required] The separator
#         format [optional] The format style, could be either one or several separated by "sep"
#       RETURNS: The formatted variable list
#===============================================================================


def evaluateEachField(expression_list, folder_string, sep, format="%s"):
    folder_list = folder_string.split(sep)
    expression_list = expression_list.split(sep)
    first_first = 'anything'
    first_folder = 'anything'
    hold = ""
    curr_format = '%s'
    remain_format = format
    for index, expression in enumerate(expression_list):
        first = expression
        first_folder = folder_list[index]

        curr_format = getFirstString(remain_format, sep)
        format = getRemainString(remain_format, sep)
        if format:
            remain_format = format

    # while remain:
    #     # 获取当前的字段
    #     first = getFirstString(remain, sep)
    #     first_folder = getFirstString(remain_folder, sep)

    #     # 剩余部分
    #     remain = getRemainString(remain, sep)
    #     remain_folder = getRemainString(remain_folder, sep)

    #     # 处理格式化
    #     curr_format = getFirstString(remain_format, sep)
    #     format = getRemainString(remain_format, sep)

        temp = ""

        # 对 first 字符串进行处理
        while first:
            first_first = getFirstString(first, ":")
            first = getRemainString(first, ":")

            # 使用 Python 格式化字符串
            bash_command = f'echo "{first_first}" | xargs printf "{curr_format}"'
            temp += subprocess.check_output(bash_command, shell=True, text=True)
            if first:  # 如果还有剩余的部分，添加分隔符
                temp += ":"

        # 拼接结果
        if hold == "":
            hold += temp
        else:
            hold = hold + sep + temp

    return hold


#===  FUNCTION  ================================================================
#          NAME: writeBatchList
#   DESCRIPTION: One of the most important function, generate the batchList.txt that
#                 is needed by all of the following steps, creating folders or executing commands
#                 the structure of batchList.txt file is like a table, each column is separated by "|"
#                 the first line of batchList.txt is the header line, first value is the separator for
#                 different variables when creating folder use the makeFolders command
#                 the last column is the condition column, and all columns in between are the variable columns
#    PARAMETERS:
#         $1 [required] The keyword list separated by "sep", use '~' when two variable change at the same time
#         $2 [required] The keyword value list separated by "sep", use '~' when two variable change at the same time
#         $3 [optional] The condition string for further control what will be added as one job
#         sep [required] The separator
#         format [optional] The format style, could be either one or several separated by "sep"
#       RETURNS: batchList.txt file
#===============================================================================


def writeBatchList(folder_string, variable_string, condition_string="1>0", sep="+", format="%s", file_path="batchList.txt"):
    origin_variable_string = variable_string
    folder_string = folder_string.replace("~", "#")
    variable_string = variable_string.replace("~", "#")

    # 递增选择逻辑
    incrementChoice = incrementChoiceProcess(origin_variable_string)

    # 获取变量列表数量
    variable_index = [1] * (variable_string.count("#") + 1)
    variable_list_count = [len(record.split()) for record in variable_string.split('#')]
    index = 0
    replaced_variable = ""
    current_condition = condition_string
    replaced_previous = ""
    processed_variable = ""

    # 清空文件
    if os.path.exists(file_path):
        os.remove(file_path)

    # 写入第一行
    writeBatchOneline(f"{sep}#{folder_string}#{condition_string}", file_path)

    while variable_index != -1:
        # 获取当前的变量字符串
        current_variable = currentVariableProcess(variable_string, variable_index)
        # print("increment_choice", incrementChoice)
        # print("variable_index", variable_index)
        # print("variable_string", variable_string)
        # print("current_variable", current_variable)
        replaced_variable = ""
        replaced_previous = current_variable
        while replaced_previous != replaced_variable:
            replaced_previous = current_variable
            replaced_variable = replaceKeywordsString(current_variable, folder_string, current_variable, "#")
            current_variable = replaced_variable

        # 处理格式化和其他字段
        processed_variable = evaluateEachField(replaced_variable, folder_string, "#", format)

        # 替换条件中的关键字
        current_condition = replaceKeywordsString(condition_string, folder_string, processed_variable, "#")
        # 判断条件是否成立
        bash_command = f"awk 'BEGIN{{if({current_condition}){{print \"true\"}}else{{print \"false\"}}}}'"
        result_str = subprocess.getoutput(bash_command)
        # print("result_str", result_str)
        if result_str.strip() == "true":
            index += 1
            print(f"Condition fulfilled: {current_condition}")

            # 记录输出
            with open(file_path, 'a') as file:
                print("\t", index, end="\t", flush=True)
                printInfo(folder_string, processed_variable, "#")
                writeBatchOneline(f"{index}#{processed_variable}#{current_condition}", file_path)
        else:
            print(f"Condition not fulfilled: {current_condition}")

        # 增加索引
        variable_index = increaseIndex(variable_list_count, variable_index, incrementChoice)


def incrementChoiceProcess(processStr):
    # 先根据 "#" 分割输入字符串为多个记录
    records = processStr.split('#')

    result = []

    # 对每个记录进行处理
    for record in records:
        # 根据 "~" 分割每条记录，获得字段数
        fields = record.split('~')

        # 如果字段数 >= 2，则记录的行号会多次输出，输出字段数次行号
        if len(fields) >= 2:
            result.extend([len(result) + 1] * len(fields))  # 这里 len(result) + 1 就是行号
        else:
            result.append(len(result) + 1)  # 只有一个字段时，输出一次行号

    return result


def currentVariableProcess(variable_string, variable_index):

    # 使用 "#" 分割字符串
    records = variable_string.split('#')
    result = ""

    # 遍历记录并按需要输出字段
    for i, record in enumerate(records):
        # 处理每个记录的字段（按空格分割）
        fields = record.split()

        if i > 0:  # 如果是第二条记录及以后
            # 输出 list_of_indices[i] 指定的字段，注意索引从 1 开始
            index = int(variable_index[i]) - 1  # 转换为 0 索引
            result += (f"#{fields[index]}")
        else:
            # 输出第一条记录的指定字段
            index = int(variable_index[i]) - 1  # 转换为 0 索引
            result += (fields[index])

    return result


#===  FUNCTION  ================================================================
#          NAME: batchAllCommand
#   DESCRIPTION: loop through all folders and execute a command
#    PARAMETERS:
#         command_string [required] the command you want to execute
#         $2 [optional]  integer that tune the indentation before output, default is 0
#       RETURNS: command output
#===============================================================================


def batchAllCommand(command_string, batch_depth=0):
    """
    该函数模拟 bash 中的 batchAllCommand，遍历所有子文件夹并执行命令
    :param command_string: 要执行的命令字符串
    :param batch_depth: 输出缩进级别
    """
    origin_stdout = sys.stdout
    # 获取当前目录路径
    current_dir = os.getcwd()

    # 获取所有子文件夹
    folder_array = [f for f in os.listdir('.') if os.path.isdir(f)]

    stdOutWithTab(batch_depth)

    if len(folder_array) == 1:
        print(f"Executing {command_string}")
        subprocess.run(command_string, shell=True)

    for dir in folder_array:
        if os.path.isdir(dir):
            print(f"Going into {dir}, from {current_dir}")
            os.chdir(dir)
            batch_depth_plus = batch_depth + 1
            restoreStdOut(origin_stdout)
            batchAllCommand(command_string, batch_depth_plus)  # 递归进入子文件夹并执行
            stdOutWithTab(batch_depth)
            os.chdir(current_dir)  # 返回上级目录
            print(f"Return from {dir}, to {current_dir}")

    restoreStdOut(origin_stdout)


# help message function


def usageStudio():
    help_text = """
`htpstudio` is a command for generating high-throughput jobs. It has three
subcommands, "schedule", "create", "execute", corresponding to the three phases
of high-throughput job generation. It is recommended to use a JSON configuration
file for controlling the command. But you may also pass variables directly to
the command as options.

Please refer to the user manual for more detailed documentation, or use 
"htpstudio schedule --help", "htpstudio create --help", "htpstudio execute --help" 
for brief introduction to each of the subcommands.
"""
    print(help_text)


def usageStudioShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    htpstudio schedule [json configuration file]
    htpstudio create [json configuration file]
    htpstudio execute [json configuration file]

Usage 2: Pass options instead of json configuration file
    htpstudio schedule -k|--keyword -v|--value [-c|--condition] [-s|--separater] [-f|--format] [-h|--help]
    htpstudio create [-h|--help] [-s|--start] [-e|--end] -f|--file ... 
    htpstudio execute [-h|--help] [-s|--start] [-e|--end] -f|--file ... 
"""
    print(help_text)


def usageSchedule():
    help_text = """
'schedule' is one of the sub-commands of htpstudio -
  schedule the folders and jobs, and create a batchList.txt file which contains
  all of the information needed for further 'create' and 'execute'. 'schedule'
  is the first phase of high-throughput jobs generation. Please refer to the
  user manual for more detailed explanations.

Usage 1 (Recommended): 
  htpstudio schedule [json configuration file]
  
  The recommended usage requires access to python. It will use the json module.
  The json configuration file contains all of the information needed to schedule
  jobs and create batchList.txt file. The identifiable keywords in the json file
  that are related to the 'schedule' command are listed below.

  List of json keywords related to 'schedule' phase:
    "FreeVarName"   A list of free format style variable names
    "FixVarName"    A list of fix format style variable names
    "VarValue"      A list of key value pairs for all fix and free "VarName"
    "VarSequence"   A list variable names to set the sequence of varying
                    keywords, and dependence between variables
    "Separator"     A char to separate keywords in the created folder names
    "Format"        A c style format for variable values in the batchList.txt
    "Condition"     A conditional statement for filtering schedule jobs

Example of usage 1:
  htpstudio schedule batch.json


Usage 2 (Not recommended): 
  htpstudio schedule [OPTION] 

  This type of usage is not recommended because it is not as easy to use as the
  previous one. But if you don't have python on your machine, you can use this
  style as this one is a pure bash shell script.

  -k, --keyword     A string that contains list keywords to loop through
  -v, --value       A string that contains the values for each keyword
  -c, --condition   A conditional statement to filter the scheduled jobs
  -s, --separater   A char used to separate keywords in the created folder names
  -f, --format      A c style format to set value format in batchList.txt
  -h, --help        Print helper information

Example of usage 2:
  htpstudio schedule -k "VAR1#@VAR2" -v "1 2 3#10 20 30" -c "1>0" -f "%s" -s "+"
"""
    print(help_text)


def usageScheduleShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    htpstudio schedule [json configuration file]

Usage 2: Pass options instead of json configuration file
    htpstudio schedule -k|--keyword -v|--value [-c|--condition] [-s|--separater] [-f|--format] [-h|--help]

Example:

    htpstudio schedule -k "@FREQ#PERIOD" -v "1e12 1e13#1e12/FREQ" -c "FREQ>1e9" -f "%.2e"
"""
    print(help_text)


def usageCreate():
    help_text = """
`create' is one of the sub-command of htpstudio - 
  create the folders, copy and modify input files into each folder according to
  the information listed in batchList.txt file. 'create' is the second phase of 
  high-throughput jobs generation. Please refer to the user manual for more 
  detailed explanations.

Usage 1 (Recommended): 
  htpstudio create [json configuration file]
  
  The recommended usage requires access to python. It will use the json module.
  The command will read necessary input files from the json configuration file
  and the keywords value pairs from batchList.txt file. The identifiable keywords 
  in the json file that are related to the 'create' command are listed below.

  List of json keywords related to 'create' phase:
    "FreeFile"   A list of free format style input file
    "FixFile"    A list of fix format style input file
    "CopyFile"   A list of file that you only want to copy and change nothing

Example of usage 1:
  htpstudio create batch.json


Usage 2 (Not recommended): 
  htpstudio create [OPTION] 

  This type of usage is not recommended because it is not as easy to use as the 
  previous one. But if you don't have python on your machine, you can use this
  style as this one is a pure bash shell script.

  -f, --file      A list of file names, decorator before the file name set the 
                  type of the file, @ for fix format, & for free format, and 
                  nothing for copy file
  -s, --start     The starting index in batchList.txt for creation
  -e, --end       The ending index in batchList.txt for creation
  -h, --help      Print helper information

Example of usage 2:
  htpstudio create -f "&input.in @jobs.pbs pot.in"
"""
    print(help_text)


def usageCreateShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    htpstudio create [json configuration file] [-s|--start] [-e|--end]

Usage 2: Pass options instead of json configuration file
    htpstudio create [-h|--help] [-s|--start] [-e|--end] -f|--file ... 

Example:

    htpstudio create -k "&input.in @jobs.pbs pot.in"
"""
    print(help_text)


def usageExecute():
    help_text = """
`execute` is one of the sub-command of htpstudio - 
  execute commands in the folders created using batchList.txt file. 'execute' 
  is the third phase of high-throughput jobs generation. Please refer to the 
  user manual for more detailed explanations.

Usage 1 (Recommended): 
  htpstudio execute [json configuration file]
  
  The recommended usage requires access to python. It will use the json module.
  The command will read necessary input files from the json configuration file
  and the keywords value pairs from batchList.txt file. The identifiable keywords 
  in the json file that are related to the 'create' command are listed below.

  List of json keywords related to 'schedule' phase:
    "Command"     A string, which is the command to be executed in each folder

Example of usage 1:
  htpstudio execute batch.json

Usage 2 (Not recommended): 
  htpstudio execute [OPTION] 

  This type of usage is not recommended because it is not as easy to use as the 
  previous one. But if you don't have python on your machine, you can use this
  style as this one is a pure bash shell script.

  -c, --command   A string, which is the command to be executed in each folder
  -s, --start     The starting index in batchList.txt for creation
  -e, --end       The ending index in batchList.txt for creation
  -h, --help      Print helper information

Example of usage 2:
  htpstudio execute -c "python script.py" -s 1 -e 10
"""
    print(help_text)


def usageExecuteShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    htpstudio execute [json configuration file] [-s|--start] [-e|--end]

Usage 2: Pass options instead of json configuration file
    htpstudio execute [-h|--help] [-s|--start] [-e|--end] -f|--file ... 

Example:

    htpstudio execute "echo FREQ"
    htpstudio execute "qsub Ferro.pbs"
"""
    print(help_text)


def printArguements():
    print(f"Command is {sys.argv[1]}")  # 打印第一个参数
    for index, arg in enumerate(sys.argv[2:], start=1):  # 从第二个参数开始遍历
        print(f"Argument {index}: {arg}")


def custom_subcommand_help(command=None):
    """自定义的帮助信息函数，按子命令显示"""
    if command == 'schedule':
        usageSchedule()
    elif command == 'create':
        usageCreate()
    elif command == 'execute':
        usageExecute()
    else:
        usageStudio()


class CustomArgumentParser(argparse.ArgumentParser):

    def print_help(self, file=None):
        """重写 print_help 方法，调用自定义帮助函数"""
        # command = self.args.command if hasattr(self, 'args') else None
        command = self.prog.split()[-1]
        custom_subcommand_help(command)


# parse args
def parseArgs():
    parser = CustomArgumentParser(prog="htpstudio")

    subparsers = parser.add_subparsers(dest="command")

    # Schedule command
    schedule_parser = subparsers.add_parser("schedule", help="Create the batchList.txt file")
    schedule_parser.add_argument("-k", "--keyword", type=str, default=None, help="Keywords for batch list", required=False)
    schedule_parser.add_argument("-v", "--value", type=str, default=None, help="Values for each keyword", required=False)
    schedule_parser.add_argument("-c", "--condition", help="Condition for filtering jobs", default="1>0")
    schedule_parser.add_argument("-s", "--separater", help="Separator", default="+")
    schedule_parser.add_argument("-f", "--format", help="Format", default="%s")
    schedule_parser.add_argument("json_file", nargs="?", help="JSON configuration file for scheduling")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create the folder structure")
    create_parser.add_argument("-f", "--file", help="Files to copy", type=str, required=False)
    create_parser.add_argument("-s", "--start", type=int, help="Start index", default=None)
    create_parser.add_argument("-e", "--end", type=int, help="End index", default=None)
    create_parser.add_argument("json_file", nargs="?", help="JSON configuration file for creating folders")

    # Execute command
    execute_parser = subparsers.add_parser("execute", help="Execute command for each folder")
    execute_parser.add_argument("-c", "--exec_command", help="Command to execute in each folder", required=False)
    execute_parser.add_argument("-s", "--start", type=int, help="Start index", default=None)
    execute_parser.add_argument("-e", "--end", type=int, help="End index", default=None)
    execute_parser.add_argument("json_file", nargs="?", help="JSON configuration file for executing command")

    args = parser.parse_args()

    return args


# schedule function
def scheduleCommand(args):
    condition_string = "1 > 0"
    format_str = "%s"
    separator = "+"
    folder_set = False
    variable_set = False
    json_set = False
    folder_string = ""
    variable_string = ""

    # 如果传递了 JSON 配置文件
    # print("args.json_file", args.json_file)
    if args.json_file is not None:
        json_set = True
        print("Stage 1: Create the batchList.txt file")
        print(f"Using the {args.json_file} configuration file")

        var_name = getJsonVar(args.json_file, "VarName")
        var_value = getJsonVar(args.json_file, "VarValue")
        condition = getJsonVar(args.json_file, "Condition")
        separator = getJsonVar(args.json_file, "Separator")
        format_str = getJsonVar(args.json_file, "Format")
        if var_name and var_value:
            writeBatchList(var_name, var_value, condition, separator, format_str)

    if json_set == False:
        if args.keyword is None or args.value is None:
            usageScheduleShort()
            return
        print("Stage 1: Create the batchList.txt file")
        print("Using options from command line.")

        folder_string = args.keyword
        variable_string = args.value
        condition_string = args.condition
        separator = args.separater
        format_str = args.format

        if args.keyword is None:
            raise ValueError("The -k or --keyword option is mandatory for batch list command, which sets the keywords for creating the batchList.txt file.")
        if variable_set is None:
            raise ValueError("The -v or --value option is mandatory for batch list command, which sets the sweeping values for each keyword in the input file.")

        # 解析关键字和变量值，生成 batchList.txt
        writeBatchList(folder_string, variable_string, condition_string, separator, format_str)


# create function
def createCommand(args):
    file_set = False
    json_set = False

    # if len(args) <= 1:
    #     usageCreateShort()

    start = args.start
    end = args.end
    file_list = args.file
    if file_list is not None:
        file_set = True
    if args.json_file is not None:
        print("Stage 2: Create the folder structure")
        print(f"Using the {args.json_file} configuration file")
        file_list = getJsonVar(args.json_file, "File")
        file_set = True

    if json_set == False:
        if file_set == True:
            makeFolders(file_list, start, end)
        else:
            raise ValueError("The -f or --file option is mandatory.")


def getEndIndex(file_path):
    """ 计算文件中的行数并返回行数减去 1 的值 """
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            return len(lines) - 1  # 减去 1 得到最后一个索引
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def executeCommand(args):
    """ Main function to execute the provided command in each folder. """
    command_set = False
    json_set = False  # 源码里这个json_set根本不会为True啊
    start = 1
    end = getEndIndex("batchList.txt")
    exec_command = "ls"  # Default command if none provided

    if args.start is not None:
        start = args.start

    if args.end is not None:
        end = args.end

    if args.exec_command is not None:
        exec_command = args.exec_command
        command_set = True
    elif args.json_file:
        json_command = getJsonVar(args.json_file, "Command")
        if json_command:
            exec_command = json_command
            command_set = True

    if not command_set:
        if not args.command:
            print("The -c or --command option is mandatory if no JSON file is provided.")
            return
    else:
        print(f"Executing command: {exec_command} from index {start} to {end}")
        execFolders(exec_command, start, end)


# main function
def runCommand():
    args = parseArgs()
    if args.command == 'schedule':
        scheduleCommand(args)
    elif args.command == 'create':
        createCommand(args)
    elif args.command == 'execute':
        executeCommand(args)
    else:
        print("Unknown command. Use --help for usage instructions.")


if __name__ == '__main__':
    runCommand()
