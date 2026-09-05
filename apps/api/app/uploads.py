"""Reading an upload without letting it decide how much memory we use.

The size check used to run after `await file.read()`, which is too late: by
then the whole body is already resident. On a 512 MB instance a careless or
hostile POST could exhaust the container before the 20 MB limit was ever
consulted -- the limit was documentation, not a defence.

Reading in chunks and stopping at the ceiling means the most memory a request
can cost is the ceiling plus one chunk, whatever the sender claims or sends.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

CHUNK = 64 * 1024


async def read_capped(file: UploadFile, limit: int, *, what: str = "file") -> bytes:
    """Read at most `limit` bytes, refusing anything larger.

    A declared Content-Length over the limit is refused before a byte is read.
    It is only a claim, so the chunked read still enforces the ceiling for a
    sender that lies or omits it.
    """
    megabytes = limit // (1024 * 1024)

    declared = file.size
    if declared is not None and declared > limit:
        raise HTTPException(413, f"{what} exceeds {megabytes} MB")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            # Stop here rather than reading to the end to find out how big it
            # was. The answer does not change the response and the bytes would
            # cost real memory to learn it.
            raise HTTPException(413, f"{what} exceeds {megabytes} MB")
        chunks.append(chunk)

    if total == 0:
        raise HTTPException(400, f"empty {what}")

    return b"".join(chunks)
