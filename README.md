# HTTP-сервер на asyncio (учебный проект)

Простой статический веб-сервер, частично реализующий HTTP/1.1: методы GET и HEAD,
отдача файлов из `DOCUMENT_ROOT`. Точка входа — `httpd.py`.

## Архитектура

**Asynchronous (event-based)** — один процесс, один поток:

- Приём соединений: `asyncio.start_server()`. На Linux event loop asyncio использует
  **epoll** (требование задания); на Windows — механизм IOCP/Proactor, поэтому
  финальное тестирование выполнялось в Linux-окружении (WSL).
- На каждое подключение `start_server` вызывает обработчик `handle_client(reader, writer)`,
  который порождает корутину `process_request` через `asyncio.create_task` — соединения
  обрабатываются конкурентно, не блокируя event loop.
- `DOCUMENT_ROOT` (аргумент `-r`) доставляется до обработчика через **замыкание**:
  `event_based_server(document_root)` → вложенный `handle_client` → `process_request`.

Код разделён на чистые функции по зонам ответственности (тестируются независимо):

| Функция | Ответственность |
|---|---|
| `parse_request(data: bytes)` | сырые байты запроса → (method, path, version, headers) |
| `resolve(path, document_root)` | путь запроса → (status, body, content_type): unquote %XX, склейка с корнем, `index.html` для директорий, проверка файла |
| `build_response(status, body, content_type, include_body)` | структура → байты HTTP-ответа (Date, Server, Content-Length, Content-Type, Connection) |
| `process_request` | транспорт: чтение из сокета, склейка запроса, вызов парсер→резолвер→сборщик, отправка |

## Запуск

```bash
python httpd.py -r /path/to/document_root
```

- `-r` (обязательный) — путь к корневой папке с файлами (DOCUMENT_ROOT).

## Возможности

- GET и HEAD → 200/403/404; прочие методы → 405
- Отдача файлов по произвольному пути внутри DOCUMENT_ROOT
- `GET /directory/` → `DOCUMENT_ROOT/directory/index.html`
- `GET /` → `DOCUMENT_ROOT/index.html`
- Декодирование `%XX` в путях (`/hello%20world.html` → файл `hello world.html`)
- Корректный Content-Type по расширению: html, htm, css, js, jpg, jpeg, png, gif, swf
  (неизвестные расширения — `application/octet-stream`)
- Заголовки ответа: Date (GMT, RFC 7231), Server, Content-Length, Content-Type, Connection
- Логирование каждого запроса: `method path -> status`
- Защита от path traversal: пути, выходящие за пределы DOCUMENT_ROOT (`/../../`),
  отклоняются со статусом 403

## Известные ограничения

- `Connection: close` на каждый запрос — keep-alive не реализован
- Масштабирование на несколько worker'ов (`-w`, задание со «звёздочкой») — не реализовано
- Файлы читаются в память целиком (для очень больших файлов оправдан потоковый ответ)

## Тестирование

### Функциональные тесты

Тест-сьют [s-stupnikov/http-test-suite](https://github.com/s-stupnikov/http-test-suite)
запускался в WSL (Ubuntu 26.04, Python 3.14), сервер — на порту 80:

```bash
sudo python3 httpd.py -r www -p 80
python3 ~/otus/http-test-suite/httptest.py
```

Результат: **Ran 23 tests — OK (23 passed)**.

Дополнительно проверено вручную:

- `GET /` → 200, `GET /style.css` → 200 (`Content-Type: text/css`)
- `GET /nope.html` → 404, `GET /subdir` → 403, `POST /` → 405
- `HEAD /page.html` → 200, заголовки без тела
- `GET /httptest/../../etc/passwd` → 403 (path traversal блокируется)

## Нагрузочное тестирование

Тест проводился из WSL (Ubuntu 26.04), файлы DOCUMENT_ROOT размещены в Linux-файловой
системе; лог запросов писался в файл (`httpd.log`), а не в терминал — синхронная запись
в консоль при высокой нагрузке блокирует event loop и искажает результаты.

```bash
ab -n 50000 -c 100 -r http://localhost:8080/
```

Результат:

```
Concurrency Level:      100
Time taken for tests:   4.763 seconds
Complete requests:      50000
Failed requests:        0
Requests per second:    10497.98 [#/sec] (mean)
Time per request:       9.526 [ms] (mean)
Time per request:       0.095 [ms] (mean, across all concurrent requests)
Transfer rate:          1671.07 [Kbytes/sec] received
```

Все 50 000 запросов выполнены без ошибок — сервер стабилен под 100 одновременных
подключений.
