"""Offline integrity and archive-path checks for the public benchmark fetcher."""

import hashlib
import io
import tarfile

import pytest

from scripts import benchmark_public_inversion as benchmark


def pinned(monkeypatch, name="cross_gradient_data/value.txt", kind="file"):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        member = tarfile.TarInfo(name)
        data = b"public synthetic bytes"
        if kind == "symlink":
            member.type, member.linkname = tarfile.SYMTYPE, "../../escape"
            archive.addfile(member)
        else:
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    payloads = {"archive": stream.getvalue(), "source": b"raise AssertionError('never execute downloaded code')"}
    monkeypatch.setattr(benchmark, "PINS", {
        "cross_gradient_data.tar.gz": ("archive", hashlib.sha256(payloads["archive"]).hexdigest()),
        "reference.py": ("source", hashlib.sha256(payloads["source"]).hexdigest()),
    })
    calls = []

    def download(url, timeout):
        calls.append(url)
        return io.BytesIO(payloads[url])

    monkeypatch.setattr(benchmark, "urlopen", download)
    return calls


def test_fetch_reuses_verified_bytes_and_never_executes_source(tmp_path, monkeypatch):
    calls = pinned(monkeypatch)
    root = benchmark.fetch(tmp_path)
    assert (root/"value.txt").read_bytes() == b"public synthetic bytes"
    assert len(calls) == 2
    benchmark.fetch(tmp_path)
    assert len(calls) == 2
    (tmp_path/"reference.py").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        benchmark.fetch(tmp_path)
    assert (tmp_path/"reference.py").read_bytes() == b"tampered"


@pytest.mark.parametrize("name,kind", [("../escape", "file"), ("/escape", "file"),
                                       ("bad\\escape", "file"), ("link", "symlink")])
def test_fetch_rejects_unsafe_archive_members(tmp_path, monkeypatch, name, kind):
    pinned(monkeypatch, name, kind)
    with pytest.raises(ValueError, match="Unsafe archive|Only regular"):
        benchmark.fetch(tmp_path)
    assert not (tmp_path/"dataset/escape").exists()
