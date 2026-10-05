package com.echo.security;

import java.util.List;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

/** Authentication created from a valid personal API key; principal is the owning user id. */
public class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {

    private final Long userId;
    private final Long apiKeyId;

    public ApiKeyAuthenticationToken(Long userId, Long apiKeyId) {
        super(List.of(new SimpleGrantedAuthority("ROLE_USER"), new SimpleGrantedAuthority("SCOPE_api")));
        this.userId = userId;
        this.apiKeyId = apiKeyId;
        setAuthenticated(true);
    }

    @Override
    public Object getCredentials() {
        return "";
    }

    @Override
    public Object getPrincipal() {
        return userId;
    }

    public Long getApiKeyId() {
        return apiKeyId;
    }
}
