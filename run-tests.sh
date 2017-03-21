#!/bin/bash
# NOTE: set environment variable `PHEWEB_DEBUG` to get an ipdb shell on failure

set -euo pipefail

rm -rf "/tmp/pheweb-test-venv-${USER}-"*

if [[ "${1:-}" == install ]]; then
    tempdir="$(mktemp -d "/tmp/pheweb-test-${USER}-XXXX")"
    pushd "$tempdir" > /dev/null
    echo -e "\n\n====> populating /$tempdir/venv3"
    virtualenv -p python3 ./venv3
    set +u && source ./venv3/bin/activate && set -u
    popd > /dev/null
    pip3 install .
    echo -e "\n\n===> \`pheweb\` is $(which pheweb)"
    which pheweb | grep -q "$tempdir"
fi

cd test/data_dir

rm -rf pheno-list.json cpra/

echo -e "\n\n\n====> ./make_phenolist.sh"
./make_phenolist.sh

echo -e "\n\n\n====> pheweb process-assoc-files"
pheweb process-assoc-files

port="$(python3 -c "print(__import__('random').randrange(8000,9000))")"
echo -e "\n\n\n====> pheweb serve --port $port"
pheweb serve --port "$port" &
pid=$!
sleep 1
curl -sSI "http://localhost:$port/" | grep -q 200
curl -sSI "http://localhost:$port/variant/15-55447871-C-T" | grep -q 200
curl -sSI "http://localhost:$port/static/variant.js" | grep -q 200
curl -sSI "http://localhost:$port/pheno/snowstorm" | grep -q 200
curl -sSI "http://localhost:$port/api/manhattan/pheno/snowstorm.json" | grep -q 200
curl -sSI "http://localhost:$port/api/qq/pheno/snowstorm.json" | grep -q 200
curl -sSI "http://localhost:$port/region/snowstorm/8:926279-1326279" | grep -q 200
curl -sSI "http://localhost:$port/api/region/snowstorm/lz-results/?filter=analysis%20in%203%20and%20chromosome%20in%20%20%278%27%20and%20position%20ge%20976279%20and%20position%20le%201276279" | grep -q 200
curl -sSI "http://localhost:$port/region/snowstorm/gene/DNAH14?include=1-225494097" | grep -q 200
curl -sSI "http://localhost:$port/api/autocomplete?query=%20DAP-2" | grep -q 200
curl -sS "http://localhost:$port/region/1/gene/SAMD11" | grep -q EAR-LENGTH
kill $pid

echo -e "\n\n====> SUCCESS"

rm -rf "/tmp/pheweb-test-venv-${USER}-"*
