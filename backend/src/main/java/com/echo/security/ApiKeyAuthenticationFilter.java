package com.echo.security;

import com.echo.model.ApiKey;
import com.echo.model.User;
import com.echo.model.UsageEvent;
import com.echo.repository.ApiKeyRepository;
import com.echo.repository.UsageEventRepository;
import com.echo.repository.UserRepository;
import com.echo.service.RateLimiter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Duration;
import java.util.Optional;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Programmatic access (Pro/Enterprise): {@code X-API-Key: echo_...}. Keys are looked up by SHA-256 hash, and each
 * call counts against the plan's daily API quota.
 */
@Component
public class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-API-Key";

    private final ApiKeyRepository keys;
    private final UserRepository users;
    private final UsageEventRepository usage;
    private final RateLimiter rateLimiter;

    public ApiKeyAuthenticationFilter(ApiKeyRepository keys, UserRepository users, UsageEventRepository usage,
                                      RateLimiter rateLimiter) {
        this.keys = keys;
        this.users = users;
        this.usage = usage;
        this.rateLimiter = rateLimiter;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String raw = request.getHeader(HEADER);
        if (raw == null || raw.isBlank()) {
            chain.doFilter(request, response);
            return;
        }
        Optional<ApiKey> key = keys.findByKeyHashAndRevokedAtIsNull(ApiKeyHasher.sha256(raw.trim()));
        Optional<User> user = key.flatMap(k -> users.findById(k.getUserId()));
        if (key.isEmpty() || user.isEmpty()) {
            reject(response, 401, "invalid-api-key", "The API key is invalid or revoked.");
            return;
        }
        int quota = user.get().getPlan().apiCallsPerDay();
        if (quota <= 0) {
            reject(response, 403, "plan-limit", "API access requires the Pro or Enterprise plan.");
            return;
        }
        if (!rateLimiter.tryAcquire("api:" + key.get().getId(), quota, Duration.ofDays(1))) {
            reject(response, 429, "rate-limited", "Daily API quota of " + quota + " calls reached.");
            return;
        }
        key.get().touch();
        keys.save(key.get());
        usage.save(new UsageEvent(user.get().getId(), UsageEvent.API_CALL, null));
        SecurityContextHolder.getContext().setAuthentication(
                new ApiKeyAuthenticationToken(user.get().getId(), key.get().getId()));
        chain.doFilter(request, response);
    }

    private static void reject(HttpServletResponse response, int status, String type, String detail) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.getWriter().write("{\"type\":\"https://echo.dev/problems/" + type + "\",\"title\":\"" + type
                + "\",\"status\":" + status + ",\"detail\":\"" + detail + "\"}");
    }
}
