import toml

def r4_uniform_01(seed):
    i4_huge = 2147483647
    if(seed == 0):
        print(" ")
        print('R4_UNIFORM_01 - Fatal error!')
        print("  Input value of SEED = 0.")
        return
    k = int(seed / 127773)
    seed = 16807 * (seed - k * 127773) - k * 2836
    if (seed < 0):
            seed = seed + i4_huge
    return seed, float(seed) * 4.656612875E-10

def read_toml(file_name):
    with open(file_name) as f:
        data = toml.load(f)
        return data

if __name__ == "__main__":
    print(r4_uniform_01(12345)) # 207482415, 0.096616
    print(r4_uniform_01(207482415)) # 1790989824, 0.833995
    print(r4_uniform_01(1790989824)) # 2035175616, 0.947702