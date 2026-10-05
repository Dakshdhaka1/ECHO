package com.echo.security;

import java.util.Optional;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

/** Resolves the authenticated user's id from a JWT or an API key (empty for anonymous requests). */
public final class CurrentUser {

    private CurrentUser() {
    }

    public static Optional<Long> id() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth instanceof JwtAuthenticationToken jwt) {
            return Optional.of(Long.valueOf(jwt.getToken().getSubject()));
        }
        if (auth instanceof ApiKeyAuthenticationToken key) {
            return Optional.of((Long) key.getPrincipal());
        }
        return Optional.empty();
    }

    public static Long require() {
        return id().orElseThrow(() -> new org.springframework.security.access.AccessDeniedException("login required"));
    }

    public static boolean isAdmin() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        return auth != null && auth.getAuthorities().stream().anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
    }
}
