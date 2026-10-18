"""Parquet tables with plain dates: ``session_date`` is a date, never a timestamp.

Columns named ``*_date`` or ``*_session`` are stored as Arrow ``date32`` and come back as
``datetime64`` columns, which is what pandas groups, sorts and compares fastest.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

DATE_SUFFIXES = ("_date", "_session", "session")


def _is_date_column(name: str) -> bool:
    return name.endswith(DATE_SUFFIXES)


def write_table(frame: pd.DataFrame, path: Path) -> None:
    """Write atomically: a temporary file in the same folder, then a rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.copy()
    for column in out.columns:
        if _is_date_column(str(column)) and pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.date
    table = pa.Table.from_pandas(out, preserve_index=False)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    os.close(fd)
    try:
        pq.write_table(table, tmp, compression="zstd")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_table(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    table = pq.read_table(path, columns=columns)
    frame: pd.DataFrame = table.to_pandas()
    for field in table.schema:
        if pa.types.is_date(field.type):
            frame[field.name] = pd.to_datetime(frame[field.name])
    return frame
