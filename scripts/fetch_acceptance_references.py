"""Download pinned SimPEG observations into an explicit external cache."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
from urllib.request import Request, urlopen

REGISTRY = Path(__file__).with_name("mvi_acceptance_sources.json")


def fetch(cache):
    cache = Path(cache)
    source = json.loads(REGISTRY.read_text())
    paths = {}
    for asset in source["assets"]:
        target = cache / asset["cache_subpath"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            data = target.read_bytes()
        else:
            with urlopen(
                Request(
                    asset["url"], headers={"User-Agent": "TerraWorkbench-validation"}
                ),
                timeout=45,
            ) as response:
                data = response.read(50000001)
        if (
            len(data) != asset["bytes"]
            or hashlib.sha256(data).hexdigest() != asset["sha256"]
        ):
            raise ValueError("Reference archive checksum/size mismatch: " + asset["id"])
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(data)
        contents = target.parent / (target.name + ".contents")
        members = {r["path"]: r for r in asset["members"]}
        with tarfile.open(target, "r:gz") as archive:
            if sum(m.size for m in archive.getmembers()) > 200000000:
                raise ValueError("Oversized expanded archive")
            found = set()
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in member.name
                    or any(":" in p for p in path.parts)
                ):
                    raise ValueError("Unsafe archive path")
                if member.isdir():
                    continue
                if not member.isfile() or member.name not in members:
                    raise ValueError("Unregistered archive member")
                data = archive.extractfile(member).read()
                expected = members[member.name]
                if (
                    len(data) != expected["bytes"]
                    or hashlib.sha256(data).hexdigest() != expected["sha256"]
                ):
                    raise ValueError("Reference member checksum mismatch")
                output = contents / Path(*path.parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                if output.exists():
                    if output.read_bytes() != data:
                        raise ValueError("Existing reference member changed")
                else:
                    with output.open("xb") as stream:
                        stream.write(data)
                found.add(member.name)
            if found != set(members):
                raise ValueError("Missing registered member")
        paths[asset["id"]] = contents / Path(asset["members"][0]["path"]).parent
    return paths, source


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    paths, source = fetch(parser.parse_args().cache)
    print(
        json.dumps(
            dict(commit=source["commit"], paths={k: str(v) for k, v in paths.items()}),
            indent=2,
        )
    )
