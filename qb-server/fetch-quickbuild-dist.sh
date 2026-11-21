#!/bin/sh
# Resolve a QuickBuild server distribution into DEST_DIR at image build time.
# Used by qb-server/Dockerfile and qb-agent/base/Dockerfile (build stage "qb-dist").
#
# Usage: fetch-quickbuild-dist.sh DEST_DIR
#
# Environment (Docker build args):
#   QB_VERSION          QuickBuild version, e.g. 16.0.37 (required)
#   QB_DOWNLOAD_URL     Distribution zip URL used when no local copy exists
#   QB_DOWNLOAD_SHA256  Expected SHA-256 of the zip (empty = skip verification)
#   QB_ENV_DIR          Directory holding local copies (default /tmp/qb-env = repo environment/)
#
# Sources (first match wins):
#   1. $QB_ENV_DIR/quickbuild-$QB_VERSION/[quickbuild-$QB_VERSION/]   unpacked distribution
#   2. $QB_ENV_DIR/quickbuild-$QB_VERSION.zip                         local zip (checksum verified)
#   3. $QB_DOWNLOAD_URL                                               download (checksum verified)

set -eu

dest="${1:?usage: fetch-quickbuild-dist.sh DEST_DIR}"
version="${QB_VERSION:?QB_VERSION is required}"
env_dir="${QB_ENV_DIR:-/tmp/qb-env}"
work="$(mktemp -d)"
src=""

for candidate in "$env_dir/quickbuild-$version/quickbuild-$version" "$env_dir/quickbuild-$version"; do
    if [ -f "$candidate/bin/server.sh" ]; then
        src="$candidate"
        echo "Using unpacked QuickBuild distribution $src"
        break
    fi
done

if [ -z "$src" ]; then
    if [ -f "$env_dir/quickbuild-$version.zip" ]; then
        archive="$env_dir/quickbuild-$version.zip"
        echo "Using local QuickBuild archive $archive"
    else
        url="${QB_DOWNLOAD_URL:?QB_DOWNLOAD_URL is required when no local distribution is present}"
        archive="$work/quickbuild.zip"
        echo "Downloading QuickBuild $version from $url"
        curl -fSL --retry 3 -o "$archive" "$url"
    fi

    if [ -n "${QB_DOWNLOAD_SHA256:-}" ]; then
        echo "${QB_DOWNLOAD_SHA256}  ${archive}" | sha256sum -c -
    else
        echo "WARNING: QB_DOWNLOAD_SHA256 is empty; skipping checksum verification"
    fi

    unzip -q "$archive" -d "$work/unpack"
    server_sh="$(find "$work/unpack" -maxdepth 3 -path '*/bin/server.sh' | head -n 1)"
    if [ -z "$server_sh" ]; then
        echo "ERROR: bin/server.sh not found in QuickBuild archive" >&2
        exit 1
    fi
    src="$(dirname "$(dirname "$server_sh")")"
fi

mkdir -p "$dest"
cp -a "$src"/. "$dest"/
rm -rf "$work"

if ! grep -q "^version=${version}\$" "$dest/asset/release"; then
    echo "ERROR: installed distribution is not QuickBuild $version:" >&2
    cat "$dest/asset/release" >&2
    exit 1
fi

chmod +x "$dest"/bin/*.sh "$dest"/bin/wrapper-linux-* "$dest"/agent/*.sh "$dest"/agent/*/*.sh
echo "QuickBuild $version distribution installed in $dest"
