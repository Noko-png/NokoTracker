from fastapi import HTTPException

MAX_DATABASE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_CSV_BYTES = 16 * 1024 * 1024
MAX_IMPORT_FILES = 64


async def copy_upload(upload, target, limit):
    size = 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, "Die Importdatei ist zu gross.")
        target.write(chunk)
    return size
