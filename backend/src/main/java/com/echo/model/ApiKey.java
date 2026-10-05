package com.echo.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;

/** Personal API key; only its SHA-256 hash is stored, the raw key is shown once at creation. */
@Entity
@Table(name = "api_keys")
public class ApiKey {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(nullable = false)
    private String name;

    @Column(name = "key_prefix", nullable = false)
    private String keyPrefix;

    @Column(name = "key_hash", nullable = false, unique = true, columnDefinition = "bpchar(64)")
    private String keyHash;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt = OffsetDateTime.now();

    @Column(name = "last_used_at")
    private OffsetDateTime lastUsedAt;

    @Column(name = "revoked_at")
    private OffsetDateTime revokedAt;

    protected ApiKey() {
    }

    public ApiKey(Long userId, String name, String keyPrefix, String keyHash) {
        this.userId = userId;
        this.name = name;
        this.keyPrefix = keyPrefix;
        this.keyHash = keyHash;
    }

    public Long getId() { return id; }
    public Long getUserId() { return userId; }
    public String getName() { return name; }
    public String getKeyPrefix() { return keyPrefix; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getLastUsedAt() { return lastUsedAt; }
    public OffsetDateTime getRevokedAt() { return revokedAt; }
    public boolean isActive() { return revokedAt == null; }
    public void touch() { lastUsedAt = OffsetDateTime.now(); }

    public void revoke() {
        if (revokedAt == null) revokedAt = OffsetDateTime.now();
    }
}
