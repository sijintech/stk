# Usage

This is the user manual

```sh
cd manual
rm -rf doxygen-out doxybook-out gatsby/source
doxygen Doxyfile
cd doxygen-out/latex; make; cd -
mkdir -p doxybook-out; doxybook2 --input doxygen-out/xml --output doxybook-out --config doxybook-config.json --templates .
# mkdir -p gatsby/source ;cp -r doxybook-out/* gatsby/source
# find ./gatsby/source -type f -name "*.md" -print0 | xargs -0 sed -i 's/^#/##/g'
# mv gatsby/source/index.md gatsby/source/index.mdx
```

```sh
cd gatsby
yarn install
yarn develop
yarn build
surge public/
```

```
perl -i -pe 's/^#/##/gm file.md'
perl -0777 -i -pe 's/^##/#/ file.md'
python ../../../scripts/doc/doc_hash_replace.py ./doxybook-out/
```
