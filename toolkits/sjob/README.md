# sjob guide
## Overview
The **`sjob`** is a tool for high-throughput computer simulation's jobs creation and execution. This command provides a convenient interface to several useful command line tools related to high-throughput computer simulations starting from scheduling job parameters, creating folder structure to final submission.

## Install sjob In Ubuntu
You can use the `sjob` command in the terminal after installing 
```bash
pip install suan
```

It is not supported for use on Windows temporarily.
## Quick Start (recommended)
Use a JSON file for configuration

**step 1:** Prepare the `batch.json` file
``` json
// batch.json
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

``` sh
# input.in
VAR1 = 100
VAR2 = 30 40 40
```

**step 2:** Schedule jobs and create the *batchList.txt* file
``` sh
sjob schedule batch.json
```

**step 3:** Double check the listed jobs in *batchList.txt* and create folders
``` sh
sjob create batch.json
```

**step 4:** Go into the created folders and check if generated files are as expected, then execute the specified command
``` sh
sjob execute batch.json
```

## Use Command-line Arguments (not recommended)
The usage without json configuration file is not recommended, you may read the explanation for each sub command below to see what variables are needed. Here is an example

You need to create the `input.in`, `pot.in`, and `ferro.pbs` files by yourself.
``` sh
folders="TEM#@exx#@eyy#REALDIM#SYSDIM"   # separated by "#", for fix format style of keyword replacment insert @ in the front
files="&input.in pot.in @ferro.pbs"     # & for free format file, @ for fix format file, nothing for just copy
TEM="298 350 560"                       # each variable is separated by " ", use ":" when the variable contains more than one number
exx="0.1 0.2 0.3"
eyy="0.1 0.2 0.3"
realdim="123:234:234 456:567:678"
sysdim="123:234:234 456:567:678"
variables="${TEM}#${exx}#${eyy}#${realdim}#${sysdim}" # different variables are separated by #"
sjob schedule -k "${folders}" -v "${variables}" -c 'exx>=eyy&&"REALDIM"=="SYSDIM"'     # No 4th argument, default of + is used
sjob create -f "${files}"
sjob execute -c "echo TEM,exx,eyy,REALDIM"
```