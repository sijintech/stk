import argparse
from .._3D.generate_phi import generate_phi
from .._4D.generate_comp import generate_comp_Icase0
from .._4D.generate_comp import generate_comp_Icase1
from .._4D.generate_comp import generate_comp_Icase2
from .._4D.generate_comp import generate_comp_Icase3
from .._5D.generate_eta import generate_eta_Icase0
from .._5D.generate_eta import generate_eta_Icase1
from .._5D.generate_eta import generate_eta_Icase2
from .._5D.generate_eta import generate_eta_Icase3
from ..basic.write_matrix import write_structure_to_file
from ..basic.utils import read_toml


def generate_structure():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f','--filename',default="tests/input_muBreakdown.toml",help='Path of configuration file for generating eta/comp/phi structure data.')
    args = parser.parse_args()


    total_config = read_toml(args.filename)
    target_program = total_config.get('target_program', None)

    if not target_program:
        raise ValueError("The 'target_program' is missing in the configuration file. Aborting.")

    if target_program == 'muBreakdown':

        common_config = total_config["common_config"]
        params = total_config["parameters"]
        output = total_config["output"]

        nx = common_config["nx"]
        ny = common_config["ny"]
        nz = common_config["nz"]
        ptclnum = common_config["ptclnum"]

        rr = params["rr"]
        shell_thickness = params["shell_thickness"]
        iseed = params["iseed"]
        structure_type = params["structure_type"]

        print("Generating structure for 'muBreakdown'...")
        phim, phip, phis, phiv = generate_phi(nx, ny, nz, rr, shell_thickness, ptclnum, iseed)

        # 输出结构到文件
        output_file = output["output_file"]
        print(f"Writing muBreakdown structure to {output_file}")
        write_structure_to_file(output_file, nx, ny, nz, phip, phis, phim, phiv, structure_type)  # 输出类型为1

    elif target_program == 'muPRODICT':

        total_config = read_toml(args.filename)
        common_config = total_config["common_config"]
        eta_config    = total_config["eta_config"]
        comp_config   = total_config["comp_config"]
        eta_case_config = total_config["eta_case_config"]
        comp_case_config = total_config["comp_case_config"]
        eta_case = eta_config["set_eta_case"]
        comp_case = comp_config["set_comp_case"]
        print("eta case: {}, comp case: {}".format(eta_case, comp_case))
        if(eta_case != -1):
          print("Start to generate eta file")
          generateEtaFileWithConfig(common_config, eta_case_config,eta_case)
          print("Finish to generate eta file")
        if(comp_case != -1):
          print("Start to generate comp file")
          generateCompFileWithConfig(common_config, comp_case_config,comp_case)
          print("Finish to generate comp file")

def generateEtaFileWithConfig(common_config, eta_case_config, case):
    eta_selected_config = {}
    for config in eta_case_config:
      if(config["case"] == case):
        eta_selected_config = config
    if(len(eta_selected_config) == 0):
      raise AttributeError("The eta configuration was not successfully read")

    generated_function = globals()["generate_eta_Icase{}".format(case)]
    generated_function(common_config, eta_selected_config)

def generateCompFileWithConfig(common_config, comp_case_config,case):
    comp_selected_config = {}
    for config in comp_case_config:
      if(config["case"] == case):
        comp_selected_config = config
    if(len(comp_selected_config) == 0):
      raise AttributeError("The comp configuration was not successfully read")
    
    generated_function = globals()["generate_comp_Icase{}".format(case)]
    generated_function(common_config, comp_selected_config)

if __name__ == '__main__':
    generate_structure()