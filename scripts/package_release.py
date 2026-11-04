#!/usr/bin/env python3
"""Deterministic offline packaging of verified upstream COIN XMRig + HiveOS wrapper."""
import argparse, gzip, hashlib, io, pathlib, tarfile

UPSTREAM_ARCHIVE_SHA="a63d82eefcebd8f5bba32199544435392014a301dbf6c90cb59c4dcfb66604b4"
UPSTREAM_BINARY_SHA="5b18de5443bf11c6565a433ab470c503c4192f6d17a33d0f8ad62c1852bcd462"
VERSION="1.1.0_beta1"
FOLDER="coinrig-native"
DOCS=["h-manifest.conf","h-config.sh","h-run.sh","h-stats.sh",
      "submission-gate.py","README.md","PROVENANCE.md","LICENSE"]

def digest(blob):
    return hashlib.sha256(blob).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--upstream-release",type=pathlib.Path,required=True)
    parser.add_argument("--out-dir",type=pathlib.Path,required=True)
    args=parser.parse_args()
    root=pathlib.Path(__file__).resolve().parents[1]/FOLDER
    release=args.upstream_release.read_bytes()
    if digest(release)!=UPSTREAM_ARCHIVE_SHA:
        raise SystemExit("Refusing non-matching upstream release")
    with tarfile.open(fileobj=io.BytesIO(release),mode="r:gz") as inp:
        binary=inp.extractfile("xmrig-6.26.0-coin/xmrig").read()
    if digest(binary)!=UPSTREAM_BINARY_SHA or not binary.startswith(b"\x7fELF"):
        raise SystemExit("Refusing unexpected upstream binary")
    if f'CUSTOM_VERSION="{VERSION}"' not in (root/"h-manifest.conf").read_text():
        raise SystemExit("Manifest version mismatch")
    files={name:(root/name).read_bytes() for name in DOCS}
    files["xmrig"]=binary
    for data in files.values():
        if b":\\Users\\" in data or b"BEGIN OPENSSH PRIVATE KEY" in data:
            raise SystemExit("Potential embedded credential or local Windows path")
    files["SHA256SUMS"]=("".join(f"{digest(blob)}  {name}\n" for name,blob in sorted(files.items()))).encode()
    args.out_dir.mkdir(parents=True,exist_ok=True)
    archive=args.out_dir/f"{FOLDER}-{VERSION}.tar.gz"
    if archive.exists():
        raise SystemExit("Archive exists; refusing overwrite")
    with archive.open("wb") as dest:
        with gzip.GzipFile(filename="",fileobj=dest,mode="wb",mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode="w",format=tarfile.GNU_FORMAT) as tar:
                directory=tarfile.TarInfo(FOLDER+"/")
                directory.type=tarfile.DIRTYPE
                directory.mode=0o755
                directory.uid=directory.gid=directory.mtime=0
                directory.uname=directory.gname="root"
                tar.addfile(directory)
                for name,blob in sorted(files.items()):
                    item=tarfile.TarInfo(FOLDER+"/"+name)
                    item.size=len(blob)
                    item.mode=0o755 if name in ("h-config.sh","h-run.sh","h-stats.sh","xmrig") else 0o644
                    item.uid=item.gid=item.mtime=0
                    item.uname=item.gname="root"
                    tar.addfile(item,io.BytesIO(blob))
    h=digest(archive.read_bytes())
    (args.out_dir/(archive.name+".sha256")).write_text(f"{h}  {archive.name}\n",encoding="ascii")
    print(f"PACKAGE={archive}\nSHA256={h}\nBYTES={archive.stat().st_size}")

if __name__=="__main__":
    main()
