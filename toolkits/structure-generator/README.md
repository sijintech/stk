# sturcture_generator
## Instruction
This is a package designed to generate eta/comp structures, consisting of four modules. In the `basic` module, there are functions for generating 3D data with various distributions and functions for writing data to files. The `eta` module contains functions for generating eta data, the `comp` module includes functions for generating comp data, and in the `scripts` module, there are functions that can be executed via the command line.

## How to use
In the `pyproject.toml` file, a command-line command `generate_structure` is defined, with its detailed implementation specified in the `scripts/generate_structure.py` file. It accepts a parameter indicating the location of the `input.toml` file and ultimately generates eta/comp structural data.

## How to add functionality
If we want to add new functionality, we can utilize the basic functionalities within the `basic` module or add new functionalities to it. Subsequently, we can introduce a new package under the `structure_generator`, employing the basic functionalities to fulfill our requirements. Finally, we define functions for command-line invocation in the `scripts` directory, and we can pass command-line parameters through `argparser` package. It's important to note that the command-line configuration should be specified in the `pyproject.toml` file.

```toml
# pyproject.toml
[project.scripts]
generate_structure = structure_generator.generate_sturcture
```

## How to build a package
[pacakge build tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/)

### build construction
If you want to build the package, run the following commands in the directory where the `pyproject.toml` is located, depending on the operating system. The built package will appear in the `dist` folder.
```sh
# windows
py -m build
# Unix/macOs
python3 -m build
```
