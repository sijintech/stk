import toml

def r4_uniform_01(seed):
    i4_huge = 2147483647
    if(seed == 0):
        print(" ")
        print('R4_UNIFORM_01 - Fatal error!')
        print("  Input value of SEED = 0.")
        return
    k = seed / 127773
    seed = 16807 * (seed - k * 127773) - k * 2836
    if (seed < 0):
            seed = seed + i4_huge
    return float(seed) * 4.656612875E-10

def read_toml(file_name):
    with open(file_name) as f:
        data = toml.load(f)
        return data