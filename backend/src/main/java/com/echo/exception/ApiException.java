package com.echo.exception;

import org.springframework.http.HttpStatus;

/** Base for domain errors rendered as RFC 7807 problem details by {@link GlobalExceptionHandler}. */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String type;

    public ApiException(HttpStatus status, String type, String message) {
        super(message);
        this.status = status;
        this.type = type;
    }

    public HttpStatus getStatus() { return status; }
    public String getType() { return type; }

    public static ApiException notFound(String what) {
        return new ApiException(HttpStatus.NOT_FOUND, "not-found", what + " not found");
    }

    public static ApiException conflict(String message) {
        return new ApiException(HttpStatus.CONFLICT, "conflict", message);
    }

    public static ApiException badRequest(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "bad-request", message);
    }

    /** The user's subscription plan does not allow this action; the frontend shows an upgrade prompt. */
    public static ApiException planLimit(String message) {
        return new ApiException(HttpStatus.FORBIDDEN, "plan-limit", message);
    }

    public static ApiException rateLimited(String message) {
        return new ApiException(HttpStatus.TOO_MANY_REQUESTS, "rate-limited", message);
    }

    public static ApiException mlUnavailable(String message) {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ml-service-unavailable", message);
    }
}
