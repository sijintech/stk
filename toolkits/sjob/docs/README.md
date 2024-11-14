# htpstudio manual
## Overview
The "htpstudio" is a tool for high-throughput computer simulation's jobs creation and execution. This command provides a convenient interface to several useful command line tools related to high-throughput computer simulations starting from scheduling job parameters, creating folder structure to final submission.

Features including 
1. User friendly json config file (available when python is installed)
2. Also capable of working with minimal dependency, only bash and awk is enough (though a little bit less user friendly than using the json config file)
3. Separate the whole jobs creation into three phases, force you to double check the correctness of your calculations after each stage to avoid errors during rush submission
4. Capable of dealing with dependency between degree of freedom
5. Support [free and fix format of keyword replacement](#free-fix-format). 
,etc.

`htpstudio` targets the most basic workflow of high-throughput computation, namely automatically create hundreds of calculation jobs to sweep through several dimension of the parameter space. 
First, an intermediate *batchList.txt* file is generated. And all of the following steps, such as folder creation, file copying, keywords replacement, folder-wise command execution is based on information in this batchList.txt file. 


## Quick start
**step 1:** Prepare the [batch.json file](#batch.json)

**step 2:** Schedule jobs and create the *batchList.txt* file
``` sh
htpstudio schedule batch.json
```

**step 3:** Double check the listed jobs in *batchList.txt* and create folders
``` sh
htpstudio create batch.json
```

**step 4** Go into the created folders and check if generated files are as expected, then execute the specified command
``` sh
htpstudio execute batch.json
```

## Minimal example
In this example, you will be sweeping through a parameter space of VAR1 and VAR2. VAR1 is a integer that can choose between three different values. VAR2 is a 3D vector that can choose between two values.

Prepare a input file, such as
``` sh
# input.in
VAR1 = 100
VAR2 = 30 40 40
```
Prepare a batch.json file, such as
``` json
{
    "FreeFile": ["input.in"],
    "FixFile": [],
    "CopyFile": [],
    "FreeVarName": ["VAR1", "VAR2"],
    "FixVarName": [],
    "VarValue": {
        "VAR1": [100, 200, 300],
        "VAR2": ["10 20 30", "20 10 30"]
    },
    "VarSequence": ["VAR1", "VAR2"],
    "Separator": "+",
    "Format": "%s",
    "Condition": "1>0",
    "Command": "pwd"
}
```
High-throughput jobs creation
``` sh
# Generate batchList.txt
htpstudio schedule batch.json
# Create folder structure
htpstudio create batch.json
# Execute the command "pwd" in each folder
htpstudio execute batch.json
```
What you will get is three things:
1. a batchList.txt file
```
        + |            VAR1 |            VAR2 |             1>0
        1 |             100 |        10 20 30 |             1>0
        2 |             100 |        20 10 30 |             1>0
        3 |             200 |        10 20 30 |             1>0
        4 |             200 |        20 10 30 |             1>0
        5 |             300 |        10 20 30 |             1>0
        6 |             300 |        20 10 30 |             1>0
```
2. 6 folders with VAR1 and VAR2 value in the folder name indicating how the input.in file is like in this folder.
```
1+VAR1_100+VAR2_10_20_30/
2+VAR1_100+VAR2_20_10_30/
3+VAR1_200+VAR2_10_20_30/
4+VAR1_200+VAR2_20_10_30/
5+VAR1_300+VAR2_10_20_30/
6+VAR1_300+VAR2_20_10_30/
```
3. Execution output of command "pwd" inside each of the generated folders.
```
Exec command: pwd in folder 1+VAR1_100+VAR2_10_20_30
        /mnt/d/SynologyDrive/nibiru/htp-studio/minimal/1+VAR1_100+VAR2_10_20_30
Exec command: pwd in folder 2+VAR1_100+VAR2_20_10_30
        /mnt/d/SynologyDrive/nibiru/htp-studio/minimal/2+VAR1_100+VAR2_20_10_30
Exec command: pwd in folder 3+VAR1_200+VAR2_10_20_30
        /mnt/d/SynologyDrive/nibiru/htp-studio/minimal/3+VAR1_200+VAR2_10_20_30
Exec command: pwd in folder 4+VAR1_200+VAR2_20_10_30
        /mnt/d/SynologyDrive/nibiru/htp-studio/minimal/4+VAR1_200+VAR2_20_10_30
Exec command: pwd in folder 5+VAR1_300+VAR2_10_20_30
        /mnt/d/SynologyDrive/nibiru/htp-studio/minimal/5+VAR1_300+VAR2_10_20_30
Exec command: pwd in folder 6+VAR1_300+VAR2_20_10_30
        /mnt/d/SynologyDrive/nibiru/htp-studio/minimal/6+VAR1_300+VAR2_20_10_30
```

## Sub-commands
As you have seen in the previous examples, the `htpstudio` command has several sub-commands, three of them are more important and each corresponding to one stage of the high-throughput jobs creation processes. 
- **Stage 1**: `schedule`   -- create a batchList.txt file in which each row correspond to one calculation and the varying parameters are specified in each column. [Details of *htpstudio schedule* is here](##Schedule)
- **Stage 2**: `create`     -- create a properly named folder structure, copy input files into each folder and replace the specified keywords according to each row in batchList.txt file. [Details of *htpstudio create* is here](##Create)
- **Stage 3**: `execute`    -- execute a command for a set of folders in the above generated jobs pool. [Details of *htpstudio execute* is here](##Execute)

The reason I explicitly separate the whole process into three stages, rather than mix them together, because it force you to slow down and potentially save a lot of your time redoing wrong calculations. It is always a good idea to double check everything before submission, 
1. checking the batchList.txt file after the scheduling phase, 
2. checking the input files in the created folders after the creation phase. 

<!-- Other sub-commands are 
- **utility** -- access to the functions defined in htpstudio file, for either debugging or convenient usage, available functions are listed below
    * getFirstString 
    * getRemainString -->


## Examples
There are two ways to use htpstudio, 1. if python is installed in the system, use a json file for configuring the parameter space, keyword names, etc. 2. if no python is available, pass those necessary arguements through command line options.
Generally the first style is recommended, because it keeps a record of your high-throughput setup, gurantee future reproducibility and easiness of improvement.  
### Style 1
Suppose you have a batch.json file that looks like this. Explanation for all of the keywords could be find [later in this manual](##batch.json). 

``` json
{
  "FreeFile" : [
    "input.in"
   ],
   "FixFile" : [
     "submit.pbs"
   ],
   "CopyFile":[
    "pot.in"
   ],
   "FreeVarName":[
     "MISFIT",
     "TEM"
   ],
   "FixVarName":["STRESS"],
  "VarValue":{
    "MISFIT":["1:1:1","2:2:2","3:3:3" ],
    "TEM":[100,200,300],
    "STRESS":[1e5,2e5,3e5]
  },
  "VarSequence":[
    ["MISFIT","TEM"],
    ["STRESS"]
  ],
   "Separator":"+",
   "Format":"%.1f",
   "Condition":"1>0",
   "Command":"echo TEM STRESS"
}
```
You need to put the htpstudio file into a folder that is in *PATH* so that you can easily access the htpstudio command. As high-throughput calculations are usually performed on high performance supercomputers, in most cases you won't have administrator previlage, so creating a `bin` folder in your home directory, add it to *PATH* with `export PATH=$PATH:~/bin`, and then copy *htpstudio* to *~/bin* is probably the easiest way to use *htpstudio*. 

You need to put the necessary files into the same directory, which shall look like this
```
dir
|- input.in
|- submit.pbs
|- pot.in
|- batch.json
```

- **input.in** is the control file, similar to INCAR for VASP, most of the varying parameters is specified in this file
- **submit.pbs** is the job queueing file for the PBS system, usually the only thing that needs to be changed is the jobs name
- **pot.in** is the physics parameters for the simulation system, similar to the POTCAR in VASP, usually this file is kept the same
- **MISFIT, TEM, STRESS** are all keywords that is used in the input.in file

#### Stage 1: Job Scheduling
``` sh
# Input
htpstudio schedule batch.json
# Output
Stage 1: Create the batchList.txt file
Condition fulfilled. 1>0
        1       &MISFIT=1.0:1.0:1.0 , &TEM=100.0 , @STRESS=100000.0
Condition fulfilled. 1>0
        2       &MISFIT=1.0:1.0:1.0 , &TEM=100.0 , @STRESS=200000.0
Condition fulfilled. 1>0
        3       &MISFIT=1.0:1.0:1.0 , &TEM=100.0 , @STRESS=300000.0
Condition fulfilled. 1>0
        4       &MISFIT=2.0:2.0:2.0 , &TEM=200.0 , @STRESS=100000.0
Condition fulfilled. 1>0
        5       &MISFIT=2.0:2.0:2.0 , &TEM=200.0 , @STRESS=200000.0
Condition fulfilled. 1>0
        6       &MISFIT=2.0:2.0:2.0 , &TEM=200.0 , @STRESS=300000.0
Condition fulfilled. 1>0
        7       &MISFIT=3.0:3.0:3.0 , &TEM=300.0 , @STRESS=100000.0
Condition fulfilled. 1>0
        8       &MISFIT=3.0:3.0:3.0 , &TEM=300.0 , @STRESS=200000.0
Condition fulfilled. 1>0
        9       &MISFIT=3.0:3.0:3.0 , &TEM=300.0 , @STRESS=300000.0
```
Using the `htpstudio schedule` command, 9 jobs are generated, the varying parameter's value is printed to screen, as well as into the *batchList.txt* file. Notice here, the MISFIT and TEM values are dependent of each other.
```
              + |         &MISFIT |            &TEM |         @STRESS |             1>0
              1 |     1.0 1.0 1.0 |           100.0 |        100000.0 |             1>0
              2 |     1.0 1.0 1.0 |           100.0 |        200000.0 |             1>0
              3 |     1.0 1.0 1.0 |           100.0 |        300000.0 |             1>0
              4 |     2.0 2.0 2.0 |           200.0 |        100000.0 |             1>0
              5 |     2.0 2.0 2.0 |           200.0 |        200000.0 |             1>0
              6 |     2.0 2.0 2.0 |           200.0 |        300000.0 |             1>0
              7 |     3.0 3.0 3.0 |           300.0 |        100000.0 |             1>0
              8 |     3.0 3.0 3.0 |           300.0 |        200000.0 |             1>0
              9 |     3.0 3.0 3.0 |           300.0 |        300000.0 |             1>0
```
#### Stage 2: Folder creation
``` sh
# Input
htpstudio create batch.json
# Created folders
'9+&MISFIT_3.0_3.0_3.0+&TEM_300.0+STRESS_300000.0'/
'8+&MISFIT_3.0_3.0_3.0+&TEM_300.0+STRESS_200000.0'/
'7+&MISFIT_3.0_3.0_3.0+&TEM_300.0+STRESS_100000.0'/
'6+&MISFIT_2.0_2.0_2.0+&TEM_200.0+STRESS_300000.0'/
'5+&MISFIT_2.0_2.0_2.0+&TEM_200.0+STRESS_200000.0'/
'4+&MISFIT_2.0_2.0_2.0+&TEM_200.0+STRESS_100000.0'/
'3+&MISFIT_1.0_1.0_1.0+&TEM_100.0+STRESS_300000.0'/
'2+&MISFIT_1.0_1.0_1.0+&TEM_100.0+STRESS_200000.0'/
'1+&MISFIT_1.0_1.0_1.0+&TEM_100.0+STRESS_100000.0'/
```
#### Stage 3: Execution (Job submission)
```sh
# Input 
htpstudio execute batch.json
# Output
Exec command: echo TEM STRESS in folder 1+&MISFIT_1.0_1.0_1.0+&TEM_100.0+STRESS_100000.0
        100.0 100000.0
Exec command: echo TEM STRESS in folder 2+&MISFIT_1.0_1.0_1.0+&TEM_100.0+STRESS_200000.0
        100.0 200000.0
Exec command: echo TEM STRESS in folder 3+&MISFIT_1.0_1.0_1.0+&TEM_100.0+STRESS_300000.0
        100.0 300000.0
Exec command: echo TEM STRESS in folder 4+&MISFIT_2.0_2.0_2.0+&TEM_200.0+STRESS_100000.0
        200.0 100000.0
Exec command: echo TEM STRESS in folder 5+&MISFIT_2.0_2.0_2.0+&TEM_200.0+STRESS_200000.0
        200.0 200000.0
Exec command: echo TEM STRESS in folder 6+&MISFIT_2.0_2.0_2.0+&TEM_200.0+STRESS_300000.0
        200.0 300000.0
Exec command: echo TEM STRESS in folder 7+&MISFIT_3.0_3.0_3.0+&TEM_300.0+STRESS_100000.0
        300.0 100000.0
Exec command: echo TEM STRESS in folder 8+&MISFIT_3.0_3.0_3.0+&TEM_300.0+STRESS_200000.0
        300.0 200000.0
Exec command: echo TEM STRESS in folder 9+&MISFIT_3.0_3.0_3.0+&TEM_300.0+STRESS_300000.0
        300.0 300000.0
```
### Style2
The usage without json configuration file is not recommended, you may read the explanation for each sub command below to see what variables are needed. Here is an example
``` sh
folders="TEM#@exx#@eyy#REALDIM#SYSDIM"   # separated by "#", for fix format style of keyword replacment insert @ in the front
files="&input.in pot.in @ferro.pbs"     # & for free format file, @ for fix format file, nothing for just copy
TEM="298 350 560"                       # each variable is separated by " ", use ":" when the variable contains more than one number
exx="0.1 0.2 0.3"
eyy="0.1 0.2 0.3"
realdim="123:234:234 456:567:678"
sysdim="123:234:234 456:567:678"
variables="${TEM}#${exx}#${eyy}#${realdim}#${sysdim}" # different variables are separated by #"
htpstudio schedule -k "${folders}" -v "${variables}" -c 'exx>=eyy&&"REALDIM"=="SYSDIM"'     # No 4th argument, default of + is used
htpstudio create -f "${files}"
htpstudio execute -c "echo TEM,exx,eyy,REALDIM"
```

---
## batch.json
[Jump back to Example, style 1](#style-1)

This is the a json file that contains necessary arguements that htpstudio needs at all three stages of high-throughput jobs creation.
Keywords include:
- **FreeFile** A list of free format style file, used in the *create* phase
- **FixFile** A list of fix format style file, used in the *create* phase
- **CopyFile** A list of file only for copying, without keyword substitution, used in the *create* phase
- **FreeVar** A list of variable keywords that to be substituted using the free format style, used in the *schedule* phase
- **FixVar** A list of variable keywords that to be substituted uing the fix format style, used in the *schedule* phase
- **VarValue** A collection of objects, with variable keywords as the keys and the sweeping values as value, used in the *schedule* phase
- **VarSequence** A list, or a list of lists, of the variable keywords. The purpose is to specify the different levels of variables, which means during the high-throughput jobs creation variables within the same level will change values at the same time, while change independently across different levels. Used in the *schedule* phase.
- **Separator** A char for separating keywords in the generated folder name, such as the "+" sign in "3+TEM_298+exx_0.1", default value is "+". You may also use "/" to generate a multilevel folder structure. Used in the *schedule* phase.
- **Format** A string. c style string format to format how the variable values are written in the *batchList.txt* file. Used in the *schedule* phase.
- **Condition**  A string. the special condition between variables that jobs are scheduled only when evaluated as true. For example, "VAR1>VAR2", only when the value of VAR1 is larger than VAR2, then the parameters are written into the *batchList.txt* file. Used in *schedule* phase.
- **Command**  A string. The command that you want to execute within each of the create folders. Used in the *execute* phase.

#### batchList.txt
The structure of the batchList.txt file is as follows:
1. The whole file is separated by "|" between columns
2. The first line is a header line. first column is the deliminator between keyword and value pairs in the created folder names, such as the "+" sign in "3+TEM_298+exx_0.1", default value is "+". You may use "/" for this so that rather than a single layer of folders, subfolders are generated. Last column is the original conditional statement. And all other columns in between are the keywords in input files to be replaced by some values.
3. The following lines are all substituting variables, each line will be used to generate one folder in the next stage. The first column is the index for current variable set. The last column is the conditional statement with keywords replaced by the corresponding variables. The middle columns are the sweeping parameters.

The an example batchList.txt file looks like this.
+ |           @FREQ |          PERIOD |        FREQ>1e9
1 |        1.00e+12 |        1.00e+00 |    1.00e+12>1e9
2 |        1.00e+13 |        1.00e-01 |    1.00e+13>1e9

The first element locates at first row, first column is the separater we set with -s option. 
The first row gives us the keywords names set with -k option. 
The last column of first row gives the conditional expression set with -c option.
The first column is the index for all of the cases to be generated.
The last column is the conditional expression with keyword replaced by the current value.
Everything in middle are the value for keywords, set with -v option.

---
## Schedule
### Description
The `htpstudio schedule` command takes care of the scheduling phase. It will generate a *batchList.txt* file that lists all of the scheduled calculations, which will be used in the creation and execution phase.

You may use a json file for configuration, or you can pass options explicitly to the commands. There are two mandatory options, 1. -k,--keyword option which tells the program what are the words to search for and replace in the second folder creation phase, 2. -v,--value option which tells the program what are the values to be used for substituting the keywords. 

### Options
- **-k**,**--keyword** *Required* Set the searching keywords, different keywords are separated by #, so e.g. "@freq#SIMDIM" means that in the creation stage, the program will search for two keywords "freq" and "phase". The declarator **@** before the keyword, indicates how the keyword will be substitute in stage 2. The default behavior is replacing the whole line that contains the keyword. This is suitable for the free format type of input, in which each line gives values for one variable, for example `SIMDIM = 100 100 100`. Adding the **@** sign will change the substituting behavior and only the keyword itself will be replaced. This is useful for the fix format type of input, in which each line contains values for more than just one variable.
- **-v**,**--value** *Required* Set the value list that will be used to replace the keywords, the values in each value list is separated by " ", and if each value is made up of more than one number, we use **|** to join them so that it won't be confused with other items in the list, and different value lists are separated by #. So, for example "1e9 1e10#10|10|10 50|50|50" means for the first keyword, it will be replaced by 1e9 or 1e10, and for the second keyword, it will be replaced by "10 10 10" or "50 50 50". Cool part of this option is that you may use the name of another keyword to represent the current value and calculate the value of this keyword. For example, keywords are "@freq#@omega", though both values needs to be changed, but we know freq\*omega=1, so for the value lists we can write "1e9 1e10#1/freq", and only two calculation cases will be written into batchList.txt freq=1e9,omega=1e-9 and freq=1e10,omega=1e-10. For now only scalar value could parsed for calculation.
- **-c**,**--condition** *Optional* Set a conditional expression for the whole parameter space, and only those cases that result in true will be written into the batchList.txt file. The default condition is "1>0", so that the whole parameter space is valid. Similar to the value option case, you may use the name of keywords to represent their current value. For example, keywords are "@exx#@eyy", and we already know exx and eyy are symmetric, which means we only need to calculate half of the whole parameter space that exx >= eyy or vice versa. So, with value lists of "-0.1 0 0.1#-0.1 0 0.1", we can set a condition of "exx>=eyy", and only 6 cases rather than 9 cases will be written into batchList.txt.
- **-s**,**--separater** *Optional* Set the separater character for different keyword value pairs of the created folder name in stage 2. The default value is **+**. You can use the separater character to control whether you want a single layer folder structure, such as 01+freq_1e9+omega_1e-9, or you want a multi-layer folder structure, such as freq_1e9/omega_1e-9
- **-f**,**--format** *Optional* Set the printf format for replacing values in value list. Default is "%s" treat the value as a string, so essentially no format and use whatever awk command displays. Useful examples would be "%.2e", scientific notation with two digits after decimal. You can set only one format, and it would be used for all of the keyword values, or you can set several formats separated by "#", for example, "%.2e#%.3f".
- **-h**,**--help** *Optional* Display helping doc (this file).

### Example
1. `htpstudio schedule -k "FREQ" -v "1e12 1e13" -f "%.2e"` 
2. `htpstudio schedule -k "@FREQ#PERIOD" -v "1e12 1e13#1e12/FREQ" -c "FREQ>1e9" -f "%.2e"` 



---
## Create
### Description
The `htpstudio create` command takes care of the folder creating phase. It will generate a list of folders/folder structures according (and only according) to the information in *batchList.txt* file. 

You may use a json file for configuration, or you can pass options explicitly to the commands. This command will take a list of files as argument, and copy them into each folder according to the batchList.txt file created with the schedule command. And of course, the keywords in these files are replaced with the values in the batchList.txt file. There are actually three types of copying that we can make, 1. pure copy, without any keyword replacement, 2. fix format type copy, during which only the keyword itself is replaced, 3. free format type copy, for which the whole line containing the keyword is replaced with a new line using the specific value.

You need to add a declarative character before each file to specify which copy style you want to use for processing the file.
- Nothing for the pure copy type
- **@** for the fix format type
- **&** for the free format type

It is true that there are some overlap between the style set here and the style we set in the schedule command, we do it in this way to remove any ambiguity. For a free format file, you can have both free and fix format of keyword replacement, while for a fix format file, you can only have fix format keyword replacement.

### Options
- **-h**, **--help**

### Example
1. `htpstudio create &input.in @Ferro.pbs pot.in`


---
## Execute
### Description
The `htpstudio execute` command takes care of the command executing phase. This command will go to each folder that is created according to the batchList.txt file, and execute the command you passed to it. Similar to the condition option and value option in the schedule command, you can use the keyword name to represent such variables current value and achieve different outcome for different folders.

You may use a json file for configuration, or you can pass options explicitly to the commands. 

### Options
- **-s**,**--start** *Optional* Set the index for the folder you want to start executing your command, you can find the index in the first column of the batchList.txt file
- **-e**,**--end** *Optional* Set the index for the folder you want to finish executing your command, you can find the index in the first column of the batchList.txt file
- **-h**, **--help**

### Example
1. htpstudio execute "echo FREQ"
2. htpstudio execute "qsub Ferro.pbs"


---
## Utility

- writeBatchList [$1:keywords] [$2:replacement\_variable] [$3:conditional\_statement] [$4:deliminator] 
  * $1: Use "#" as the separator between keywordes, default if the free foramt style of keyword, which means the whole line will be replace with the keyword and value pair. You may choose to use the fix format style by adding a "@" sign before the keyword, which means only the keyword itself will be replaced by the sweeping value,e.g. "SYSDIM#TEM", "TEM#@exx#@eyy"
  * $2: Use "#" as the separator between different variable, and " " as separator for one variable but different values, then ":" as separator for different numbers 
 for one replacement (since it's replacing the whole line, there may be more than more numbers) e.g. "100:100:100 200:200:200#200 250 300" 
  * $3: awk style conditional statement, you may use the keyword to represent the current variable value, e.g. 'exx>=eyy&&"REALDIM"=="SYSDIM"', which means only those cases that exx are greater or equal than eyy and SYSDIM are the same as REALDIM will be generated, notice the quotation mark around REALDIM and SYSDIM because the value for these two keywords are not one number, comparison between they should be comparison between strings.
  * $4: The deliminator to be used for later folder generation stage for separating keyword, value pair. Default value is "+", you can set it to "/" which will generate subfolders structures, and each level is related to one variable changed, e.g. if you don't set this argument, then the folder will look like 01+TEM_350+exx_0.3, if you set it to be "/", then the folder will be like TEM_350/exx_0.3/
- makeFolders [$1:file\_list] [$2:start\_index] [$3:end\_index]
  * $1: Use " " as the separator between files,  add "&" before the file name you want to be processed as free format file, "@" before the file name you want to be processed as fix format file, and nothing for files just copy but not processed. e.g. "&input.in @ferro.pbs". Notice free format file can contains both free format type variables and fix type variables, which means the substitution of variables will be determined by the type you set for individual keyword, and fix format file
  can only have fix format style variables, which means no matter what style is set for the keywords, it will be treated as fix format style when replacement is made for fix format files.
  * $2: Optional argument that set the starting row/index(inside the batchList.txt file) for folder generation,d efault is 1, so starting from index=1 of batchList.txt which is the second row.
  * $3: Optional argument that set the ending row/index(inside the batchList.txt file) for folder generation,d efault is the line number of the batchList.txt file, so folder creation will end when it reach the last line of batchList.txt file.
- execFolders [$1:command] [$2:start\_index] [$3:end\_index]
  * $1: The command you want to execute for each generated folder from makeFolders, you can use the keyword here to represent the variable value within the folder, e.g. echo TEM,exx,eyy
  * $2: Optional argument that set the starting row/index(inside the batchList.txt file) for folder generation,d efault is 1, so starting from index=1 of batchList.txt which is the second row.
  * $3: Optional argument that set the ending row/index(inside the batchList.txt file) for folder generation,d efault is the line number of the batchList.txt file, so folder creation will end when it reach the last line of batchList.txt file.
- batchAllCommand [$1:command\_string]  
  * $1: A command in the form of string, that is the words you would type in terminal to execute the command, e.g. "qsub ferro.pbs"

---
## Free & Fix Format 

When it comes to simulation input, there are roughly two styles, one is fix format, which means the position and sequence of each parameter is fix, and the other is free format which means the position and sequence is not fixed, the file is valid as long as user follows some rules such as "keyword=value".

Let's see an example:
``` sh
# fix format, if you switch the sequence of line 1 and 2, program will crash
10          # value of VAR1, 
10 20 30    # vector of VAR2
```
``` sh
# free format, you can switch the sequence of line 1 and 2
VAR1 = 10
VAR2 = 10 20 30
```
