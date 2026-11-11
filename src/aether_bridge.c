#include "../include/aether_bridge.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET aether_socket_t;
#define AETHER_INVALID_SOCKET INVALID_SOCKET
#define aether_close_socket closesocket
#else
#include <arpa/inet.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
typedef int aether_socket_t;
#define AETHER_INVALID_SOCKET (-1)
#define aether_close_socket close
#endif

#define AETHER_MAX_RESPONSE_SIZE (1024U * 1024U)

static int send_all(aether_socket_t socket_fd, const char *data, size_t length) {
    size_t sent = 0;
    while (sent < length) {
#ifdef _WIN32
        int result = send(socket_fd, data + sent, (int)(length - sent), 0);
#else
#ifdef MSG_NOSIGNAL
        ssize_t result = send(socket_fd, data + sent, length - sent, MSG_NOSIGNAL);
#else
        ssize_t result = send(socket_fd, data + sent, length - sent, 0);
#endif
#endif
        if (result <= 0) {
            return -1;
        }
        sent += (size_t)result;
    }
    return 0;
}

int aether_dispatch_json(const char *json_envelope, char *out_buffer, int buffer_size) {
    struct sockaddr_in address;
    aether_socket_t socket_fd = AETHER_INVALID_SOCKET;
    char *request = NULL;
    char *response = NULL;
    size_t envelope_length;
    size_t request_length;
    size_t response_length = 0;
    size_t response_capacity = 0;
    int status_code = -4;
    int result = -2;
#ifdef _WIN32
    DWORD timeout_ms = 10000;
#else
    struct timeval timeout = {10, 0};
#endif

    if (out_buffer != NULL && buffer_size > 0) {
        out_buffer[0] = '\0';
    }
    if (json_envelope == NULL || out_buffer == NULL || buffer_size <= 0) {
        return -1;
    }

    envelope_length = strlen(json_envelope);
    if (envelope_length == 0 || envelope_length > AETHER_MAX_RESPONSE_SIZE) {
        return -1;
    }

#ifdef _WIN32
    {
        WSADATA winsock_data;
        if (WSAStartup(MAKEWORD(2, 2), &winsock_data) != 0) {
            return -2;
        }
    }
#endif

    socket_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (socket_fd == AETHER_INVALID_SOCKET) {
        goto cleanup;
    }
#ifdef _WIN32
    setsockopt(
        socket_fd, SOL_SOCKET, SO_RCVTIMEO,
        (const char *)&timeout_ms, sizeof(timeout_ms)
    );
    setsockopt(
        socket_fd, SOL_SOCKET, SO_SNDTIMEO,
        (const char *)&timeout_ms, sizeof(timeout_ms)
    );
#else
    setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(socket_fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
#ifdef SO_NOSIGPIPE
    {
        int no_sigpipe = 1;
        setsockopt(socket_fd, SOL_SOCKET, SO_NOSIGPIPE, &no_sigpipe, sizeof(no_sigpipe));
    }
#endif
#endif

    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons(8000);
    if (inet_pton(AF_INET, "127.0.0.1", &address.sin_addr) != 1 ||
        connect(socket_fd, (struct sockaddr *)&address, sizeof(address)) != 0) {
        goto cleanup;
    }

    request_length = envelope_length + 256;
    request = (char *)malloc(request_length);
    if (request == NULL) {
        goto cleanup;
    }
    {
        int header_length = snprintf(
            request,
            request_length,
            "POST /api/v1/unified/dispatch HTTP/1.1\r\n"
            "Host: 127.0.0.1:8000\r\n"
            "Content-Type: application/json\r\n"
            "Connection: close\r\n"
            "Content-Length: %zu\r\n\r\n",
            envelope_length
        );
        if (header_length < 0 || (size_t)header_length >= request_length ||
            (size_t)header_length + envelope_length > request_length) {
            goto cleanup;
        }
        memcpy(request + header_length, json_envelope, envelope_length);
        request_length = (size_t)header_length + envelope_length;
    }
    if (send_all(socket_fd, request, request_length) != 0) {
        goto cleanup;
    }

    response_capacity = 4096;
    response = (char *)malloc(response_capacity);
    if (response == NULL) {
        goto cleanup;
    }
    for (;;) {
        char chunk[4096];
#ifdef _WIN32
        int received = recv(socket_fd, chunk, (int)sizeof(chunk), 0);
#else
        ssize_t received = recv(socket_fd, chunk, sizeof(chunk), 0);
#endif
        if (received == 0) {
            break;
        }
        if (received < 0) {
            goto cleanup;
        }
        if (response_length + (size_t)received > AETHER_MAX_RESPONSE_SIZE) {
            result = -3;
            goto cleanup;
        }
        if (response_length + (size_t)received + 1 > response_capacity) {
            size_t new_capacity = response_capacity;
            char *new_response;
            while (new_capacity < response_length + (size_t)received + 1) {
                new_capacity *= 2;
            }
            new_response = (char *)realloc(response, new_capacity);
            if (new_response == NULL) {
                goto cleanup;
            }
            response = new_response;
            response_capacity = new_capacity;
        }
        memcpy(response + response_length, chunk, (size_t)received);
        response_length += (size_t)received;
    }
    response[response_length] = '\0';

    {
        char *body = strstr(response, "\r\n\r\n");
        size_t body_length;
        if (body == NULL || sscanf(response, "HTTP/%*s %d", &status_code) != 1) {
            goto cleanup;
        }
        body += 4;
        body_length = response_length - (size_t)(body - response);
        if (body_length >= (size_t)buffer_size) {
            result = -3;
            goto cleanup;
        }
        memcpy(out_buffer, body, body_length);
        out_buffer[body_length] = '\0';
        result = status_code;
    }

cleanup:
    if (socket_fd != AETHER_INVALID_SOCKET) {
        aether_close_socket(socket_fd);
    }
    free(request);
    free(response);
#ifdef _WIN32
    WSACleanup();
#endif
    return result;
}
