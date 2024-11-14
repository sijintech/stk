# Compile user manual and documentation

Documentation is for developers and manual is for users.
We are now using doxygen + doxybook2 to generate our user manual.

```
cd documentation
doxygen Doxyfile
cd doxygen-out/latex; make; cd -
mkdir -p doxybook-out
doxybook2 --input doxygen-out/xml --output doxybook-out --config doxybook-config.json
cd mkdocs
mkdocs serve
```

```
cd manual
doxygen Doxyfile
cd doxygen-out/latex; make; cd -
mkdir -p doxybook-out
doxybook2 --input doxygen-out/xml --output doxybook-out --config doxybook-config.json
mkdocs serve
```
