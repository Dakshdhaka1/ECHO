package com.echo.repository;

import com.echo.model.Alert;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AlertRepository extends JpaRepository<Alert, Long> {

    List<Alert> findTop100ByUserIdOrderByCreatedAtDesc(Long userId);

    long countByUserIdAndReadAtIsNull(Long userId);

    Optional<Alert> findByIdAndUserId(Long id, Long userId);
}
