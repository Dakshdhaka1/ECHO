package com.echo.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;

/** API key generation and hashing. Keys are random 32-byte values; only the SHA-256 hash is persisted. */
public final class ApiKeyHasher {

    private static final SecureRandom RANDOM = new SecureRandom();

    private ApiKeyHasher() {
    }

    public static String newKey() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return "echo_" + Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static String sha256(String raw) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(raw.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
