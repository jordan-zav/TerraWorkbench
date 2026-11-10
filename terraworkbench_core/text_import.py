"""Shared text-table import settings for previews, paging and processing."""

import codecs
import csv
import warnings
from pathlib import Path

SEPARATORS = {"comma": ",", "semicolon": ";", "tab": "\t", "space": r"\s+", "pipe": "|"}
DEFAULT_OPTIONS = dict(
    separator="auto",
    encoding="auto",
    decimal=".",
    skip_rows=0,
    custom_separator="",
    has_header=True,
    column_names="",
    quotechar='"',
    escapechar="",
    comment="",
    thousands="",
    missing_values="",
    keep_default_na=True,
    skip_blank_lines=True,
)


def inspect_text(
    path,
    separator="auto",
    encoding="auto",
    decimal=".",
    skip_rows=0,
    custom_separator="",
    has_header=True,
    column_names="",
    quotechar='"',
    escapechar="",
    comment="",
    thousands="",
    missing_values="",
    keep_default_na=True,
    skip_blank_lines=True,
):
    path = Path(path)
    if separator not in ("auto", "custom", *SEPARATORS):
        raise ValueError("Unknown separator.")
    if decimal not in (".", ","):
        raise ValueError("Decimal symbol must be a dot or comma.")
    if (
        isinstance(skip_rows, bool)
        or int(skip_rows) != skip_rows
        or not 0 <= skip_rows <= 100000
    ):
        raise ValueError("Rows before the header must be an integer from 0 to 100000.")
    for name, value in [
        ("quote", quotechar),
        ("escape", escapechar),
        ("comment", comment),
        ("thousands", thousands),
    ]:
        if len(value) > 1 or value in ("\n", "\r"):
            raise ValueError(name + " must be one character or empty.")
    if separator == "custom" and (
        len(custom_separator) != 1 or custom_separator in ("\n", "\r")
    ):
        raise ValueError("Custom separator must be exactly one character.")
    if thousands and thousands == decimal:
        raise ValueError("Thousands and decimal symbols must differ.")
    if encoding == "auto":
        with path.open("rb") as stream:
            sample = stream.read(65536)
        if sample.startswith(codecs.BOM_UTF16_LE) or sample.startswith(
            codecs.BOM_UTF16_BE
        ):
            encoding = "utf-16"
        else:
            try:
                codecs.getincrementaldecoder("utf-8-sig")().decode(sample, final=False)
                encoding = "utf-8-sig"
            except UnicodeDecodeError:
                encoding = "cp1252"
    codecs.lookup(encoding)
    with path.open(encoding=encoding, errors="strict") as stream:
        for _ in range(int(skip_rows)):
            stream.readline()
        skip = int(skip_rows)
        first = stream.readline()
        while first and (
            (skip_blank_lines and not first.strip())
            or (comment and first.lstrip().startswith(comment))
        ):
            skip += 1
            first = stream.readline()
        header = first
        if has_header and first.strip() == "Raw track data":
            header = stream.readline()
            skip += 1
        if has_header:
            skip += 1
        lines = [first.rstrip("\r\n")]
        if header != first:
            lines.append(header.rstrip("\r\n"))
        lines.extend(stream.readline().rstrip("\r\n") for _ in range(6))
    header = header.lstrip("/ ").strip() if has_header else header.strip()
    if separator == "auto":
        try:
            sep = csv.Sniffer().sniff(header, delimiters="\t;,|").delimiter
        except csv.Error:
            sep = r"\s+"
    elif separator == "custom":
        sep = custom_separator
    else:
        sep = SEPARATORS[separator]
    if sep == decimal:
        raise ValueError("Separator and decimal symbol must differ.")
    if thousands and thousands == sep:
        raise ValueError("Thousands and separator symbols must differ.")
    csv_args = dict(
        quotechar=quotechar or None,
        quoting=csv.QUOTE_MINIMAL if quotechar else csv.QUOTE_NONE,
        escapechar=escapechar or None,
        skipinitialspace=True,
    )
    fields = (
        header.split()
        if sep == r"\s+"
        else next(csv.reader([header], delimiter=sep, **csv_args))
    )
    if column_names.strip():
        columns = [name.strip() for name in next(csv.reader([column_names]))]
        if len(columns) != len(fields):
            raise ValueError("Column name count must match the input column count.")
    else:
        columns = (
            [name.strip() for name in fields]
            if has_header
            else ["Column " + str(i + 1) for i in range(len(fields))]
        )
    if (
        not columns
        or any(not name for name in columns)
        or len(set(columns)) != len(columns)
    ):
        raise ValueError("Unique, nonempty column headers are required.")
    return dict(
        columns=columns,
        sep=sep,
        encoding=encoding,
        decimal=decimal,
        skiprows=skip,
        quotechar=quotechar,
        escapechar=escapechar,
        comment=comment,
        thousands=thousands,
        missing_values=[
            token.strip() for token in missing_values.split("|") if token.strip()
        ],
        keep_default_na=keep_default_na,
        skip_blank_lines=skip_blank_lines,
        has_header=has_header,
        header="\n".join(lines),
    )


def csv_options(info):
    return dict(
        sep=info["sep"],
        encoding=info["encoding"],
        decimal=info["decimal"],
        skiprows=info["skiprows"],
        names=info["columns"],
        on_bad_lines="error",
        index_col=False,
        skipinitialspace=True,
        quotechar=info["quotechar"] or None,
        quoting=csv.QUOTE_MINIMAL if info["quotechar"] else csv.QUOTE_NONE,
        escapechar=info["escapechar"] or None,
        comment=info["comment"] or None,
        thousands=info["thousands"] or None,
        na_values=info["missing_values"],
        keep_default_na=info["keep_default_na"],
        skip_blank_lines=info["skip_blank_lines"],
    )


def read_text_table(path, nrows=None, **options):
    import pandas as pd

    info = inspect_text(path, **options)
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.ParserWarning)
        try:
            frame = pd.read_csv(path, nrows=nrows, **csv_options(info))
        except pd.errors.ParserWarning as exc:
            raise ValueError(
                "Data rows do not match the header; check the separator and header row."
            ) from exc
    return frame, info
