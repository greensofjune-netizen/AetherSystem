#ifndef AETHER_BRIDGE_H
#define AETHER_BRIDGE_H

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Dispatch a JSON envelope to the loopback Aether API at 127.0.0.1:8000.
 * Returns the HTTP status code on response, -1 for invalid arguments,
 * -2 for connection or I/O errors, -3 if the response does not fit,
 * or -4 for an invalid HTTP response. out_buffer is always NUL-terminated
 * when buffer_size is positive.
 */
int aether_dispatch_json(const char *json_envelope, char *out_buffer, int buffer_size);

#ifdef __cplusplus
}
#endif

#endif
