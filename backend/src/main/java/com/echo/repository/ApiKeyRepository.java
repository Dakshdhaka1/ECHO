package com.echo.repository;

import com.echo.model.ApiKey;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ApiKeyRepository extends JpaRepository<ApiKey, Long> {

    Optional<ApiKey> findByKeyHashAndRevokedAtIsNull(String keyHash);

    List<ApiKey> findByUserIdOrderByCreatedAtDesc(Long userId);

    long countByUserIdAndRevokedAtIsNull(Long userId);

    Optional<ApiKey> findByIdAndUserId(Long id, Long userId);
}
