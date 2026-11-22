#!/usr/bin/env bash
# Run from a workstation with Docker and the local CLI venv. Tests the committed HEAD.
set -euo pipefail

repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
python=${1:-"$repo/.venv/bin/python"}
[[ "$python" = /* && -x "$python" ]] || { echo "Supply an absolute path to the local venv Python." >&2; exit 1; }
tmp=$(mktemp -d)
setup=""
offline=""
image=""
cleanup() {
    if [[ -n "$offline" ]]; then docker rm -f "$offline" >/dev/null || true; fi
    if [[ -n "$setup" ]]; then docker rm -f "$setup" >/dev/null || true; fi
    if [[ -n "$image" ]]; then docker image rm "$image" >/dev/null || true; fi
    rm -rf -- "$tmp"
}
trap cleanup EXIT
limits=(--platform linux/amd64 --cpus 2 --memory 16g)
setup=$(docker run -d "${limits[@]}" ubuntu:24.04 sleep infinity)
docker exec -e DEBIAN_FRONTEND=noninteractive "$setup" bash -ec '
    apt-get update -qq
    apt-get install -y -qq ca-certificates git sudo python3 python3-venv python3-pip build-essential
    python3 -c "import sys; assert sys.version_info[:2] == (3, 12)"
    useradd -m team
    useradd -m evaluator
    echo "evaluator ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/evaluator
    chmod 440 /etc/sudoers.d/evaluator
    install -d -o team -g team /opt/solution{,/input,/output}
'

# Copy one committed tree, including its revision, into the disposable VM.
git clone -q --bare --no-local --depth 1 "$repo" "$tmp/release.git"
docker cp "$tmp/release.git" "$setup:/tmp/release.git"
docker exec "$setup" chown -R team:team /tmp/release.git
docker exec -u team -e HOME=/home/team -w /opt/solution "$setup" bash -ec '
    git clone -q --no-local --depth 1 /tmp/release.git ~/release
    bash ~/release/deploy/vm_setup.sh
    cd repo/data/uzp/dane
    find . -iname "*.pdf" -exec cp --parents -t /opt/solution/input -- {} +
'
image=$(docker commit "$setup")
offline=$(docker run -d "${limits[@]}" --network none "$image" sleep infinity)
docker cp "$setup:/opt/solution/input" "$tmp/input"
docker cp "$setup:/opt/solution/repo" "$tmp/repo"

cd "$tmp"
env -i HOME="$HOME" PATH="$PATH" PYTHONPATH="$tmp/repo" "$python" -P -m kio2json \
    --input input --output reference --jobs 2
count=$(find input -iname '*.pdf' | wc -l)
[[ "$count" -eq 226 && $(find reference -type f | wc -l) -eq "$count" ]]
for pass in first after-restart; do
    if [[ "$pass" == after-restart ]]; then
        docker stop "$offline" >/dev/null
        docker start "$offline" >/dev/null
    fi
    docker exec "$offline" find /opt/solution/output -type f -delete
    start=$(date +%s)
    docker exec -u evaluator -e HOME=/home/evaluator -w /opt/solution "$offline" bash -ec '
        command=$(sed -n "/^sudo /p" RUN.md)
        test -n "$command"
        bash -ec "$command"
    '
    elapsed=$(($(date +%s) - start))
    docker cp "$offline:/opt/solution/output" "$tmp/$pass"
    diff -qr reference "$pass"
    awk -v p="$pass" -v n="$count" -v t="$elapsed" \
        'BEGIN {printf "%s: %d/%d byte-identical, %ds offline; 150-PDF estimate %.1fs\n", p,n,n,t,t*150/n}'
    rm -rf -- "${tmp:?}/$pass"
done
