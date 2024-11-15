import numpy as np
import pandas as pd
import glob
import numba
from numba import jit

domainTypeLabel = [' ']*27
domainTypeLabel[0]  = "    Substrate"
domainTypeLabel[1]  = "R1+( 1, 1, 1)"
domainTypeLabel[2]  = "R1-(-1,-1,-1)"
domainTypeLabel[3]  = "R2+(-1, 1, 1)"
domainTypeLabel[4]  = "R2-( 1,-1,-1)"
domainTypeLabel[5]  = "R3+(-1,-1, 1)"
domainTypeLabel[6]  = "R3-( 1, 1,-1)"
domainTypeLabel[7]  = "R4+( 1,-1, 1)"
domainTypeLabel[8]  = "R4-(-1, 1,-1)"
domainTypeLabel[9]  = "O1+( 1, 1, 0)"
domainTypeLabel[10] = "O1-(-1,-1, 0)"
domainTypeLabel[11] = "O2+( 1,-1, 0)"
domainTypeLabel[12] = "O2-(-1, 1, 0)"
domainTypeLabel[13] = "O3+( 1, 0, 1)"
domainTypeLabel[14] = "O3-(-1, 0,-1)"
domainTypeLabel[15] = "O4+( 1, 0,-1)"
domainTypeLabel[16] = "O4-(-1, 0, 1)"
domainTypeLabel[17] = "O5+( 0, 1, 1)"
domainTypeLabel[18] = "O5-( 0,-1,-1)"
domainTypeLabel[19] = "O6+( 0, 1,-1)"
domainTypeLabel[20] = "O6-( 0,-1, 1)"
domainTypeLabel[21] = "a1+( 1, 0, 0)"
domainTypeLabel[22] = "a1-(-1, 0, 0)"
domainTypeLabel[23] = "a2+( 0, 1, 0)"
domainTypeLabel[24] = "a2-( 0,-1, 0)"
domainTypeLabel[25] = " C+( 0, 0, 1)"
domainTypeLabel[26] = " C-( 0, 0,-1)"



paiColor=[
        [0, "rgb(192, 192, 192)"],
        [0.01851, "rgb(192, 192, 192)"],
    
        [0.01851, "rgb(0, 0, 255)"],
        [0.0570096, "rgb(0, 0, 255)"],
    
        [0.0570096, "rgb(117, 182, 207)"],    
        [0.0955092, "rgb(117, 182, 207)"],    
    
        [0.0955092, "rgb(0, 40, 0)"],    
        [0.1340088, "rgb(0, 40, 0)"],    
    
        [0.1340088, "rgb(0, 255, 0)"],
        [0.1725084, "rgb(0, 255, 0)"],
    
        [0.1725084, "rgb(255, 0, 0)"],
        [0.211008,  "rgb(255, 0, 0)"],
    
        [0.211008, "rgb(255, 145, 161)"],
        [0.2495076,  "rgb(255, 145, 161)"],    
    
        [0.2495076, "rgb(255, 107, 0)"],
        [0.2880072,  "rgb(255, 107, 0)"],
    
        [0.2880072,  "rgb(255, 255, 0)"],
        [0.3265068,  "rgb(255, 255, 0)"],
    
        [0.3265068,  "rgb(255, 0, 255)"],
        [0.3650064,  "rgb(255, 0, 255)"],

        [0.3650064, "rgb(165, 33, 33)"],
        [0.403506, "rgb(165, 33, 33)"],
    
        [0.403506, "rgb(229, 144, 161)"],
        [0.4420056, "rgb(229, 144, 161)"],
    
        [0.4420056, "rgb(191, 100, 191)"],
        [0.4805052, "rgb(191, 100, 191)"],

        [0.4805052, "rgb(106, 7, 89)"],
        [0.50, "rgb(106, 7, 89)"],
    
        [0.5005052, "rgb(106, 101, 7)"],
        [0.5190048, "rgb(106, 101, 7)"],

        [0.5190048, "rgb(172, 127, 76)"],
        [0.5575044, "rgb(172, 127, 76)"],

        [0.5575044, "rgb(121, 9, 36)"],
        [0.596004, "rgb(121, 9, 36)"],

        [0.596004, "rgb(245, 64, 50)"],
        [0.6345036, "rgb(245, 64, 50)"],

        [0.6345036, "rgb(90, 247, 90)"],
        [0.6730032, "rgb(90, 247, 90)"],
    
        [0.6730032, "rgb(9, 164, 9)"],
        [0.7115028, "rgb(9, 164, 9)"] ,   
    
        [0.7115028, "rgb(195, 195, 195)"],
        [0.7500024, "rgb(195, 195, 195)"]    ,

        [0.7500024, "rgb(43, 43, 43)"],
        [0.788502, "rgb(43, 43, 43)"],
    
        [0.788502, "rgb(144, 144, 144)"],
        [0.8270016, "rgb(144, 144, 144)"],
    
        [0.8270016, "rgb(100, 4, 225)"],
        [0.8655012, "rgb(100, 4, 225)"],
    
        [0.8655012, "rgb(0, 0, 0)"],
        [0.9040008, "rgb(0, 0, 0)"],
    
        [0.9040008, "rgb(255, 180, 0)"],
        [0.9425004, "rgb(255, 180, 0)"],
    
        [0.9425004, "rgb(225, 207, 76)"],
        [0.981, "rgb(225, 207, 76)"],
    
        [0.981, "rgb(226, 110, 7)"],
        [1.0, "rgb(226, 110, 7)"],
    ]





crr = [(0.752912, 0.752912, 0.752912),
 (0.0, 0.0, 1.0),
 (0.46, 0.7175, 0.8135),
 (0.0, 0.153787, 0.0),
 (0.0, 1.0, 0.0),
 (1.0, 0.0, 0.0),
 (1.0, 0.566921, 0.633741),
 (1.0, 0.418685, 0.0),
 (1.0, 1.0, 0.0),
 (1.0, 0.0, 1.0),
 (0.64629, 0.130165, 0.130165),
 (0.9, 0.566921, 0.633741),
 (0.751111, 0.393695, 0.751111),
 (0.418685, 0.027128, 0.027128),
 (0.678201, 0.49827, 0.301423),
 (0.476371, 0.035432, 0.14173),
 (0.961169, 0.251965, 0.199862),
 (0.355309, 0.968874, 0.355309),
 (0.038446, 0.64629, 0.038446),
 (0.766921, 0.766921, 0.766921),
 (0.16955, 0.16955, 0.16955),
 (0.566921, 0.566921, 0.566921),
 (0.393695, 0.015747, 0.885813),
 (0.0, 0.0, 0.0),
 (1.0, 0.710881, 0.0),
 (0.885813, 0.813533, 0.301423),
 (0.8867188, 0.4335937, 0.0273438)]


boundaries = [0,  0.5,  1.5,  2.5,  3.5,  4.5,  5.5,  6.5,  7.5,  8.5,
        9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 19.5,
       20.5, 21.5, 22.5, 23.5, 24.5, 25.5, 26]




def toDomain(x): 
    domainTypeLabel = [' ']*27
    domainTypeLabel[0]  = "    Substrate"
    domainTypeLabel[1]  = "R1+( 1, 1, 1)"
    domainTypeLabel[2]  = "R1-(-1,-1,-1)"
    domainTypeLabel[3]  = "R2+(-1, 1, 1)"
    domainTypeLabel[4]  = "R2-( 1,-1,-1)"
    domainTypeLabel[5]  = "R3+(-1,-1, 1)"
    domainTypeLabel[6]  = "R3-( 1, 1,-1)"
    domainTypeLabel[7]  = "R4+( 1,-1, 1)"
    domainTypeLabel[8]  = "R4-(-1, 1,-1)"
    domainTypeLabel[9]  = "O1+( 1, 1, 0)"
    domainTypeLabel[10] = "O1-(-1,-1, 0)"
    domainTypeLabel[11] = "O2+( 1,-1, 0)"
    domainTypeLabel[12] = "O2-(-1, 1, 0)"
    domainTypeLabel[13] = "O3+( 1, 0, 1)"
    domainTypeLabel[14] = "O3-(-1, 0,-1)"
    domainTypeLabel[15] = "O4+( 1, 0,-1)"
    domainTypeLabel[16] = "O4-(-1, 0, 1)"
    domainTypeLabel[17] = "O5+( 0, 1, 1)"
    domainTypeLabel[18] = "O5-( 0,-1,-1)"
    domainTypeLabel[19] = "O6+( 0, 1,-1)"
    domainTypeLabel[20] = "O6-( 0,-1, 1)"
    domainTypeLabel[21] = "a1+( 1, 0, 0)"
    domainTypeLabel[22] = "a1-(-1, 0, 0)"
    domainTypeLabel[23] = "a2+( 0, 1, 0)"
    domainTypeLabel[24] = "a2-( 0,-1, 0)"
    domainTypeLabel[25] = " C+( 0, 0, 1)"
    domainTypeLabel[26] = " C-( 0, 0,-1)"
    
    if np.isnan(x) or x == -1:
        return "None"
    return domainTypeLabel[int(x)]

def dat_to_df(A, columns):
    shape = A.shape
    index = pd.MultiIndex.from_product([range(s)for s in shape], names=columns)
    df = pd.DataFrame({'A': A.flatten()}, index=index).reset_index()
    return df

def pfEnergy_to_df(fname):
    with open(fname) as f:
        read_data = f.readlines()
        
    head = read_data[0].replace(' Energy', '_Energy').replace('Grad ', 'Grad_').split()
    df = [[conv(item) 
              for item in line.split() if ':' not in item] 
                      for line in read_data[1:]] 

    df = pd.DataFrame(df)
    df.columns = head
    del read_data
    print(df.columns)
    return df


def conv(stt):
    try:
        return float(stt)
    except ValueError:
        stt = 'E-'.join(stt.split('-'))
        stt = 'E+'.join(stt.split('+'))
        if stt[0]=='E':
            stt = stt[1:]
        return float(stt)
    



def pfDat_to_df(path):
    with open(path) as f:
        read_data = f.readlines()

    df = [list(map(float, line.split())) for line in read_data] 

    head = df[0]
    del df[0]

    df = np.array(df)
    df = pd.DataFrame(df)
    if df.shape[1] == 9:
        df.columns = ['x', 'y', 'z', 'gx', 'gy', 'gz', 'lx', 'ly', 'lz']

    elif df.shape[1] == 6:
        df.columns = ['x', 'y', 'z', 'gx', 'gy', 'gz']

    elif df.shape[1] == 4:
        df.columns = ['x', 'y', 'z', 'n']

    
    df = df.astype(float)
    return df

def pdDat_to_list(fname):
    with open(fname) as f:
        read_data = f.readlines()
        
    head = read_data[0].split()
    df = [list(map(float, line.split())) for line in read_data[1:]] 
    return df, head



def pf_summary(path):
    folderList = glob.glob(path + '*')

    SYSDIM = []
    REALDIM = []
    LBULK = []
    FILMTHICK = []
    SUBTHICK = []

    TEM = []
    TTOTAL = []
    MISFIT = []

    GRADPCON = []
    LELEC = []
    CELECBC = []
    DIELECON = []
    GRADQCON = []
    LDEFECT = []
    TIMESTART = []
    TIMEEND = []

    RUNS = []

    for folder in folderList:
        with open(folder + '/input.in') as f:
            input_ = f.read().splitlines() 
            
        SYSDIM  += [list(map(int, line.split()[-3:])) for line in input_ if "SYSDIM = " in line and "#" not in line]
        REALDIM += [list(map(int, line.split()[-3:])) for line in input_ if "REALDIM = " in line and "#" not in line]    
        LBULK += [line.split()[-1].upper()=="T" for line in input_ if "LBULK = " in line and "#" not in line]
        FILMTHICK += [int(line.split()[-1]) for line in input_ if "FILMTHICK = " in line and "#" not in line]
        SUBTHICK += [int(line.split()[-1]) for line in input_ if "SUBTHICK = " in line and "#" not in line]

        TEM += [int(line.split()[-1]) for line in input_ if "TEM = " in line and "#" not in line]
        TTOTAL += [int(line.split()[-1]) for line in input_ if "TTOTAL = " in line and "#" not in line]
        MISFIT += [list(map(float, line.split()[-3:])) for line in input_ if "MISFIT = " in line and "#" not in line]

        LELEC += [line.split()[-1].upper()=="T" for line in input_ if "LELEC = " in line and "#" not in line]
        CELECBC += [int(line.split()[-1]) for line in input_ if "CELECBC = " in line and "#" not in line]

        DIELECON += [list(map(int, line.split()[-3:])) for line in input_ if "DIELECON = " in line and "#" not in line] \
                      if [list(map(int, line.split()[-3:])) 
                          for line in input_ if "DIELECON = " in line and "#" not in line] != [] else [np.nan] 

        GRADPCON += [list(map(float, line.split()[-3:])) for line in input_ if "GRADPCON = " in line and "#" not in line]  
        GRADQCON += [list(map(float, line.split()[-3:])) for line in input_ if "GRADQCON = " in line and "#" not in line] 

        LDEFECT += [line.split()[-1].upper()=="T" for line in input_ if "LDEFECT = " in line and "#" not in line]\
                    if [line.split()[-1].upper()=="T" 
                        for line in input_ if "LDEFECT = " in line and "#" not in line] != [] else [np.nan] 
        RUNS += [folder.split('/')[-1]]


    for log in glob.glob( path + '*/*.o*'):
        with open(log) as f:
            logcontent = f.read().splitlines()     

        TIMESTART += [logcontent[0]]
        TIMEEND += [logcontent[-1]]

    df = pd.DataFrame({
        "SYSDIM":SYSDIM, 
        "REALDIM": REALDIM,
        "LBULK":LBULK,
        "FILMTHICK":FILMTHICK,
        "SUBTHICK":SUBTHICK,

        "TEM":TEM,
        "TTOTAL":TTOTAL,
        "MISFIT":MISFIT,

        "LELEC":LELEC,
        "CELECBC":CELECBC,
        "DIELECON": DIELECON,

        "GRADPCON":GRADPCON,
        "GRADQCON": GRADQCON,

        "LDEFECT":LDEFECT, 

        "RUNS": RUNS, 
#        "TIMESTART": TIMESTART, 
#        "TIMEEND":TIMEEND,

    })
    return df