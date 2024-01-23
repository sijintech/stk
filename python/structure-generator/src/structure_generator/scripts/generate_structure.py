import argparse
from .._4D.generate_comp import generate_comp_Icase0
from .._4D.generate_comp import generate_comp_Icase1
from .._4D.generate_comp import generate_comp_Icase2
from .._4D.generate_comp import generate_comp_Icase3
from .._5D.generate_eta import generate_eta_Icase0
from .._5D.generate_eta import generate_eta_Icase1
from .._5D.generate_eta import generate_eta_Icase2
from .._5D.generate_eta import generate_eta_Icase3
from ..basic.utils import read_toml

def generate_structure():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f','--filename',default="input.toml",help='Path of configuration file for generating eta/comp structure data.')
    args = parser.parse_args()
    
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