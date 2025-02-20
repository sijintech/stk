# **sjob** 手册
## 概述
**sjob**是一种用于高通量计算机模拟作业创建和执行的工具。该命令为与高通量计算机模拟相关的多个实用命令行工具提供了便捷的接口，从调度作业参数、创建文件夹结构到最终提交作业。

功能包括：
1. 用户友好的json配置文件（在安装python时可用）
2. 也能在最小依赖下工作，能在Windows和Linux系统终端使用命令行参数运行（尽管相比使用json配置文件稍欠用户友好性）
3. 将整个作业创建过程分为三个阶段，迫使你在每个阶段后仔细检查计算的正确性，以避免匆忙提交时的错误
4. 能够处理自由度之间的依赖关系
5. 支持[自由和固定的关键字替换格式](#自由--固定格式)。

`sjob` 针对高通量计算的最基本工作流程，即自动创建数百个计算作业以扫描参数空间的多个维度。
首先，生成一个中间的 batchList.txt 文件。所有后续步骤，如文件夹创建、文件复制、关键字替换、按文件夹执行的命令，都基于此 batchList.txt 文件中的信息。

## 快速开始

### 安装
您可以在安装 `suan` 包后在命令行终端使用 sjob 命令：
```sh
pip install suan
```

## 使用
**步骤 1**： 准备 [batch.json 文件](#batchjson)。
**步骤 2**： 调度作业并创建 *batchList.txt* 文件。
```sh
sjob schedule batch.json
```

**步骤 3**：仔细检查 *batchList.txt* 中列出的作业并创建文件夹。
```sh
sjob create batch.json
```

**步骤 4**：进入创建的文件夹并检查生成的文件是否符合预期，然后执行指定的命令。
```sh
sjob execute batch.json
```

## 最小示例
在本示例中，您将遍历 VAR1 和 VAR2 的参数空间。VAR1 是一个整数，可以在三个不同的值之间选择。VAR2 是一个 3D 向量，可以在两个值之间选择。

准备一个输入文件（input.in），例如：
```sh
# input.in
VAR1 = 100
VAR2 = 30 40 40
```
准备一个 json 文件（batch.json），例如：
```json
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
高通量作业创建
```sh
# 生成 batchList.txt 文件
sjob schedule batch.json
# 生成目录结构
sjob create batch.json
# 在每个文件夹目录下执行命令 “pwd”
sjob execute batch.json
```
执行了schedule，create，execute命令后，你将获得三样东西：
1. 1 个 batchList.txt 文件。
```
        + |            VAR1 |            VAR2 |             1>0
        1 |             100 |        10 20 30 |             1>0
        2 |             100 |        20 10 30 |             1>0
        3 |             200 |        10 20 30 |             1>0
        4 |             200 |        20 10 30 |             1>0
        5 |             300 |        10 20 30 |             1>0
        6 |             300 |        20 10 30 |             1>0
```
2. 6个文件夹，文件夹名称中包含 VAR1 和 VAR2 的值，对应该文件夹中的 input.in 文件中的内容。
```
1+VAR1_100+VAR2_10_20_30/
2+VAR1_100+VAR2_20_10_30/
3+VAR1_200+VAR2_10_20_30/
4+VAR1_200+VAR2_20_10_30/
5+VAR1_300+VAR2_10_20_30/
6+VAR1_300+VAR2_20_10_30/
```
3. 在每个生成的文件夹内执行命令 “pwd” 的输出。
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

## 子命令介绍
如您在之前的示例中所看到的，`sjob` 命令有几个子命令，其中三个最为重要，分别对应高通量作业创建过程的三个阶段。
- **阶段 1**： `schedule`   --创建一个 batchList.txt 文件，其中每一行对应一个计算，变化的参数在每一列中指定。[sjob schedule 的详细信息在这里](#schedule)
- **阶段 2**：`create` -- 创建一个正确命名的文件夹结构，将输入文件复制到每个文件夹中，并根据 batchList.txt 文件中的每一行替换指定的关键词。[sjob create 的详细信息在这里](#create)
- **阶段 3**：`execute` -- 为上述生成的作业池中的一组文件夹执行命令。[sjob execute 的详细信息在这里](#execute)

之所以将整个过程明确地分为三个阶段，而不是将它们混在一起，是因为这样可以迫使你放慢速度，从而避免在计算错误时浪费大量时间重新做。提交前，最好先仔细检查一遍：
1. 在调度（schedule）阶段后，检查 batchList.txt 文件，
2. 在创建（create）阶段后，检查创建的文件夹中的输入文件。

## 示例
有两种使用 sjob 的方式：1. 使用一个 JSON 文件来配置参数空间、关键词名称等；2. 通过命令行选项传递这些必要的参数。
通常推荐使用第一种方式，因为它可以保留你的高通量设置记录，确保未来的可重现性和便于改进。
### 风格 1
假设你有一个 batch.json 文件，内容如下所示。所有关键词的解释可以在本[手册后续部分](#batchjson)找到。

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
你需要将必要的文件放入同一目录中，目录结构应如下所示：
```
dir
|- input.in
|- submit.pbs
|- pot.in
|- batch.json
```

- **input.in** 是控制文件，类似于 VASP 中的 INCAR，大部分变化的参数都在这个文件中指定。
- **submit.pbs** 是 PBS 系统的作业排队文件，通常唯一需要更改的就是作业的名称。
- **pot.in** 是模拟系统的物理参数，类似于 VASP 中的 POTCAR，通常这个文件保持不变。
- **MISFIT, TEM, STRESS** 是在 input.in 文件中使用的关键词。

#### 阶段 1：作业调度
``` sh
# Input
sjob schedule batch.json
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
使用 `sjob schedule` 命令后，将生成 9 个作业。变化参数的值将同时打印到屏幕上，并写入到 *batchList.txt* 文件中。需要注意的是，这里 MISFIT 和 TEM 的值是相互依赖的。
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
#### 阶段 2：文件夹创建
``` sh
# Input
sjob create batch.json
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
### 阶段 3：执行（作业提交）
```sh
# Input 
sjob execute batch.json
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
### 风格 2
不建议在没有 JSON 配置文件的情况下使用命令行参数运行，您可以阅读下面每个子命令的解释，以了解所需的变量。以下是一个示例：
``` sh
folders="TEM#@exx#@eyy#REALDIM#SYSDIM"   # 用 “#” 分隔，为了固定关键字替换的格式样式，在（关键字）前面插入 “@” 
files="&input.in pot.in @ferro.pbs"     # “&” 用于自由格式文件，“@” 用于固定格式文件，不使用任何符号则仅表示复制
TEM="298 350 560"                       # 每个变量用 “ ”（空格）分隔，当变量包含不止一个数字时使用 “:”（冒号）
exx="0.1 0.2 0.3"
eyy="0.1 0.2 0.3"
realdim="123:234:234 456:567:678"
sysdim="123:234:234 456:567:678"
variables="${TEM}#${exx}#${eyy}#${realdim}#${sysdim}" # 不同的变量用 “#” 分隔
sjob schedule -k "${folders}" -v "${variables}" -c 'exx>=eyy&&"REALDIM"=="SYSDIM"'     # 没有第四个参数时，将使用 “+” 作为默认值
sjob create -f "${files}"
sjob execute -c "echo TEM,exx,eyy,REALDIM"
```

---
## batch.json
[跳回到示例，风格 1](#风格-1)

这是一个 JSON 文件，它包含了在创建高通量作业的所有三个阶段中，sjob 所需的必要参数。
关键词包括：
- **FreeFile**：自由格式样式的文件列表，用于 *create* 阶段
- **FixFile** 一个固定格式样式文件的列表，用于 *create* 阶段
- **CopyFile** 一个仅用于复制的文件列表，不进行关键字替换，用于 *create* 阶段
- **FreeVar** 一个变量关键字列表，这些关键字将使用自由格式样式进行替换，用于 *schedule* 阶段
- **FixVar** 一个变量关键字列表，这些关键字将使用固定格式样式进行替换，用于 *schedule* 阶段
- **VarValue** 一个对象集合，以变量关键字为键，以扫描值为值，用于 *schedule* 阶段
- **VarSequence** 一个列表，或列表的列表，用于指定变量的不同层次。这意味着在高通量作业创建过程中，同一层次内的变量将同时更改值，而不同层次之间的变量将独立更改。用于 *schedule* 阶段
- **Separator** 一个字符，用于分隔生成文件夹名称中的关键字，例如“3+TEM_298+exx_0.1”中的“+”号，默认值为“+”。你也可以使用“/”来生成多层文件夹结构。用于 *schedule* 阶段
- **Format** 一个字符串。C风格字符串格式，用于格式化变量值在 *batchList.txt* 文件中的写入方式。用于 *schedule* 阶段
- **Condition** 一个字符串。变量之间的特殊条件，只有当评估为真时才会调度作业。例如，“VAR1>VAR2”，只有当 VAR1 的值大于 VAR2 时，参数才会写入 *batchList.txt* 文件。用于 *schedule* 阶段
- **Command** 一个字符串。你希望在每个创建的文件夹中执行的命令。用于 *execute* 阶段

#### batchList.txt
batchList.txt 文件的结构如下：
1. 整个文件的列与列之间用 | 分隔
2. 第一行是标题行。第一列是在创建的文件夹名称中关键字与值对之间的分隔符，例如 “3+TEM_298+exx_0.1” 中的 “+” 符号，默认值为 “+”。你可以在此处使用 “/”，这样生成的就不是单层文件夹，而是子文件夹。最后一列是原始的条件语句。而中间的所有其他列则是输入文件中要被某些值替换的关键字
3. 接下来的各行都是用于替换的变量，每一行将用于在下一阶段生成一个文件夹。第一列是当前变量集的索引。最后一列是将关键字替换为相应变量后的条件语句。中间的列是遍历的参数

一个示例的 batchList.txt 文件看起来像这样：
+ |           @FREQ |          PERIOD |        FREQ>1e9
1 |        1.00e+12 |        1.00e+00 |    1.00e+12>1e9
2 |        1.00e+13 |        1.00e-01 |    1.00e+13>1e9

第一个元素位于第一行第一列，它是我们通过 -s 选项设置的分隔符。
第一行给出了我们通过 -k 选项设置的关键字名称。
第一行的最后一列给出了通过 -c 选项设置的条件表达式。
第一列是所有要生成的情况的索引。
最后一列是将关键字替换为当前值后的条件表达式。
中间的所有内容都是通过 -v 选项设置的关键字对应的值。

---
## Schedule
### 概述
`sjob schedule` 命令负责调度阶段的工作。它将生成一个名为 *batchList.txt* 的文件，该文件列出了所有已调度的计算任务，这些任务将在创建和执行阶段中使用。

你可以使用一个 JSON 文件进行配置，也可以明确地将选项传递给命令。有两个必需的选项：1. -k（或 --keyword）选项，它告知程序在第二个文件夹创建阶段要搜索并替换的关键字是什么；2. -v（或 --value）选项，它告知程序用于替换关键字的值是什么。

### 可选参数
- **-k**，**--keyword** *必需* 设置要搜索的关键字，不同的关键字用 # 分隔。例如，"@freq#SIMDIM" 表示在创建阶段，程序将搜索两个关键字 "freq" 和 "phase"。关键字前的符号 **@** 表示该关键字在第二阶段将如何被替换。默认情况下，程序会替换包含该关键字的整行，这适用于自由格式的输入，即每行只为一个变量赋值，例如 `SIMDIM = 100 100 100`。添加 **@** 符号会改变替换行为，仅替换关键字本身，这对于固定格式的输入很有用，因为在固定格式输入中，每行包含多个变量的值。
- **-v**，**--value** *必需* 设置用于替换关键字的值列表。每个值列表中的值用 “”（空格）分隔，如果每个值由多个数字组成，我们使用 **|** 将它们连接起来，以免与列表中的其他项混淆，不同的值列表用 “#” 分隔。例如，1e9 1e10#10|10|10 50|50|50 表示对于第一个关键字，它将被替换为 1e9 或 1e10，对于第二个关键字，它将被替换为 10 10 10 或 50 50 50。此选项的巧妙之处在于，你可以使用另一个关键字的名称来表示当前值并计算该关键字的值。例如，关键字为 @freq#@omega，虽然两个值都需要改变，但我们知道 freq * omega = 1，所以对于值列表我们可以写成 1e9 1e10#1/freq，这样只有两种计算情况会被写入 batchList.txt 文件，即 freq = 1e9，omega = 1e - 9 和 freq = 1e10，omega = 1e - 10。目前，仅支持对标量值进行计算解析。
- **-c**，**--condition** *可选* 为整个参数空间设置一个条件表达式，只有那些使表达式结果为真的情况才会被写入 batchList.txt 文件。默认条件是 1>0，这使得整个参数空间都是有效的。与 -v 选项类似，你可以使用关键字的名称来表示它们的当前值。例如，关键字为 @exx#@eyy，并且我们已知 exx 和 eyy 是对称的，这意味着我们只需要计算整个参数空间中 exx >= eyy 或者反之的那一半情况。因此，对于值列表 -0.1 0 0.1#-0.1 0 0.1，我们可以设置条件 exx>=eyy，这样只有 6 种情况而非 9 种情况会被写入 batchList.txt 文件。
- **-s**，**--separater** *可选*：设置在第 2 阶段创建的文件夹名称中不同关键字 - 值对之间的分隔字符。默认值为 +。你可以使用该分隔字符来控制是要单层文件夹结构，例如 01+freq_1e9+omega_1e - 9，还是要多层文件夹结构，例如 freq_1e9/omega_1e - 9。
- **-f**，**--format** *可选*：为值列表中的替换值设置 printf 格式。默认是 %s，即将值视为字符串，本质上不进行格式设置，直接使用 awk 命令显示的内容。实用的示例可以是 %.2e，即保留两位小数的科学记数法。你可以只设置一种格式，该格式将应用于所有关键字的值；或者你也可以设置多个用 # 分隔的格式，例如 %.2e#%.3f。
- **-h**，**--help** *可选*：显示帮助文档（即此文件）。
  
### 示例
1. `sjob schedule -k "FREQ" -v "1e12 1e13" -f "%.2e"` 
2. `sjob schedule -k "@FREQ#PERIOD" -v "1e12 1e13#1e12/FREQ" -c "FREQ>1e9" -f "%.2e"` 



---
## Create
### 概述
`sjob create` 命令负责文件夹创建阶段的工作。它会（且仅会）根据 *batchList.txt* 文件中的信息生成一系列文件夹或文件夹结构。

你可以使用 JSON 文件进行配置，也可以直接向命令传递选项。此命令会接收一个文件列表作为参数，并根据使用 schedule 命令创建的 batchList.txt 文件将这些文件复制到每个文件夹中。当然，这些文件中的关键字会被 batchList.txt 文件中的值替换。实际上，复制操作有三种类型：1. 纯复制，不进行任何关键字替换；2. 固定格式类型复制，在此过程中仅替换关键字本身；3. 自由格式类型复制，会用包含特定值的新行替换包含关键字的整行。

你需要在每个文件前添加一个声明字符，以指定处理该文件时要使用的复制样式：
- 不添加字符表示纯复制类型
- **@** 表示固定格式类型
- **&** 表示自由格式类型
这里设置的样式与 schedule 命令中设置的样式确实存在一些重叠，但我们这样做是为了消除任何歧义。对于自由格式文件，你可以同时进行自由格式和固定格式的关键字替换；而对于固定格式文件，你只能进行固定格式的关键字替换。

### 选项
-h，--help *可选*：显示帮助文档。

### 示例
1.` sjob create &input.in @Ferro.pbs pot.in`


---
## Execute
### 概述
`sjob execute` 命令负责命令执行阶段的工作。该命令会进入根据 batchList.txt 文件创建的每个文件夹，并执行你传递给它的命令。与 schedule 命令中的条件选项和值选项类似，你可以使用关键字名称来表示这些变量的当前值，从而为不同的文件夹实现不同的执行结果。

你可以使用 JSON 文件进行配置，也可以直接向命令明确传递选项。

### 选项
- **-s**，**--start** *可选*：设置你想要开始执行命令的文件夹的索引，你可以在 batchList.txt 文件的第一列找到该索引。
- **-e**，**--end** *可选*：设置你想要结束执行命令的文件夹的索引，你可以在 batchList.txt 文件的第一列找到该索引。
- **-h**，**--help** *可选*：显示帮助文档。

### 示例
1. `sjob execute "echo FREQ"`
2. `sjob execute "qsub Ferro.pbs"`


---
## 实用工具

- writeBatchList [$1:关键字] [$2: 替换变量] [$3:条件语句] [$4: 分隔符]
  * $1：关键字之间用 # 分隔，默认采用自由格式的关键字，即整行将被关键字和值对替换。你可以在关键字前加 @ 符号来选择固定格式，这意味着只有关键字本身会被遍历值替换，例如 SYSDIM#TEM”、“TEM#@exx#@eyy。
  * $2：不同变量之间用 # 分隔，同一变量的不同值用 “ ” 分隔，对于一次替换中的不同数字用 : 分隔（因为是替换整行，可能会有多个数字），例如 100:100:100 200:200:200#200 250 300。
  * $3：awk 风格的条件语句，你可以用关键字表示当前变量的值，例如 exx>=eyy&&"REALDIM"=="SYSDIM"，这意味着只有当 exx 大于或等于 eyy 且 SYSDIM 与 REALDIM 相同时的情况才会被生成。注意 REALDIM 和 SYSDIM 要加引号，因为这两个关键字的值不是单个数字，它们之间的比较应该是字符串比较。
  * $4：用于后续文件夹生成阶段分隔关键字 - 值对的分隔符。默认值是 +，你可以将其设置为 /，这样会生成子文件夹结构，且每个层级与一个变量的变化相关。例如，如果你不设置这个参数，文件夹可能像 01+TEM_350+exx_0.3；如果你将其设置为 /，文件夹会像 TEM_350/exx_0.3/。
- makeFolders [$1:文件列表] [$2: 起始索引] [$3: 结束索引]
  * $1：文件之间用 “ ” 分隔，如果你想将某个文件按自由格式处理，在文件名前加 &；如果你想将某个文件按固定格式处理，在文件名前加 @；若文件仅需复制而不处理，则什么都不加，例如 &input.in @ferro.pbs。注意，自由格式文件可以同时包含自由格式类型和固定类型的变量，这意味着变量的替换方式将由为单个关键字设置的类型决定；而固定格式文件只能有固定格式风格的变量，这意味着无论为关键字设置何种风格，在对固定格式文件进行替换时，都会将其视为固定格式风格。
  * $2：可选参数，用于设置文件夹生成的起始行/索引（在 batchList.txt 文件内），默认值是 1，即从 batchList.txt 索引为 1 的行（也就是第二行）开始。
  * $3：可选参数，用于设置文件夹生成的结束行/索引（在 batchList.txt 文件内），默认值是 batchList.txt 文件的行数，所以当到达 batchList.txt 文件的最后一行时，文件夹创建将结束。
- execFolders [$1:命令] [$2: 起始索引] [$3: 结束索引]
  * $1：你想在 makeFolders 生成的每个文件夹中执行的命令，你可以在这里用关键字表示文件夹内的变量值，例如 echo TEM,exx,eyy。
  * $2：可选参数，用于设置文件夹生成的起始行/索引（在 batchList.txt 文件内），默认值是 1，即从 batchList.txt 索引为 1 的行（也就是第二行）开始。
  * $3：可选参数，用于设置文件夹生成的结束行/索引（在 batchList.txt 文件内），默认值是 batchList.txt 文件的行数，所以当到达 batchList.txt 文件的最后一行时，文件夹创建将结束。
- batchAllCommand [$1: 命令字符串]
  * $1：以字符串形式表示的命令，也就是你在终端中输入执行的命令，例如 qsub ferro.pbs。

---
## 自由 & 固定格式

在模拟输入方面，大致有两种格式。一种是固定格式，即每个参数的位置和顺序都是固定的；另一种是自由格式，意味着参数的位置和顺序不固定，只要用户遵循诸如 “关键字 = 值” 这样的规则，文件就是有效的。

让我们看一个例子：
``` sh
# 对于固定格式而言，如果你调换第一行和第二行的顺序，程序就会崩溃
10          # VAR1 值
10 20 30    # VAR2 值
```
``` sh
# 自由格式下，你可以调换第一行和第二行的顺序
VAR1 = 10
VAR2 = 10 20 30
```