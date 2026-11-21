#!/bin/sh
# Fetch EB Garamond (OFL) for the story PDF build. Fonts land in .assets/fonts,
# which is git-ignored; the PDF itself is committed.
set -e
cd "$(dirname "$0")/.."
mkdir -p .assets/fonts
cd .assets/fonts
curl -sL -o eb.tgz https://registry.npmjs.org/@fontsource/eb-garamond/-/eb-garamond-5.3.0.tgz
tar xzf eb.tgz \
  package/files/eb-garamond-latin-400-normal.woff \
  package/files/eb-garamond-latin-400-italic.woff \
  package/files/eb-garamond-latin-600-normal.woff \
  package/files/eb-garamond-latin-600-italic.woff \
  package/files/eb-garamond-latin-700-normal.woff
mv package/files/*.woff .
rm -rf package eb.tgz
python3 - <<'PY'
from fontTools.ttLib import TTFont
import glob
for f in glob.glob('*.woff'):
    t = TTFont(f); t.flavor = None; t.save(f[:-5] + '.ttf')
PY
echo "fonts ready in $PWD"
