import json
import subprocess
import os
import shutil
from datetime import datetime
import sys
import re
import argparse
import getpass
import click

#===============================================================================
#
#          FILE:  sjob
#
#         USAGE:  sjob [schedule|create|execute] [batch json file]
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


@click.group()
def sjob():
    pass


def getShell():
    if os.name == 'nt':
        return 'powershell'
    else:
        return 'bash'


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
    # Use current user if user_name is not provided
    if user_name is None:
        user_name = getpass.getuser()
    # Execute the command and get the output
    try:
        if os.name != 'nt':
            result = subprocess.check_output([command, "-u", user_name], text=True)
            # Calculate the number of lines, subtracting the header count
            number_of_lines = len(result.splitlines())
            out = number_of_lines - header
            return out
        else:
            print("Windows 系统可能没有直接对应的作业查询命令，请根据实际情况修改。")
            return None
    except subprocess.CalledProcessError as e:
        print(f"Error executing command {command}: {e}")
        return None


#===  FUNCTION  ================================================================
#          NAME: getRunning
#   DESCRIPTION: Get the amount of jobs currently you're running of only jobs submitted by sjob
#    PARAMETERS: None
#       RETURNS: Total number of running jobs.
#===============================================================================


def getRunning():
    # Get the current user
    user_name = getpass.getuser()

    # Get the output of the qstat command
    try:
        if os.name != 'nt':
            qstat_output = subprocess.check_output(["qstat", "-u", user_name], text=True)
        else:
            print("Windows 系统可能没有直接对应的作业查询命令，请根据实际情况修改。")
            return None
    except subprocess.CalledProcessError as e:
        print(f"Error executing qstat command: {e}")
        return None

    # Extract job IDs from lines after the 6th line and save to allRunningList.log
    all_running_list_path = os.path.expanduser('~/allRunningList.log')
    with open(all_running_list_path, 'w') as file:
        lines = qstat_output.splitlines()[5:]  # Skip the first five lines
        for line in lines:
            job_id = line.split()[0]  # Assume the job ID is in the first column
            file.write(job_id + '\n')

    # Read originalList.log and allRunningList.log to perform a diff comparison
    original_list_path = os.path.expanduser('~/originalList.log')
    running_list_path = os.path.expanduser('~/runningList.log')

    try:
        with open(all_running_list_path, 'r') as all_file, open(original_list_path, 'r') as original_file:
            all_lines = set(all_file.readlines())
            original_lines = set(original_file.readlines())

        # Calculate the difference: lines in allRunningList.log that are not in originalList.log
        running_lines = all_lines - original_lines

        # Save the differences to runningList.log
        with open(running_list_path, 'w') as running_file:
            running_file.writelines(running_lines)

        # Return the number of running jobs
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
    # Set file paths
    to_run_list_path = os.path.expanduser('~/toRunList.log')
    finished_list_path = os.path.expanduser('~/finishedList.log')
    original_list_path = os.path.expanduser('~/originalList.log')
    auto_job_submission_script_path = os.path.expanduser('~/autoJobSubmission.sh')

    # If the ~/toRunList.log file exists, delete it and recreate it
    if os.path.exists(to_run_list_path):
        os.remove(to_run_list_path)

    # Create ~/toRunList.log and ~/finishedList.log files
    with open(to_run_list_path, 'w'), open(finished_list_path, 'w'):
        pass  # Create empty files

    # Change to the specified directory
    os.chdir(register_folder)

    # Get the current directory
    current_folder = os.getcwd()

    # If end is None, calculate end
    if end is None:
        try:
            with open('batchList.txt', 'r') as file:
                lines = file.readlines()
            end = len(lines) - 1
        except FileNotFoundError:
            print("batchList.txt not found.")
            return

    # Generate the content of the ~/toRunList.log file
    with open(to_run_list_path, 'a') as to_run_file:
        for i in range(start, end + 1):
            folder_name = getFolderName(i)
            to_run_file.write(f"{current_folder}/{folder_name}\n")

    # Execute the qstat command and save the output to ~/originalList.log
    try:
        if os.name != 'nt':
            qstat_output = subprocess.check_output(["qstat", "-u", "xuc116"], text=True)
        else:
            print("Windows 系统可能没有直接对应的作业查询命令，请根据实际情况修改。")
        with open(original_list_path, 'w') as original_list_file:
            for line in qstat_output.splitlines()[5:]:  # Skip the first five lines
                job_id = line.split()[0]  # Assume the job ID is in the first column
                original_list_file.write(f"{job_id}\n")
    except subprocess.CalledProcessError as e:
        print(f"Error executing qstat command: {e}")
        return

    # Create the autoJobSubmission.sh script
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
        result = subprocess.run([getShell(), '-c', command], shell=False, text=True, capture_output=True)
        print(result.stdout)
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
    """Decide whether to submit new jobs based on the current number of jobs."""
    # Get the total number of jobs and the number of currently running jobs
    all_running_number = getJobNum()
    running_number = getRunning()

    # Calculate the maximum number of new jobs that can be submitted
    max_next_submit = max(0, 100 - all_running_number)
    allow_next_submit = max(0, max_run - running_number)

    # Get the number of jobs waiting to be submitted
    to_run_list_path = os.path.expanduser('~/toRunList.log')

    with open(to_run_list_path, 'r') as file:
        jobs_left = sum(1 for _ in file.readlines())  # Count the number of lines in toRunList.log

    next_submit = min(max_next_submit, allow_next_submit, jobs_left)

    print(f"Current running jobs: {running_number} ({all_running_number}), "
          f"to be submitted: {next_submit}, command: {command}")

    # Submit jobs
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
    # Get the current directory
    cur_dir = os.getcwd()

    # Remove the files if they exist
    if os.path.exists(check_list):
        os.remove(check_list)
    uncheck_list = f"un{check_list}"
    if os.path.exists(uncheck_list):
        os.remove(uncheck_list)

    # Assume you have a list of directories to check for the file
    # For each directory, check if the file exists
    directories = []  # List of directories to process
    for folder in directories:
        folder_path = os.path.join(cur_dir, folder)

        # Check if the file exists in the directory
        if os.path.isfile(os.path.join(folder_path, file_name)):
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
    # Split the string using the specified separator and get the first part, stripping any leading or trailing spaces
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
    # Split the string by the specified separator
    parts = parse_string.split(separator)

    # If there are more than one part after splitting, it means there is a remainder
    if len(parts) > 1:
        # Return the part after the separator, stripping any leading or trailing spaces
        return separator.join(parts[1:]).strip()
    else:
        # If the separator is not found, return an empty string
        return ""


#===  FUNCTION  ================================================================
#          NAME: stdOutWithTab
#   DESCRIPTION: redirect the command output through paste command that add certain level of tab before
#    PARAMETERS:
#         level [required] tab levels
#       RETURNS: None
#===============================================================================
def stdOutWithTab(level):
    # Generate the specified number of tab characters
    tab_string = '\t' * level

    # # Redirect the standard output to include tab characters when printing
    # def custom_print(*args, **kwargs):
    #     print(tab_string, end="")
    #     print(*args, **kwargs)

    # # Replace the original print function
    # sys.stdout = type(sys.stdout)(custom_print)
    return tab_string


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
        # Read all lines and store them as a list
        lines = file.readlines()

    # Get the specified line (index starts from 0, so use index directly)
    line = lines[index].strip()  # .strip() is used to remove the newline character at the end of the line

    # Split the fields by '|'
    fields = line.split('|')

    # Get the specified column (note that column starts from 1, so subtract 1 for indexing)
    if column <= len(fields):
        var = fields[column - 1].strip()  # Remove any possible spaces
        return var
    else:
        return None  # If the column number exceeds the number of fields in the line, return None


#===  FUNCTION  ================================================================
#          NAME: getVariableOfIndex
#   DESCRIPTION: Get the value of specific row in batchList.txt, the variables are separted by '|'
#    PARAMETERS:
#             row [required] the row number, or the index number at column 1
#       RETURNS: all the variables at row in batchList.txt
#===============================================================================


def getVariableOfIndex(index, file_path="batchList.txt"):
    # Read the file
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Get the specified line (index starts from 0, so we directly take the index line)
    line = lines[index].strip()  # Remove trailing whitespace characters

    # Split the string by '|' and get the part starting from the second column
    columns = line.split('|')[1:-1]  # Exclude the first and last columns

    # Rejoin the columns
    result = '|'.join([col[::1] for col in columns])  # This part seems redundant as col[::1] is the same as col

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
            # Read the first line of the file
            line = file.readline().strip()

            # Split the line by '|'
            columns = line.split('|')

            # Return the number of columns minus 2
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

    # Traverse the index from right to left
    for i in range(index_count - 1, -1, -1):
        # In the first round, hold keeps the value of the choice
        if i > 0:
            hold = choice[i - 1]

        # If the current index is less than the upper limit
        if index_bound[i] > current_index[i]:
            increased = True
            current_index[i] += 1  # Increase the current index

            # If the choice is not equal to hold, terminate
            if choice[i] != hold:
                break
        else:
            current_index[i] = 1  # Reset to 1

    # If no index has been increased, return -1
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
    # Get the variable names and values
    var_name = getVariableOfIndex(0, file_path)  # Get variable names from the first line
    var_val = getVariableOfIndex(index, file_path)  # Get variable values from the specified line

    # Debugging prints (optional)
    # print("string", string)
    # print("var_name", var_name)
    # print("var_val", var_val)

    # Use replaceKeywordsString to replace keywords in the string

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
    # Get the number of columns in var_name and var_val
    columns = len(var_name.split(sep))
    if file[0] == '&' or file[0] == '@':
        with open(file[1:], 'r') as f:
            content = f.read()
    else:
        with open(file, 'r') as f:
            content = f.read()

    for i in range(columns):
        # Get each part of var_name and var_val
        variable_name = getFirstString(var_name, sep)
        var_name = getRemainString(var_name, sep)

        variable_val = getFirstString(var_val, sep)
        var_val = getRemainString(var_val, sep)

        # Handle replacement rules
        if file[0] == '&' or file[0] == '@':
            if file[0] == '&' and variable_name[0] != '@':
                # Free format (direct replacement)
                if variable_name[0] == '&':
                    content = re.sub(f"{re.escape(variable_name[1:])}", f"{variable_name[1:]} = {variable_val}", content)
                else:
                    content = re.sub(f"{re.escape(variable_name)}", f"{variable_name} = {variable_val}", content)
            else:
                # Fixed format (line-by-line replacement)
                if variable_name[0] == '@':
                    content = re.sub(f"{re.escape(variable_name[1:])}", variable_val, content)
                else:
                    content = re.sub(f"{re.escape(variable_name)}", variable_val, content)

    # Write the modified content back to the file
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
    # Get var_name and var_val
    var_name = getVariableOfIndex(0)  # Get variable names from the first line
    var_val = getVariableOfIndex(index)  # Get variable values from the specified line

    # Call the replaceKeywordsFile function to perform the replacement
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
    # Read the batchList.txt file
    try:
        with open(file_path, 'r') as file:
            columns = len(file.readline().strip().split('|'))  # Get the number of columns
            lines = file.readlines()  # Read all lines

        # Get the separator and other necessary values
        sep = getColumnOfIndex(0, 1).strip()  # Get the separator from the first line, second column
        index_1 = index + 1
        first_line = getVariableOfIndex(0)  # Get the first line variables
        line = getVariableOfIndex(index)  # Get the variables from the specified line

        columns_1 = columns - 1  # Number of columns minus one
        last_index = len(lines)  # Total number of lines
        digits = len(str(last_index))  # Number of digits in the last index

        # Format pad_index
        pad_index = str(index).zfill(digits)  # Zero-pad the index to match the number of digits

        if sep == "/":
            name = ""  # If the separator is "/", do not prepend the index
        else:
            name = f"{pad_index}{sep}"  # Prepend the zero-padded index and separator

        for j in range(2, columns):  # Iterate through the columns starting from the third column
            var_name = getColumnOfIndex(0, j).strip()  # Get the variable name from the first line
            if var_name.startswith("@"):
                var_name = var_name[1:]  # Remove "@" if present

            var_val = getColumnOfIndex(index, j).strip().replace(" ", "_")  # Get the variable value and replace spaces with underscores

            if j == columns_1:
                sep = ""  # No separator for the last column
            name += f"{var_name}_{var_val}{sep}"  # Append the formatted variable name and value

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
    # Get the folder name
    name = getFolderName(index, file_path)
    print(f"Creating folder {name}")
    file_list = file_list.split(' ')

    # Create the folder
    os.makedirs(name, exist_ok=True)
    # Iterate through the file list and process each file
    for file in file_list:
        if file == '':
            pass
        elif file[0] == "&" or file[0] == "@":
            # Special handling for path prefixes
            src_file = file[1:]
            dest_file = os.path.join(name, src_file)
            shutil.copy(src_file, dest_file)
            replaceKeywordsFileIndex(f"{file[0]}{dest_file}", index)
        else:
            # Normal processing
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
    # Get the first part and the remaining part
    first_name, remain_name = getFirstString(name, sep), getRemainString(name, sep)
    first_val, remain_val = getFirstString(val, sep), getRemainString(val, sep)

    # Replace colons with a space (similar to sed 's/:/ /g' in Bash)
    first_sep = first_val.replace(":", " ")

    # Print the current part
    if remain_name:
        # If there are remaining parts, print the current part and continue recursively
        print(f"{first_name}={first_val} , ", end="")
        printInfo(remain_name, remain_val, sep)
    else:
        # If there are no remaining parts, print the current part and move to the next line
        print(f"{first_name}={first_val}")


#===  FUNCTION  ================================================================
#          NAME: writeBatchOneline
#   DESCRIPTION: Write one line of the batchList.txt file
#    PARAMETERS:
#         $1 [required] The string lists for the line, could be either the keywords or keyword values
#       RETURNS: write one line of variables into batchList.txt file, separated by "|"
#===============================================================================


def writeBatchOneline(columns, file_path="batchList.txt"):
    # Get the first part and the remaining part
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

    # # Replace colons with a space (similar to sed 's/:/ /g' in Bash)
    # first_sep = first.replace(":", " ")
    # print('first', first)
    # print('first_sep', first_sep)
    # with open(file_path, 'a') as file:
    #     if remain:
    #         # Print the current part and continue recursively
    #         file.write(f"{first_sep:15} | ")
    #         writeBatchOneline(remain, file_path)
    #     else:
    #         # Print the current part and move to the next line
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
    # Calculate the total number of lines in the file
    if start is None:
        start = 1
    try:
        with open(batch_list_file, 'r') as f:
            lines = f.readlines()
            last_index = len(lines) - 1
    except FileNotFoundError:
        print(f"Error: The file '{batch_list_file}' was not found.")
        return

    # If end is not specified, use the index of the last line
    if end is None:
        end = last_index

    # Loop through each line
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

#===  FUNCTION  ================================================================
#          NAME: execFolders
#   DESCRIPTION: Execute commands inside the folders created from batchList.txt file
#    PARAMETERS:
#         command_string [required] the command to execute, notice you can use the keywords in the header line of batchList.txt file
#                                    and it will be substituted by the variable values for each folder
#         start [optional] the initial index, default is 1
#         end [optional] the last index, default is total number of rows
#       RETURNS: None
#===============================================================================


def execFolders(command_string, start=1, end=None, batch_list_file="batchList.txt"):
    origin_stdout = sys.stdout

    last_index = getEndIndex(batch_list_file)

    # If end is not specified, use the index of the last line
    if end is None:
        end = last_index

    # Get the current working directory
    current_pwd = os.getcwd()

    temp_cmd = "temp command"

    for i in range(start, end + 1):
        # Get the folder name
        folder_name = getFolderName(i)

        # Replace placeholders in the command
        temp_cmd = replaceKeywordsStringIndex(command_string, i)

        print(f"Exec command: {command_string} in folder {folder_name}")

        # Output indentation (imitating stdOutWithTab for indentation)

        # Change to the target folder
        os.chdir(folder_name)

        try:

            # Execute the command
            result = subprocess.run([getShell(), '-c', temp_cmd], shell=False, text=True, capture_output=True)
            print(stdOutWithTab(1), end="")
            print(result.stdout.strip())

        except subprocess.CalledProcessError as e:
            print(f"Error executing command in folder {folder_name}: {e}")

        # Return to the original working directory
        os.chdir(current_pwd)

        # Restore standard output
        restoreStdOut(origin_stdout)


#===  FUNCTION  ================================================================
#          NAME: execFoldersSilent
#   DESCRIPTION: Execute commands inside the folders created from batchList.txt file silently
#    PARAMETERS:
#         command_string [required] the command to execute, notice you can use the keywords in the header line of batchList.txt file
#                                    and it will be substituted by the variable values for each folder
#         start [optional] the initial index, default is 1
#         end [optional] the last index, default is total number of rows
#       RETURNS: None
#===============================================================================


def execFoldersSilent(command_string, start=1, end=None, batch_list_file="batchList.txt"):
    origin_stdout = sys.stdout
    try:
        # Calculate the total number of lines in batchList.txt
        with open(batch_list_file, 'r') as f:
            lines = f.readlines()
            last_index = len(lines) - 1
    except FileNotFoundError:
        print(f"Error: The file '{batch_list_file}' was not found.")
        return

    # If end is not specified, use the index of the last line
    end = end or last_index

    # Get the current working directory
    current_pwd = os.getcwd()

    for i in range(start, end + 1):
        # Get the folder name
        folder_name = getFolderName(i)

        # Replace placeholders in the command
        temp_cmd = replaceKeywordsStringIndex(command_string, i)

        # Output indentation (imitating stdOutWithTab)
        print(stdOutWithTab(1), end="")

        # Change to the target folder
        os.chdir(folder_name)

        try:
            # Execute the command
            result = subprocess.run([getShell(), '-c', temp_cmd], shell=False, text=True, capture_output=True)
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error executing command in folder {folder_name}: {e}")

        # Return to the original working directory
        os.chdir(current_pwd)

        # Restore standard output
        restoreStdOut(origin_stdout)


#===  FUNCTION  ================================================================
#          NAME: execFoldersUnfinished
#   DESCRIPTION: Execute commands inside the folders created from batchList.txt file silently
#    PARAMETERS:
#         command_string [required] the command to execute, notice you can use the keywords in the header line of batchList.txt file
#                                    and it will be substituted by the variable values for each folder
#         fileName [required] the file that marks the finish of a job
#         start [optional] the initial index, default is 1
#         end [optional] the last index, default is total number of rows
#       RETURNS: Print either "folder already finished" or "exec command" to screen
#===============================================================================


def execFoldersUnfinished(command_string, file_name, start=1, end=None, batch_list_file="batchList.txt"):
    origin_stdout = sys.stdout
    try:
        # Calculate the total number of lines in batchList.txt
        with open(batch_list_file, 'r') as f:
            lines = f.readlines()
            last_index = len(lines) - 1
    except FileNotFoundError:
        print(f"Error: The file '{batch_list_file}' was not found.")
        return

    # If end is not specified, use the index of the last line
    end = end or last_index

    # Get the current working directory
    current_pwd = os.getcwd()

    for i in range(start, end + 1):
        # Get the folder name
        folder_name = getFolderName(i)

        # Replace placeholders in the command
        temp_cmd = replaceKeywordsStringIndex(command_string, i)

        # Change to the target folder
        os.chdir(folder_name)

        # Check if batchList.txt contains the current folder path
        if os.path.isfile(f"../{file_name}"):
            with open(f"../{file_name}", 'r') as file:
                lines = file.readlines()
                folder_path = os.path.abspath(folder_name)  # Get the absolute path of the current folder
                if folder_path in [line.strip() for line in lines]:
                    print(f"Folder {folder_name}, already finished, see {file_name}")
                    os.chdir(current_pwd)
                    continue

        # Execute the command
        print(f"Exec command: {command_string} in folder {folder_name}")
        # print(stdOutWithTab(1), end="")

        try:
            result = subprocess.run([getShell(), '-c', temp_cmd], shell=False, text=True, capture_output=True)
            print(result.stdout.strip())
            # pass
        except subprocess.CalledProcessError as e:
            print(f"Error executing command in folder {folder_name}: {e}")

        # Restore standard output
        restoreStdOut(origin_stdout)

        # Return to the original working directory
        os.chdir(current_pwd)


#===  FUNCTION  ================================================================
#          NAME: evaluateEachField
#   DESCRIPTION: Apply the format to each of the variables
#    PARAMETERS:
#         expression_list [required] The variable list separated by "sep"
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

        temp = ""

        # Process the first string
        while first:
            first_first = getFirstString(first, ":")
            first = getRemainString(first, ":")

            # Use Python string formatting
            bash_command = f'echo "{first_first}" | xargs printf "{curr_format}"'
            temp += subprocess.check_output(bash_command, shell=True, text=True)
            if first:  # If there are remaining parts, add the separator
                temp += ":"

        # Concatenate the results
        if hold == "":
            hold += temp
        else:
            hold = hold + sep + temp

    return hold


#===  FUNCTION  ================================================================
#          NAME: writeBatchList
#   DESCRIPTION: One of the most important functions, generate the batchList.txt that
#                 is needed by all of the following steps, creating folders or executing commands
#                 the structure of batchList.txt file is like a table, each column is separated by "|"
#                 the first line of batchList.txt is the header line, first value is the separator for
#                 different variables when creating folder use the makeFolders command
#                 the last column is the condition column, and all columns in between are the variable columns
#    PARAMETERS:
#         folder_string [required] The keyword list separated by "sep", use '~' when two variables change at the same time
#         variable_string [required] The keyword value list separated by "sep", use '~' when two variables change at the same time
#         condition_string [optional] The condition string for further control what will be added as one job
#         sep [required] The separator
#         format [optional] The format style, could be either one or several separated by "sep"
#       RETURNS: batchList.txt file
#===============================================================================


def writeBatchList(folder_string, variable_string, condition_string="1>0", sep="+", format="%s", file_path="batchList.txt"):
    origin_variable_string = variable_string
    folder_string = folder_string.replace("~", "#")
    variable_string = variable_string.replace("~", "#")

    # Increment choice logic
    incrementChoice = incrementChoiceProcess(origin_variable_string)

    # Get the number of variable lists
    variable_index = [1] * (variable_string.count("#") + 1)
    variable_list_count = [len(record.split()) for record in variable_string.split('#')]
    index = 0
    replaced_variable = ""
    current_condition = condition_string
    replaced_previous = ""
    processed_variable = ""

    # Clear the file
    if os.path.exists(file_path):
        os.remove(file_path)

    # Write the first line
    writeBatchOneline(f"{sep}#{folder_string}#{condition_string}", file_path)

    while variable_index != -1:
        # Get the current variable string
        current_variable = currentVariableProcess(variable_string, variable_index)
        replaced_variable = ""
        replaced_previous = current_variable
        while replaced_previous != replaced_variable:
            replaced_previous = current_variable
            replaced_variable = replaceKeywordsString(current_variable, folder_string, current_variable, "#")
            current_variable = replaced_variable

        # Process formatting and other fields
        processed_variable = evaluateEachField(replaced_variable, folder_string, "#", format)

        # Replace keywords in the condition
        current_condition = replaceKeywordsString(condition_string, folder_string, processed_variable, "#")
        # Evaluate the condition
        bash_command = f"awk 'BEGIN{{if({current_condition}){{print \"true\"}}else{{print \"false\"}}}}'"
        result_str = subprocess.getoutput(bash_command)
        if result_str.strip() == "true":
            index += 1
            print(f"Condition fulfilled: {current_condition}")

            # Record output
            with open(file_path, 'a') as file:
                print("\t", index, end="\t", flush=True)
                printInfo(folder_string, processed_variable, "#")
                writeBatchOneline(f"{index}#{processed_variable}#{current_condition}", file_path)
        else:
            print(f"Condition not fulfilled: {current_condition}")

        # Increment the index
        variable_index = increaseIndex(variable_list_count, variable_index, incrementChoice)


def incrementChoiceProcess(processStr):
    # Split the input string into multiple records based on "#"
    records = processStr.split('#')

    result = []

    # Process each record
    for record in records:
        # Split each record into fields based on "~"
        fields = record.split('~')

        # If the number of fields >= 2, the record's line number will be output multiple times, output the line number for each field
        if len(fields) >= 2:
            result.extend([len(result) + 1] * len(fields))  # Here len(result) + 1 is the line number
        else:
            result.append(len(result) + 1)  # For a single field, output the line number once

    return result


def currentVariableProcess(variable_string, variable_index):
    # Split the string based on "#"
    records = variable_string.split('#')
    result = ""

    # Iterate through the records and output fields as needed
    for i, record in enumerate(records):
        # Process the fields of each record (split by space)
        fields = record.split()

        if i > 0:  # For the second record and beyond
            # Output the field specified by list_of_indices[i], note that the index starts from 1
            index = int(variable_index[i]) - 1  # Convert to 0-based index
            result += (f"#{fields[index]}")
        else:
            # Output the specified field of the first record
            index = int(variable_index[i]) - 1  # Convert to 0-based index
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
    This function simulates the batchAllCommand in bash, traversing all subfolders and executing the command.
    :param command_string: The command string to execute
    :param batch_depth: The indentation level for output
    """
    origin_stdout = sys.stdout
    # Get the current directory path
    current_dir = os.getcwd()

    # Get all subfolders
    folder_array = [f for f in os.listdir('.') if os.path.isdir(f)]

    print(stdOutWithTab(batch_depth), end="")

    if len(folder_array) == 1:
        print(f"Executing {command_string}")
        subprocess.run(command_string, shell=True)

    for dir in folder_array:
        if os.path.isdir(dir):
            print(f"Going into {dir}, from {current_dir}")
            os.chdir(dir)
            batch_depth_plus = batch_depth + 1
            restoreStdOut(origin_stdout)
            batchAllCommand(command_string, batch_depth_plus)  # Recursively enter subfolders and execute
            print(stdOutWithTab(batch_depth), end="")
            os.chdir(current_dir)  # Return to the parent directory
            print(f"Return from {dir}, to {current_dir}")

    restoreStdOut(origin_stdout)


# help message function


def usageStudio():
    help_text = """
`sjob` is a command for generating high-throughput jobs. It has three
subcommands, "schedule", "create", "execute", corresponding to the three phases
of high-throughput job generation. It is recommended to use a JSON configuration
file for controlling the command. But you may also pass variables directly to
the command as options.

Please refer to the user manual for more detailed documentation, or use 
"sjob schedule --help", "sjob create --help", "sjob execute --help" 
for brief introduction to each of the subcommands.
"""
    print(help_text)


def usageStudioShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    sjob schedule [json configuration file]
    sjob create [json configuration file]
    sjob execute [json configuration file]

Usage 2: Pass options instead of json configuration file
    sjob schedule -k|--keyword -v|--value [-c|--condition] [-s|--separater] [-f|--format] [-h|--help]
    sjob create [-h|--help] [-s|--start] [-e|--end] -f|--file ... 
    sjob execute [-h|--help] [-s|--start] [-e|--end] -f|--file ... 
"""
    print(help_text)


def usageSchedule():
    help_text = """
'schedule' is one of the sub-commands of sjob -
  schedule the folders and jobs, and create a batchList.txt file which contains
  all of the information needed for further 'create' and 'execute'. 'schedule'
  is the first phase of high-throughput jobs generation. Please refer to the
  user manual for more detailed explanations.

Usage 1 (Recommended): 
  sjob schedule [json configuration file]
  
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
  sjob schedule batch.json


Usage 2 (Not recommended): 
  sjob schedule [OPTION] 

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
  sjob schedule -k "VAR1#@VAR2" -v "1 2 3#10 20 30" -c "1>0" -f "%s" -s "+"
"""
    print(help_text)


def usageScheduleShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    sjob schedule [json configuration file]

Usage 2: Pass options instead of json configuration file
    sjob schedule -k|--keyword -v|--value [-c|--condition] [-s|--separater] [-f|--format] [-h|--help]

Example:

    sjob schedule -k "@FREQ#PERIOD" -v "1e12 1e13#1e12/FREQ" -c "FREQ>1e9" -f "%.2e"
"""
    print(help_text)


def usageCreate():
    help_text = """
`create' is one of the sub-command of sjob - 
  create the folders, copy and modify input files into each folder according to
  the information listed in batchList.txt file. 'create' is the second phase of 
  high-throughput jobs generation. Please refer to the user manual for more 
  detailed explanations.

Usage 1 (Recommended): 
  sjob create [json configuration file]
  
  The recommended usage requires access to python. It will use the json module.
  The command will read necessary input files from the json configuration file
  and the keywords value pairs from batchList.txt file. The identifiable keywords 
  in the json file that are related to the 'create' command are listed below.

  List of json keywords related to 'create' phase:
    "FreeFile"   A list of free format style input file
    "FixFile"    A list of fix format style input file
    "CopyFile"   A list of file that you only want to copy and change nothing

Example of usage 1:
  sjob create batch.json


Usage 2 (Not recommended): 
  sjob create [OPTION] 

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
  sjob create -f "&input.in @jobs.pbs pot.in"
"""
    print(help_text)


def usageCreateShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    sjob create [json configuration file] [-s|--start] [-e|--end]

Usage 2: Pass options instead of json configuration file
    sjob create [-h|--help] [-s|--start] [-e|--end] -f|--file ... 

Example:

    sjob create -k "&input.in @jobs.pbs pot.in"
"""
    print(help_text)


def usageExecute():
    help_text = """
`execute` is one of the sub-command of sjob - 
  execute commands in the folders created using batchList.txt file. 'execute' 
  is the third phase of high-throughput jobs generation. Please refer to the 
  user manual for more detailed explanations.

Usage 1 (Recommended): 
  sjob execute [json configuration file]
  
  The recommended usage requires access to python. It will use the json module.
  The command will read necessary input files from the json configuration file
  and the keywords value pairs from batchList.txt file. The identifiable keywords 
  in the json file that are related to the 'create' command are listed below.

  List of json keywords related to 'schedule' phase:
    "Command"     A string, which is the command to be executed in each folder

Example of usage 1:
  sjob execute batch.json

Usage 2 (Not recommended): 
  sjob execute [OPTION] 

  This type of usage is not recommended because it is not as easy to use as the 
  previous one. But if you don't have python on your machine, you can use this
  style as this one is a pure bash shell script.

  -c, --command   A string, which is the command to be executed in each folder
  -s, --start     The starting index in batchList.txt for creation
  -e, --end       The ending index in batchList.txt for creation
  -h, --help      Print helper information

Example of usage 2:
  sjob execute -c "python script.py" -s 1 -e 10
"""
    print(help_text)


def usageExecuteShort():
    help_text = """
Usage 1: Prepare a batch.json configuration file, then
    sjob execute [json configuration file] [-s|--start] [-e|--end]

Usage 2: Pass options instead of json configuration file
    sjob execute [-h|--help] [-s|--start] [-e|--end] -f|--file ... 

Example:

    sjob execute "echo FREQ"
    sjob execute "qsub Ferro.pbs"
"""
    print(help_text)


def printArguements():
    print(f"Command is {sys.argv[1]}")  # Print the first argument
    for index, arg in enumerate(sys.argv[2:], start=1):  # Iterate from the second argument
        print(f"Argument {index}: {arg}")


def custom_subcommand_help(command=None):
    """Custom help information function, displayed by subcommand"""
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
        """Override the print_help method to call the custom help function"""
        # command = self.args.command if hasattr(self, 'args') else None
        command = self.prog.split()[-1]
        custom_subcommand_help(command)


# # parse args
# def parseArgs():
#     parser = CustomArgumentParser(prog="sjob")

#     subparsers = parser.add_subparsers(dest="command")

#     # Schedule command
#     schedule_parser = subparsers.add_parser("schedule", help="Create the batchList.txt file")
#     schedule_parser.add_argument("-k", "--keyword", type=str, default=None, help="Keywords for batch list", required=False)
#     schedule_parser.add_argument("-v", "--value", type=str, default=None, help="Values for each keyword", required=False)
#     schedule_parser.add_argument("-c", "--condition", help="Condition for filtering jobs", default="1>0")
#     schedule_parser.add_argument("-s", "--separater", help="Separator", default="+")
#     schedule_parser.add_argument("-f", "--format", help="Format", default="%s")
#     schedule_parser.add_argument("json_file", nargs="?", help="JSON configuration file for scheduling")

#     # Create command
#     create_parser = subparsers.add_parser("create", help="Create the folder structure")
#     create_parser.add_argument("-f", "--file", help="Files to copy", type=str, required=False)
#     create_parser.add_argument("-s", "--start", type=int, help="Start index", default=None)
#     create_parser.add_argument("-e", "--end", type=int, help="End index", default=None)
#     create_parser.add_argument("json_file", nargs="?", help="JSON configuration file for creating folders")

#     # Execute command
#     execute_parser = subparsers.add_parser("execute", help="Execute command for each folder")
#     execute_parser.add_argument("-c", "--exec_command", help="Command to execute in each folder", required=False)
#     execute_parser.add_argument("-s", "--start", type=int, help="Start index", default=None)
#     execute_parser.add_argument("-e", "--end", type=int, help="End index", default=None)
#     execute_parser.add_argument("json_file", nargs="?", help="JSON configuration file for executing command")

#     args = parser.parse_args()

#     return args


# schedule function
# sjob schedule -k '@FREQ#PERIOD' -v "1e12 1e13#1e12/FREQ" -c "1>0" -f='%s'
@sjob.command(name='schedule')
@click.argument('json_file', type=click.Path(exists=True), default=None)
@click.option('--keyword', '-k', help='Keywords for batch list')
@click.option('--value', '-v', help='Values for each keyword')
@click.option('--condition', '-c', help='Condition for filtering jobs', default="1>0")
@click.option('--separater', '-s', help='Separator', default="+")
@click.option('--format', '-f', help='Format', default="%s")
def scheduleCommand(json_file, keyword, value, condition, separater, format):
    '''Main function to create the batchList.txt file.'''
    # init config dict
    config = {}
    config['json_set'] = False

    # check if json file is provided
    if json_file is not None:
        print("Stage 1: Create the batchList.txt file")
        print(f"Using the {json_file} configuration file")
        config['json_set'] = True
        config['var_name'] = getJsonVar(json_file, "VarName")
        config['var_value'] = getJsonVar(json_file, "VarValue")
        config['condition'] = getJsonVar(json_file, "Condition")
        config['separator'] = getJsonVar(json_file, "Separator")
        config['format_str'] = getJsonVar(json_file, "Format")
        if config['var_name'] and config['var_value']:
            writeBatchList(config['var_name'], config['var_value'], config['condition'], config['separator'], config['format_str'])
    else:
        config['json_set'] = False
        config['var_name'] = keyword
        config['var_value'] = value
        config['condition'] = condition
        config['separator'] = separater
        config['format_str'] = format

        if config['var_name'] is None:
            raise ValueError("The -k or --keyword option is mandatory for batch list command, which sets the keywords for creating the batchList.txt file.")
        if config['var_value'] is None:
            raise ValueError("The -v or --value option is mandatory for batch list command, which sets the sweeping values for each keyword in the input file.")
        writeBatchList(config['var_name'], config['var_value'], config['condition'], config['separator'], config['format_str'])


# create function
@sjob.command(name='create')
@click.argument('json_file', type=click.Path(exists=True), default=None)
@click.option('--file_list', '-f', help='Files to copy', default=None)
@click.option('--start', '-s', type=int, help='Start index', default=None)
@click.option('--end', '-e', type=int, help='End index', default=None)
def createCommand(json_file, file_list, start, end):
    '''Main function to create the folder structure and copy files into the folders.'''

    config = {}
    config['file_set'] = False
    config['json_set'] = False
    if file_list is not None:
        config['file_set'] = True
        config['file_list'] = file_list
    if json_file is not None:
        print("Stage 2: Create the folder structure")
        print(f"Using the {json_file} configuration file")
        config['file_list'] = getJsonVar(json_file, "File")
        config['file_set'] = True

    if config['file_set'] == True:
        makeFolders(config['file_list'], start, end)
    else:
        raise ValueError("The -f or --file option is mandatory.")


def getEndIndex(file_path):
    """ Calculate the number of lines in the file and return the value of the line count minus 1 """
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            return len(lines) - 1  # Subtract 1 to get the last index
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


@sjob.command(name='execute')
@click.argument('json_file', type=click.Path(exists=True), default=None)
@click.option('--command', '-c', default=None, help='Command to execute in each folder')
@click.option('--start', '-s', type=int, help='Start index', default=1)
@click.option('--end', '-e', type=int, help='End index', default=None)
def executeCommand(json_file, command, start, end):
    """ Main function to execute the provided command in each folder. """
    config = {}
    config['command_set'] = False
    config['json_set'] = False
    config['start'] = start
    config['end'] = getEndIndex('batchList.txt')
    config['exec_command'] = 'ls'

    if command is not None:
        command['exec_command'] = command
        config['command_set'] = True
    elif json_file:
        json_command = getJsonVar(json_file, 'Command')
        if json_command:
            config['exec_command'] = json_command
            config['command_set'] = True

    if not config['command_set']:
        if not command:
            print("The -c or --command option is mandatory if no JSON file is provided.")
            return
    else:
        print(f"Executing command: {config['exec_command']} from index {config['start']} to {config['end']}")
        execFolders(config['exec_command'], config['start'], config['end'])


# # main function
# def runCommand():
#     args = parseArgs()
#     if args.command == 'schedule':
#         scheduleCommand(args)
#     elif args.command == 'create':
#         createCommand(args)
#     elif args.command == 'execute':
#         executeCommand(args)
#     else:
#         print("Unknown command. Use --help for usage instructions.")

# if __name__ == '__main__':
#     runCommand()
if __name__ == '__main__':
    sjob()
