import argparse
import asyncio
import logging
from email.utils import formatdate
from pathlib import Path
from urllib.parse import unquote

MSG_TERMINATOR = b"\r\n\r\n"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    filename="httpd.log",
)
logger = logging.getLogger("httpd")

MIME_TYPES = {
    '.html': 'text/html',
    '.htm': 'text/html',
    '.css': 'text/css',
    '.js': 'text/javascript',
    '.mjs': 'text/javascript',
    '.txt': 'text/plain',
    '.csv': 'text/csv',
    '.xml': 'application/xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.swf': 'application/x-shockwave-flash'
}

async def event_based_server(document_root, port) -> None:

    async def handle_client(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
    
        handler_task = process_request(reader, writer, document_root)
        asyncio.create_task(handler_task)

    server = await asyncio.start_server(
        handle_client,
        "127.0.0.1",
        port,
        reuse_address=True,
    )

    async with server:
        logger.info("server started, DOCUMENT_ROOT=%s", document_root)
        await server.serve_forever()


def parse_request(data: bytes) -> tuple[str, str, str, dict]:
    text = data.decode("utf-8")
    lines = list(filter(bool, text.splitlines()))
    method, path, version = lines[0].split(" ")
    headers = {}
    for line in lines[1:]:
        k, v = line.split(":", 1) 
        headers[k] = v.strip()
    return method, path, version, headers

def build_response(status_text, body: bytes, content_type: str, include_body: bool = False) -> bytes:
    server_name = "MyServer/1.0"
    content_length = str(len(body))
    date = formatdate(usegmt=True)
    
    lines = [status_text, 
            f"Date: {date}",
            f"Server: {server_name}", 
            f"Content-Length: {content_length}", 
            f"Content-Type: {content_type}",
            "Connection: close",
    ]

    head = "\r\n".join(lines) + "\r\n\r\n"
    response = head.encode("utf-8")

    if include_body:
        response +=  body

    return response

def resolve(path, document_root):
    path = path.split("?", 1)[0]
    p = unquote(path)
    p = p.lstrip('/')
    if not p or p.endswith('/'):
        p += "index.html"

    address = Path(document_root) / p
    suffix = address.suffix.lower()
    content_type = MIME_TYPES.get(suffix, "application/octet-stream")

    root_abs = Path(document_root).resolve()
    addr_abs = address.resolve()
    if not addr_abs.is_relative_to(root_abs):
        return ("HTTP/1.1 403 Forbidden", b"", content_type)

    if address.is_dir():
        return  ("HTTP/1.1 403 Forbidden", b"", content_type)
    elif address.is_file():
        try:
            body = address.read_bytes()
            return ("HTTP/1.1 200 OK", body, content_type)
        except PermissionError:
            return ("HTTP/1.1 403 Forbidden", b"", content_type)

    return ("HTTP/1.1 404 Not Found", b"", content_type)



async def process_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    document_root:str,
) -> None:
    
    client_message = b''
    while not client_message.endswith(MSG_TERMINATOR):

        message_chunk = await reader.read(1024)

        if not message_chunk:
            return

        client_message += message_chunk

    method, path, _version, _headers = parse_request(client_message)

    if method in ("GET", "HEAD"):
        status, body, content_type = resolve(path, document_root)
        data = build_response(status, body, content_type, include_body=(method == "GET"))
    else:
        status = "HTTP/1.1 405 Method Not Allowed"
        body, content_type = b"", "text/html; charset=utf-8"
        data = build_response(status, body, content_type)

    logger.info("%s %s -> %s", method, path, status)
    writer.write(data) 
    await writer.drain()
    writer.close()

    await writer.wait_closed()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Простой HTTP-сервер для отдачи статических файлов", 
        
        )
    parser.add_argument(
        "-r",
        help="путь к DOCUMENT_ROOT",
        required=True)
    parser.add_argument(
        "-p",
        type=int,
        default=8080,
        help="порт прослушивания")
    args  = parser.parse_args()
    main_coro = event_based_server(args.r, args.p)
    asyncio.run(main_coro)